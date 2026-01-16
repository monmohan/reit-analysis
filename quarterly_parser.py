#!/usr/bin/env python3
"""
Quarterly Report Parser

Extracts structured data from REIT quarterly reports using pdfplumber.
Focuses on operational metrics and market analysis sections.

Usage:
    uv run python quarterly_parser.py C38U.SI
    uv run python quarterly_parser.py --all
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

import pdfplumber


# Paths
CONFIG_PATH = Path(__file__).parent / "config" / "reit_ir_urls.json"
CACHE_DIR = Path(__file__).parent / "data" / "pdf_cache"
EXTRACTED_DIR = Path(__file__).parent / "data" / "extracted_data"


def load_config() -> dict:
    """Load the REIT IR URLs config."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    with open(CONFIG_PATH) as f:
        return json.load(f)


def extract_report_date(text: str) -> Optional[str]:
    """Extract report date from quarterly report text."""
    # Look for patterns like "30 September 2025" or "as at 30 Sep 2025"
    patterns = [
        r"(?:as at|As at|As At)\s+(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def extract_quarter_label(text: str) -> Optional[str]:
    """Extract quarter label like '3Q 2025' or '1H 2025'."""
    patterns = [
        r"([1-4]Q\s*\d{4})",  # 3Q 2025
        r"([12]H\s*\d{4})",   # 1H 2025
        r"(Q[1-4]\s*\d{4})",  # Q3 2025
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def extract_percentage(text: str, keyword: str, context_window: int = 100) -> Optional[float]:
    """Extract a percentage value near a keyword."""
    # Find keyword position
    keyword_lower = keyword.lower()
    text_lower = text.lower()
    pos = text_lower.find(keyword_lower)
    if pos == -1:
        return None

    # Get context around keyword
    start = max(0, pos - context_window)
    end = min(len(text), pos + len(keyword) + context_window)
    context = text[start:end]

    # Look for percentage patterns
    patterns = [
        r"(\d{1,3}\.?\d*)\s*%",  # 97.2%
        r"(\d{1,3}\.?\d*)\s*ppts?",  # 1.3 ppts
    ]
    for pattern in patterns:
        matches = re.findall(pattern, context)
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                continue
    return None


def extract_occupancy(text: str) -> dict:
    """Extract occupancy rates by segment."""
    result = {}

    # Look for "Portfolio Occupancy" followed by high percentage (90-100%)
    # CICT format: "Portfolio Occupancy 97.2%"
    portfolio_patterns = [
        r"Portfolio\s*Occupancy\s*(9\d\.?\d*)\s*%",
        r"Occupancy\s*(9\d\.?\d*)\s*%.*?ppts?\s*QoQ",  # pattern with QoQ change
        r"PORTFOLIO.*?(9\d\.?\d*)\s*%",
    ]
    for pattern in portfolio_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            val = float(match.group(1))
            if 90 <= val <= 100:
                result["portfolio"] = val
                break

    # Retail occupancy - look for "RETAIL" section with 90%+ values
    retail_patterns = [
        r"RETAIL\s*(?:\d{1,2}\s+\w+\s+\d{4}\s+){0,2}(9\d\.?\d*)\s*%?\s*(9\d\.?\d*)\s*%",
        r"Retail.*?Occupancy.*?(9\d\.?\d*)\s*%",
    ]
    for pattern in retail_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            # Take the last group (latest value)
            groups = [g for g in match.groups() if g]
            if groups:
                val = float(groups[-1])
                if 90 <= val <= 100:
                    result["retail"] = val
                    break

    # Office occupancy - look for "OFFICE" section with 80-100% values (office can be lower)
    office_patterns = [
        r"OFFICE\s*(?:\d{1,2}\s+\w+\s+\d{4}\s+){0,2}(\d{2}\.?\d*)\s*%?\s*(\d{2}\.?\d*)\s*%",
        r"Office.*?Occupancy.*?(\d{2}\.?\d*)\s*%",
    ]
    for pattern in office_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            groups = [g for g in match.groups() if g]
            if groups:
                val = float(groups[-1])
                if 80 <= val <= 100:
                    result["office"] = val
                    break

    return result


def extract_wale(text: str) -> dict:
    """Extract weighted average lease expiry by segment."""
    result = {}

    # Portfolio WALE
    portfolio_match = re.search(
        r"(?:Portfolio|PORTFOLIO)\s*(?:WALE)?\s*(\d+\.?\d*)\s*(?:Years?|years?|yrs?)",
        text, re.IGNORECASE
    )
    if portfolio_match:
        result["portfolio"] = float(portfolio_match.group(1))

    # Look for WALE followed by years
    wale_match = re.search(
        r"WALE\s*(\d+\.?\d*)\s*(?:Years?|years?|yrs?)",
        text, re.IGNORECASE
    )
    if wale_match and "portfolio" not in result:
        result["portfolio"] = float(wale_match.group(1))

    return result


def extract_rent_reversion(text: str) -> dict:
    """Extract rent reversion percentages."""
    result = {}

    # CICT Highlights format:
    # "YTD Sep Rent Reversion" then
    # "Retail Portfolio" ▲ 7.8%
    # "Office Portfolio" ▲ 6.5%
    # Values are typically 0-15% for rent reversion

    # Look for Retail Portfolio followed by small percentage (reversion is typically 0-15%)
    retail_patterns = [
        r"Retail\s*Portfolio\s*[▲↑]\s*(\d{1,2}\.?\d*)\s*%",
        r"Rent\s*Reversion.*?Retail.*?(\d{1,2}\.?\d*)\s*%",
    ]
    for pattern in retail_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            val = float(match.group(1))
            # Sanity check - rent reversion typically 0-15%
            if 0 <= val <= 20:
                result["retail"] = val
                break

    # Look for Office Portfolio with similar range
    office_patterns = [
        r"Office\s*Portfolio\s*[▲↑]\s*(\d{1,2}\.?\d*)\s*%",
        r"Rent\s*Reversion.*?Office.*?(\d{1,2}\.?\d*)\s*%",
    ]
    for pattern in office_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            val = float(match.group(1))
            if 0 <= val <= 20:
                result["office"] = val
                break

    return result


def extract_leverage(text: str) -> Optional[float]:
    """Extract aggregate leverage percentage."""
    patterns = [
        # CICT format: "Aggregate Leverage 39.2%"
        r"Aggregate\s*Leverage\d?\s*(\d{2,3}\.?\d*)\s*%",
        r"Aggregate\s*Leverage\s*(\d{2,3}\.?\d*)\s*%",
        r"Leverage\s*(\d{2,3}\.?\d*)\s*%",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            # Sanity check - leverage typically between 30-50%
            if 20 <= val <= 60:
                return val
    return None


def extract_cost_of_debt(text: str) -> Optional[float]:
    """Extract average cost of debt."""
    patterns = [
        # CICT format: "Average Cost of Debt 3.3%"
        r"Average\s*Cost\s*of\s*Debt\d?\s*(\d+\.?\d*)\s*%",
        r"Cost\s*of\s*Debt\s*(\d+\.?\d*)\s*%",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            # Sanity check - cost of debt typically 2-6%
            if 1 <= val <= 10:
                return val
    return None


def extract_npi(text: str) -> Optional[str]:
    """Extract Net Property Income."""
    patterns = [
        r"(?:NPI|Net\s*Property\s*Income)\s*S?\$?\s*(\d+(?:,\d{3})*\.?\d*)\s*(?:M|million|m)",
        r"NPI\s*S?\$?(\d+\.?\d*)\s*(?:M|million|m)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", "")
            return f"S${value}M"
    return None


def extract_top_tenants(text: str) -> list:
    """Extract top tenants list."""
    tenants = []

    # Look for numbered tenant entries with percentage
    # CICT format: "1 RC Hotels (Pte) Ltd 4.6 Hotel"
    # More specific pattern to avoid false matches
    lines = text.split("\n")

    for line in lines:
        # Skip header lines
        if "Top 10 Tenants" in line or "Gross Rental Income" in line:
            continue

        # Pattern: number, tenant name, percentage, sector
        match = re.match(
            r"^\s*(\d{1,2})\s+([A-Za-z][A-Za-z0-9\s\(\)\.&,\-]+?)\s+(\d+\.?\d*)\s+([A-Za-z][A-Za-z\s&/\-]+)\s*$",
            line.strip()
        )
        if match:
            rank, name, percentage, sector = match.groups()
            try:
                rank_int = int(rank)
                pct = float(percentage)
                # Sanity check - percentage should be < 20%
                if rank_int <= 10 and pct < 20:
                    tenants.append({
                        "rank": rank_int,
                        "name": name.strip(),
                        "percentage": pct,
                        "sector": sector.strip(),
                    })
            except (ValueError, IndexError):
                continue

    # Sort by rank and return top 10
    tenants.sort(key=lambda x: x["rank"])
    return tenants[:10]


def extract_lease_expiry(text: str) -> dict:
    """Extract lease expiry profile."""
    result = {}

    # Look for year percentages
    # Pattern: "2026" followed by percentages for retail/office
    years = ["2025", "2026", "2027", "2028", "2029", "2030"]

    for year in years:
        # Look for the year followed by percentage values
        pattern = rf"{year}\s+(\d+\.?\d*)\s*%?\s+(\d+\.?\d*)\s*%?"
        match = re.search(pattern, text)
        if match:
            result[year] = {
                "retail": float(match.group(1)),
                "office": float(match.group(2)),
            }

    return result


def extract_market_data(text: str) -> dict:
    """Extract market analysis data."""
    result = {}

    # Singapore GDP forecast - look for "2025 Forecast" followed by percentage range
    gdp_patterns = [
        r"2025\s*Forecast\s*(\d+\.?\d*)\s*(?:to|-)\s*(\d+\.?\d*)\s*%?\s*YoY",
        r"GDP.*?2025\s*Forecast\s*(\d+\.?\d*)\s*(?:to|-)\s*(\d+\.?\d*)\s*%",
    ]
    for pattern in gdp_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            result["sg_gdp_forecast"] = f"{match.group(1)}-{match.group(2)}%"
            break

    # Look for retail rent YoY in the Market Information section
    # CICT page 29 format: "Orchard Road Rents" with "▲2.4% YoY"
    # The format is typically: $38.35 ▲0.7% QoQ ▲2.4% YoY

    # Find the Singapore Retail Rent section and extract YoY values
    retail_rent_section = re.search(
        r"SINGAPORE\s*RETAIL\s*RENT.*?Orchard.*?(\d+\.?\d*)\s*%\s*YoY.*?Suburban.*?(\d+\.?\d*)\s*%\s*YoY",
        text, re.IGNORECASE | re.DOTALL
    )
    if retail_rent_section:
        result["sg_orchard_rent_yoy"] = float(retail_rent_section.group(1))
        result["sg_suburban_rent_yoy"] = float(retail_rent_section.group(2))
    else:
        # Alternative: look for just YoY near Orchard/Suburban
        orchard_match = re.search(
            r"Orchard\s*Road\s*Rents.*?(\d+\.?\d*)\s*%\s*YoY",
            text, re.IGNORECASE | re.DOTALL
        )
        if orchard_match:
            result["sg_orchard_rent_yoy"] = float(orchard_match.group(1))

        suburban_match = re.search(
            r"Suburban\s*Rents.*?(\d+\.?\d*)\s*%\s*YoY",
            text, re.IGNORECASE | re.DOTALL
        )
        if suburban_match:
            result["sg_suburban_rent_yoy"] = float(suburban_match.group(1))

    # Grade A Office rents - CICT page 33 format
    # "SINGAPORE GRADE A OFFICE RENTS" with "▲2.1% YoY"
    office_yoy = re.search(
        r"GRADE\s*A\s*OFFICE\s*RENTS.*?(\d+\.?\d*)\s*%\s*YoY",
        text, re.IGNORECASE | re.DOTALL
    )
    if office_yoy:
        result["sg_office_rent_yoy"] = float(office_yoy.group(1))

    # Core inflation forecast
    inflation_match = re.search(
        r"(?:Core\s*)?Inflation.*?2025\s*Forecast\s*(\d+\.?\d*)\s*(?:to|-)\s*(\d+\.?\d*)\s*%",
        text, re.IGNORECASE | re.DOTALL
    )
    if inflation_match:
        result["sg_core_inflation_forecast"] = f"{inflation_match.group(1)}-{inflation_match.group(2)}%"

    return result


def extract_quarterly_data(pdf_path: Path) -> dict:
    """
    Extract key data from a quarterly report PDF.

    Returns structured data for investment analysis.
    """
    result = {
        "source_file": pdf_path.name,
        "report_date": None,
        "quarter": None,
        "operational_metrics": {},
        "capital_metrics": {},
        "market_data": {},
        "extraction_notes": [],
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extract text from all pages
            full_text = ""
            page_texts = {}

            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"
                page_texts[i + 1] = page_text

            # Extract report metadata
            result["report_date"] = extract_report_date(full_text)
            result["quarter"] = extract_quarter_label(full_text)

            # Extract operational metrics - use full text for reliability
            # Different REITs may have different page layouts
            result["operational_metrics"]["occupancy"] = extract_occupancy(full_text)
            result["operational_metrics"]["wale"] = extract_wale(full_text)
            result["operational_metrics"]["rent_reversion"] = extract_rent_reversion(full_text)
            result["operational_metrics"]["npi"] = extract_npi(full_text)

            # For top tenants and lease expiry, search through all pages for the tables
            tenants_found = False
            lease_found = False
            for page_num, page_text in page_texts.items():
                if "Top 10 Tenants" in page_text and not tenants_found:
                    result["operational_metrics"]["top_tenants"] = extract_top_tenants(page_text)
                    tenants_found = True
                if "Lease Expiry" in page_text and not lease_found:
                    result["operational_metrics"]["lease_expiry"] = extract_lease_expiry(page_text)
                    lease_found = True

            if not tenants_found:
                result["operational_metrics"]["top_tenants"] = []
            if not lease_found:
                result["operational_metrics"]["lease_expiry"] = {}

            # Extract capital metrics - use full text
            result["capital_metrics"]["leverage"] = extract_leverage(full_text)
            result["capital_metrics"]["cost_of_debt"] = extract_cost_of_debt(full_text)

            # Extract market data - use full text
            result["market_data"] = extract_market_data(full_text)

            # Add extraction notes
            if not result["operational_metrics"]["occupancy"]:
                result["extraction_notes"].append("Could not extract occupancy data")
            if not result["operational_metrics"]["wale"]:
                result["extraction_notes"].append("Could not extract WALE data")
            if not result["capital_metrics"]["leverage"]:
                result["extraction_notes"].append("Could not extract leverage data")

    except Exception as e:
        result["extraction_notes"].append(f"Error: {str(e)}")

    return result


def get_quarterly_pdfs(ticker: str) -> list[Path]:
    """Get list of quarterly report PDFs for a REIT."""
    cache_dir = CACHE_DIR / ticker
    if not cache_dir.exists():
        return []

    # Find PDF files matching quarterly patterns
    pdfs = []
    for pdf_file in cache_dir.glob("*.pdf"):
        name = pdf_file.name.lower()
        # Skip annual reports
        if name.startswith("ar"):
            continue
        # SGX-style: YYYYMMDD_HHMMSS_TICKER_*.pdf
        if re.match(r"^\d{8}_\d{6}_", pdf_file.name):
            pdfs.append(pdf_file)
        # Keppel DC REIT style: kdcreit-*.pdf
        elif name.startswith("kdcreit"):
            pdfs.append(pdf_file)
        # Keppel REIT style: kreit-*.pdf or mrel-kreit-*.pdf
        elif "kreit" in name:
            pdfs.append(pdf_file)

    # Sort by date (newest first) - use filename for sorting
    pdfs.sort(key=lambda x: x.name, reverse=True)
    return pdfs


def extract_all_quarters(ticker: str, num_quarters: int = 4) -> dict:
    """
    Extract data from the last N quarters for a REIT.

    Returns combined data suitable for LLM analysis.
    """
    config = load_config()
    reit_config = config.get(ticker, {})

    result = {
        "ticker": ticker,
        "name": reit_config.get("name", ticker),
        "quarters": [],
        "extraction_summary": {},
    }

    pdfs = get_quarterly_pdfs(ticker)[:num_quarters]

    if not pdfs:
        result["extraction_summary"]["error"] = "No quarterly PDFs found"
        return result

    for pdf_path in pdfs:
        quarterly_data = extract_quarterly_data(pdf_path)
        result["quarters"].append(quarterly_data)

    # Summary
    result["extraction_summary"]["total_quarters"] = len(result["quarters"])
    result["extraction_summary"]["date_range"] = (
        f"{result['quarters'][-1].get('quarter', 'Unknown')} to "
        f"{result['quarters'][0].get('quarter', 'Unknown')}"
    )

    return result


def format_for_llm(data: dict) -> str:
    """
    Format extracted quarterly data as concise text for LLM consumption.

    Target: ~500-1000 tokens of structured, investment-relevant data.
    """
    lines = []

    ticker = data.get("ticker", "Unknown")
    name = data.get("name", "Unknown")
    quarters = data.get("quarters", [])

    if not quarters:
        return f"{name} ({ticker}): No quarterly data available."

    lines.append(f"## {name} ({ticker}) - Quarterly Data")
    lines.append("")

    # Latest quarter details
    latest = quarters[0]
    quarter_label = latest.get("quarter", "Latest")
    report_date = latest.get("report_date", "")

    lines.append(f"### {quarter_label} ({report_date})")
    lines.append("")

    # Operational metrics
    ops = latest.get("operational_metrics", {})

    occupancy = ops.get("occupancy", {})
    if occupancy:
        occ_parts = []
        if "portfolio" in occupancy:
            occ_parts.append(f"Portfolio: {occupancy['portfolio']}%")
        if "retail" in occupancy:
            occ_parts.append(f"Retail: {occupancy['retail']}%")
        if "office" in occupancy:
            occ_parts.append(f"Office: {occupancy['office']}%")
        if occ_parts:
            lines.append(f"**Occupancy:** {' | '.join(occ_parts)}")

    wale = ops.get("wale", {})
    if wale:
        wale_val = wale.get("portfolio", wale.get("retail", "N/A"))
        lines.append(f"**WALE:** {wale_val} years")

    npi = ops.get("npi")
    if npi:
        lines.append(f"**Net Property Income:** {npi}")

    rent_rev = ops.get("rent_reversion", {})
    if rent_rev:
        rev_parts = []
        if "retail" in rent_rev:
            rev_parts.append(f"Retail: +{rent_rev['retail']}%")
        if "office" in rent_rev:
            rev_parts.append(f"Office: +{rent_rev['office']}%")
        if rev_parts:
            lines.append(f"**Rent Reversion:** {' | '.join(rev_parts)}")

    # Capital metrics
    capital = latest.get("capital_metrics", {})
    if capital.get("leverage"):
        lines.append(f"**Leverage:** {capital['leverage']}%")
    if capital.get("cost_of_debt"):
        lines.append(f"**Cost of Debt:** {capital['cost_of_debt']}%")

    # Top tenants
    top_tenants = ops.get("top_tenants", [])[:5]
    if top_tenants:
        lines.append("")
        lines.append("**Top 5 Tenants:**")
        for tenant in top_tenants:
            lines.append(f"  - {tenant['name']}: {tenant['percentage']}% ({tenant['sector']})")

    # Market data
    market = latest.get("market_data", {})
    if market:
        lines.append("")
        lines.append("**Market Context:**")
        if market.get("sg_gdp_forecast"):
            lines.append(f"  - SG GDP Forecast: {market['sg_gdp_forecast']}")
        if market.get("sg_orchard_rent_yoy"):
            lines.append(f"  - Orchard Retail Rent: +{market['sg_orchard_rent_yoy']}% YoY")
        if market.get("sg_suburban_rent_yoy"):
            lines.append(f"  - Suburban Retail Rent: +{market['sg_suburban_rent_yoy']}% YoY")
        if market.get("sg_office_rent_yoy"):
            lines.append(f"  - Grade A Office Rent: +{market['sg_office_rent_yoy']}% YoY")

    # Trend data (if multiple quarters)
    if len(quarters) > 1:
        lines.append("")
        lines.append("### Quarterly Trend")

        # Occupancy trend
        occ_trend = []
        for q in reversed(quarters):
            q_label = q.get("quarter", "?")
            q_occ = q.get("operational_metrics", {}).get("occupancy", {}).get("portfolio")
            if q_occ:
                occ_trend.append(f"{q_label}: {q_occ}%")

        if occ_trend:
            lines.append(f"**Occupancy:** {' → '.join(occ_trend)}")

    lines.append("")
    lines.append(f"*Source: {name} Quarterly Business Updates*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract data from REIT quarterly reports"
    )
    parser.add_argument(
        "ticker",
        nargs="?",
        help="REIT ticker (e.g., C38U.SI)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Extract data for all REITs",
    )
    parser.add_argument(
        "-n", "--num-quarters",
        type=int,
        default=4,
        help="Number of quarters to extract (default: 4)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save extracted data to file",
    )

    args = parser.parse_args()

    if not args.ticker and not args.all:
        parser.print_help()
        print("\nERROR: Provide a ticker or use --all")
        sys.exit(1)

    if args.all:
        config = load_config()
        tickers = list(config.keys())
    else:
        tickers = [args.ticker]

    for ticker in tickers:
        print(f"\n=== {ticker} ===")

        data = extract_all_quarters(ticker, args.num_quarters)

        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            formatted = format_for_llm(data)
            print(formatted)

        if args.save:
            EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
            output_path = EXTRACTED_DIR / f"{ticker}.json"
            with open(output_path, "w") as f:
                json.dumps(data, f, indent=2, default=str)
            print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
