#!/usr/bin/env python3
"""
Data Cache Module

Manages cached quarterly data for REIT analysis.
Provides fresh or cached data to the agent tools.

Usage:
    from data_cache import get_reit_qualitative_data
    data = get_reit_qualitative_data("C38U.SI")
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from quarterly_parser import extract_all_quarters, format_for_llm, get_quarterly_pdfs


# Paths
CONFIG_PATH = Path(__file__).parent / "config" / "reit_ir_urls.json"
CACHE_DIR = Path(__file__).parent / "data" / "pdf_cache"
EXTRACTED_DIR = Path(__file__).parent / "data" / "extracted_data"


def load_config() -> dict:
    """Load the REIT IR URLs config."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_cached_data(ticker: str) -> Optional[dict]:
    """
    Load cached extracted data for a REIT if available.

    Returns None if no cache exists or cache is stale.
    """
    cache_path = EXTRACTED_DIR / f"{ticker}.json"

    if not cache_path.exists():
        return None

    try:
        with open(cache_path) as f:
            data = json.load(f)

        # Check if cache is stale (older than 7 days)
        if "extracted_at" in data:
            extracted_at = datetime.fromisoformat(data["extracted_at"])
            age_days = (datetime.now() - extracted_at).days
            if age_days > 7:
                print(f"[CACHE] {ticker} cache is {age_days} days old, refreshing...")
                return None

        return data
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def save_to_cache(ticker: str, data: dict) -> None:
    """Save extracted data to cache."""
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    data["extracted_at"] = datetime.now().isoformat()

    cache_path = EXTRACTED_DIR / f"{ticker}.json"
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def has_quarterly_pdfs(ticker: str) -> bool:
    """Check if we have quarterly PDFs downloaded for a REIT."""
    pdfs = get_quarterly_pdfs(ticker)
    return len(pdfs) > 0


def get_reit_quarterly_structured(
    ticker: str,
    force_refresh: bool = False,
    num_quarters: int = 4,
) -> Optional[dict]:
    """
    Get structured quarterly data for a REIT (not formatted text).

    Returns dict with quarters data, or None if no data available.
    Used by setup_node to combine with Yahoo data.
    """
    # Check if we have PDFs
    if not has_quarterly_pdfs(ticker):
        return None

    # Check cache first
    if not force_refresh:
        cached = get_cached_data(ticker)
        if cached and cached.get("quarters"):
            return cached

    # Extract fresh data
    data = extract_all_quarters(ticker, num_quarters)

    # Only cache if we got quarters
    if data.get("quarters"):
        save_to_cache(ticker, data)
        return data

    return None


def get_reit_qualitative_data(
    ticker: str,
    company_name: str = "",
    force_refresh: bool = False,
    num_quarters: int = 4,
) -> str:
    """
    Get qualitative data for a REIT from quarterly reports.

    This function:
    1. Checks for cached extracted data
    2. If cache is fresh, returns formatted data
    3. If cache is stale or missing, extracts from PDFs
    4. Returns formatted text suitable for LLM consumption

    Args:
        ticker: REIT ticker (e.g., "C38U.SI")
        company_name: Company name (optional, for display)
        force_refresh: Force re-extraction even if cached
        num_quarters: Number of quarters to extract (default: 4)

    Returns:
        Formatted string with quarterly data for LLM
    """
    config = load_config()
    reit_config = config.get(ticker, {})

    # Use config name if company_name not provided
    if not company_name:
        company_name = reit_config.get("name", ticker)

    # Check if we have PDFs to work with
    if not has_quarterly_pdfs(ticker):
        return f"""## {company_name} ({ticker}) - Quarterly Data

**No quarterly reports available.**

To download quarterly reports, run:
```
uv run python pdf_downloader.py {ticker}
```

*Source: Quarterly reports not yet downloaded*
"""

    # Check cache first (unless force refresh)
    if not force_refresh:
        cached = get_cached_data(ticker)
        if cached:
            print(f"[CACHE] Using cached data for {ticker}")
            return format_for_llm(cached)

    # Extract fresh data
    print(f"[EXTRACT] Extracting quarterly data for {ticker}...")
    data = extract_all_quarters(ticker, num_quarters)

    # Cache the extracted data
    save_to_cache(ticker, data)

    return format_for_llm(data)


def get_all_reits_qualitative_data(force_refresh: bool = False) -> dict[str, str]:
    """
    Get qualitative data for all configured REITs.

    Returns dict mapping ticker to formatted data string.
    """
    config = load_config()
    results = {}

    for ticker in config:
        try:
            data = get_reit_qualitative_data(ticker, force_refresh=force_refresh)
            results[ticker] = data
        except Exception as e:
            results[ticker] = f"Error extracting data for {ticker}: {e}"

    return results


def check_data_freshness() -> dict:
    """
    Check the freshness of cached data for all REITs.

    Returns dict with status for each REIT.
    """
    config = load_config()
    status = {}

    for ticker, reit_config in config.items():
        ticker_status = {
            "name": reit_config.get("name", ticker),
            "has_pdfs": has_quarterly_pdfs(ticker),
            "num_pdfs": len(get_quarterly_pdfs(ticker)),
            "has_cache": False,
            "cache_age_days": None,
        }

        cache_path = EXTRACTED_DIR / f"{ticker}.json"
        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    data = json.load(f)
                if "extracted_at" in data:
                    extracted_at = datetime.fromisoformat(data["extracted_at"])
                    ticker_status["has_cache"] = True
                    ticker_status["cache_age_days"] = (datetime.now() - extracted_at).days
            except Exception:
                pass

        status[ticker] = ticker_status

    return status


if __name__ == "__main__":
    # Print status of all REITs
    print("REIT Data Freshness Status")
    print("=" * 80)

    status = check_data_freshness()

    for ticker, info in status.items():
        print(f"\n{ticker} - {info['name']}")
        print(f"  PDFs: {info['num_pdfs']} downloaded")
        if info['has_cache']:
            print(f"  Cache: {info['cache_age_days']} days old")
        else:
            print("  Cache: Not available")
