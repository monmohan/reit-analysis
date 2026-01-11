"""
Singapore REIT Analysis Agent - Map-Reduce Architecture

Orchestrates parallel REIT analysis using LangGraph fan-out/fan-in pattern.
Each REIT is analyzed independently by a mini-agent, then results are merged.
"""
import os
import sys
import argparse
import asyncio
import json
from datetime import datetime
from typing import TypedDict, Annotated, List, Optional, Any
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.types import Send

from config import load_llm_config
from llm import create_llm
from tools import search_reit_qualitative_info
from yahoo_finance_api import get_reit_data_structured
from singapore_reits import get_top_reits_by_market_cap
from mini_agent import analyze_single_reit

# 1. SETUP & AUTH
load_dotenv()

# Load LLM configuration
llm_config = load_llm_config()

print(f"[CONFIG] Primary LLM: {llm_config['primary_llm']['provider']}")


# =============================================================================
# STATE DEFINITIONS
# =============================================================================

class REITAnalysis(TypedDict):
    """Result from a single REIT mini-agent."""
    ticker: str
    company_name: str
    swan_qualified: bool
    swan_score: int
    metrics: Optional[dict]
    tenants_found: Optional[List[str]]
    rationale: str
    error: Optional[str]


def merge_analyses(existing: List[REITAnalysis], new: List[REITAnalysis]) -> List[REITAnalysis]:
    """Reducer function to merge analysis results."""
    return existing + new


class OrchestratorState(TypedDict):
    """State for the main orchestrator graph."""
    mode: str
    top: int
    reits_to_screen: int
    user_preferences: dict
    # Yahoo data for all candidates
    candidates: List[dict]
    # Results from mini-agents (uses reducer)
    reit_analyses: Annotated[List[REITAnalysis], merge_analyses]
    # Final outputs
    top_swans: List[REITAnalysis]
    final_report: str


# =============================================================================
# NODE FUNCTIONS
# =============================================================================

def setup_node(state: OrchestratorState) -> dict:
    """
    Fetch Yahoo data for all REITs and apply basic quantitative filter.
    """
    reits_to_screen = state["reits_to_screen"]
    mode = state["mode"]

    print(f"\n[SETUP] Fetching top {reits_to_screen} Singapore REITs by market cap...")

    # Get top REITs by market cap
    top_reits = get_top_reits_by_market_cap(reits_to_screen)

    if not top_reits:
        print("[SETUP] Error: Could not fetch REIT list")
        return {"candidates": []}

    # Fetch detailed Yahoo data for each
    print(f"\n[SETUP] Fetching detailed data for {len(top_reits)} REITs...")
    candidates = []

    for ticker, market_cap, company_name in top_reits:
        data = get_reit_data_structured(ticker)
        if data:
            candidates.append(data)
            print(f"  [OK] {ticker}")
        else:
            print(f"  [SKIP] {ticker} - No data")

    # Basic sanity filter for SWAN mode
    if mode == "swan":
        # Remove obviously unqualified REITs (very high gearing or no ICR data)
        filtered = []
        for c in candidates:
            gearing = c.get('gearing_ratio')
            icr = c.get('icr')

            # Skip if gearing > 50% (way above SWAN threshold)
            if gearing is not None and gearing > 0.50:
                print(f"  [FILTER] {c['ticker']} - Gearing {gearing:.2%} too high")
                continue

            # Skip if ICR < 2.0 (debt servicing risk)
            if icr is not None and icr < 2.0:
                print(f"  [FILTER] {c['ticker']} - ICR {icr:.2f}x too low")
                continue

            filtered.append(c)

        print(f"\n[SETUP] {len(filtered)} candidates after basic filter (from {len(candidates)})")
        candidates = filtered

    print(f"[SETUP] Ready to analyze {len(candidates)} REITs\n")
    return {"candidates": candidates}


def fan_out_to_mini_agents(state: OrchestratorState) -> List[Send]:
    """
    Fan-out: Create a Send for each REIT candidate to be processed by mini-agent.
    """
    candidates = state["candidates"]
    mode = state["mode"]

    if not candidates:
        print("[FAN-OUT] No candidates to analyze")
        return []

    print(f"[FAN-OUT] Spawning {len(candidates)} mini-agents...")

    # Create Send objects for each candidate
    sends = []
    for candidate in candidates:
        sends.append(
            Send("mini_agent_node", {
                "reit_data": candidate,
                "mode": mode
            })
        )

    return sends


def mini_agent_node(state: dict) -> dict:
    """
    Process a single REIT using the mini-agent.
    This node is invoked via Send() for each REIT.
    """
    reit_data = state["reit_data"]
    mode = state["mode"]
    ticker = reit_data.get('ticker', 'UNKNOWN')

    print(f"[MINI-AGENT] Analyzing {ticker}...")

    # Create LLMs - one with tools, one without (for final JSON output)
    primary_llm = create_llm(llm_config["primary_llm"])
    llm_with_tools = primary_llm.bind_tools([search_reit_qualitative_info])
    llm_no_tools = create_llm(llm_config["primary_llm"])  # No tools bound

    # Run mini-agent synchronously (we're already in parallel via Send)
    try:
        # Use asyncio.run since mini_agent is async but we're in sync context
        result = asyncio.run(
            analyze_single_reit(reit_data, llm_with_tools, llm_no_tools, mode)
        )
    except Exception as e:
        print(f"[MINI-AGENT] Error for {ticker}: {e}")
        result = {
            "ticker": ticker,
            "company_name": reit_data.get('company_name', 'Unknown'),
            "swan_qualified": False,
            "swan_score": 0,
            "error": str(e),
            "rationale": f"Analysis failed: {str(e)}"
        }

    print(f"[MINI-AGENT] Completed {ticker}: score={result.get('swan_score', 0)}")

    # Return result to be merged via reducer
    return {"reit_analyses": [result]}


def reduce_node(state: OrchestratorState) -> dict:
    """
    Reduce: Filter qualified SWANs, sort by score, take top N.
    """
    analyses = state["reit_analyses"]
    top_n = state["top"]
    mode = state["mode"]

    print(f"\n[REDUCE] Processing {len(analyses)} analysis results...")

    if mode == "swan":
        # Filter to only SWAN-qualified
        qualified = [a for a in analyses if a.get("swan_qualified", False)]
        print(f"[REDUCE] {len(qualified)} REITs qualified as SWAN")

        # Sort by swan_score descending
        qualified.sort(key=lambda x: x.get("swan_score", 0), reverse=True)

        # Take top N
        top_swans = qualified[:top_n]
    else:
        # For value mode (future), different logic
        top_swans = sorted(analyses, key=lambda x: x.get("swan_score", 0), reverse=True)[:top_n]

    print(f"[REDUCE] Top {len(top_swans)} selected:")
    for i, swan in enumerate(top_swans, 1):
        print(f"  {i}. {swan['ticker']} - Score: {swan.get('swan_score', 0)}")

    return {"top_swans": top_swans}


def report_node(state: OrchestratorState) -> dict:
    """
    Generate final report using LLM to synthesize individual analyses.
    """
    top_swans = state["top_swans"]
    all_analyses = state["reit_analyses"]
    mode = state["mode"]
    top = state["top"]

    print(f"\n[REPORT] Generating final {mode.upper()} report...")

    if not top_swans:
        return {"final_report": "No qualified REITs found for the selected criteria."}

    # Load reduce prompt
    try:
        with open(f"prompts/{mode}_reduce_prompt.txt", 'r') as f:
            reduce_prompt_template = f.read()
    except FileNotFoundError:
        reduce_prompt_template = "Summarize the following REIT analyses:\n{individual_analyses}"

    # Format individual analyses for prompt
    individual_analyses = ""
    for analysis in all_analyses:
        individual_analyses += f"\n### {analysis['ticker']} ({analysis['company_name']})\n"
        individual_analyses += f"- SWAN Qualified: {analysis.get('swan_qualified', False)}\n"
        individual_analyses += f"- SWAN Score: {analysis.get('swan_score', 0)}/10\n"

        metrics = analysis.get('metrics', {})
        if metrics:
            individual_analyses += f"- Gearing: {metrics.get('gearing', 'N/A')}\n"
            individual_analyses += f"- ICR: {metrics.get('icr', 'N/A')}\n"
            individual_analyses += f"- Beta: {metrics.get('beta', 'N/A')}\n"
            individual_analyses += f"- Sponsor: {metrics.get('sponsor', 'N/A')} (Tier {metrics.get('sponsor_tier', 'N/A')})\n"

        tenants = analysis.get('tenants_found', [])
        if tenants:
            individual_analyses += f"- Tenants Found: {', '.join(tenants[:5])}\n"

        individual_analyses += f"\nRationale:\n{analysis.get('rationale', 'No rationale provided')}\n"
        individual_analyses += "\n---\n"

    # Format prompt
    prompt = reduce_prompt_template.format(
        num_reits=len(all_analyses),
        individual_analyses=individual_analyses,
        top=top
    )

    # Call LLM to generate report
    reduce_llm = create_llm(llm_config["primary_llm"])

    response = reduce_llm.invoke([
        SystemMessage(content="You are a professional investment analyst writing a REIT report for conservative retiree investors."),
        HumanMessage(content=prompt)
    ])

    final_report = response.content
    print("[REPORT] Report generation complete")

    return {"final_report": final_report}


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================

def build_orchestrator_graph():
    """
    Build the main orchestrator graph with fan-out/fan-in pattern.
    """
    workflow = StateGraph(OrchestratorState)

    # Add nodes
    workflow.add_node("setup", setup_node)
    workflow.add_node("mini_agent_node", mini_agent_node)
    workflow.add_node("reduce", reduce_node)
    workflow.add_node("report", report_node)

    # Define edges
    workflow.add_edge(START, "setup")
    workflow.add_conditional_edges("setup", fan_out_to_mini_agents, ["mini_agent_node"])
    workflow.add_edge("mini_agent_node", "reduce")
    workflow.add_edge("reduce", "report")
    workflow.add_edge("report", END)

    return workflow.compile()


# =============================================================================
# CLI AND MAIN
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Singapore REIT Analysis Agent')
    parser.add_argument('--mode', choices=['swan', 'value'], default='swan',
                        help='Analysis mode: swan (safe dividend) or value (undervalued)')
    parser.add_argument('--top', type=int, default=5,
                        help='Number of top REITs to recommend (default: 5)')
    parser.add_argument('--reits', type=int, default=10,
                        help='Number of REITs to screen (default: 10)')
    return parser.parse_args()


def collect_user_preferences() -> dict:
    """Collect user preferences through prompts."""
    print("\n[PREFERENCES] Let's gather your investment preferences...\n")

    preferences = {}

    print("Risk Tolerance:")
    print("  - conservative: Minimize volatility, prefer blue-chip sponsors")
    print("  - moderate: Balanced risk-reward")
    risk = input("Your choice [default: moderate]: ").strip().lower()

    if risk in ['conservative', 'moderate']:
        preferences['risk_tolerance'] = risk
    else:
        preferences['risk_tolerance'] = 'moderate'

    print(f"\n[OK] Risk Tolerance: {preferences['risk_tolerance']}\n")
    return preferences


def save_report(report: str, mode: str, analyses: List[dict]):
    """Save the final report to a markdown file in results directory."""
    import os

    # Ensure results directory exists
    os.makedirs("results", exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_filename = f"results/{mode}_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    mode_title = "SWAN (Sleep Well At Night)" if mode == "swan" else "Value"

    # Build raw data section
    raw_data = "| Ticker | Company | SWAN Score | Qualified |\n"
    raw_data += "|--------|---------|------------|----------|\n"
    for a in analyses:
        raw_data += f"| {a['ticker']} | {a['company_name'][:30]} | {a.get('swan_score', 0)} | {a.get('swan_qualified', False)} |\n"

    markdown_content = f"""# Singapore REIT {mode_title} Analysis

**Generated:** {timestamp}
**Mode:** {mode.upper()}

---

## Raw Analysis Data

{raw_data}

---

## AI Analysis Report

{report}

---

## About This Report

This analysis was generated using a Map-Reduce architecture:
1. Fetched Yahoo Finance data for Singapore REITs
2. Analyzed each REIT independently with web search for qualitative info
3. Filtered and ranked by SWAN criteria
4. Generated final report synthesis

**Data Source:** Yahoo Finance + Web Search
**Analysis Date:** {datetime.now().strftime("%Y-%m-%d")}

### Disclaimer
This report is for informational purposes only and should not be considered as financial advice.
Always conduct your own research and consult with a qualified financial advisor before making investment decisions.
"""

    with open(output_filename, 'w') as f:
        f.write(markdown_content)

    return output_filename


def main():
    """Main entry point."""
    args = parse_args()

    print("\n" + "="*60)
    print("SINGAPORE REIT ANALYSIS AGENT - MAP-REDUCE ARCHITECTURE")
    print("="*60)
    print(f"\n[CONFIG] Mode: {args.mode.upper()}")
    print(f"[CONFIG] Screening top {args.reits} REITs")
    print(f"[CONFIG] Recommending top {args.top} picks")

    # Collect user preferences
    user_preferences = collect_user_preferences()

    # Build and run the orchestrator graph
    app = build_orchestrator_graph()

    initial_state = {
        "mode": args.mode,
        "top": args.top,
        "reits_to_screen": args.reits,
        "user_preferences": user_preferences,
        "candidates": [],
        "reit_analyses": [],
        "top_swans": [],
        "final_report": ""
    }

    print("\n[AGENT] Starting analysis pipeline...\n")

    # Run the graph
    final_state = app.invoke(initial_state)

    # Save report
    output_file = save_report(
        final_state["final_report"],
        args.mode,
        final_state["reit_analyses"]
    )

    print("\n" + "="*60)
    print(f"Analysis complete! Report saved to: {output_file}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
