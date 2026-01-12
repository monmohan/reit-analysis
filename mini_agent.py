"""
Mini-Agent for Single REIT Analysis

A lightweight LangGraph subgraph that analyzes ONE REIT.
Used in the map phase of the map-reduce architecture.
"""
import json
import re
import asyncio
from typing import TypedDict, Annotated, List, Optional, Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from tools import search_reit_qualitative_info


class MiniAgentState(TypedDict):
    """State for single REIT analysis mini-agent."""
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]
    ticker: str
    company_name: str
    yahoo_data: dict
    result: Optional[dict]  # Final JSON result
    tool_called: bool  # Track if web search has been called


def load_single_reit_prompt(mode: str = "swan") -> str:
    """Load the single REIT prompt template."""
    prompt_file = f"prompts/{mode}_single_reit_prompt.txt"
    try:
        with open(prompt_file, 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")


def format_yahoo_data(data: dict) -> str:
    """Format Yahoo Finance data as readable text for LLM."""
    output = []

    # Basic Info
    output.append(f"Ticker: {data.get('ticker', 'N/A')}")
    output.append(f"Company: {data.get('company_name', 'N/A')}")
    output.append(f"Current Price: ${data.get('current_price', 'N/A')}")
    output.append(f"Market Cap: ${data.get('market_cap', 0) / 1e9:.2f}B" if data.get('market_cap') else "Market Cap: N/A")

    # Key Metrics
    output.append(f"\nKey Metrics:")
    output.append(f"  P/B Ratio: {data.get('price_to_book', 'N/A')}")
    output.append(f"  Gearing Ratio: {data.get('gearing_ratio', 'N/A')}")
    output.append(f"  ICR: {data.get('icr', 'N/A')}x" if data.get('icr') else "  ICR: N/A")
    output.append(f"  Beta: {data.get('beta', 'N/A')}")
    output.append(f"  Current Yield: {data.get('current_year_dividend_yield', 'N/A'):.2f}%" if data.get('current_year_dividend_yield') else "  Current Yield: N/A")
    output.append(f"  YTD Performance: {data.get('ytd_performance', 'N/A'):.2f}%" if data.get('ytd_performance') is not None else "  YTD Performance: N/A")

    # Dividend History
    div_history = data.get('dividend_history', [])
    if div_history:
        output.append(f"\nDividend History (DPU):")
        for div in div_history[:5]:  # Last 5 years
            output.append(f"  {div['year']}: {div['amount']*100:.2f}c (yield {div['yield']:.2f}%)")

    # Analyst Info
    if data.get('analyst_rating'):
        output.append(f"\nAnalyst Rating: {data.get('analyst_rating')}")
    if data.get('target_price_mean'):
        output.append(f"Target Price: ${data.get('target_price_mean'):.2f}")

    return "\n".join(output)


def create_mini_agent_node(llm_with_tools, llm_no_tools):
    """Create the LLM node for mini-agent."""

    def mini_agent_node(state: MiniAgentState) -> dict:
        """Process the REIT analysis request."""
        messages = state["messages"]
        ticker = state["ticker"]

        # If tool already called, use LLM without tools to force JSON output
        if state.get("tool_called", False):
            print(f"[AGENT] {ticker}: Tool already called, requesting JSON output")
            # Add instruction to output JSON
            force_json_msg = HumanMessage(content="""
The web search has been completed. Now you MUST output your analysis as JSON.

DO NOT call any more tools. Just output the JSON response as specified in the original prompt.
Your response must start with { and be valid JSON.
""")
            messages_with_instruction = messages + [force_json_msg]
            response = llm_no_tools.invoke(messages_with_instruction)
        else:
            response = llm_with_tools.invoke(messages)

        return {"messages": [response]}

    return mini_agent_node


def tool_router(state: MiniAgentState) -> str:
    """Route to tools if needed, otherwise to output parser."""
    # If tool already called, go directly to output parser
    if state.get("tool_called", False):
        return "output_parser"

    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return "output_parser"


def tools_wrapper_node(tool_node):
    """Wrapper that marks tool_called=True after tools execute."""
    def wrapper(state: MiniAgentState) -> dict:
        result = tool_node.invoke(state)
        # Mark that tool has been called
        result["tool_called"] = True
        return result
    return wrapper


def output_parser_node(state: MiniAgentState) -> dict:
    """Parse the final LLM response into structured JSON."""
    ticker = state["ticker"]

    # Find the last AIMessage with actual content (not just tool_calls)
    response_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            content = msg.content
            if content and len(content.strip()) > 0:
                response_text = content
                break

    if not response_text:
        print(f"[OUTPUT PARSER] {ticker}: No AIMessage with content found")
        # Try to build a result from any available data
        return {"result": {
            "ticker": ticker,
            "company_name": state["company_name"],
            "swan_qualified": False,
            "swan_score": 0,
            "parse_error": True,
            "rationale": "LLM did not return text content after tool call"
        }}

    print(f"[OUTPUT PARSER] {ticker}: Response length={len(response_text)} chars")
    print(f"[OUTPUT PARSER] {ticker}: First 200 chars: {response_text[:200]}...")

    # Try to extract JSON from response
    result = _parse_json_response(response_text, ticker, state["company_name"])

    if result.get("parse_error"):
        print(f"[OUTPUT PARSER] {ticker}: JSON parse failed, using fallback")
    else:
        print(f"[OUTPUT PARSER] {ticker}: Parsed OK - score={result.get('swan_score')}, qualified={result.get('swan_qualified')}")

    return {"result": result}


def _parse_json_response(response_text: str, ticker: str, company_name: str) -> dict:
    """Extract JSON from LLM response."""
    # Try to find JSON block
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    json_match = re.search(r'\{[\s\S]*"ticker"[\s\S]*\}', response_text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Fallback: create minimal result from response
    return {
        "ticker": ticker,
        "company_name": company_name,
        "swan_qualified": False,
        "swan_score": 0,
        "parse_error": True,
        "rationale": response_text[:500] if response_text else "Failed to parse response"
    }


def build_mini_agent_graph(llm_with_tools, llm_no_tools):
    """
    Build the mini-agent subgraph for single REIT analysis.

    Args:
        llm_with_tools: LLM with search_reit_qualitative_info tool bound
        llm_no_tools: LLM without tools (for final JSON output)

    Returns:
        Compiled subgraph
    """
    # Create tool node with just the web search tool
    base_tool_node = ToolNode([search_reit_qualitative_info])

    # Wrap tool node to track that tool has been called
    def tool_node_with_flag(state: MiniAgentState) -> dict:
        result = base_tool_node.invoke(state)
        result["tool_called"] = True
        return result

    # Create agent node with both LLMs
    agent_node = create_mini_agent_node(llm_with_tools, llm_no_tools)

    # Build graph
    workflow = StateGraph(MiniAgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node_with_flag)
    workflow.add_node("output_parser", output_parser_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", tool_router, ["tools", "output_parser"])
    workflow.add_edge("tools", "agent")  # After tool, go back to agent for final response
    workflow.add_edge("output_parser", END)

    return workflow.compile()


async def analyze_single_reit(
    reit_data: dict,
    llm_with_tools,
    llm_no_tools,
    mode: str = "swan",
    semaphore: Optional[asyncio.Semaphore] = None
) -> dict:
    """
    Analyze a single REIT using the mini-agent.

    Args:
        reit_data: Yahoo Finance data dict for this REIT
        llm_with_tools: LLM with tools bound
        llm_no_tools: LLM without tools (for final JSON output)
        mode: Analysis mode ("swan" or "value")
        semaphore: Optional semaphore for rate limiting

    Returns:
        Analysis result dict with swan_qualified, swan_score, rationale, etc.
    """
    ticker = reit_data.get('ticker', 'UNKNOWN')
    company_name = reit_data.get('company_name', 'Unknown REIT')

    print(f"[MINI-AGENT] Starting analysis of {ticker} ({company_name})")

    try:
        # Rate limiting
        if semaphore:
            async with semaphore:
                return await _run_mini_agent(reit_data, llm_with_tools, llm_no_tools, mode)
        else:
            return await _run_mini_agent(reit_data, llm_with_tools, llm_no_tools, mode)

    except Exception as e:
        print(f"[MINI-AGENT] Error analyzing {ticker}: {e}")
        return {
            "ticker": ticker,
            "company_name": company_name,
            "swan_qualified": False,
            "swan_score": 0,
            "error": str(e),
            "rationale": f"Analysis failed: {str(e)}"
        }


async def _run_mini_agent(reit_data: dict, llm_with_tools, llm_no_tools, mode: str) -> dict:
    """Internal function to run the mini-agent."""
    ticker = reit_data.get('ticker', 'UNKNOWN')
    company_name = reit_data.get('company_name', 'Unknown REIT')

    # Load and format prompt
    prompt_template = load_single_reit_prompt(mode)
    yahoo_formatted = format_yahoo_data(reit_data)

    prompt = prompt_template.format(
        ticker=ticker,
        company_name=company_name,
        yahoo_data_formatted=yahoo_formatted
    )

    # Build and run the mini-agent graph
    graph = build_mini_agent_graph(llm_with_tools, llm_no_tools)

    initial_state = {
        "messages": [HumanMessage(content=prompt)],
        "ticker": ticker,
        "company_name": company_name,
        "yahoo_data": reit_data,
        "result": None,
        "tool_called": False
    }

    # Run synchronously (graph.invoke is not async)
    # We're in an async context but LangGraph invoke is sync
    final_state = graph.invoke(initial_state)

    result = final_state.get("result")

    if result:
        print(f"[MINI-AGENT] Completed {ticker}: swan_qualified={result.get('swan_qualified', 'N/A')}")
    else:
        print(f"[MINI-AGENT] Completed {ticker}: No result parsed")
        result = {
            "ticker": ticker,
            "company_name": company_name,
            "swan_qualified": False,
            "swan_score": 0,
            "rationale": "No result parsed from mini-agent"
        }

    return result
