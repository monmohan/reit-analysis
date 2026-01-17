"""
Mini-Agent for Single REIT Analysis

A lightweight LangGraph subgraph that analyzes ONE REIT.
Used in the map phase of the map-reduce architecture.

Simplified version: No tool calls - receives all data upfront (Yahoo + quarterly).
"""
import json
import re
from typing import TypedDict, Annotated, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END


class MiniAgentState(TypedDict):
    """State for single REIT analysis mini-agent."""
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]
    ticker: str
    company_name: str
    combined_data: dict  # Yahoo + quarterly data combined
    result: Optional[dict]  # Final JSON result


def load_single_reit_prompt(mode: str = "swan") -> str:
    """Load the single REIT prompt template."""
    prompt_file = f"prompts/{mode}_single_reit_prompt.txt"
    try:
        with open(prompt_file, 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")


def format_combined_data(data: dict) -> str:
    """
    Format combined Yahoo + quarterly data as readable text for LLM.

    Args:
        data: Combined data object with 'yahoo', 'quarterly', 'data_status' keys
    """
    output = []
    yahoo = data.get("yahoo", {})
    quarterly = data.get("quarterly")
    latest_quarter = data.get("latest_quarter", {})
    data_status = data.get("data_status", "unknown")

    # ===== YAHOO FINANCE DATA =====
    output.append("=" * 50)
    output.append("YAHOO FINANCE DATA")
    output.append("=" * 50)

    # Basic Info
    output.append(f"Ticker: {yahoo.get('ticker', 'N/A')}")
    output.append(f"Company: {yahoo.get('company_name', 'N/A')}")
    output.append(f"Current Price: S${yahoo.get('current_price', 'N/A')}")
    if yahoo.get('market_cap'):
        output.append(f"Market Cap: S${yahoo.get('market_cap', 0) / 1e9:.2f}B")

    # Key Metrics
    output.append(f"\nKey Metrics:")
    output.append(f"  P/B Ratio: {yahoo.get('price_to_book', 'N/A')}")

    gearing = yahoo.get('gearing_ratio')
    if gearing is not None:
        output.append(f"  Gearing Ratio: {gearing:.1%}")
    else:
        output.append("  Gearing Ratio: N/A")

    icr = yahoo.get('icr')
    if icr is not None:
        output.append(f"  Interest Coverage Ratio (ICR): {icr:.2f}x")
    else:
        output.append("  ICR: N/A")

    output.append(f"  Beta: {yahoo.get('beta', 'N/A')}")

    div_yield = yahoo.get('current_year_dividend_yield')
    if div_yield is not None:
        output.append(f"  Current Dividend Yield: {div_yield:.2f}%")

    ytd = yahoo.get('ytd_performance')
    if ytd is not None:
        output.append(f"  YTD Performance: {ytd:+.2f}%")

    # Dividend History
    div_history = yahoo.get('dividend_history', [])
    if div_history:
        output.append(f"\nDividend History (DPU):")
        for div in div_history[:5]:
            output.append(f"  {div['year']}: {div['amount']*100:.2f}c (yield {div['yield']:.2f}%)")

    # Analyst Info
    if yahoo.get('analyst_rating'):
        output.append(f"\nAnalyst Rating: {yahoo.get('analyst_rating')}")
    if yahoo.get('target_price_mean'):
        output.append(f"Target Price: S${yahoo.get('target_price_mean'):.2f}")

    # ===== QUARTERLY REPORT DATA =====
    # Use new formatter with full text + summaries for deep analysis
    if data_status == "partial" or not quarterly:
        output.append("\n" + "=" * 50)
        output.append("QUARTERLY REPORT DATA")
        output.append("=" * 50)
        output.append("⚠️ QUARTERLY DATA NOT AVAILABLE")
        output.append("Analysis will be based on Yahoo Finance data only.")
        output.append("This is a limitation - some operational metrics may be missing.")
        output.append("\n" + "=" * 50)
    else:
        # Use full text + summaries formatter for comprehensive analysis
        quarterly_text = format_full_plus_summaries(data)
        output.append("\n" + quarterly_text)

    return "\n".join(output)


def format_full_plus_summaries(data: dict, max_latest_chars: int = 80000) -> str:
    """
    Format quarterly data with full text for latest quarter + summaries for earlier quarters.

    This provides:
    - Deep qualitative context from latest quarter (full PDF text)
    - Trend context from earlier quarters (LLM-generated summaries)
    - Structured metrics table for quantitative comparison

    Args:
        data: Combined data object with 'quarterly' key
        max_latest_chars: Max characters for latest quarter full text
    """
    output = []
    quarterly = data.get("quarterly", {})
    quarters = quarterly.get("quarters", [])

    if not quarters:
        return "No quarterly report data available."

    output.append("=" * 60)
    output.append("QUARTERLY ANALYSIS DATA")
    output.append("=" * 60)

    # ===== LATEST QUARTER - FULL TEXT =====
    latest = quarters[0]
    quarter_label = latest.get("quarter", "Latest")
    report_date = latest.get("report_date", "")
    full_text = latest.get("full_text", "")

    output.append(f"\n## LATEST QUARTER: {quarter_label} ({report_date})")
    output.append("=" * 60)
    output.append("FULL REPORT TEXT (for deep qualitative analysis):")
    output.append("-" * 40)

    if full_text:
        output.append(full_text[:max_latest_chars])
        if len(full_text) > max_latest_chars:
            output.append(f"\n[Truncated at {max_latest_chars} characters]")
    else:
        output.append("[Full text not available - using structured metrics only]")
        output.append(_format_structured_metrics(latest))

    # ===== EARLIER QUARTERS - LLM SUMMARIES =====
    if len(quarters) > 1:
        output.append("\n" + "=" * 60)
        output.append("EARLIER QUARTERS - SUMMARIES (for trend context)")
        output.append("=" * 60)

        for q in quarters[1:]:
            q_label = q.get("quarter", "Unknown")
            q_date = q.get("report_date", "")
            summary = q.get("summary", "")

            output.append(f"\n### {q_label} ({q_date})")
            output.append("-" * 40)

            if summary:
                output.append(summary)
            else:
                output.append("[Summary not available - using structured metrics]")
                output.append(_format_structured_metrics(q))

    # ===== STRUCTURED METRICS TABLE =====
    output.append("\n" + "=" * 60)
    output.append("QUARTERLY METRICS COMPARISON")
    output.append("=" * 60)
    output.append(_format_metrics_table(quarters))

    return "\n".join(output)


def _format_structured_metrics(quarter: dict) -> str:
    """Format structured metrics as fallback when full_text/summary unavailable."""
    lines = []
    op = quarter.get("operational_metrics", {})
    cap = quarter.get("capital_metrics", {})

    occupancy = op.get("occupancy", {})
    if occupancy:
        if isinstance(occupancy, dict):
            occ_val = occupancy.get("portfolio", occupancy.get("retail", "N/A"))
        else:
            occ_val = occupancy
        lines.append(f"Occupancy: {occ_val}%")

    wale = op.get("wale", {})
    if wale:
        if isinstance(wale, dict):
            wale_val = wale.get("portfolio", "N/A")
        else:
            wale_val = wale
        lines.append(f"WALE: {wale_val} years")

    rent_rev = op.get("rent_reversion", {})
    if rent_rev:
        rev_parts = []
        for seg, val in rent_rev.items():
            if val is not None:
                rev_parts.append(f"{seg}: {val:+.1f}%")
        if rev_parts:
            lines.append(f"Rent Reversion: {', '.join(rev_parts)}")

    if cap.get("leverage"):
        lines.append(f"Leverage: {cap['leverage']:.1f}%")
    if cap.get("cost_of_debt"):
        lines.append(f"Cost of Debt: {cap['cost_of_debt']:.2f}%")

    return "\n".join(lines) if lines else "No metrics available"


def _format_metrics_table(quarters: list) -> str:
    """Format metrics as comparison table across quarters."""
    lines = []
    lines.append(f"{'Quarter':<12} {'Occupancy':<12} {'WALE':<10} {'Leverage':<12} {'Cost of Debt':<12}")
    lines.append("-" * 60)

    for q in quarters:
        quarter_label = (q.get("quarter") or "?")[:11]
        op = q.get("operational_metrics", {})
        cap = q.get("capital_metrics", {})

        # Extract occupancy
        occ = op.get("occupancy", {})
        if isinstance(occ, dict):
            occ_val = occ.get("portfolio", occ.get("retail", "N/A"))
        else:
            occ_val = occ if occ else "N/A"
        occ_str = f"{occ_val}%" if occ_val != "N/A" else "N/A"

        # Extract WALE
        wale = op.get("wale", {})
        if isinstance(wale, dict):
            wale_val = wale.get("portfolio", "N/A")
        else:
            wale_val = wale if wale else "N/A"
        wale_str = f"{wale_val}y" if wale_val != "N/A" else "N/A"

        # Extract leverage and cost of debt
        leverage = cap.get("leverage")
        lev_str = f"{leverage:.1f}%" if leverage else "N/A"

        cod = cap.get("cost_of_debt")
        cod_str = f"{cod:.2f}%" if cod else "N/A"

        lines.append(f"{quarter_label:<12} {occ_str:<12} {wale_str:<10} {lev_str:<12} {cod_str:<12}")

    return "\n".join(lines)


def create_agent_node(llm):
    """Create the LLM node for mini-agent (no tools)."""

    def agent_node(state: MiniAgentState) -> dict:
        """Process the REIT analysis request."""
        messages = state["messages"]
        response = llm.invoke(messages)
        return {"messages": [response]}

    return agent_node


def output_parser_node(state: MiniAgentState) -> dict:
    """Parse the final LLM response into structured JSON."""
    ticker = state["ticker"]
    company_name = state["company_name"]

    # Get the last AI message
    response_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            content = msg.content
            if content and len(content.strip()) > 0:
                response_text = content
                break

    if not response_text:
        print(f"[OUTPUT PARSER] {ticker}: No AIMessage with content found")
        return {"result": {
            "ticker": ticker,
            "company_name": company_name,
            "swan_qualified": False,
            "swan_score": 0,
            "parse_error": True,
            "rationale": "LLM did not return text content"
        }}

    print(f"[OUTPUT PARSER] {ticker}: Response length={len(response_text)} chars")

    # Try to extract JSON from response
    result = _parse_json_response(response_text, ticker, company_name)

    if result.get("parse_error"):
        print(f"[OUTPUT PARSER] {ticker}: JSON parse failed, using fallback")
    else:
        # Detect mode from result keys (value_score vs swan_score)
        if "value_score" in result:
            print(f"[OUTPUT PARSER] {ticker}: Parsed OK - score={result.get('value_score')}, qualified={result.get('value_qualified')}")
        else:
            print(f"[OUTPUT PARSER] {ticker}: Parsed OK - score={result.get('swan_score')}, qualified={result.get('swan_qualified')}")

    return {"result": result}


def _sanitize_json_string(json_str: str) -> str:
    """
    Sanitize JSON string by escaping control characters that break parsing.
    Newlines and tabs inside string values need to be escaped.
    """
    # Replace literal control characters with escaped versions
    # This handles cases where LLM outputs raw newlines in string values
    result = []
    in_string = False
    escape_next = False

    for char in json_str:
        if escape_next:
            result.append(char)
            escape_next = False
            continue

        if char == '\\':
            result.append(char)
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            result.append(char)
            continue

        if in_string:
            # Escape control characters inside strings
            if char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            else:
                result.append(char)
        else:
            result.append(char)

    return ''.join(result)


def _parse_json_response(response_text: str, ticker: str, company_name: str) -> dict:
    """Extract JSON from LLM response."""
    # Try to find JSON block in markdown code fence
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = _sanitize_json_string(json_match.group(1))
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[JSON PARSE] {ticker}: Code fence JSON decode error: {e}")

    # Try to parse the entire response as JSON (if LLM returned raw JSON)
    stripped = response_text.strip()
    if stripped.startswith('{') and stripped.endswith('}'):
        json_str = _sanitize_json_string(stripped)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[JSON PARSE] {ticker}: Raw JSON decode error: {e}")

    # Last attempt: find outermost braces and sanitize
    start = response_text.find('{')
    end = response_text.rfind('}')
    if start != -1 and end != -1 and end > start:
        json_str = _sanitize_json_string(response_text[start:end+1])
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[JSON PARSE] {ticker}: Brace extraction decode error: {e}")

    # Fallback: create minimal result from response
    print(f"[JSON PARSE] {ticker}: All parsing attempts failed")
    return {
        "ticker": ticker,
        "company_name": company_name,
        "swan_qualified": False,
        "swan_score": 0,
        "parse_error": True,
        "rationale": response_text[:500] if response_text else "Failed to parse response"
    }


def build_mini_agent_graph(llm):
    """
    Build the simplified mini-agent subgraph for single REIT analysis.

    No tools - just LLM analysis and JSON parsing.

    Args:
        llm: LLM instance (no tools bound)

    Returns:
        Compiled subgraph
    """
    agent_node = create_agent_node(llm)

    # Build simple graph: agent → output_parser → END
    workflow = StateGraph(MiniAgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("output_parser", output_parser_node)

    workflow.set_entry_point("agent")
    workflow.add_edge("agent", "output_parser")
    workflow.add_edge("output_parser", END)

    return workflow.compile()


def analyze_single_reit(
    combined_data: dict,
    llm,
    mode: str = "swan",
) -> dict:
    """
    Analyze a single REIT using the mini-agent.

    Args:
        combined_data: Combined Yahoo + quarterly data dict
        llm: LLM instance (no tools)
        mode: Analysis mode ("swan" or "value")

    Returns:
        Analysis result dict with swan_qualified, swan_score, rationale, etc.
    """
    ticker = combined_data.get('ticker', 'UNKNOWN')
    company_name = combined_data.get('company_name', 'Unknown REIT')
    data_status = combined_data.get('data_status', 'unknown')

    print(f"[MINI-AGENT] Starting analysis of {ticker} ({company_name}) - data: {data_status}")

    try:
        # Load and format prompt
        prompt_template = load_single_reit_prompt(mode)
        combined_formatted = format_combined_data(combined_data)

        prompt = prompt_template.format(
            ticker=ticker,
            company_name=company_name,
            combined_data_formatted=combined_formatted,
            data_status=data_status,
        )

        # Build and run the mini-agent graph
        graph = build_mini_agent_graph(llm)

        initial_state = {
            "messages": [HumanMessage(content=prompt)],
            "ticker": ticker,
            "company_name": company_name,
            "combined_data": combined_data,
            "result": None,
        }

        # Run the graph
        final_state = graph.invoke(initial_state)

        result = final_state.get("result")

        if result:
            # Add data_status to result for report
            result["data_status"] = data_status
            # Detect mode from result keys
            if "value_score" in result:
                print(f"[MINI-AGENT] Completed {ticker}: value_qualified={result.get('value_qualified', 'N/A')}, score={result.get('value_score', 0)}")
            else:
                print(f"[MINI-AGENT] Completed {ticker}: swan_qualified={result.get('swan_qualified', 'N/A')}, score={result.get('swan_score', 0)}")
        else:
            print(f"[MINI-AGENT] Completed {ticker}: No result parsed")
            result = {
                "ticker": ticker,
                "company_name": company_name,
                "swan_qualified": False,
                "swan_score": 0,
                "data_status": data_status,
                "rationale": "No result parsed from mini-agent"
            }

        return result

    except Exception as e:
        print(f"[MINI-AGENT] Error analyzing {ticker}: {e}")
        return {
            "ticker": ticker,
            "company_name": company_name,
            "swan_qualified": False,
            "swan_score": 0,
            "data_status": data_status,
            "error": str(e),
            "rationale": f"Analysis failed: {str(e)}"
        }
