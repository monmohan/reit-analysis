import yfinance as yf

def get_reit_info(ticker: str) -> str:
    """
    Fetches REIT info using yfinance with error handling for missing data.
    """
    try:
        stock = yf.Ticker(ticker)
        
        # 1. Fetch Info (safely)
        # fast_info is generally more reliable and faster than .info
        try:
            current_price = stock.fast_info.last_price
            market_cap = stock.fast_info.market_cap
        except (AttributeError, KeyError):
            # Fallback for some tickers if fast_info fails
            info = stock.info
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            market_cap = info.get('marketCap')

        # Check if we actually got data
        if current_price is None:
            return f"Error: Could not fetch price data for {ticker}. The ticker might be delisted or Yahoo is blocking the request."

        # Format Basic Data
        price_str = f"${current_price:.2f}"
        market_cap_str = f"${market_cap/1e9:.2f}B" if market_cap else "N/A"

        # 2. Fetch History for YTD
        # Using 'max' allows us to manually filter for this year safely
        hist = stock.history(period="1y")
        
        ytd_str = "N/A"
        if not hist.empty:
            # Filter for current year
            current_year = str(hist.index[-1].year)
            this_year_data = hist.loc[current_year]
            
            if not this_year_data.empty:
                start_price = this_year_data.iloc[0]['Close']
                ytd_perf = ((current_price - start_price) / start_price) * 100
                ytd_str = f"{ytd_perf:+.2f}%"

        # 3. Dividend Summary (Last 5 Years)
        div_str = ""
        try:
            divs = stock.dividends
            if not divs.empty:
                # Filter last 5 years
                last_5_years = divs.sort_index(ascending=False)
                last_5_years = last_5_years.head(20) # Approximate count (4 quarters * 5 years)
                
                # Group by year to show annual yield
                yearly_divs = last_5_years.groupby(last_5_years.index.year).sum().sort_index(ascending=False)
                
                lines = []
                for year, amount in yearly_divs.items():
                    # Simple check to stop after 5 years
                    if len(lines) >= 5: break
                    lines.append(f"  {year}: ${amount:.4f} total")
                
                div_str = "\nDividend History (Recent Years):\n" + "\n".join(lines)
        except Exception:
            div_str = "\nDividend data unavailable."

        return f"""
REIT Information for {ticker}
{'=' * 50}
Current Price: {price_str}
Market Cap:    {market_cap_str}
YTD Performance: {ytd_str}
{div_str}
"""

    except Exception as e:
        return f"Critical Error fetching {ticker}: {str(e)}"

# --- Test Block ---
if __name__ == "__main__":
    # Test with C38U.SI (CapitaLand Integrated Commercial Trust)
    print(get_reit_info("C38U.SI"))