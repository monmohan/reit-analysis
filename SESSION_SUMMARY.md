# Singapore REIT Analysis Agent - Session State

**Date:** 2025-12-28
**Project:** AI Agent for analyzing Singapore REITs with LLM-powered qualitative analysis

---

## What Was Built

LangGraph-based AI agent that:
1. Fetches top 20 Singapore REITs by market cap from Yahoo Finance
2. Collects financial metrics (P/B ratio, dividend yield, YTD performance, gearing ratio)
3. Presents unified quantitative data table sorted by market cap
4. Applies LLM-powered qualitative "Fund Manager" analysis
5. Generates timestamped markdown reports with investment recommendations

---

## Key Files

### Core Agent
- **`reit_info_agent.py`**: Main LangGraph agent
  - Azure OpenAI with temperature=1 (creative analysis)
  - Tools: `get_reit_info()` and `analyze_top_singapore_reits()`
  - External prompt loading via `load_prompt()` (lines 176-197)
  - LLM response capture logic (lines 220-240)
  - Generates `reit_analysis_YYYYMMDD_HHMMSS.md`

### Data Layer
- **`yahoo_finance_api.py`**: Yahoo Finance data fetching
  - `get_reit_info(ticker)`: Formatted string output
  - `get_reit_data_structured(ticker)`: Dictionary output
  - Fetches: price, market cap, P/B ratio, gearing (debt/assets), dividend history, YTD performance
  - Balance sheet fallback for missing data

- **`singapore_reits.py`**: REIT discovery
  - Curated list of 24 Singapore REIT tickers
  - `get_top_reits_by_market_cap(limit=20)`: Returns top REITs by market cap

### Prompts
- **`prompts/reit_audit_prompt.txt`**: External prompt template
  - Parameterized with `{limit}` placeholder
  - Current version: Qualitative "Fund Manager" analysis with resilience stress test, safety filter, sponsor analysis

### Dependencies
- **`requirements.txt`**: langchain-openai, langgraph, yfinance, pandas, azure-identity, python-dotenv
- **`azure_auth.py`**: Azure AD token authentication
- **`test_reit_components.py`**: Test suite (all tests passing)

---

## Current Configuration

- **Model**: Azure OpenAI GPT-4, temperature=1
- **Default limit**: 20 REITs
- **Prompt source**: `prompts/reit_audit_prompt.txt`
- **Output**: Markdown reports with "Sleep Well" picks, "Value" picks, "Avoid" list

---

## How to Use

```bash
# Run analysis
python3 reit_info_agent.py

# Modify prompt
nano prompts/reit_audit_prompt.txt

# Run tests
python3 test_reit_components.py
```

---

## Key Design Decisions

1. **Division of Labor**: Python handles data/arithmetic (100% accurate), LLM handles qualitative reasoning (business models, risk assessment)
2. **External Prompts**: Enables rapid iteration without code changes
3. **Unified Table**: Single table with all metrics, sorted by market cap
4. **Temperature=1**: Creative, nuanced analysis vs deterministic rules

---

## Critical Fixes Applied

1. **Timezone comparison error**: Changed to date-based comparison in pandas
2. **Pandas deprecation**: Changed `resample('Y')` to `resample('YE')`
3. **Missing Total Assets**: Added balance sheet fallback for gearing calculation
4. **LLM response not captured**: Fixed tool_calls check to properly detect empty list
5. **Pivot from arithmetic to qualitative**: LLM now does Fund Manager analysis, not rule-based checks

---

## Environment Variables Required

```bash
AZURE_OPENAI_DEPLOYMENT_NAME=<your-deployment>
AZURE_OPENAI_API_VERSION=<api-version>
AZURE_OPENAI_ENDPOINT=<your-endpoint>
AZURE_TOKEN_URL=<token-url>
AZURE_CLIENT_ID=<client-id>
AZURE_CLIENT_SECRET=<client-secret>
```

---

## File Structure

```
/Users/singhmo/code/agents/ai-agent-learning/
├── reit_info_agent.py          # Main agent
├── yahoo_finance_api.py         # Data fetching
├── singapore_reits.py           # REIT discovery
├── azure_auth.py                # Authentication
├── requirements.txt             # Dependencies
├── test_reit_components.py      # Test suite
├── prompts/
│   └── reit_audit_prompt.txt   # Current prompt
└── reit_analysis_*.md          # Generated reports
```

---

**Current State**: All components working, tests passing, ready to run
