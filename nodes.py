"""
Node definitions for the REIT Analysis Agent graph.

Contains node functions for:
- Preference collection and parsing
- Agent decision making
- Routing logic
- Reflection/critique for analysis depth
"""
import re
import json
from typing import Dict

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import END

from state import AgentState


def collect_user_preferences() -> Dict:
    """
    Collect user preferences through sequential prompts with defaults.

    Returns:
        Dictionary with user preferences
    """
    print("[AGENT] Let's gather your investment preferences...\n")

    preferences = {}

    # 1. Risk Tolerance
    print("Risk Tolerance:")
    print("  - conservative: Minimize volatility, prefer blue-chip sponsors")
    print("  - moderate: Balanced risk-reward")
    risk = input("Your choice [default: moderate]: ").strip().lower()

    if risk in ['conservative', 'moderate']:
        preferences['risk_tolerance'] = risk
        print(f"✓ Risk Tolerance: {risk}\n")
    else:
        preferences['risk_tolerance'] = 'moderate'
        print(f"✓ Risk Tolerance: moderate (default)\n")

    # Display final preferences
    print("="*80)
    print("YOUR PREFERENCES:")
    print(f"- Risk Tolerance: {preferences.get('risk_tolerance', 'Not specified')}")
    print("="*80)
    print()

    return preferences


def preference_collector_node(state: AgentState) -> AgentState:
    """
    Signals that we're ready to collect preferences.
    The interrupt will occur AFTER this node executes.
    """
    if state["preferences_collected"]:
        # Preferences already collected, pass through
        return state

    # Add a message indicating we're about to collect preferences
    message = "Ready to collect user investment preferences..."

    return {"messages": [HumanMessage(content=message)]}


def preference_parser_node(state: AgentState) -> AgentState:
    """
    Receives preferences dict and creates summary message for LLM context.
    """
    # Preferences are passed directly from state, not parsed from user input
    preferences = state.get("user_preferences", {})

    # Create summary for LLM context
    prefs_summary = f"""
User Investment Profile:
- Risk Tolerance: {preferences.get('risk_tolerance', 'Not specified')}
"""

    return {
        "user_preferences": preferences,
        "preferences_collected": True,
        "messages": [HumanMessage(content=prefs_summary)]
    }


def create_agent_node(llm_with_tools):
    """
    Factory function to create an agent node with the given LLM.

    Args:
        llm_with_tools: LLM with tools bound

    Returns:
        Agent node function
    """
    def agent_node(state: AgentState):
        """Enhanced agent with preference awareness."""
        messages = state["messages"]
        preferences = state["user_preferences"]

        if state["preferences_collected"] and preferences:
            # Create preference context for LLM
            pref_context = f"""
CONSIDERATION: USER PREFERENCES
============================================
The user has specified these investment criteria:

Risk Tolerance: {preferences.get('risk_tolerance', 'Not specified')}

INTERPRETATION GUIDELINES (Remember: REITs are dividend investments first):
- "conservative" risk → Prioritize dividend stability and capital preservation.
- "moderate" risk → Expectation of growth and can take some volatility for long term growth, but still must consider dividend stability and capital preservation.

============================================
"""

            # Prepend preference context to message history
            enriched_messages = [HumanMessage(content=pref_context)] + messages

            # Call LLM with enriched context
            response = llm_with_tools.invoke(enriched_messages)
        else:
            # No preferences collected, use original behavior
            response = llm_with_tools.invoke(messages)

        return {"messages": [response]}

    return agent_node


def router(state: AgentState):
    """
    Routes to tools if the last message has tool calls, otherwise ends.
    """
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# =============================================================================
# REFLECTION: Pure LLM-based critique node
# =============================================================================

def load_reflection_prompt() -> str:
    """Load reflection prompt from file."""
    try:
        with open('prompts/reflection_prompt.txt', 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError("Reflection prompt file not found at prompts/reflection_prompt.txt")


def create_reflection_node(llm):
    """
    Factory function to create a reflection node that critiques analysis depth.

    Args:
        llm: LLM instance (without tools bound)

    Returns:
        Reflection node function
    """
    reflection_prompt = load_reflection_prompt()

    def reflection_node(state: AgentState) -> dict:
        """
        Evaluates the agent's analysis for depth and quality using LLM.

        Returns:
            State updates: analysis_approved, reflection_feedback, reflection_count
        """
        messages = state["messages"]
        current_count = state.get("reflection_count", 0)
        max_reflections = state.get("max_reflections", 2)

        print(f"[DEBUG REFLECTION] Entered reflection node, iteration={current_count}, max={max_reflections}")

        # Find the last AI analysis message (not a tool call)
        analysis_message = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not getattr(msg, 'tool_calls', None):
                analysis_message = msg
                break

        if not analysis_message:
            # No analysis to evaluate yet
            print("[DEBUG REFLECTION] No analysis message found!")
            return {
                "analysis_approved": False,
                "reflection_feedback": "No analysis found to evaluate.",
                "reflection_count": current_count,
            }

        analysis_text = analysis_message.content
        print(f"[DEBUG REFLECTION] Found analysis, length={len(analysis_text)} chars")

        # Check if max retries reached - accept anyway
        if current_count > max_reflections:
            print("[DEBUG REFLECTION] Max reflections reached, auto-approving")
            return {
                "analysis_approved": True,
                "reflection_feedback": "Maximum reflection iterations reached. Accepting current analysis.",
                "reflection_count": current_count,
            }

        # Call LLM to evaluate analysis quality
        evaluation_request = f"""{reflection_prompt}

--- ANALYSIS TO EVALUATE ---
{analysis_text}
---

Please evaluate the analysis and respond with the JSON format specified above."""

        try:
            print("[DEBUG REFLECTION] Calling reflection LLM...")
            response = llm.invoke([
                SystemMessage(content="You are a quality assurance analyst for REIT research. Respond only with the requested JSON format."),
                HumanMessage(content=evaluation_request)
            ])

            response_text = response.content
            print(f"[DEBUG REFLECTION] LLM response received, length={len(response_text)} chars")
            print(f"[DEBUG REFLECTION] Response preview: {response_text[:300]}...")

            # Parse LLM response for approval decision
            approved, feedback = _parse_reflection_response(response_text)
            print(f"[DEBUG REFLECTION] Parsed: approved={approved}")

            if approved:
                return {
                    "analysis_approved": True,
                    "reflection_feedback": None,
                    "reflection_count": current_count,
                }
            else:
                return {
                    "analysis_approved": False,
                    "reflection_feedback": feedback,
                    "reflection_count": current_count + 1,
                }

        except Exception as e:
            # On error, accept the analysis to avoid blocking
            print(f"[DEBUG REFLECTION ERROR] {str(e)}")
            return {
                "analysis_approved": True,
                "reflection_feedback": f"Reflection error: {str(e)}. Accepting current analysis.",
                "reflection_count": current_count,
            }

    return reflection_node


def _parse_reflection_response(response_text: str) -> tuple[bool, str]:
    """
    Parse the reflection LLM response to extract approval and feedback.

    Args:
        response_text: Raw LLM response

    Returns:
        Tuple of (approved: bool, feedback: str)
    """
    # Try to parse JSON from response
    try:
        # Find JSON object in response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            approved = data.get("approved", False)
            feedback = data.get("feedback", "Analysis needs improvement.")
            return (approved, feedback)
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: look for keywords
    lower_response = response_text.lower()
    if '"approved": true' in lower_response or '"approved":true' in lower_response:
        return (True, None)

    # Default: not approved, extract any feedback text
    return (False, "Analysis needs more depth. Please include specific tenant names, DPU trends, sponsor tier classifications, and yield trap analysis.")


def create_reflection_aware_agent_node(llm_with_tools):
    """
    Factory function to create an agent node that incorporates reflection feedback.

    Args:
        llm_with_tools: LLM with tools bound

    Returns:
        Agent node function
    """
    def agent_node(state: AgentState):
        """Agent with preference and reflection feedback awareness."""
        messages = state["messages"]
        preferences = state.get("user_preferences", {})
        reflection_feedback = state.get("reflection_feedback")
        reflection_count = state.get("reflection_count", 0)

        # On retry, filter messages to avoid context bloat
        # Keep: HumanMessages (prompts), AIMessages with tool_calls, ToolMessages (data)
        # Drop: AIMessages without tool_calls (old analyses that are superseded)
        if reflection_count > 0:
            from langchain_core.messages import ToolMessage
            filtered_messages = []
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    filtered_messages.append(msg)
                elif isinstance(msg, ToolMessage):
                    filtered_messages.append(msg)
                elif isinstance(msg, AIMessage):
                    # Keep AIMessages that have tool_calls (needed for ToolMessage context)
                    # Drop AIMessages that are just analysis (no tool_calls)
                    if getattr(msg, 'tool_calls', None):
                        filtered_messages.append(msg)
                    # else: skip - this is an old analysis
            messages = filtered_messages
            print(f"[AGENT] Retry {reflection_count}: Using {len(messages)} filtered messages (dropped old analyses)")

        context_parts = []

        # Add preference context
        if state.get("preferences_collected") and preferences:
            pref_context = f"""
CONSIDERATION: USER PREFERENCES
============================================
The user has specified these investment criteria:

Risk Tolerance: {preferences.get('risk_tolerance', 'Not specified')}

INTERPRETATION GUIDELINES (Remember: REITs are dividend investments first):
- "conservative" risk → Prioritize dividend stability and capital preservation.
- "moderate" risk → Expectation of growth and can take some volatility for long term growth, but still must consider dividend stability and capital preservation.

============================================
"""
            context_parts.append(pref_context)

        # Add reflection feedback if this is a retry
        if reflection_feedback and reflection_count > 0:
            feedback_context = f"""
CRITICAL: ANALYSIS REJECTED - ACTION REQUIRED (Iteration {reflection_count})
============================================
Your previous analysis was REJECTED for lacking specific details.

Feedback: {reflection_feedback}

ACTION REQUIRED - YOU MUST DO THIS BEFORE RESPONDING:
1. CALL the search_reit_qualitative_info tool for EACH REIT in your SWAN list
2. Use the tool results to get SPECIFIC tenant names, asset details, and recent news
3. ONLY AFTER getting tool results, rewrite your analysis with those specifics

DO NOT respond with analysis text. Your next action MUST be tool calls.

Example tool call:
search_reit_qualitative_info(ticker="C38U.SI", company_name="CapitaLand Integrated Commercial Trust")

Call this tool for each REIT you are recommending. The tool will return tenant names, property details, and news that you MUST incorporate into your revised analysis.
============================================
"""
            context_parts.append(feedback_context)

        # Build enriched messages
        if context_parts:
            context_message = HumanMessage(content="\n".join(context_parts))
            enriched_messages = [context_message] + messages
            response = llm_with_tools.invoke(enriched_messages)
        else:
            response = llm_with_tools.invoke(messages)

        return {"messages": [response]}

    return agent_node


def tool_router(state: AgentState) -> str:
    """
    Routes to tools if the last message has tool calls, otherwise to reflection.
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return "reflection"


def reflection_router(state: AgentState):
    """
    Routes based on reflection evaluation outcome.

    Returns:
        "agent" - if analysis not approved and retries remain
        END - if approved or max retries reached
    """
    if state.get("analysis_approved", False):
        return END
    # Use > not >= so agent gets one more try where reflection_node will auto-approve
    if state.get("reflection_count", 0) > state.get("max_reflections", 2):
        return END
    return "agent"
