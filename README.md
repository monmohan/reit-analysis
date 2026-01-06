# Singapore REIT Analysis Agent

An AI-powered agent built with LangGraph and Azure OpenAI that analyzes Singapore REITs (Real Estate Investment Trusts) and provides investment recommendations tailored for conservative income-focused investors.

## Overview

This agent combines **deterministic financial data fetching** from Yahoo Finance with **AI-powered qualitative analysis** to help investors—particularly retirees—identify "SWAN" (Sleep Well At Night) dividend-paying REITs in the Singapore market.

The system fetches real-time data for 24 Singapore-listed REITs, ranks them by market capitalization, and applies a 3-Tier Retiree Safety Framework to categorize investments:

- **SWAN List** - Low volatility, Tier 1 sponsors, essential tenants
- **Value List** - Fundamentally strong REITs trading at a discount
- **Red Flags** - REITs to avoid with explicit risk warnings

## Features

- **Comprehensive Data Fetching** - Retrieves financial metrics for 24 Singapore REITs from Yahoo Finance
- **Market Cap Ranking** - Automatically ranks REITs by market capitalization
- **AI Qualitative Analysis** - Fund Manager persona provides professional investment analysis
- **Human-in-the-Loop (HITL)** - Interactive preference collection for personalized recommendations
- **3-Tier Safety Framework** - Evaluates Financial Health, Income Stability, and Sponsor Strength
- **Web Search Integration** - Fetches latest news and tenant information via DuckDuckGo
- **Markdown Report Generation** - Produces timestamped reports combining quantitative data with qualitative insights

## Quick Start

### Prerequisites
- Python 3.10+
- Azure OpenAI access with deployed model
- Azure AD credentials

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd reit-analysis

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
```

### Run the Agent

```bash
python3 reit_info_agent.py
```

The agent will:
1. Prompt you for investment preferences (risk tolerance, max P/B ratio)
2. Fetch and analyze top Singapore REITs
3. Generate a timestamped markdown report: `reit_analysis_YYYYMMDD_HHMMSS.md`

## Architecture

### Three-Layer Design

```
┌─────────────────────────────────────────────┐
│              Agent Layer                     │
│  reit_info_agent.py, nodes.py, tools.py     │
│  LangGraph orchestration + HITL workflow     │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│              Auth Layer                      │
│  azure_auth.py                              │
│  Azure AD OAuth 2.0 token provider          │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│              Data Layer                      │
│  yahoo_finance_api.py - Financial metrics   │
│  singapore_reits.py - REIT discovery        │
└─────────────────────────────────────────────┘
```

### LangGraph Workflow

```
preference_collector → preference_parser → agent → [router]
                                                      │
                                         ┌────────────┴────────────┐
                                         ↓                         ↓
                                      tools → agent (loop)        END
```

### Design Principles

- **Division of Labor**: Python handles deterministic operations (data fetching, arithmetic, ranking); LLM handles qualitative reasoning (business analysis, risk assessment)
- **Dual Data Formats**: Structured dicts for programmatic use, formatted strings for LLM consumption
- **External Prompts**: Prompt templates live in `prompts/` directory, enabling behavior changes without code modifications

## Project Structure

| File | Purpose |
|------|---------|
| `reit_info_agent.py` | Main entry point; LangGraph orchestration |
| `state.py` | TypedDict definitions for AgentState and UserPreferences |
| `nodes.py` | Node functions: preference collection, parsing, agent logic, routing |
| `tools.py` | LLM-bound tools: REIT lookup, batch analysis, web search |
| `yahoo_finance_api.py` | Yahoo Finance interface with dual output modes |
| `singapore_reits.py` | Curated list of 24 Singapore REIT tickers |
| `azure_auth.py` | Azure AD OAuth 2.0 authentication |
| `prompts/reit_audit_prompt.txt` | Fund Manager persona prompt template |

## Key Financial Metrics

The agent fetches these metrics per REIT:

| Metric | Description |
|--------|-------------|
| Current Price | Latest trading price |
| Market Cap | Total market capitalization |
| P/B Ratio | Price-to-Book ratio (below 1.0 = trading below book value) |
| Gearing Ratio | Debt/Total Assets (40%+ triggers safety concerns) |
| Interest Coverage Ratio | Ability to service debt (below 3.0x = warning) |
| Dividend Yield | Current yield percentage |
| DPU History | 5-year Distribution Per Unit with CAGR calculation |
| YTD Performance | Year-to-date price change |

## Customization

### Modifying the Analysis Prompt

Edit `prompts/reit_audit_prompt.txt` to change the AI's analysis style, framework, or persona without modifying code:

```bash
nano prompts/reit_audit_prompt.txt
```

### Adding REITs

Update the ticker list in `singapore_reits.py` to include additional REITs.

## Testing

```bash
# Run full test suite (3 tests)
python3 test_reit_components.py

# Test individual components in Python REPL
python3
>>> from yahoo_finance_api import get_reit_info
>>> print(get_reit_info("C38U.SI"))  # CapitaLand Ascendas REIT
```

## Sample Output

Generated reports include:
- **Raw Data Table** - All REITs with complete metrics
- **DPU Trends** - Dividend history with calculated CAGR per REIT
- **AI Analysis** - SWAN categorization, value picks, and red flags with detailed rationale

Example report: `reit_analysis_20260105_121130.md`

## Technical Documentation

For detailed architecture documentation, design decisions, and development guidelines, see [CLAUDE.md](./CLAUDE.md).

## Dependencies

- `langchain-openai` - Azure OpenAI integration
- `langgraph` - Graph orchestration with checkpointing
- `azure-identity` - Azure authentication
- `yfinance` - Yahoo Finance API
- `pandas` - Data manipulation
- `duckduckgo-search` - Web search for qualitative info

## License

MIT
