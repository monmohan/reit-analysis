"""
Singapore REIT Analysis Agent - Map-Reduce Architecture

Orchestrates parallel REIT analysis using LangGraph fan-out/fan-in pattern.
Each REIT is analyzed independently by a mini-agent, then results are merged.
"""
import os
import sys
import argparse
import json
from datetime import datetime
from typing import TypedDict, Annotated, List, Optional, Any
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.types import Send

from config import load_llm_config
from llm import create_llm
from yahoo_finance_api import get_reit_data_structured
from singapore_reits import get_top_reits_by_market_cap
from data_cache import get_reit_quarterly_structured
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


class FilteredREIT(TypedDict):
    """A REIT that was filtered out during setup."""
    ticker: str
    company_name: str
    reason: str
    metrics: dict


class OrchestratorState(TypedDict):
    """State for the main orchestrator graph."""
    mode: str
    top: int
    reits_to_screen: int
    user_preferences: dict
    # Combined Yahoo + quarterly data for candidates
    candidates: List[dict]
    # REITs filtered out with reasons (for report)
    filtered_out: List[FilteredREIT]
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
    Fetch Yahoo + quarterly data for all REITs, combine, and categorize.

    Returns:
        candidates: List of REITs to analyze (with combined data)
        filtered_out: List of REITs excluded with reasons
    """
    reits_to_screen = state["reits_to_screen"]
    mode = state["mode"]

    print(f"\n[SETUP] Fetching top {reits_to_screen} Singapore REITs by market cap...")

    # Step 1: Get top REITs by market cap
    top_reits = get_top_reits_by_market_cap(reits_to_screen)

    if not top_reits:
        print("[SETUP] Error: Could not fetch REIT list")
        return {"candidates": [], "filtered_out": []}

    # Step 2: Fetch Yahoo + quarterly data for each REIT
    print(f"\n[SETUP] Fetching Yahoo + quarterly data for {len(top_reits)} REITs...")

    all_reits = []  # All REITs with combined data
    for ticker, market_cap, company_name in top_reits:
        # Fetch Yahoo data
        yahoo_data = get_reit_data_structured(ticker)
        if not yahoo_data:
            print(f"  [SKIP] {ticker} - No Yahoo data")
            continue

        # Fetch quarterly data from cache
        quarterly_data = get_reit_quarterly_structured(ticker)

        # Determine data status
        if quarterly_data and quarterly_data.get("quarters"):
            data_status = "complete"
            data_gaps = []
            # Extract latest quarter metrics for easy access
            latest_quarter = quarterly_data["quarters"][0] if quarterly_data["quarters"] else {}
            print(f"  [OK] {ticker} - Yahoo + {len(quarterly_data['quarters'])} quarters")
        else:
            data_status = "partial"
            data_gaps = ["No quarterly PDF data available"]
            latest_quarter = {}
            print(f"  [PARTIAL] {ticker} - Yahoo only (no quarterly PDFs)")

        # Build combined data object
        combined = {
            "ticker": ticker,
            "company_name": yahoo_data.get("company_name", company_name),
            "data_status": data_status,
            "data_gaps": data_gaps,
            "yahoo": yahoo_data,
            "quarterly": quarterly_data,
            "latest_quarter": latest_quarter,
        }
        all_reits.append(combined)

    # Step 3: Apply basic quantitative filter
    candidates = []
    filtered_out = []

    for reit in all_reits:
        yahoo = reit["yahoo"]
        ticker = reit["ticker"]
        gearing = yahoo.get('gearing_ratio')
        icr = yahoo.get('icr')

        # Check filter criteria (for SWAN mode)
        if mode == "swan":
            # Filter: Gearing > 50%
            if gearing is not None and gearing > 0.50:
                filtered_out.append({
                    "ticker": ticker,
                    "company_name": reit["company_name"],
                    "reason": f"Gearing {gearing:.1%} exceeds 50% threshold",
                    "metrics": {"gearing": gearing, "icr": icr}
                })
                print(f"  [FILTER] {ticker} - Gearing {gearing:.1%} too high")
                continue

            # Filter: ICR < 2.0
            if icr is not None and icr < 2.0:
                filtered_out.append({
                    "ticker": ticker,
                    "company_name": reit["company_name"],
                    "reason": f"ICR {icr:.2f}x below 2.0x threshold",
                    "metrics": {"gearing": gearing, "icr": icr}
                })
                print(f"  [FILTER] {ticker} - ICR {icr:.2f}x too low")
                continue

        candidates.append(reit)

    # Summary
    complete_count = sum(1 for c in candidates if c["data_status"] == "complete")
    partial_count = sum(1 for c in candidates if c["data_status"] == "partial")

    print(f"\n[SETUP] Summary:")
    print(f"  - Candidates: {len(candidates)} ({complete_count} complete, {partial_count} partial)")
    print(f"  - Filtered out: {len(filtered_out)}")
    print(f"[SETUP] Ready to analyze {len(candidates)} REITs\n")

    return {"candidates": candidates, "filtered_out": filtered_out}


def fan_out_to_mini_agents(state: OrchestratorState) -> List[Send]:
    """
    Fan-out: Create a Send for each REIT candidate to be processed by mini-agent.
    """
    candidates = state["candidates"]
    mode = state["mode"]

    if not candidates:
        print("[FAN-OUT] No candidates to analyze")
        return []

    complete = sum(1 for c in candidates if c.get("data_status") == "complete")
    partial = sum(1 for c in candidates if c.get("data_status") == "partial")
    print(f"[FAN-OUT] Spawning {len(candidates)} mini-agents ({complete} complete, {partial} partial data)...")

    # Create Send objects for each candidate
    sends = []
    for candidate in candidates:
        sends.append(
            Send("mini_agent_node", {
                "combined_data": candidate,
                "mode": mode
            })
        )

    return sends


def mini_agent_node(state: dict) -> dict:
    """
    Process a single REIT using the mini-agent.
    This node is invoked via Send() for each REIT.
    """
    combined_data = state["combined_data"]
    mode = state["mode"]
    ticker = combined_data.get('ticker', 'UNKNOWN')

    print(f"[MINI-AGENT] Analyzing {ticker}...")

    # Create LLM (no tools needed - all data is pre-fetched)
    llm = create_llm(llm_config["primary_llm"])

    # Run mini-agent synchronously
    try:
        result = analyze_single_reit(combined_data, llm, mode)
    except Exception as e:
        print(f"[MINI-AGENT] Error for {ticker}: {e}")
        result = {
            "ticker": ticker,
            "company_name": combined_data.get('company_name', 'Unknown'),
            "swan_qualified": False,
            "swan_score": 0,
            "data_status": combined_data.get('data_status', 'unknown'),
            "error": str(e),
            "rationale": f"Analysis failed: {str(e)}"
        }

    print(f"[MINI-AGENT] Completed {ticker}: score={result.get('swan_score', 0)}")

    # Return result to be merged via reducer
    return {"reit_analyses": [result]}


def reduce_node(state: OrchestratorState) -> dict:
    """
    Reduce: Filter qualified REITs, sort by score, take top N.
    Handles both SWAN and VALUE modes.
    """
    analyses = state["reit_analyses"]
    top_n = state["top"]
    mode = state["mode"]

    print(f"\n[REDUCE] Processing {len(analyses)} analysis results...")

    if mode == "swan":
        # Filter to only SWAN-qualified
        qualified_key = "swan_qualified"
        score_key = "swan_score"
        qualified = [a for a in analyses if a.get(qualified_key, False)]
        print(f"[REDUCE] {len(qualified)} REITs qualified as SWAN")
    else:
        # VALUE mode
        qualified_key = "value_qualified"
        score_key = "value_score"
        qualified = [a for a in analyses if a.get(qualified_key, False)]
        print(f"[REDUCE] {len(qualified)} REITs qualified as VALUE")

    # Sort by score descending
    qualified.sort(key=lambda x: x.get(score_key, 0), reverse=True)

    # Take top N
    top_picks = qualified[:top_n]

    print(f"[REDUCE] Top {len(top_picks)} selected:")
    for i, pick in enumerate(top_picks, 1):
        print(f"  {i}. {pick['ticker']} - Score: {pick.get(score_key, 0)}")

    return {"top_swans": top_picks}


def report_node(state: OrchestratorState) -> dict:
    """
    Generate final report using LLM to synthesize individual analyses.
    Includes sections for filtered-out REITs and data gaps.
    """
    top_swans = state["top_swans"]
    all_analyses = state["reit_analyses"]
    filtered_out = state.get("filtered_out", [])
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
        data_status = analysis.get('data_status', 'unknown')
        status_flag = " ⚠️ (Partial Data)" if data_status == "partial" else ""

        individual_analyses += f"\n### {analysis['ticker']} ({analysis['company_name']}){status_flag}\n"
        individual_analyses += f"- SWAN Qualified: {analysis.get('swan_qualified', False)}\n"
        individual_analyses += f"- SWAN Score: {analysis.get('swan_score', 0)}/10\n"
        individual_analyses += f"- Data Status: {data_status}\n"

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

    # Build filtered_out section
    if filtered_out:
        filtered_out_section = "The following REITs were excluded from analysis due to failing basic quantitative filters:\n\n"
        filtered_out_section += "| Ticker | Company | Reason | Gearing | ICR |\n"
        filtered_out_section += "|--------|---------|--------|---------|-----|\n"
        for reit in filtered_out:
            metrics = reit.get('metrics', {})
            gearing = f"{metrics.get('gearing', 0):.1%}" if metrics.get('gearing') else "N/A"
            icr = f"{metrics.get('icr', 0):.2f}x" if metrics.get('icr') else "N/A"
            filtered_out_section += f"| {reit['ticker']} | {reit['company_name'][:30]} | {reit['reason']} | {gearing} | {icr} |\n"
    else:
        filtered_out_section = "No REITs were excluded from analysis. All screened REITs met the basic quantitative filters."

    # Build data_gaps section
    partial_data_reits = [a for a in all_analyses if a.get('data_status') == 'partial']
    if partial_data_reits:
        data_gaps_section = "The following REITs were analyzed with incomplete data (missing quarterly PDF reports):\n\n"
        data_gaps_section += "| Ticker | Company | Missing Data |\n"
        data_gaps_section += "|--------|---------|-------------|\n"
        for reit in partial_data_reits:
            data_gaps_section += f"| {reit['ticker']} | {reit['company_name'][:30]} | Quarterly PDF reports |\n"
        data_gaps_section += "\n**Action:** Download quarterly reports using `uv run python pdf_downloader.py <ticker>` and re-run for more accurate analysis."
    else:
        data_gaps_section = "All analyzed REITs had complete data (Yahoo Finance + quarterly PDF reports)."

    # Format prompt
    prompt = reduce_prompt_template.format(
        num_reits=len(all_analyses),
        individual_analyses=individual_analyses,
        filtered_out_section=filtered_out_section,
        data_gaps_section=data_gaps_section,
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
    parser.add_argument('--no-input', action='store_true',
                        help='Skip interactive prompts, use default preferences')
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


def save_report(report: str, mode: str, analyses: List[dict], candidates: List[dict] = None):
    """Save the final report to a markdown file in results directory."""
    import os

    # Ensure results directory exists
    os.makedirs("results", exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_filename = f"results/{mode}_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    mode_title = "SWAN (Sleep Well At Night)" if mode == "swan" else "Value"

    # Mode-specific keys
    score_key = "swan_score" if mode == "swan" else "value_score"
    qualified_key = "swan_qualified" if mode == "swan" else "value_qualified"
    score_label = "SWAN Score" if mode == "swan" else "Value Score"

    # Build raw data section
    raw_data = f"| Ticker | Company | {score_label} | Qualified |\n"
    raw_data += "|--------|---------|------------|----------|\n"
    for a in analyses:
        raw_data += f"| {a['ticker']} | {a['company_name'][:30]} | {a.get(score_key, 0)} | {a.get(qualified_key, False)} |\n"

    # Build Yahoo Finance data appendix
    yahoo_table = "| Ticker | Price | Market Cap | P/B | Gearing | ICR | Beta | Yield |\n"
    yahoo_table += "|--------|-------|------------|-----|---------|-----|------|-------|\n"
    if candidates:
        for c in candidates:
            yahoo = c.get("yahoo", {})
            ticker = c.get("ticker", "N/A")
            price = f"S${yahoo.get('current_price', 0):.2f}" if yahoo.get('current_price') else "N/A"
            market_cap = f"S${yahoo.get('market_cap', 0) / 1e9:.1f}B" if yahoo.get('market_cap') else "N/A"
            pb = f"{yahoo.get('price_to_book', 0):.2f}" if yahoo.get('price_to_book') else "N/A"
            gearing = f"{yahoo.get('gearing_ratio', 0):.1%}" if yahoo.get('gearing_ratio') else "N/A"
            icr = f"{yahoo.get('icr', 0):.2f}x" if yahoo.get('icr') else "N/A"
            beta = f"{yahoo.get('beta', 0):.2f}" if yahoo.get('beta') else "N/A"
            div_yield = f"{yahoo.get('current_year_dividend_yield', 0):.2f}%" if yahoo.get('current_year_dividend_yield') else "N/A"
            yahoo_table += f"| {ticker} | {price} | {market_cap} | {pb} | {gearing} | {icr} | {beta} | {div_yield} |\n"

    # Build DPU history appendix
    dpu_table = "| Ticker | Company | 2023 | 2024 | 2025 | Trend |\n"
    dpu_table += "|--------|---------|------|------|------|-------|\n"
    if candidates:
        for c in candidates:
            yahoo = c.get("yahoo", {})
            ticker = c.get("ticker", "N/A")
            company = c.get("company_name", "N/A")[:20]
            div_history = yahoo.get("dividend_history", [])

            # Extract DPU by year
            dpu_by_year = {}
            for div in div_history:
                year = div.get("year")
                amount = div.get("amount", 0)
                if year:
                    dpu_by_year[year] = f"{amount * 100:.2f}c"

            dpu_2023 = dpu_by_year.get(2023, "N/A")
            dpu_2024 = dpu_by_year.get(2024, "N/A")
            dpu_2025 = dpu_by_year.get(2025, "N/A")

            # Determine trend
            trend = "N/A"
            if len(div_history) >= 2:
                amounts = [d.get("amount", 0) for d in div_history[:3]]
                if all(amounts[i] >= amounts[i+1] for i in range(len(amounts)-1)):
                    trend = "Growing"
                elif all(amounts[i] <= amounts[i+1] for i in range(len(amounts)-1)):
                    trend = "Declining"
                else:
                    trend = "Mixed"

            dpu_table += f"| {ticker} | {company} | {dpu_2023} | {dpu_2024} | {dpu_2025} | {trend} |\n"

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

## Appendix A: Yahoo Finance Data

{yahoo_table}

---

## Appendix B: DPU History

{dpu_table}

---

## About This Report

This analysis was generated using a Map-Reduce architecture:
1. Fetched Yahoo Finance data + quarterly PDF reports for Singapore REITs
2. Analyzed each REIT independently with combined financial and operational data
3. Filtered and ranked by {mode.upper()} criteria
4. Generated final report synthesis

**Data Source:** Yahoo Finance + Quarterly PDF Reports
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

    # Collect user preferences (or use defaults for non-interactive mode)
    if getattr(args, 'no_input', False):
        print("[CONFIG] Using default preferences (non-interactive mode)")
        user_preferences = {'risk_tolerance': 'moderate'}
    else:
        user_preferences = collect_user_preferences()

    # Build and run the orchestrator graph
    app = build_orchestrator_graph()

    initial_state = {
        "mode": args.mode,
        "top": args.top,
        "reits_to_screen": args.reits,
        "user_preferences": user_preferences,
        "candidates": [],
        "filtered_out": [],
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
        final_state["reit_analyses"],
        final_state["candidates"]
    )

    print("\n" + "="*60)
    print(f"Analysis complete! Report saved to: {output_file}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
