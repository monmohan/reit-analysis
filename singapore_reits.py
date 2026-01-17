"""
Singapore REIT Tickers and Discovery Functions
"""
import json
import yfinance as yf
from pathlib import Path
from typing import List, Tuple


# Curated list of Singapore REIT tickers
# Source: Singapore Exchange (SGX) - REITs traded on SGX
SINGAPORE_REITS = [
    'C38U.SI',   # CapitaLand Integrated Commercial Trust
    'A17U.SI',   # Ascendas REIT
    'ME8U.SI',   # Mapletree Industrial Trust
    'M44U.SI',   # Mapletree Logistics Trust
    'N2IU.SI',   # Mapletree Pan Asia Commercial Trust
    'TS0U.SI',   # Mapletree North Asia Commercial Trust
    'AJBU.SI',   # Keppel REIT
    'K71U.SI',   # Keppel DC REIT
    'T82U.SI',   # Suntec REIT
    'D5IU.SI',   # Frasers Centrepoint Trust
    'J69U.SI',   # Frasers Logistics & Commercial Trust
    'BUOU.SI',   # Frasers Hospitality Trust
    'C2PU.SI',   # CapitaLand Ascott Trust
    'BTOU.SI',   # Digital Core REIT
    'CMOU.SI',   # Cromwell European REIT
    'P40U.SI',   # Parkway Life REIT
    'CJLU.SI',   # NetLink NBN Trust
    'J85.SI',    # Sabana REIT
    'OXMU.SI',   # OUE Commercial REIT
    'LJ3.SI',    # Manulife US REIT
    'UD1U.SI',   # United Hampshire US REIT
    'CY6U.SI',   # Lendlease Global Commercial REIT
    'AU8U.SI',   # Dasin Retail Trust
]


def get_top_reits_by_market_cap(limit: int = 20) -> List[Tuple[str, float, str]]:
    """
    Fetches market capitalization for all Singapore REITs and returns top N by market cap.

    Args:
        limit: Number of top REITs to return (default: 10)

    Returns:
        List of tuples: (ticker, market_cap, company_name)
        Sorted by market cap in descending order
    """
    reit_data = []

    print(f"Fetching market cap data for {len(SINGAPORE_REITS)} Singapore REITs...")

    for ticker in SINGAPORE_REITS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if info and 'marketCap' in info and info['marketCap']:
                market_cap = info['marketCap']
                company_name = info.get('longName', ticker)
                reit_data.append((ticker, market_cap, company_name))
                print(f"  ✓ {ticker}: ${market_cap/1e9:.2f}B")
            else:
                print(f"  ✗ {ticker}: No market cap data")

        except Exception as e:
            print(f"  ✗ {ticker}: Error - {str(e)}")
            continue

    # Sort by market cap (descending)
    reit_data.sort(key=lambda x: x[1], reverse=True)

    # Return top N
    top_reits = reit_data[:limit]

    print(f"\nTop {limit} REITs by Market Cap:")
    for i, (ticker, market_cap, name) in enumerate(top_reits, 1):
        print(f"  {i}. {ticker} ({name}): ${market_cap/1e9:.2f}B")

    return top_reits


def get_reits_with_pdfs() -> List[str]:
    """
    Returns list of REIT tickers that have PDF data configured.
    Reads from config/reit_ir_urls.json and checks for high confidence entries.

    Returns:
        List of ticker symbols with PDF data available
    """
    config_path = Path(__file__).parent / "config" / "reit_ir_urls.json"
    if not config_path.exists():
        print(f"[WARNING] Config file not found: {config_path}")
        return []

    with open(config_path) as f:
        config = json.load(f)

    # Return tickers with high confidence (have quarterly_url and sample_pdfs)
    pdf_tickers = [
        ticker for ticker, data in config.items()
        if data.get("confidence") == "high" and data.get("quarterly_url")
    ]

    return pdf_tickers


if __name__ == "__main__":
    # Test the function
    top_10 = get_top_reits_by_market_cap(10)
