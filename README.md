# Singapore REIT Analysis Agent

An AI-powered agent built with LangGraph Map-Reduce architecture that analyzes Singapore REITs using Yahoo Finance data combined with quarterly PDF report extraction.

## Overview

This agent combines **deterministic financial data** from Yahoo Finance with **operational insights** extracted from quarterly PDF reports to provide AI-powered investment analysis. It supports two analysis modes:

- **SWAN Mode** - "Sleep Well At Night" conservative analysis for retirees seeking stable dividends
- **VALUE Mode** - Value investing analysis for income investors seeking upside potential with margin of safety

## Features

- **Map-Reduce Architecture** - Parallel analysis of multiple REITs with independent mini-agents
- **Dual Data Sources** - Yahoo Finance metrics + quarterly PDF report extraction
- **PDF Extraction Pipeline** - Automated download and parsing of investor relations documents
- **Full-Text Analysis** - Latest quarter full text (~25K tokens) + LLM summaries of earlier quarters
- **Two Analysis Modes** - SWAN (conservative) and VALUE (growth) investment frameworks
- **Markdown Reports** - Professional reports with rankings, deep dives, and risk analysis

## Quick Start

### Prerequisites
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Azure OpenAI or Anthropic API access

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd reit-analysis

# Install dependencies with uv
uv sync
```

### Configuration

Create a `.env` file in the project root:

```env
# Azure OpenAI (if using)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret

# Anthropic (if using)
ANTHROPIC_API_KEY=your-api-key
```

### Running the Agent

```bash
# SWAN mode (conservative analysis) - default
uv run python reit_info_agent.py

# VALUE mode (value investing analysis)
uv run python reit_info_agent.py --mode value

# Analyze all 11 REITs with PDF data
uv run python reit_info_agent.py --mode swan --reits 11

# Non-interactive mode (skip preference prompts)
uv run python reit_info_agent.py --no-input

# Use all REITs by market cap (including those without PDFs)
uv run python reit_info_agent.py --all-reits
```

### PDF Data Pipeline

```bash
# Download quarterly PDFs for all configured REITs
uv run python pdf_downloader.py --all

# Download for a specific REIT
uv run python pdf_downloader.py C38U.SI

# Extract and cache data from PDFs
uv run python quarterly_parser.py C38U.SI

# Check cache status
uv run python data_cache.py
```

## Architecture

### Map-Reduce Pattern

```
START
  │
setup_node
  ├─ Fetch top N REITs by market cap
  ├─ Get Yahoo Finance data (price, yield, gearing, ICR, DPU history)
  ├─ Get quarterly PDF data (occupancy, WALE, tenants, rent reversion)
  └─ Pre-filter (gearing > 50% or ICR < 2.0 → excluded)
  │
fan_out_to_mini_agents [PARALLEL]
  └─ Send() spawns independent mini-agent per REIT
  │
mini_agent_node (parallel execution)
  ├─ Load mode-specific prompt (swan/value)
  ├─ Format combined Yahoo + quarterly data
  ├─ LLM analyzes and outputs structured JSON
  └─ Parse JSON result (score, qualified, rationale)
  │
reduce_node
  ├─ Filter to qualified REITs only
  ├─ Sort by score descending
  └─ Take top N
  │
report_node
  ├─ Load reduce prompt template
  ├─ LLM synthesizes individual analyses into final report
  └─ Output markdown with rankings, deep dives, exclusions
  │
END → Save to results/
```

### Key Files

| File | Purpose |
|------|---------|
| `reit_info_agent.py` | Main orchestrator - LangGraph StateGraph, fan-out/fan-in |
| `mini_agent.py` | Single REIT analyzer - receives pre-fetched data, returns JSON |
| `yahoo_finance_api.py` | Yahoo Finance interface - price, yield, metrics, DPU history |
| `quarterly_parser.py` | PDF extraction - occupancy, WALE, tenants, leverage |
| `pdf_downloader.py` | Playwright-based PDF discovery and download |
| `data_cache.py` | Caching layer with 7-day TTL and LLM summaries |
| `singapore_reits.py` | Curated S-REIT list with market cap ranking |

## Analysis Modes

### SWAN Mode (Conservative)

**Target**: Retirees seeking capital preservation and stable dividends

**Hard Requirements** (must meet ALL):
1. Tier 1 Sponsor (CapitaLand, Mapletree, Frasers, Keppel)
2. Gearing below 50%
3. Interest Coverage Ratio (ICR) above 3.0x
4. Low volatility (Beta below 0.8)
5. Stable DPU - no consecutive dividend cuts in 3 years

### VALUE Mode (Growth)

**Target**: Income investors seeking upside potential with margin of safety

**Hard Requirements** (must meet ALL):
1. P/B ratio below 0.9 (NAV discount)
2. Dividend yield above 6%
3. Gearing below 45%
4. ICR above 2.5x
5. DPU decline less than 30% over 3 years

## REITs with PDF Data

The following 11 REITs have quarterly PDF data configured:

| Ticker | Company | Sector |
|--------|---------|--------|
| C38U.SI | CapitaLand Integrated Commercial Trust | Retail/Office |
| A17U.SI | CapitaLand Ascendas REIT | Industrial/Logistics |
| N2IU.SI | Mapletree Pan Asia Commercial Trust | Commercial |
| M44U.SI | Mapletree Logistics Trust | Logistics |
| ME8U.SI | Mapletree Industrial Trust | Industrial/Data Centre |
| AJBU.SI | Keppel DC REIT | Data Centre |
| K71U.SI | Keppel REIT | Office |
| J69U.SI | Frasers Centrepoint Trust | Suburban Retail |
| BUOU.SI | Frasers Logistics & Commercial Trust | Logistics/Commercial |
| CJLU.SI | NetLink NBN Trust | Infrastructure |
| HMN.SI | CapitaLand Ascott Trust | Hospitality |

## LLM Configuration

Edit `llm_config.json` to configure the LLM provider:

```json
{
  "primary_llm": {
    "provider": "azure_openai",
    "model": null,
    "temperature": 1.0
  }
}
```

**Supported Providers**:
- `azure_openai` - Uses Azure OpenAI with Azure AD authentication
- `anthropic` - Uses Anthropic Claude API

## Sample Output

Reports are saved to `results/` directory:
- `swan_analysis_YYYYMMDD_HHMMSS.md` - SWAN mode reports
- `value_analysis_YYYYMMDD_HHMMSS.md` - VALUE mode reports

Each report includes:
- Executive Summary with top recommendations
- Individual REIT deep dives with tenant details
- REITs that did not qualify with reasons
- Appendix with raw Yahoo Finance data and DPU history

## Technical Documentation

For detailed architecture, design decisions, and development guidelines, see [CLAUDE.md](./CLAUDE.md).

## License

MIT
