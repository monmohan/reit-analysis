"""
Node definitions for the REIT Analysis Agent graph.

Contains node functions for:
- Preference collection and parsing
- Agent decision making
- Routing logic
"""
from typing import Dict

from langchain_core.messages import HumanMessage
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

    # 2. Maximum Price-to-Book
    print("Maximum Price-to-Book ratio:")
    print("  Enter a ratio (e.g., 1.0) or press Enter for none")
    max_pb = input("Your choice [default: none]: ").strip()

    if max_pb:
        try:
            max_pb_float = float(max_pb)
            preferences['max_price_to_book'] = max_pb_float
            print(f"✓ Maximum Price-to-Book: {max_pb_float}\n")
        except ValueError:
            print(f"✓ Maximum Price-to-Book: none (invalid input, using default)\n")
    else:
        print(f"✓ Maximum Price-to-Book: none\n")

    # Display final preferences
    print("="*80)
    print("YOUR PREFERENCES:")
    print(f"- Risk Tolerance: {preferences.get('risk_tolerance', 'Not specified')}")
    print(f"- Maximum Price-to-Book: {preferences.get('max_price_to_book', 'none')}")
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
- Max P/B: {preferences.get('max_price_to_book', 'No limit')}
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
Preferred Price-to-Book: {preferences.get('max_price_to_book', 'No limit')}

INTERPRETATION GUIDELINES (Remember: REITs are dividend investments first):
- "conservative" risk → Prioritize dividend stability and capital preservation.
- "moderate" risk →  Expectation of growth and can take some volatility for long term growth, but still must consider dividend stability and capital preservation.

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
