"""
Tool definitions for the REIT Analysis Agent.

Contains tools that can be bound to the LLM for:
- Fetching individual REIT data
- Analyzing top Singapore REITs
- Web search for qualitative information
"""
from langchain_core.tools import tool
from duckduckgo_search import DDGS

from yahoo_finance_api import get_reit_info as fetch_reit_info, get_reit_data_structured
from singapore_reits import get_top_reits_by_market_cap


@tool
def get_reit_info(ticker: str) -> str:
    """
    Fetches detailed information about a Singapore REIT stock from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., 'C38U.SI' for CapitaLand Integrated Commercial Trust)

    Returns:
        Formatted string with current price, dividend yield history, YTD performance, and market cap
    """
    return fetch_reit_info(ticker)


@tool
def analyze_top_singapore_reits(limit: int = 20) -> str:
    """
    Analyzes the top Singapore REITs by market capitalization and ranks them by various metrics.

    This tool will:
    1. Find the top N Singapore REITs by market cap
    2. Fetch detailed data for each REIT
    3. Rank them by Price-to-Book ratio, Dividend Yield, YTD Performance, and Gearing Ratio

    Args:
        limit: Number of top REITs to analyze (default: 10)

    Returns:
        Formatted analysis with rankings and detailed breakdown
    """
    print(f"\n{'='*80}")
    print(f"ANALYZING TOP {limit} SINGAPORE REITs BY MARKET CAP")
    print(f"{'='*80}\n")

    # Step 1: Get top REITs by market cap
    top_reits = get_top_reits_by_market_cap(limit)

    if not top_reits:
        return "Error: Unable to fetch Singapore REIT data"

    # Step 2: Fetch detailed data for each REIT
    print(f"\nFetching detailed data for {len(top_reits)} REITs...")
    reit_data_list = []

    for ticker, market_cap, company_name in top_reits:
        print(f"  Fetching {ticker}...")
        data = get_reit_data_structured(ticker)
        if data:
            reit_data_list.append(data)

    if not reit_data_list:
        return "Error: Unable to fetch detailed data for REITs"

    print(f"\nSuccessfully fetched data for {len(reit_data_list)} REITs\n")

    # Step 3: Create unified table
    output = f"\n{'='*127}\n"
    output += f"TOP {len(reit_data_list)} SINGAPORE REITs - COMPREHENSIVE ANALYSIS (Sorted by Market Cap)\n"
    output += f"{'='*127}\n\n"

    # Table header
    output += f"{'Rank':<6}{'Ticker':<12}{'Company Name':<35}{'Mkt Cap':<12}{'Price':<9}{'P/B':<7}{'Yield':<8}{'YTD':<10}{'Gearing':<8}{'ICR':<7}\n"
    output += "-" * 127 + "\n"

    # Table rows - already sorted by market cap from get_top_reits_by_market_cap()
    for i, reit in enumerate(reit_data_list, 1):
        # Format each field with N/A handling
        ticker = reit.get('ticker', 'N/A')
        company = reit.get('company_name', 'N/A')[:32]  # Truncate long names

        # Market Cap
        market_cap = reit.get('market_cap')
        if market_cap:
            market_cap_str = f"${market_cap/1e9:.2f}B"
        else:
            market_cap_str = "N/A"

        # Price
        price = reit.get('current_price')
        price_str = f"${price:.2f}" if price else "N/A"

        # P/B Ratio
        pb = reit.get('price_to_book')
        pb_str = f"{pb:.2f}" if pb else "N/A"

        # Dividend Yield
        div_yield = reit.get('current_year_dividend_yield')
        yield_str = f"{div_yield:.2f}%" if div_yield else "N/A"

        # YTD Performance
        ytd = reit.get('ytd_performance')
        if ytd is not None:
            sign = "+" if ytd >= 0 else ""
            ytd_str = f"{sign}{ytd:.2f}%"
        else:
            ytd_str = "N/A"

        # Gearing Ratio
        gearing = reit.get('gearing_ratio')
        gearing_str = f"{gearing:.2f}" if gearing else "N/A"

        # Interest Coverage Ratio (ICR)
        icr = reit.get('icr')
        icr_str = f"{icr:.2f}x" if icr else "N/A"

        # Format row
        output += f"{i:<6}{ticker:<12}{company:<35}{market_cap_str:<12}{price_str:<9}{pb_str:<7}{yield_str:<8}{ytd_str:<10}{gearing_str:<8}{icr_str:<7}\n"

    output += "\n" + "="*127 + "\n"

    # Step 4: Add DPU Trends section for each REIT
    output += "\n\nDPU TRENDS & DIVIDEND HISTORY\n"
    output += "="*80 + "\n\n"

    for reit in reit_data_list:
        ticker = reit.get('ticker', 'N/A')
        company = reit.get('company_name', 'N/A')
        dividend_history = reit.get('dividend_history', [])

        output += f"--- {ticker} ({company}) ---\n"

        if dividend_history and len(dividend_history) > 0:
            # Display dividend history
            for div in dividend_history:
                year = div.get('year', 'N/A')
                amount = div.get('amount', 0)
                div_yield = div.get('yield', 0)
                output += f"  {year}: {amount*100:.2f}¢ (yield {div_yield:.2f}%)\n"

            # Calculate CAGR if we have at least 2 years of data
            if len(dividend_history) >= 2:
                # dividend_history is sorted descending (newest first)
                newest = dividend_history[0]
                oldest = dividend_history[-1]
                years = newest['year'] - oldest['year']

                if years > 0 and oldest['amount'] > 0 and newest['amount'] > 0:
                    cagr = ((newest['amount'] / oldest['amount']) ** (1 / years) - 1) * 100
                    sign = "+" if cagr >= 0 else ""
                    output += f"  {years}-Year DPU CAGR: {sign}{cagr:.1f}%\n"
        else:
            output += "  No dividend history available\n"

        output += "\n"

    output += "="*80 + "\n"

    return output


@tool
def search_reit_qualitative_info(ticker: str, company_name: str) -> str:
    """
    Searches the web for qualitative information about a Singapore REIT.

    Use this tool to get deeper insights about a REIT beyond the quantitative metrics,
    including:
    - Top tenants and tenant mix
    - Key assets and property locations
    - Recent news (acquisitions, disposals, quarterly results)
    - Sponsor information and asset pipeline
    - Analyst commentary and ratings

    Args:
        ticker: The REIT's stock ticker (e.g., 'C38U.SI')
        company_name: The full company name (e.g., 'CapitaLand Integrated Commercial Trust')

    Returns:
        Formatted string with qualitative information from web search results
    """
    print(f"\n[WEB SEARCH] Searching for qualitative info on {ticker} ({company_name})...")

    try:
        ddgs = DDGS()

        # Search queries for different aspects
        queries = [
            f'"{company_name}" REIT top tenants portfolio 2024',
            f'"{company_name}" REIT news acquisitions 2024 2025',
            f'"{company_name}" REIT quarterly results DPU',
        ]

        all_results = []

        for query in queries:
            results = ddgs.text(query, max_results=3)
            all_results.extend(results)

        if not all_results:
            return f"No web search results found for {company_name} ({ticker})"

        # Format results
        output = f"\n{'='*80}\n"
        output += f"WEB SEARCH RESULTS: {company_name} ({ticker})\n"
        output += f"{'='*80}\n\n"

        seen_titles = set()
        for i, result in enumerate(all_results, 1):
            title = result.get('title', 'No title')
            # Deduplicate by title
            if title in seen_titles:
                continue
            seen_titles.add(title)

            body = result.get('body', 'No description')
            href = result.get('href', '')

            output += f"[{len(seen_titles)}] {title}\n"
            output += f"    {body}\n"
            output += f"    Source: {href}\n\n"

        output += f"{'='*80}\n"
        output += "\nUse this information to provide deeper qualitative analysis about:\n"
        output += "- Tenant quality and lease profiles\n"
        output += "- Asset locations and property grades\n"
        output += "- Recent corporate actions and news\n"
        output += "- Sponsor support and pipeline\n"

        print(f"[WEB SEARCH] Found {len(seen_titles)} unique results for {ticker}")
        return output

    except Exception as e:
        error_msg = f"Error searching for {company_name}: {str(e)}"
        print(f"[WEB SEARCH] {error_msg}")
        return error_msg


# Export all tools as a list for easy binding
all_tools = [get_reit_info, analyze_top_singapore_reits, search_reit_qualitative_info]
