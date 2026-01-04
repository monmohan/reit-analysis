import os
import asyncio
import operator
import uuid
from typing import TypedDict, Annotated, List, Optional, Literal, Dict
from datetime import datetime
from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from azure_auth import get_azure_ad_token
from yahoo_finance_api import get_reit_info as fetch_reit_info, get_reit_data_structured
from singapore_reits import get_top_reits_by_market_cap

# 1. SETUP & AUTH
load_dotenv()

llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_ad_token_provider=get_azure_ad_token,
    temperature=1
)

# 2. DEFINING TOOLS
@tool
def get_reit_info(ticker: str) -> str:
    """
    Fetches detailed information about a Singapore REIT stock from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., 'C38U.SI' for CapitaLand Integrated Commercial Trust)

    Returns:
        Formatted string with current price, dividend yield history, YTD performance, and market cap
    """
    return fetch_reit_info(ticker)

@tool
def analyze_top_singapore_reits(limit: int = 20) -> str:
    """
    Analyzes the top Singapore REITs by market capitalization and ranks them by various metrics.

    This tool will:
    1. Find the top N Singapore REITs by market cap
    2. Fetch detailed data for each REIT
    3. Rank them by Price-to-Book ratio, Dividend Yield, YTD Performance, and Gearing Ratio

    Args:
        limit: Number of top REITs to analyze (default: 10)

    Returns:
        Formatted analysis with rankings and detailed breakdown
    """
    print(f"\n{'='*80}")
    print(f"ANALYZING TOP {limit} SINGAPORE REITs BY MARKET CAP")
    print(f"{'='*80}\n")

    # Step 1: Get top REITs by market cap
    top_reits = get_top_reits_by_market_cap(limit)

    if not top_reits:
        return "Error: Unable to fetch Singapore REIT data"

    # Step 2: Fetch detailed data for each REIT
    print(f"\nFetching detailed data for {len(top_reits)} REITs...")
    reit_data_list = []

    for ticker, market_cap, company_name in top_reits:
        print(f"  Fetching {ticker}...")
        data = get_reit_data_structured(ticker)
        if data:
            reit_data_list.append(data)

    if not reit_data_list:
        return "Error: Unable to fetch detailed data for REITs"

    print(f"\nSuccessfully fetched data for {len(reit_data_list)} REITs\n")

    # Step 3: Create unified table
    output = f"\n{'='*127}\n"
    output += f"TOP {len(reit_data_list)} SINGAPORE REITs - COMPREHENSIVE ANALYSIS (Sorted by Market Cap)\n"
    output += f"{'='*127}\n\n"

    # Table header
    output += f"{'Rank':<6}{'Ticker':<12}{'Company Name':<35}{'Mkt Cap':<12}{'Price':<9}{'P/B':<7}{'Yield':<8}{'YTD':<10}{'Gearing':<8}{'ICR':<7}\n"
    output += "-" * 127 + "\n"

    # Table rows - already sorted by market cap from get_top_reits_by_market_cap()
    for i, reit in enumerate(reit_data_list, 1):
        # Format each field with N/A handling
        ticker = reit.get('ticker', 'N/A')
        company = reit.get('company_name', 'N/A')[:32]  # Truncate long names

        # Market Cap
        market_cap = reit.get('market_cap')
        if market_cap:
            market_cap_str = f"${market_cap/1e9:.2f}B"
        else:
            market_cap_str = "N/A"

        # Price
        price = reit.get('current_price')
        price_str = f"${price:.2f}" if price else "N/A"

        # P/B Ratio
        pb = reit.get('price_to_book')
        pb_str = f"{pb:.2f}" if pb else "N/A"

        # Dividend Yield
        div_yield = reit.get('current_year_dividend_yield')
        yield_str = f"{div_yield:.2f}%" if div_yield else "N/A"

        # YTD Performance
        ytd = reit.get('ytd_performance')
        if ytd is not None:
            sign = "+" if ytd >= 0 else ""
            ytd_str = f"{sign}{ytd:.2f}%"
        else:
            ytd_str = "N/A"

        # Gearing Ratio
        gearing = reit.get('gearing_ratio')
        gearing_str = f"{gearing:.2f}" if gearing else "N/A"

        # Interest Coverage Ratio (ICR)
        icr = reit.get('icr')
        icr_str = f"{icr:.2f}x" if icr else "N/A"

        # Format row
        output += f"{i:<6}{ticker:<12}{company:<35}{market_cap_str:<12}{price_str:<9}{pb_str:<7}{yield_str:<8}{ytd_str:<10}{gearing_str:<8}{icr_str:<7}\n"

    output += "\n" + "="*127 + "\n"

    return output

tools = [get_reit_info, analyze_top_singapore_reits]

# Bind tools to LLM
llm_with_tools = llm.bind_tools(tools)

# Create ToolNode using built-in
tool_node = ToolNode(tools)

# 3. STATE DEFINITION
class UserPreferences(TypedDict):
    """Structured storage for user investment preferences"""
    risk_tolerance: Optional[Literal["conservative", "moderate"]]
    max_price_to_book: Optional[float]

class AgentState(TypedDict):
    """Extended state with HITL support"""
    messages: Annotated[List[BaseMessage], operator.add]
    user_preferences: UserPreferences
    preferences_collected: bool
    needs_clarification: bool
    clarification_question: Optional[str]

# 3.5 HELPER FUNCTION FOR PREFERENCE COLLECTION
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

# 4. NODES
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

# 5. ROUTER
def router(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# 6. GRAPH CONSTRUCTION
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("preference_collector", preference_collector_node)
workflow.add_node("preference_parser", preference_parser_node)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

# Define flow
workflow.set_entry_point("preference_collector")
workflow.add_edge("preference_collector", "preference_parser")
workflow.add_edge("preference_parser", "agent")
workflow.add_conditional_edges("agent", router, ["tools", END])
workflow.add_edge("tools", "agent")

# Compile with checkpointer and interrupt
memory = MemorySaver()
app = workflow.compile(
    checkpointer=memory,
    interrupt_after=["preference_collector"]
)

# 7. PROMPT LOADING
def load_prompt(prompt_file='prompts/reit_audit_prompt.txt', limit=20):
    """
    Load prompt template from file and format with parameters.

    Args:
        prompt_file: Path to prompt template file
        limit: Number of REITs to analyze

    Returns:
        Formatted prompt string
    """
    try:
        with open(prompt_file, 'r') as f:
            template = f.read()
        return template.format(limit=limit)
    except FileNotFoundError:
        print(f"Error: Prompt file '{prompt_file}' not found")
        raise
    except Exception as e:
        print(f"Error loading prompt: {e}")
        raise

# 8. EXECUTION
async def main():
    print("--- REIT ANALYSIS AGENT WITH HUMAN-IN-THE-LOOP ---\n")

    # Generate unique thread ID for state persistence
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Load base prompt
    base_prompt = load_prompt(limit=20)

    # Initialize state
    initial_state = {
        "messages": [HumanMessage(content=base_prompt)],
        "user_preferences": {},
        "preferences_collected": False,
        "needs_clarification": False,
        "clarification_question": None
    }

    # Step 1: Start graph execution - will run until interrupt
    print("[AGENT] Initializing...\n")
    async for event in app.astream(initial_state, config, stream_mode="values"):
        # Graph will stop at the interrupt point
        # The preference_collector_node has executed and added its message
        pass

    # Step 2: THE INTERRUPT HAPPENED! Graph is paused.
    # Now collect user preferences with sequential prompts
    user_preferences = collect_user_preferences()

    # Step 3: Resume graph with collected preferences
    # Use update_state to inject preferences into the paused graph
    app.update_state(
        config,
        {
            "user_preferences": user_preferences,
            "preferences_collected": False  # Will be set to True by preference_parser_node
        }
    )

    # Step 4: Continue graph execution to completion
    tool_output = ""
    final_response = ""

    print("[AGENT] Processing analysis...\n")
    async for event in app.astream(None, config, stream_mode="values"):
        last_msg = event["messages"][-1]

        # Capture tool output (contains raw rankings data)
        if hasattr(last_msg, "name") and last_msg.name == "analyze_top_singapore_reits":
            tool_output = last_msg.content
            print("[TOOLS] Data collection complete\n")

        # Store the final agent response (synthesis)
        # Check if tool_calls is empty or doesn't exist
        elif hasattr(last_msg, "content"):
            has_tool_calls = hasattr(last_msg, "tool_calls") and last_msg.tool_calls
            if not has_tool_calls:
                final_response = last_msg.content
                print(f"[AGENT] Analysis complete\n")

    # Generate markdown report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_filename = f"reit_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    markdown_content = f"""# Singapore REIT Analysis Report

**Generated:** {timestamp}
**Query:** Analyze top 20 Singapore REITs with user preferences

---

## Raw Data Table

```
{tool_output if tool_output else "No tool output captured"}
```

---

## AI Analysis & Audit

{final_response if final_response else "No AI analysis captured"}

---

## About This Report

This analysis was generated by an AI agent that:
1. Fetched the top Singapore REITs by market capitalization from Yahoo Finance
2. Collected detailed financial metrics for each REIT
3. Ranked them by multiple performance indicators

**Data Source:** Yahoo Finance
**Analysis Date:** {datetime.now().strftime("%Y-%m-%d")}

### Disclaimer
This report is for informational purposes only and should not be considered as financial advice.
Always conduct your own research and consult with a qualified financial advisor before making investment decisions.
"""

    # Write to file
    with open(output_filename, 'w') as f:
        f.write(markdown_content)

    print("\n" + "="*80)
    print(f"✅ Analysis complete! Report saved to: {output_filename}")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
