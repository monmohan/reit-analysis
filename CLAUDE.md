# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

A **Singapore REIT Analysis Agent** using LangGraph Map-Reduce architecture. It combines Yahoo Finance data with quarterly PDF report extraction to provide AI-powered investment analysis using two strategies:

- **SWAN Mode**: "Sleep Well At Night" conservative analysis for retirees seeking stable dividends
- **VALUE Mode**: Value investing analysis for income investors seeking upside potential

## Development Commands

### Environment Setup
```bash
# Install dependencies (requires uv: https://docs.astral.sh/uv/)
uv sync
```

### Running the Agent
```bash
# SWAN mode (default) - conservative analysis
uv run python reit_info_agent.py

# VALUE mode - value investing analysis
uv run python reit_info_agent.py --mode value

# Custom parameters
uv run python reit_info_agent.py --mode swan --top 5 --reits 15

# Non-interactive mode (skip user preference prompts)
uv run python reit_info_agent.py --no-input
```

### PDF Data Pipeline
```bash
# Download quarterly PDFs for all REITs
uv run python pdf_downloader.py --all

# Download for single REIT
uv run python pdf_downloader.py C38U.SI

# Extract data from PDFs
uv run python quarterly_parser.py C38U.SI

# Check cache status
uv run python data_cache.py

# Discover new REIT IR URLs
uv run python tools/research_ir_urls.py C38U.SI
```

### Testing
```bash
# Parser tests
uv run python test_quarterly_parser.py

# Component tests
uv run python test_reit_components.py
```

## Architecture Overview

### Map-Reduce Agent Pattern

```
START
  ↓
setup_node
  ├→ Fetch top N REITs by market cap
  ├→ Get Yahoo Finance data (price, yield, gearing, ICR, DPU history)
  ├→ Get quarterly PDF data (occupancy, WALE, tenants, rent reversion)
  └→ Pre-filter (gearing > 50% or ICR < 2.0 → excluded)
  ↓
fan_out_to_mini_agents [PARALLEL]
  └→ Send() spawns independent mini-agent per REIT
  ↓
mini_agent_node (parallel execution)
  ├→ Load mode-specific prompt (swan/value)
  ├→ Format combined Yahoo + quarterly data
  ├→ LLM analyzes and outputs structured JSON
  └→ Parse JSON result (swan_score/value_score, qualified, rationale)
  ↓
reduce_node
  ├→ Filter to qualified REITs only
  ├→ Sort by score descending
  └→ Take top N
  ↓
report_node
  ├→ Load reduce prompt template
  ├→ LLM synthesizes individual analyses into final report
  └→ Output markdown with rankings, deep dives, exclusions
  ↓
END → Save to results/
```

### Key Files

| File | Purpose |
|------|---------|
| `reit_info_agent.py` | Main orchestrator - LangGraph StateGraph, fan-out/fan-in |
| `mini_agent.py` | Single REIT analyzer - stateless, receives pre-fetched data |
| `yahoo_finance_api.py` | Yahoo Finance interface - price, yield, metrics, DPU history |
| `quarterly_parser.py` | PDF extraction - occupancy, WALE, tenants, leverage, full text |
| `pdf_downloader.py` | Playwright-based PDF discovery and download |
| `data_cache.py` | Caching layer with 7-day TTL + LLM summary generation |
| `singapore_reits.py` | Curated list of 24 S-REITs with market cap ranking |
| `tools.py` | Tool definitions (get_reit_info, analyze_top_reits, search_qualitative) |
| `llm/llm_factory.py` | LLM factory - Azure OpenAI / Anthropic Claude |

### Directory Structure

```
├── config/
│   ├── llm_config.py        # LLM configuration loader
│   └── reit_ir_urls.json    # REIT IR URLs and PDF patterns
├── data/
│   ├── pdf_cache/{ticker}/  # Downloaded quarterly PDFs
│   └── extracted_data/      # Cached JSON extractions (7-day TTL)
├── llm/
│   └── llm_factory.py       # LLM provider factory
├── prompts/
│   ├── swan_single_reit_prompt.txt   # SWAN individual analysis
│   ├── swan_reduce_prompt.txt        # SWAN report synthesis
│   ├── value_single_reit_prompt.txt  # VALUE individual analysis
│   └── value_reduce_prompt.txt       # VALUE report synthesis
├── tools/
│   └── research_ir_urls.py  # IR URL discovery utility
└── results/                 # Generated reports
```

## Analysis Modes

### SWAN Mode (Conservative)

**Target Investor**: Retirees seeking capital preservation and stable dividends

**Hard Requirements** (must meet ALL):
1. Tier 1 Sponsor (CapitaLand, Mapletree, Frasers, Keppel)
2. Gearing below 50%
3. Interest Coverage Ratio (ICR) above 3.0x
4. Low volatility (Beta below 0.8)
5. Stable DPU - no consecutive dividend cuts in 3 years

**Scoring Enhancers**: Essential tenants, occupancy > 95%, WALE > 3 years, positive rent reversion

### VALUE Mode (Growth)

**Target Investor**: Income investors seeking upside potential with margin of safety

**Hard Requirements** (must meet ALL):
1. P/B ratio below 0.9 (NAV discount)
2. Dividend yield above 6%
3. Gearing below 45%
4. ICR above 2.5x
5. DPU decline less than 30% over 3 years

**Scoring Enhancers**: Deep P/B discount (< 0.75), yield > 7.5%, improving occupancy, analyst upside

## PDF Data Pipeline

### 1. Discovery (`tools/research_ir_urls.py`)
- Uses Playwright to navigate REIT investor relations pages
- Identifies quarterly report PDF patterns
- Generates regex for automated matching
- Saves configuration to `config/reit_ir_urls.json`

### 2. Download (`pdf_downloader.py`)
- Reads IR URLs from config
- Discovers PDFs matching quarterly patterns
- Resolves SGX tracker.pl redirect URLs
- Parallel download (4 workers)
- Caches to `data/pdf_cache/{ticker}/`

### 3. Extraction (`quarterly_parser.py`)
Extracts structured data from PDFs:
- Occupancy rates (portfolio, office, retail)
- WALE (Weighted Average Lease Expiry)
- Top 10 tenants with sector and contribution %
- Rent reversion by segment
- Leverage (aggregate gearing)
- Cost of debt
- Full PDF text (`full_text`) for deep qualitative analysis

### 4. Caching (`data_cache.py`)
- 7-day TTL on extracted data
- Auto-refresh on stale cache
- Graceful fallback when PDFs unavailable

## Deep Analysis Architecture

### Full Text + Summaries Approach

The system uses a two-stage approach for comprehensive REIT analysis:

**Stage 1: PDF Extraction** (`quarterly_parser.py`)
- Extracts structured metrics (occupancy, WALE, leverage, etc.)
- Stores complete PDF text in `full_text` field

**Stage 2: Summary Generation** (`data_cache.py`)
- Latest quarter: Full text passed directly to LLM (~25K tokens)
- Earlier quarters: LLM generates 500-700 word summaries (~2K tokens each)
- Uses fast/cheap model for summary generation

**Data Formatting** (`mini_agent.py`)
- `format_full_plus_summaries()` combines:
  - Full report text for latest quarter (deep qualitative analysis)
  - LLM-generated summaries for earlier quarters (trend context)
  - Structured metrics table for quantitative comparison

### Token Budget

| Quarter | Content Type | Token Budget |
|---------|--------------|--------------|
| Latest (Q0) | Full PDF text | ~25K |
| Q-1 | LLM summary | ~2K |
| Q-2 | LLM summary | ~2K |
| Q-3 | LLM summary | ~2K |
| **Total per REIT** | | **~31K** |

## Configuration

### LLM Configuration (`llm_config.json`)
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
- `azure_openai` - Uses AZURE_OPENAI_* env vars + Azure AD auth
- `anthropic` - Uses ANTHROPIC_API_KEY env var

### Environment Variables (`.env`)
```
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
```

## Design Principles

### Division of Labor
- **Python handles**: Data fetching, arithmetic, market cap ranking, PDF extraction (deterministic)
- **LLM handles**: Qualitative analysis, risk assessment, investment recommendations (creative/nuanced)

### Key Patterns
- **Map-Reduce**: Parallel mini-agents for scalable analysis
- **Data Pre-fetching**: All data fetched before LLM analysis (no runtime tool calls)
- **External Prompts**: Behavior modification without code changes
- **Robust JSON Parsing**: Multi-stage extraction with control character sanitization
- **Graceful Degradation**: Missing quarterly data → analysis continues with Yahoo only
- **Full Text + Summaries**: Deep analysis of latest quarter with full PDF text, LLM-generated summaries for earlier quarters (trend context)
