# REIT Analysis Quality Improvement Plan

## 1. Architecture Overview

### Current State
```
User Input → Preference Collection → Agent Node → Tool Calls → Reflection → Report
                                         ↓
                              analyze_top_singapore_reits()
                                         ↓
                              Yahoo Finance (limited fields)
                                         ↓
                              LLM generates brief analysis
                                         ↓
                              Reflection checks specificity
                                         ↓
                              Single markdown report
```

**Current Limitations:**
- Yahoo Finance extraction uses only ~10 fields (misses analyst ratings, business summary, etc.)
- Web search exists but is ineffective (2 vague queries, no source prioritization)
- All REITs get same depth of analysis (brief rationales)
- No exemplar to guide quality

### Target State
```
Stage 1 (Ranking):
  User Input → Agent → Yahoo Finance (expanded: 30+ fields)
                            ↓
              LLM ranks into SWAN / Value / Red Flags
                            ↓
              Brief rationales per REIT
                            ↓
              Select top N SWAN + top N Value for Stage 2

Stage 2 (Deep-Dive) - for each selected REIT:
  Yahoo Finance (full data) + Smart Web Search (3-tier)
                            ↓
              Structured extraction → JSON
                            ↓
              Exemplar-guided generation (9 sections)
                            ↓
              Reflection against exemplar quality
                            ↓
              Individual deep-dive markdown file

Final Assembly:
  ranking_summary.md + deep-dive-*.md → full-report.md
```

---

## 2. Stage 1: Ranking (Detailed)

### 2.1 Purpose
Analyze all Singapore REITs and categorize into SWAN, Value, and Red Flags lists with brief rationales. Select top N from SWAN and Value for Stage 2 deep-dives.

### 2.2 Input
- User preferences (risk tolerance: conservative/moderate)
- `--deep-dive-count N` CLI argument (default: 2)

### 2.3 Yahoo Finance Data Extraction

#### Currently Extracted (NO CHANGE):
| Field | Source | Usage |
|-------|--------|-------|
| `ticker` | Input parameter | Identifier |
| `company_name` | `info['longName']` | Display name |
| `current_price` | `info['currentPrice']` or `info['regularMarketPrice']` | Valuation |
| `market_cap` | `info['marketCap']` | Size ranking |
| `price_to_book` | `info['priceToBook']` | Valuation metric |
| `gearing_ratio` | Calculated: `info['totalDebt'] / info['totalAssets']` | Safety metric |
| `icr` | Calculated: `financials['EBIT'] / abs(financials['Interest Expense'])` | Safety metric |
| `dividend_history` | `stock.dividends` resampled by year (last 5 years) | Income analysis |
| `current_year_dividend_yield` | Calculated from latest annual dividend / price | Income metric |
| `ytd_performance` | Calculated from `stock.history(period='ytd')` | Momentum |

#### NEW Fields to Extract (CHANGE):
| Field | Source | Usage |
|-------|--------|-------|
| `analyst_rating` | `info['averageAnalystRating']` | e.g., "1.7 - Buy" |
| `recommendation_key` | `info['recommendationKey']` | "buy", "hold", "sell" |
| `recommendation_mean` | `info['recommendationMean']` | 1.0-5.0 scale |
| `num_analyst_opinions` | `info['numberOfAnalystOpinions']` | Coverage depth |
| `target_price_mean` | `info['targetMeanPrice']` | Analyst target |
| `target_price_high` | `info['targetHighPrice']` | Upside potential |
| `target_price_low` | `info['targetLowPrice']` | Downside risk |
| `business_summary` | `info['longBusinessSummary']` | Contains: property count, portfolio value, geography, sponsor |
| `sector` | `info['sector']` | e.g., "Real Estate" |
| `industry` | `info['industry']` | e.g., "REIT - Industrial" |
| `website` | `info['website']` | Used in Stage 2 for smart search |
| `company_officers` | `info['companyOfficers']` | CEO, CFO names |
| `debt_to_equity` | `info['debtToEquity']` | Alternative leverage metric |
| `current_ratio` | `info['currentRatio']` | Liquidity |
| `quick_ratio` | `info['quickRatio']` | Liquidity |
| `return_on_assets` | `info['returnOnAssets']` | Profitability |
| `return_on_equity` | `info['returnOnEquity']` | Profitability |
| `revenue_growth` | `info['revenueGrowth']` | Growth metric |
| `earnings_growth` | `info['earningsGrowth']` | Growth metric |
| `payout_ratio` | `info['payoutRatio']` | Dividend sustainability |
| `beta` | `info['beta']` | Volatility measure |
| `free_cashflow` | `info['freeCashflow']` | Cash generation |
| `operating_cashflow` | `info['operatingCashflow']` | Cash generation |
| `held_percent_insiders` | `info['heldPercentInsiders']` | Alignment |
| `held_percent_institutions` | `info['heldPercentInstitutions']` | Institutional confidence |
| `five_year_avg_dividend_yield` | `info['fiveYearAvgDividendYield']` | Yield stability |
| `fifty_two_week_high` | `info['fiftyTwoWeekHigh']` | Range context |
| `fifty_two_week_low` | `info['fiftyTwoWeekLow']` | Range context |
| `fifty_two_week_change` | `info['fiftyTwoWeekChange']` | 1-year performance |

### 2.4 Web Search in Stage 1
**None.** Stage 1 uses Yahoo Finance data only. Web search is reserved for Stage 2 deep-dives.

### 2.5 LLM Analysis Prompt

**Current prompt location:** `prompts/reit_audit_prompt.txt`

**Changes to prompt:**
1. Add instruction to use new analyst rating fields
2. Add instruction to extract sponsor name from `business_summary`
3. Add instruction to rank REITs within each category (SWAN, Value)

**Prompt additions:**
```
## Additional Data Available

You now have access to these additional fields per REIT:
- Analyst consensus: {analyst_rating}, {recommendation_key}, {num_analyst_opinions} analysts
- Price targets: Mean ${target_price_mean}, High ${target_price_high}, Low ${target_price_low}
- Business summary (extract sponsor name and property count from this)
- Financial ratios: ROA {return_on_assets}, ROE {return_on_equity}
- Growth: Revenue {revenue_growth}, Earnings {earnings_growth}
- Liquidity: Current ratio {current_ratio}, Quick ratio {quick_ratio}
- Ownership: Insiders {held_percent_insiders}%, Institutions {held_percent_institutions}%

## Ranking Requirement

Within each category (SWAN, Value), rank the REITs from best to worst.
The top {deep_dive_count} from SWAN and top {deep_dive_count} from Value will receive detailed analysis.
```

### 2.6 Reflection in Stage 1
**No change** from current reflection prompt. Checks for:
- Specific tenant names (not generic phrases)
- Actual DPU figures
- Professional prose
- Sponsor tier classification

### 2.7 Stage 1 Output

**Format:** Intermediate markdown with ranked lists

```markdown
## SWAN List (Sleep Well At Night)
Ranked by overall suitability for conservative retirees:

| Rank | REIT | Ticker | Yield | Gearing | ICR | Analyst Rating | Key Strength |
|------|------|--------|-------|---------|-----|----------------|--------------|
| 1 | Parkway Life REIT | C2PU.SI | 4.2% | 35.1% | 8.2x | 1.8 - Buy | Healthcare moat |
| 2 | ... | ... | ... | ... | ... | ... | ... |

### 1. Parkway Life REIT (C2PU.SI) - SELECTED FOR DEEP-DIVE
{2-3 paragraph brief rationale}

### 2. ...

---

## Value List
Ranked by upside potential with acceptable risk:

| Rank | REIT | Ticker | P/B | Yield | Discount to NAV | Analyst Rating | Key Opportunity |
|------|------|--------|-----|-------|-----------------|----------------|-----------------|
| 1 | ... | ... | ... | ... | ... | ... | ... |

### 1. {REIT Name} - SELECTED FOR DEEP-DIVE
{2-3 paragraph brief rationale}

---

## Red Flags (Avoid)
{Table and brief rationales - no ranking needed}
```

### 2.8 Selection for Stage 2

After Stage 1 completes:
1. Parse SWAN list, take top N tickers
2. Parse Value list, take top N tickers
3. Pass these 2N tickers to Stage 2

---

## 3. Stage 2: Deep-Dive (Detailed)

### 3.1 Purpose
Generate comprehensive 4-5 page analysis for each selected REIT, matching the quality and structure of the exemplar report.

### 3.2 Input
- List of tickers from Stage 1 (top N SWAN + top N Value)
- Exemplar section files
- Yahoo Finance data (already fetched in Stage 1, reuse)

### 3.3 Process Flow (Per REIT)

```
For each ticker in selected_reits:
    Step 1: Retrieve Yahoo Finance data (from Stage 1 cache)
    Step 2: Execute smart web search (3-tier)
    Step 3: Extract structured data from search results
    Step 4: Load exemplar sections
    Step 5: Generate deep-dive analysis
    Step 6: Reflect against exemplar quality
    Step 7: If rejected, retry with feedback (max 2 retries)
    Step 8: Save individual markdown file
```

### 3.4 Step 1: Yahoo Finance Data

Reuse data from Stage 1. No additional API calls needed.

Data available:
- All fields from Section 2.3 (current + new)
- Formatted for LLM consumption

### 3.5 Step 2: Smart Web Search (3-Tier)

#### Tier 1: Official Company Sources

**Source Discovery:**
```python
website = yahoo_data['website']  # e.g., "https://www.frasersproperty.com/reits/flct"
domain = extract_domain(website)  # e.g., "frasersproperty.com"
company_name = yahoo_data['company_name']
ticker = yahoo_data['ticker']
```

**Queries (execute all 4):**
```
Query 1.1: site:{domain} quarterly results 2025
Query 1.2: site:{domain} investor presentation
Query 1.3: site:{domain} annual report 2024
Query 1.4: site:{domain} "{company_name}" DPU distribution
```

**Per query:**
- Max results: 3
- Fetch full page content for top 2 results
- Max content per page: 8000 characters

#### Tier 2: SGX Filings

**Queries (execute 2):**
```
Query 2.1: site:sgx.com "{company_name}" announcement
Query 2.2: site:links.sgx.com "{ticker}" OR "{company_name}"
```

**Per query:**
- Max results: 3
- Fetch full page content for top 2 results
- Max content per page: 8000 characters

#### Tier 3: Business News

**Queries (execute 3):**
```
Query 3.1: "{company_name}" quarterly results site:businesstimes.com.sg
Query 3.2: "{company_name}" site:theedgesingapore.com
Query 3.3: "{company_name}" REIT analysis site:straitstimes.com
```

**Per query:**
- Max results: 2
- Fetch full page content for top 1 result
- Max content per page: 6000 characters

#### Total Search Volume
- Tier 1: 4 queries × 2 pages = up to 8 pages fetched
- Tier 2: 2 queries × 2 pages = up to 4 pages fetched
- Tier 3: 3 queries × 1 page = up to 3 pages fetched
- **Total: up to 15 pages per REIT**

### 3.6 Step 3: Structured Extraction

**LLM Call:** Pass all fetched page content to LLM with extraction prompt.

**Extraction Prompt:**
```
Extract structured data from the following web search results for {company_name} ({ticker}).

Only extract information that is EXPLICITLY stated in the sources.
If a field is not found, set it to null.
Do not infer or calculate values not directly stated.

Return valid JSON matching this schema:

{
  "tenants": [
    {
      "name": "string - tenant company name",
      "percentage_nla": "number or null - % of Net Lettable Area",
      "percentage_gri": "number or null - % of Gross Rental Income",
      "sector": "string - e.g., Supermarket, F&B, Healthcare"
    }
  ],
  "top_assets": [
    {
      "name": "string - property name",
      "location": "string - area/district",
      "nla_sqft": "number or null",
      "type": "string - Retail, Office, Industrial, etc.",
      "occupancy_percent": "number or null"
    }
  ],
  "portfolio_metrics": {
    "total_properties": "number or null",
    "total_valuation_billions": "number or null",
    "portfolio_occupancy_percent": "number or null",
    "wale_years": "number or null - Weighted Average Lease Expiry",
    "rental_reversion_percent": "number or null - latest reported"
  },
  "capital_management": {
    "hedging_percent": "number or null - % of debt hedged to fixed rate",
    "avg_cost_of_debt_percent": "number or null",
    "debt_maturity_profile": "string or null - description of maturity spread"
  },
  "sponsor": {
    "name": "string",
    "stake_percent": "number or null - sponsor's ownership stake"
  },
  "recent_developments": [
    "string - acquisition, divestment, AEI, or other material event"
  ],
  "aei_projects": [
    {
      "asset": "string - property name",
      "cost_millions": "number or null",
      "completion_date": "string or null",
      "expected_roi_percent": "number or null"
    }
  ],
  "quarterly_highlights": {
    "latest_quarter": "string - e.g., Q4 FY2025",
    "revenue_millions": "number or null",
    "revenue_growth_yoy_percent": "number or null",
    "npi_millions": "number or null",
    "npi_growth_yoy_percent": "number or null",
    "dpu_cents": "number or null",
    "dpu_growth_yoy_percent": "number or null",
    "management_outlook": "string or null - key commentary"
  },
  "sources_used": ["list of URLs where data was found"]
}

WEB SEARCH RESULTS:
{concatenated_page_contents}
```

**Output:** Structured JSON saved for use in generation.

### 3.7 Step 4: Load Exemplar Sections

**Exemplar Files Location:** `prompts/exemplars/`

| File | Section Title | Key Elements |
|------|---------------|--------------|
| `01_sponsor_analysis.md` | Corporate Structure and Sponsor Analysis | Sponsor name, ROFR, governance, ESG ratings |
| `02_portfolio_analysis.md` | Portfolio Analysis: The Suburban Moat | Asset table, geographic strategy, transport integration |
| `03_financial_performance.md` | Financial Performance: The Income Engine | Revenue/NPI trends, 10-year DPU table, variance analysis |
| `04_capital_management.md` | Capital Management: The Balance Sheet | Gearing, ICR, hedging, debt maturity chart |
| `05_operational_resilience.md` | Operational Resilience and Tenant Analysis | Occupancy, rental reversions, tenant concentration |
| `06_growth_vectors.md` | Strategic Growth Vectors | AEIs, regional connectivity, pipeline |
| `07_risk_analysis.md` | Risk Analysis | Interest rate, recession, supply risks |
| `08_valuation.md` | Valuation and Comparative Analysis | P/NAV, peer comparison, yield gap |
| `09_conclusion.md` | Conclusion and Recommendation | Verdict, allocation advice, rating |

**Load all 9 files and concatenate for prompt injection.**

### 3.8 Step 5: Generate Deep-Dive Analysis

**Generation Prompt:**
```
You are a senior Portfolio Manager generating a comprehensive investment analysis
for {company_name} ({ticker}) for conservative retirees.

## QUANTITATIVE DATA (from Yahoo Finance)

Company: {company_name}
Ticker: {ticker}
Current Price: ${current_price} SGD
Market Cap: ${market_cap_billions}B SGD
Price-to-Book: {price_to_book}
Gearing Ratio: {gearing_ratio_percent}%
Interest Coverage Ratio: {icr}x
Debt-to-Equity: {debt_to_equity}%
Current Ratio: {current_ratio}
Beta: {beta}

Dividend History:
{formatted_dividend_history_table}

5-Year Avg Dividend Yield: {five_year_avg_dividend_yield}%
Payout Ratio: {payout_ratio}%

YTD Performance: {ytd_performance}%
52-Week Range: ${fifty_two_week_low} - ${fifty_two_week_high}
52-Week Change: {fifty_two_week_change}%

Analyst Consensus: {analyst_rating} ({num_analyst_opinions} analysts)
Price Targets: Low ${target_price_low}, Mean ${target_price_mean}, High ${target_price_high}

ROA: {return_on_assets}%
ROE: {return_on_equity}%
Revenue Growth: {revenue_growth}%
Earnings Growth: {earnings_growth}%

Free Cash Flow: ${free_cashflow_millions}M
Operating Cash Flow: ${operating_cashflow_millions}M

Insider Ownership: {held_percent_insiders}%
Institutional Ownership: {held_percent_institutions}%

Business Summary:
{business_summary}

## QUALITATIVE DATA (from Web Search)

{structured_extraction_json_formatted}

## EXEMPLAR - Follow this structure, depth, and tone EXACTLY:

{all_9_exemplar_sections_concatenated}

---

## INSTRUCTIONS

Generate a comprehensive analysis for {company_name} following the exemplar's:

1. STRUCTURE: Use all 9 sections with the same headings
2. DEPTH: Each section should be comparable in length and detail to the exemplar
3. TABLES: Include tables where the exemplar has them:
   - Asset snapshot table (Section 2)
   - DPU history table (Section 3)
4. SPECIFICITY: Use actual data from above - specific tenant names, exact percentages, real figures
5. TONE: Professional, retiree-focused, balanced (acknowledge both strengths and risks)
6. CITATIONS: Reference data sources where available

CRITICAL RULES:
- Use ONLY data provided above. Do not hallucinate tenant names, figures, or facts.
- If data for a section is unavailable, state "Data not available" rather than inventing.
- Every claim should be traceable to either Yahoo Finance data or Web Search results.
```

### 3.9 Step 6: Reflection Against Exemplar

**Reflection Prompt:**
```
You are evaluating a REIT analysis against exemplar quality standards.

## EXEMPLAR QUALITY STANDARDS (reference):
{exemplar_sections_summary}

## ANALYSIS TO EVALUATE:
{generated_analysis}

## EVALUATION CRITERIA

### 1. Structure Completeness
- [ ] Has all 9 sections?
- [ ] Section order matches exemplar?
- [ ] Each section has appropriate depth (not just 1-2 sentences)?

### 2. Specificity (CRITICAL - Auto-reject if missing)
- [ ] Names specific tenants with percentages (not "diversified tenants")?
- [ ] Lists actual asset names with locations?
- [ ] Includes specific DPU figures with year-over-year context?
- [ ] States exact occupancy rate?
- [ ] Mentions specific gearing/ICR numbers?

### 3. Tables Present
- [ ] Asset snapshot table with columns: Asset, Location, NLA, Key Characteristics?
- [ ] DPU history table with at least 5 years?

### 4. Analytical Depth
- [ ] Explains "WHY" not just "WHAT"?
- [ ] Compares to peers where relevant?
- [ ] Discusses risks with mitigations?
- [ ] Provides retiree-specific context?

### 5. Professional Tone
- [ ] Full sentences (not bullet shorthand)?
- [ ] Balanced view (strengths AND weaknesses)?
- [ ] Clear recommendation with rating?

## RESPONSE FORMAT

Return JSON:
{
  "approved": true/false,
  "quality_score": 1-10,
  "section_scores": {
    "sponsor_analysis": 1-10,
    "portfolio_analysis": 1-10,
    "financial_performance": 1-10,
    "capital_management": 1-10,
    "operational_resilience": 1-10,
    "growth_vectors": 1-10,
    "risk_analysis": 1-10,
    "valuation": 1-10,
    "conclusion": 1-10
  },
  "critical_failures": ["list of auto-reject issues"],
  "missing_elements": ["list of other gaps"],
  "feedback": "Specific instructions for improvement"
}

APPROVAL RULES:
- Any critical failure (specificity issues) = rejected regardless of score
- Quality score < 7 = rejected
- All sections must score >= 6
```

### 3.10 Step 7: Retry Logic

```python
max_retries = 2
retry_count = 0

while not approved and retry_count < max_retries:
    if retry_count > 0:
        # Add reflection feedback to generation prompt
        generation_prompt += f"""

## PREVIOUS ATTEMPT REJECTED

Feedback: {reflection_feedback}
Critical failures: {critical_failures}

Address ALL issues above in your revised analysis.
"""

    analysis = generate_deep_dive(generation_prompt)
    reflection_result = reflect_on_analysis(analysis)

    if reflection_result['approved']:
        approved = True
    else:
        retry_count += 1
        reflection_feedback = reflection_result['feedback']
        critical_failures = reflection_result['critical_failures']

if not approved:
    # Auto-approve after max retries with warning
    analysis += "\n\n---\n*Note: This analysis may have quality gaps. Manual review recommended.*"
```

### 3.11 Step 8: Save Individual File

**Output Location:** `intermediate/deep-dive-{ticker}.md`

**File Format:**
```markdown
# {Company Name}: Comprehensive Investment Analysis

*Generated: {timestamp}*
*Data Sources: Yahoo Finance, {list of web sources used}*

---

## 1. Corporate Structure and Sponsor Analysis
{section_content}

## 2. Portfolio Analysis
{section_content}

... (all 9 sections)

---

## Sources
{list of URLs from structured extraction}
```

---

## 4. Final Assembly

### 4.1 Process

After all deep-dives complete:

```python
# Load Stage 1 output
ranking_content = read_file("intermediate/ranking_summary.md")

# Load all deep-dive files
deep_dives = []
for ticker in selected_reits:
    content = read_file(f"intermediate/deep-dive-{ticker}.md")
    deep_dives.append(content)

# Combine into final report
final_report = f"""
# Singapore REIT Analysis Report

*Generated: {timestamp}*
*Analysis by: AI Portfolio Manager*

---

## Executive Summary

{generate_executive_summary(ranking_content, deep_dives)}

---

# Part 1: Market Overview & Rankings

{ranking_content}

---

# Part 2: Deep-Dive Analyses

{"---".join(deep_dives)}

---

## Disclaimer

This analysis is generated by AI for educational purposes only.
Not financial advice. Consult a licensed financial advisor before investing.
"""

# Save final report
save_file(f"reit_analysis_{timestamp}.md", final_report)
```

### 4.2 Executive Summary Generation

**Prompt:**
```
Generate a 200-word executive summary for this REIT analysis report.

Top SWAN picks: {swan_list}
Top Value picks: {value_list}

Include:
1. Current market environment for S-REITs (1-2 sentences)
2. Top recommendations with one-line rationale each
3. Key themes/observations across the analysis
4. Risk factors investors should monitor

Tone: Professional, confident but balanced.
```

---

## 5. Files to Modify/Create

### 5.1 Files to Modify

| File | Changes |
|------|---------|
| `yahoo_finance_api.py` | Add 25+ new fields to `get_reit_data_structured()` |
| `tools.py` | Rewrite `search_reit_qualitative_info()` with 3-tier search, add `extract_structured_data()` |
| `nodes.py` | Add `deep_dive_node()`, `deep_dive_reflection_node()`, update graph routing |
| `reit_info_agent.py` | Add CLI flag, two-stage orchestration, file assembly |
| `state.py` | Add `selected_for_deep_dive`, `deep_dive_results` fields |
| `prompts/reit_audit_prompt.txt` | Add instructions for new fields, ranking requirement |
| `prompts/reflection_prompt.txt` | Minor updates for Stage 1 reflection |

### 5.2 Files to Create

| File | Purpose |
|------|---------|
| `prompts/exemplars/01_sponsor_analysis.md` | Exemplar section 1 |
| `prompts/exemplars/02_portfolio_analysis.md` | Exemplar section 2 |
| `prompts/exemplars/03_financial_performance.md` | Exemplar section 3 |
| `prompts/exemplars/04_capital_management.md` | Exemplar section 4 |
| `prompts/exemplars/05_operational_resilience.md` | Exemplar section 5 |
| `prompts/exemplars/06_growth_vectors.md` | Exemplar section 6 |
| `prompts/exemplars/07_risk_analysis.md` | Exemplar section 7 |
| `prompts/exemplars/08_valuation.md` | Exemplar section 8 |
| `prompts/exemplars/09_conclusion.md` | Exemplar section 9 |
| `prompts/deep_dive_generation_prompt.txt` | Stage 2 generation template |
| `prompts/deep_dive_reflection_prompt.txt` | Stage 2 reflection criteria |
| `prompts/extraction_prompt.txt` | Structured data extraction template |

---

## 6. CLI Interface

```bash
# Stage 1 only (current behavior, but with expanded Yahoo Finance fields)
python3 reit_info_agent.py

# Stage 1 + Stage 2 with 2 deep-dives per category
python3 reit_info_agent.py --deep-dive-count 2

# Stage 1 + Stage 2 with 3 deep-dives per category
python3 reit_info_agent.py --deep-dive-count 3

# Stage 1 + Stage 2 with custom output directory
python3 reit_info_agent.py --deep-dive-count 2 --output-dir ./reports
```

---

## 7. Iteration Plan

### Iteration 1: Expand Yahoo Finance Extraction
**Scope:** Update `yahoo_finance_api.py` only
- Add all 25+ new fields to `get_reit_data_structured()`
- Update `get_reit_info()` to format new fields for LLM
- Test on 3 sample REITs (BUOU.SI, C38U.SI, J69U.SI)
- **No workflow changes**

### Iteration 2: Create Exemplar Files
**Scope:** Create prompt files only
- Split FCT exemplar into 9 section files
- Create `prompts/exemplars/` directory structure
- Create `prompts/deep_dive_generation_prompt.txt`
- Create `prompts/deep_dive_reflection_prompt.txt`
- Create `prompts/extraction_prompt.txt`
- **No code changes**

### Iteration 3: Rewrite Web Search
**Scope:** Update `tools.py` only
- Implement 3-tier source discovery
- Implement structured extraction function
- Test search on 2 sample REITs
- **No workflow changes**

### Iteration 4: Implement Stage 2 Workflow
**Scope:** Update `nodes.py`, `state.py`, `reit_info_agent.py`
- Add `--deep-dive-count` CLI flag
- Add deep-dive generation node
- Add exemplar-based reflection node
- Wire up two-stage workflow
- Test with `--deep-dive-count 1`

### Iteration 5: Output Assembly & Polish
**Scope:** Final integration
- Implement file combination logic
- Add executive summary generation
- End-to-end testing with `--deep-dive-count 2`
- Fix edge cases and error handling

---

## 8. Verification Plan

### Per-Iteration Tests

| Iteration | Test |
|-----------|------|
| 1 | Run `get_reit_data_structured('BUOU.SI')` and verify all 35+ fields populated |
| 2 | Manually review exemplar files match original FCT report structure |
| 3 | Run search on J69U.SI, verify results from all 3 tiers, verify JSON extraction valid |
| 4 | Run `--deep-dive-count 1`, verify deep-dive file generated, verify reflection runs |
| 5 | Run `--deep-dive-count 2`, verify final report combines all sections correctly |

### End-to-End Quality Check
1. Compare generated deep-dive against FCT exemplar manually
2. Verify tenant names, occupancy rates are factual (cross-check with sources)
3. Verify tables are properly formatted
4. Verify reflection correctly rejects low-quality output (test with bad input)

---

## 9. Success Criteria

1. Stage 1 produces ranked SWAN/Value/Red Flags lists with expanded metrics
2. Stage 2 deep-dives have all 9 sections matching exemplar structure
3. Deep-dives contain specific tenant names (not generic phrases)
4. Deep-dives contain actual numbers with sources
5. Deep-dives include formatted tables (assets, DPU history)
6. Reflection successfully rejects low-quality output
7. Final combined report is well-formatted and readable
8. End-to-end run completes without errors in < 10 minutes
9. Generated facts are verifiable against cited sources
