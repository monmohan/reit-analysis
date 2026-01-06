"""
Test cases for reflection/critique node functionality.

Tests the pure LLM-based reflection approach for analyzing REIT analysis quality.
"""
import unittest
from unittest.mock import Mock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

from nodes import (
    _parse_reflection_response,
    create_reflection_node,
    create_reflection_aware_agent_node,
    tool_router,
    reflection_router,
)


class TestParseReflectionResponse(unittest.TestCase):
    """Test reflection response parsing logic."""

    def test_parse_approved_json(self):
        """Parse JSON response with approved=true."""
        response = '''
        {
            "approved": true,
            "quality_score": 8,
            "missing_elements": [],
            "feedback": null
        }
        '''
        approved, feedback = _parse_reflection_response(response)
        self.assertTrue(approved)

    def test_parse_rejected_json(self):
        """Parse JSON response with approved=false and feedback."""
        response = '''
        {
            "approved": false,
            "quality_score": 4,
            "missing_elements": ["tenant_info", "dpu_trend"],
            "feedback": "Add specific tenant names and DPU analysis"
        }
        '''
        approved, feedback = _parse_reflection_response(response)
        self.assertFalse(approved)
        self.assertIn("tenant", feedback.lower())

    def test_parse_json_with_surrounding_text(self):
        """Parse JSON embedded in prose."""
        response = '''
        After reviewing the analysis, here is my assessment:

        {
            "approved": false,
            "quality_score": 5,
            "feedback": "Missing sponsor tier classification"
        }

        Please address these issues.
        '''
        approved, feedback = _parse_reflection_response(response)
        self.assertFalse(approved)
        self.assertIn("sponsor", feedback.lower())

    def test_parse_fallback_approved(self):
        """Fallback parsing detects approval keywords."""
        response = 'The analysis looks good. "approved": true'
        approved, feedback = _parse_reflection_response(response)
        self.assertTrue(approved)

    def test_parse_fallback_rejected(self):
        """Fallback to default rejection when parsing fails."""
        response = "This analysis is incomplete and needs work."
        approved, feedback = _parse_reflection_response(response)
        self.assertFalse(approved)
        self.assertIn("depth", feedback.lower())


class TestToolRouter(unittest.TestCase):
    """Test tool routing logic."""

    def test_routes_to_tools_when_tool_calls_present(self):
        """Route to tools when last message has tool calls."""
        mock_message = Mock()
        mock_message.tool_calls = [{"name": "get_reit_info"}]
        state = {"messages": [mock_message]}

        result = tool_router(state)
        self.assertEqual(result, "tools")

    def test_routes_to_reflection_when_no_tool_calls(self):
        """Route to reflection when no tool calls."""
        mock_message = Mock()
        mock_message.tool_calls = []
        state = {"messages": [mock_message]}

        result = tool_router(state)
        self.assertEqual(result, "reflection")

    def test_routes_to_reflection_when_tool_calls_missing(self):
        """Route to reflection when tool_calls attribute missing."""
        mock_message = Mock(spec=[])  # No tool_calls attribute
        state = {"messages": [mock_message]}

        result = tool_router(state)
        self.assertEqual(result, "reflection")


class TestReflectionRouter(unittest.TestCase):
    """Test reflection routing logic."""

    def test_routes_to_end_when_approved(self):
        """Route to end when analysis is approved."""
        state = {
            "analysis_approved": True,
            "reflection_count": 0,
            "max_reflections": 2,
        }
        result = reflection_router(state)
        self.assertEqual(result, END)

    def test_routes_to_agent_when_not_approved(self):
        """Route back to agent when not approved and retries remain."""
        state = {
            "analysis_approved": False,
            "reflection_count": 1,
            "max_reflections": 2,
        }
        result = reflection_router(state)
        self.assertEqual(result, "agent")

    def test_routes_to_end_at_max_retries(self):
        """Route to end when max retries reached."""
        state = {
            "analysis_approved": False,
            "reflection_count": 2,
            "max_reflections": 2,
        }
        result = reflection_router(state)
        self.assertEqual(result, END)

    def test_routes_to_end_beyond_max_retries(self):
        """Route to end when beyond max retries."""
        state = {
            "analysis_approved": False,
            "reflection_count": 3,
            "max_reflections": 2,
        }
        result = reflection_router(state)
        self.assertEqual(result, END)


class TestReflectionNode(unittest.TestCase):
    """Test reflection node behavior."""

    def test_reflection_approves_on_llm_approval(self):
        """Reflection node approves when LLM returns approved=true."""
        # Mock LLM
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = '{"approved": true, "quality_score": 8, "feedback": null}'
        mock_llm.invoke.return_value = mock_response

        # Create reflection node
        reflection_node = create_reflection_node(mock_llm)

        # Create state with analysis message
        state = {
            "messages": [
                HumanMessage(content="Analyze REITs"),
                AIMessage(content="Here is my detailed analysis with tenant info..."),
            ],
            "reflection_count": 0,
            "max_reflections": 2,
        }

        result = reflection_node(state)

        self.assertTrue(result["analysis_approved"])
        self.assertEqual(result["reflection_count"], 0)

    def test_reflection_rejects_with_feedback(self):
        """Reflection node rejects and provides feedback."""
        # Mock LLM
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = '{"approved": false, "quality_score": 4, "feedback": "Missing tenant details"}'
        mock_llm.invoke.return_value = mock_response

        reflection_node = create_reflection_node(mock_llm)

        state = {
            "messages": [
                HumanMessage(content="Analyze REITs"),
                AIMessage(content="Generic analysis without specifics"),
            ],
            "reflection_count": 0,
            "max_reflections": 2,
        }

        result = reflection_node(state)

        self.assertFalse(result["analysis_approved"])
        self.assertEqual(result["reflection_count"], 1)
        self.assertIn("tenant", result["reflection_feedback"].lower())

    def test_reflection_accepts_at_max_retries(self):
        """Reflection accepts analysis when max retries reached."""
        mock_llm = Mock()
        reflection_node = create_reflection_node(mock_llm)

        state = {
            "messages": [
                AIMessage(content="Some analysis"),
            ],
            "reflection_count": 2,
            "max_reflections": 2,
        }

        result = reflection_node(state)

        self.assertTrue(result["analysis_approved"])
        # LLM should not be called
        mock_llm.invoke.assert_not_called()

    def test_reflection_handles_no_analysis(self):
        """Reflection handles state with no analysis message."""
        mock_llm = Mock()
        reflection_node = create_reflection_node(mock_llm)

        state = {
            "messages": [
                HumanMessage(content="Just a question"),
            ],
            "reflection_count": 0,
            "max_reflections": 2,
        }

        result = reflection_node(state)

        self.assertFalse(result["analysis_approved"])
        self.assertIn("No analysis", result["reflection_feedback"])


class TestReflectionAwareAgentNode(unittest.TestCase):
    """Test reflection-aware agent node."""

    def test_agent_includes_feedback_on_retry(self):
        """Agent includes reflection feedback in context on retry."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = "Improved analysis"
        mock_llm.invoke.return_value = mock_response

        agent_node = create_reflection_aware_agent_node(mock_llm)

        state = {
            "messages": [HumanMessage(content="Analyze REITs")],
            "user_preferences": {"risk_tolerance": "conservative"},
            "preferences_collected": True,
            "reflection_feedback": "Add tenant details",
            "reflection_count": 1,
        }

        result = agent_node(state)

        # Check that LLM was called with enriched messages
        call_args = mock_llm.invoke.call_args[0][0]
        # First message should contain context
        context_text = call_args[0].content
        self.assertIn("REJECTED", context_text)
        self.assertIn("tenant", context_text.lower())

    def test_agent_works_without_feedback(self):
        """Agent works normally without reflection feedback."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = "Initial analysis"
        mock_llm.invoke.return_value = mock_response

        agent_node = create_reflection_aware_agent_node(mock_llm)

        state = {
            "messages": [HumanMessage(content="Analyze REITs")],
            "user_preferences": {},
            "preferences_collected": False,
            "reflection_feedback": None,
            "reflection_count": 0,
        }

        result = agent_node(state)

        self.assertEqual(len(result["messages"]), 1)
        mock_llm.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
