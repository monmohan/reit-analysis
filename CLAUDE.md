# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Singapore REIT Analysis Agent** built with LangGraph and Azure OpenAI. It fetches financial data for Singapore REITs from Yahoo Finance, ranks them by market cap, and provides AI-powered qualitative investment analysis using a "Fund Manager" persona.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Running the Agent
```bash
# Main execution
python3 reit_info_agent.py

# Generates timestamped markdown report: reit_analysis_YYYYMMDD_HHMMSS.md
```

### Testing
```bash
# Run full test suite (3 tests: single REIT, ranking, multi-REIT workflow)
python3 test_reit_components.py

# Test specific components in Python REPL
python3
>>> from yahoo_finance_api import get_reit_info, get_reit_data_structured
>>> get_reit_info("C38U.SI")  # CapitaLand Ascendas REIT
```

### Modifying Agent Behavior
```bash
# Edit prompt template (no code changes needed)
nano prompts/reit_audit_prompt.txt

# Then re-run agent
python3 reit_info_agent.py
```

## Architecture Overview

### Three-Layer Architecture

**Data Layer** - Financial data fetching and REIT discovery:
- `yahoo_finance_api.py` - Yahoo Finance interface with two output modes:
  - `get_reit_data_structured()` → Dict (for programmatic use)
  - `get_reit_info()` → formatted string (for LLM consumption)
- `singapore_reits.py` - Curated list of 24 Singapore REIT tickers + market cap ranking
- `gemini_yfin.py` - Lightweight fallback implementation

**Auth Layer** - Azure authentication:
- `azure_auth.py` - Azure AD OAuth 2.0 token provider for OpenAI API access

**Agent Layer** - AI orchestration:
- `reit_info_agent.py` - Main entry point using LangGraph StateGraph pattern
- `prompt_tool.py` - Reusable agent framework template (educational reference)

### Key Architectural Patterns

**Agent-Based Orchestration (LangGraph)**:
```
Agent Node → Router → Tool Node → Agent Node (loop until completion)
```
- Agent evaluates request and decides whether to call tools
- Router uses conditional edges based on `tool_calls` presence
- Tools execute, results feed back to agent for synthesis

**Tool-Augmented LLM**:
Two tools bound to Azure OpenAI:
1. `get_reit_info(ticker)` - Single REIT lookup
2. `analyze_top_singapore_reits(limit)` - Batch analysis with market cap rankings

**Message Accumulation Pattern**:
```python
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
```
Uses `operator.add` as reducer to automatically append messages, preserving full conversation context through multi-turn interactions.

**External Prompt Management**:
- Prompts live in `prompts/reit_audit_prompt.txt` (not hardcoded)
- Enables behavior modification without code changes
- Current persona: "veteran Fund Manager" with 3-tier analysis framework

**Data Flow**:
```
User Input
    ↓
reit_info_agent.py (LangGraph orchestrator)
    ↓
Azure OpenAI LLM ← Azure AD Token
    ↓
Tool Decision
    ├→ get_reit_info() → yahoo_finance_api.py
    └→ analyze_top_singapore_reits()
       ├→ singapore_reits.get_top_reits_by_market_cap()
       └→ yahoo_finance_api.get_reit_data_structured() per ticker
           ↓
           yfinance.Ticker API
    ↓
Tool Results → LLM Synthesis → Markdown Report
```

## Critical Design Decisions

### Division of Labor
- **Python handles**: Deterministic operations (data fetching, arithmetic, market cap ranking) → 100% accurate
- **LLM handles**: Qualitative reasoning (business model analysis, risk assessment, investment recommendations) → Creative/nuanced

### Dual Data Formats
`yahoo_finance_api.py` provides two interfaces:
- `get_reit_data_structured()` → Dict for Python logic (sorting, filtering)
- `get_reit_info()` → Formatted string for LLM readability

### Report Generation as Post-Processing
Rather than returning analysis directly:
1. Capture raw tool output (quantitative rankings table)
2. Capture LLM synthesis (qualitative analysis)
3. Combine both in timestamped markdown report
4. Preserves data integrity while allowing narrative interpretation

### Conditional Tool Routing
```python
def router(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END
```
Automatically routes based on LLM's decision, enabling self-directed multi-turn workflows.


## Key Financial Metrics

The system fetches these metrics per REIT:
- **Current Price** & **Market Cap** - Size and valuation
- **Price-to-Book (P/B) Ratio** - Value indicator (below 1.0 = trading below book value)
- **Gearing Ratio** - Debt/Total Assets (40%+ triggers safety concerns)
- **Dividend Yield** - Last 5 years with yield calculations
- **YTD Performance** - Year-to-date price change percentage


