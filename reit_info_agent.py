import os
import asyncio
import operator
from typing import TypedDict, Annotated, List
from datetime import datetime
from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

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
    output = f"\n{'='*120}\n"
    output += f"TOP {len(reit_data_list)} SINGAPORE REITs - COMPREHENSIVE ANALYSIS (Sorted by Market Cap)\n"
    output += f"{'='*120}\n\n"

    # Table header
    output += f"{'Rank':<6}{'Ticker':<12}{'Company Name':<35}{'Mkt Cap':<12}{'Price':<9}{'P/B':<7}{'Yield':<8}{'YTD':<10}{'Gearing':<8}\n"
    output += "-" * 120 + "\n"

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

        # Format row
        output += f"{i:<6}{ticker:<12}{company:<35}{market_cap_str:<12}{price_str:<9}{pb_str:<7}{yield_str:<8}{ytd_str:<10}{gearing_str:<8}\n"

    output += "\n" + "="*120 + "\n"

    return output

tools = [get_reit_info, analyze_top_singapore_reits]

# Bind tools to LLM
llm_with_tools = llm.bind_tools(tools)

# Create ToolNode using built-in
tool_node = ToolNode(tools)

# 3. STATE DEFINITION
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

# 4. NODES
def agent_node(state: AgentState):
    """The agent decides what to do."""
    messages = state["messages"]
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

workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("agent")

workflow.add_conditional_edges("agent", router, ["tools", END])
workflow.add_edge("tools", "agent")

app = workflow.compile()

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
    print("--- REIT ANALYSIS AGENT ---")
    print("\nThis agent can:")
    print("1. Analyze individual REITs (e.g., 'Get info about C38U.SI')")
    print("2. Analyze top Singapore REITs (e.g., 'Analyze the top 10 Singapore REITs')")
    print("\n" + "="*80 + "\n")

    # Load prompt from external file
    user_input = load_prompt(limit=25)

    inputs = {"messages": [HumanMessage(content=user_input)]}

    # Capture analysis results
    tool_output = ""
    final_response = ""

    async for event in app.astream(inputs):
        print("----------------EVENT----------------\n")
        print(event)
        print("----------------EVENT END----------------\n")
        for key, value in event.items():
            print(f"\n[Node: {key}]")
            last_msg = value["messages"][-1]

            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                print(f"  -> Calling tool: {last_msg.tool_calls[0]['name']}")
            elif hasattr(last_msg, "content"):
                content = last_msg.content
                print(f"  -> Response received ({len(content)} chars)")

                # Capture tool output (contains raw rankings data)
                if key == "tools" and content:
                    tool_output = content

                # Store the final agent response (synthesis)
                # Check if tool_calls is empty or doesn't exist
                if key == "agent" and content:
                    has_tool_calls = hasattr(last_msg, "tool_calls") and last_msg.tool_calls
                    if not has_tool_calls:
                        final_response = content
                        print(f"  -> Captured final AI response ({len(content)} chars)")

    # Generate markdown report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_filename = f"reit_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    markdown_content = f"""# Singapore REIT Analysis Report

**Generated:** {timestamp}
**Query:** {user_input}

---

## Raw Data Table

{tool_output if tool_output else "No tool output captured"}

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
