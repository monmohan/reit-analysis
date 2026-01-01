import yfinance as yf
from datetime import datetime
import pandas as pd
from typing import Optional, Dict, Any


def get_reit_info(ticker: str) -> str:
    """
    Fetches detailed information about a Singapore REIT stock from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., 'C38U.SI' for CapitaLand Integrated Commercial Trust)

    Returns:
        Formatted string with current price, dividend yield history, YTD performance, and market cap
    """
    try:
        # Fetch stock data
        stock = yf.Ticker(ticker)
        info = stock.info

        # Validate that we got data
        if not info or 'symbol' not in info:
            return f"Error: Unable to fetch data for ticker '{ticker}'. Please verify the ticker symbol."

        # Extract basic info
        company_name = info.get('longName', ticker)
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        market_cap = info.get('marketCap')
        price_to_book = info.get('priceToBook')

        # Extract debt and assets for gearing ratio
        total_debt = info.get('totalDebt')
        total_assets = info.get('totalAssets')

        # If totalAssets not in info, try balance sheet
        if total_assets is None:
            try:
                balance_sheet = stock.balance_sheet
                if not balance_sheet.empty and 'Total Assets' in balance_sheet.index:
                    total_assets = balance_sheet.loc['Total Assets'].iloc[0]
                if not balance_sheet.empty and 'Total Debt' in balance_sheet.index and total_debt is None:
                    total_debt = balance_sheet.loc['Total Debt'].iloc[0]
            except:
                pass

        gearing_ratio = None
        if total_debt is not None and total_assets is not None and total_assets > 0:
            gearing_ratio = total_debt / total_assets

        if current_price is None:
            return f"Error: Current price data not available for {ticker}"

        # Get dividend history (last 5 years or max available)
        current_year = datetime.now().year
        dividends = stock.dividends

        if len(dividends) > 0:
            # Filter last 5 years using date comparison (timezone-safe)
            five_years_ago_date = datetime(current_year - 5, 1, 1).date()
            recent_dividends = dividends[dividends.index.date >= five_years_ago_date]

            if len(recent_dividends) == 0:
                recent_dividends = dividends  # Use all available if less than 5 years
        else:
            recent_dividends = pd.Series(dtype=float)

        # Calculate YTD performance
        ytd_performance = None
        try:
            history = stock.history(period='ytd')
            if len(history) > 0:
                start_price = history['Close'].iloc[0]
                current_close = history['Close'].iloc[-1]
                ytd_performance = ((current_close - start_price) / start_price) * 100
        except Exception:
            ytd_performance = None

        # Format output
        output = f"=== REIT Information: {ticker} ===\n"
        output += f"Company: {company_name}\n"
        output += f"Current Price: ${current_price:.2f} SGD\n"

        if market_cap:
            market_cap_billion = market_cap / 1_000_000_000
            output += f"Market Cap: ${market_cap_billion:.2f} billion SGD\n"
        else:
            output += "Market Cap: N/A\n"

        if price_to_book:
            output += f"Price to Book Ratio: {price_to_book:.2f}\n"
        else:
            output += "Price to Book Ratio: N/A\n"

        if gearing_ratio is not None:
            output += f"Gearing Ratio (Debt/Assets): {gearing_ratio:.2f}\n"
        else:
            output += "Gearing Ratio (Debt/Assets): N/A\n"

        output += "\n"

        # Dividend information
        if len(recent_dividends) > 0:
            total_annual_dividend = recent_dividends.resample('YE').sum()

            # Per-year dividend yield breakdown
            output += "Dividend Yield by Year:\n"
            for date, annual_amount in total_annual_dividend.sort_index(ascending=False).items():
                year = date.year
                yearly_yield = (annual_amount / current_price) * 100 if current_price else 0
                output += f"  - {year}: {yearly_yield:.2f}%\n"
        else:
            output += "Dividend Yield: No dividend history available\n"

        output += "\n"

        if ytd_performance is not None:
            sign = "+" if ytd_performance >= 0 else ""
            output += f"YTD Performance: {sign}{ytd_performance:.2f}%\n"
        else:
            output += "YTD Performance: N/A\n"

        return output

    except Exception as e:
        return f"Error fetching data for {ticker}: {str(e)}"


def get_reit_data_structured(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetches REIT data and returns it as a structured dictionary for analysis.

    Args:
        ticker: Stock ticker symbol (e.g., 'C38U.SI')

    Returns:
        Dictionary with REIT data, or None if data fetch fails
    """
    try:
        # Fetch stock data
        stock = yf.Ticker(ticker)
        info = stock.info

        # Validate that we got data
        if not info or 'symbol' not in info:
            return None

        # Extract basic info
        company_name = info.get('longName', ticker)
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        market_cap = info.get('marketCap')
        price_to_book = info.get('priceToBook')

        # Extract debt and assets for gearing ratio
        total_debt = info.get('totalDebt')
        total_assets = info.get('totalAssets')

        # If totalAssets not in info, try balance sheet
        if total_assets is None:
            try:
                balance_sheet = stock.balance_sheet
                if not balance_sheet.empty and 'Total Assets' in balance_sheet.index:
                    total_assets = balance_sheet.loc['Total Assets'].iloc[0]
                if not balance_sheet.empty and 'Total Debt' in balance_sheet.index and total_debt is None:
                    total_debt = balance_sheet.loc['Total Debt'].iloc[0]
            except:
                pass

        gearing_ratio = None
        if total_debt is not None and total_assets is not None and total_assets > 0:
            gearing_ratio = total_debt / total_assets

        if current_price is None:
            return None

        # Get dividend history (last 5 years or max available)
        current_year = datetime.now().year
        dividends = stock.dividends

        current_year_dividend_yield = None
        dividend_history = []

        if len(dividends) > 0:
            # Filter last 5 years using date comparison (timezone-safe)
            five_years_ago_date = datetime(current_year - 5, 1, 1).date()
            recent_dividends = dividends[dividends.index.date >= five_years_ago_date]

            if len(recent_dividends) == 0:
                recent_dividends = dividends  # Use all available if less than 5 years

            # Calculate annual dividends and yields
            total_annual_dividend = recent_dividends.resample('YE').sum()

            for date, annual_amount in total_annual_dividend.sort_index(ascending=False).items():
                year = date.year
                yearly_yield = (annual_amount / current_price) * 100 if current_price else 0
                dividend_history.append({
                    'year': year,
                    'amount': float(annual_amount),
                    'yield': float(yearly_yield)
                })

            # Get current year (most recent) dividend yield
            if len(dividend_history) > 0:
                current_year_dividend_yield = dividend_history[0]['yield']

        # Calculate YTD performance
        ytd_performance = None
        try:
            history = stock.history(period='ytd')
            if len(history) > 0:
                start_price = history['Close'].iloc[0]
                current_close = history['Close'].iloc[-1]
                ytd_performance = ((current_close - start_price) / start_price) * 100
        except Exception:
            ytd_performance = None

        return {
            'ticker': ticker,
            'company_name': company_name,
            'current_price': float(current_price) if current_price else None,
            'market_cap': float(market_cap) if market_cap else None,
            'price_to_book': float(price_to_book) if price_to_book else None,
            'gearing_ratio': float(gearing_ratio) if gearing_ratio is not None else None,
            'current_year_dividend_yield': current_year_dividend_yield,
            'dividend_history': dividend_history,
            'ytd_performance': float(ytd_performance) if ytd_performance is not None else None
        }

    except Exception as e:
        print(f"Error fetching structured data for {ticker}: {str(e)}")
        return None
