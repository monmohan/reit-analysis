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

        # Calculate Interest Coverage Ratio (ICR)
        icr = None
        try:
            financials = stock.financials  # Income statement

            if not financials.empty:
                # Try to get EBIT
                ebit = None
                if 'EBIT' in financials.index:
                    ebit = financials.loc['EBIT'].iloc[0]
                elif 'Operating Income' in financials.index:
                    ebit = financials.loc['Operating Income'].iloc[0]
                elif 'EBITDA' in financials.index:
                    ebit = financials.loc['EBITDA'].iloc[0]

                # Try to get Interest Expense
                interest_expense = None
                if 'Interest Expense' in financials.index:
                    interest_expense = financials.loc['Interest Expense'].iloc[0]
                elif 'Net Interest Expense' in financials.index:
                    interest_expense = financials.loc['Net Interest Expense'].iloc[0]

                # Calculate ICR
                if ebit is not None and interest_expense is not None and interest_expense != 0:
                    icr = ebit / abs(interest_expense)  # abs() since interest expense is usually negative
        except Exception:
            icr = None

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

        if icr is not None:
            output += f"Interest Coverage Ratio (ICR): {icr:.2f}x\n"
        else:
            output += "Interest Coverage Ratio (ICR): N/A\n"

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

        # Analyst Consensus
        output += "\n--- Analyst Consensus ---\n"
        analyst_rating = info.get('averageAnalystRating')
        if analyst_rating:
            output += f"Analyst Rating: {analyst_rating}\n"
        recommendation = info.get('recommendationKey')
        if recommendation:
            output += f"Recommendation: {recommendation.upper()}\n"
        num_analysts = info.get('numberOfAnalystOpinions')
        if num_analysts:
            output += f"Number of Analysts: {num_analysts}\n"
        target_mean = info.get('targetMeanPrice')
        target_high = info.get('targetHighPrice')
        target_low = info.get('targetLowPrice')
        if target_mean:
            output += f"Target Price: ${target_mean:.2f} (Low: ${target_low:.2f}, High: ${target_high:.2f})\n"

        # Company Profile
        output += "\n--- Company Profile ---\n"
        sector = info.get('sector')
        industry = info.get('industry')
        if sector:
            output += f"Sector: {sector}\n"
        if industry:
            output += f"Industry: {industry}\n"
        website = info.get('website')
        if website:
            output += f"Website: {website}\n"
        business_summary = info.get('longBusinessSummary')
        if business_summary:
            # Truncate to ~200 chars for readability
            summary = business_summary[:200] + "..." if len(business_summary) > 200 else business_summary
            output += f"Business: {summary}\n"

        # Financial Health
        output += "\n--- Financial Health ---\n"
        debt_to_equity = info.get('debtToEquity')
        if debt_to_equity is not None:
            output += f"Debt to Equity: {debt_to_equity:.2f}\n"
        roa = info.get('returnOnAssets')
        if roa is not None:
            output += f"Return on Assets: {roa*100:.2f}%\n"
        roe = info.get('returnOnEquity')
        if roe is not None:
            output += f"Return on Equity: {roe*100:.2f}%\n"
        beta = info.get('beta')
        if beta is not None:
            output += f"Beta: {beta:.3f}\n"
        payout = info.get('payoutRatio')
        if payout is not None:
            output += f"Payout Ratio: {payout*100:.2f}%\n"

        # 52-Week Price Range
        output += "\n--- 52-Week Price Range ---\n"
        high_52 = info.get('fiftyTwoWeekHigh')
        low_52 = info.get('fiftyTwoWeekLow')
        change_52 = info.get('fiftyTwoWeekChange')
        if high_52 and low_52:
            output += f"52-Week High: ${high_52:.2f}\n"
            output += f"52-Week Low: ${low_52:.2f}\n"
        if change_52 is not None:
            sign = "+" if change_52 >= 0 else ""
            output += f"52-Week Change: {sign}{change_52*100:.2f}%\n"

        # Ownership
        output += "\n--- Ownership ---\n"
        insiders = info.get('heldPercentInsiders')
        institutions = info.get('heldPercentInstitutions')
        if insiders is not None:
            output += f"Insider Ownership: {insiders*100:.2f}%\n"
        if institutions is not None:
            output += f"Institutional Ownership: {institutions*100:.2f}%\n"

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

        # Calculate Interest Coverage Ratio (ICR)
        icr = None
        try:
            financials = stock.financials  # Income statement

            if not financials.empty:
                # Try to get EBIT
                ebit = None
                if 'EBIT' in financials.index:
                    ebit = financials.loc['EBIT'].iloc[0]
                elif 'Operating Income' in financials.index:
                    ebit = financials.loc['Operating Income'].iloc[0]
                elif 'EBITDA' in financials.index:
                    ebit = financials.loc['EBITDA'].iloc[0]

                # Try to get Interest Expense
                interest_expense = None
                if 'Interest Expense' in financials.index:
                    interest_expense = financials.loc['Interest Expense'].iloc[0]
                elif 'Net Interest Expense' in financials.index:
                    interest_expense = financials.loc['Net Interest Expense'].iloc[0]

                # Calculate ICR
                if ebit is not None and interest_expense is not None and interest_expense != 0:
                    icr = ebit / abs(interest_expense)  # abs() since interest expense is usually negative
        except Exception:
            icr = None

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
            # Original fields
            'ticker': ticker,
            'company_name': company_name,
            'current_price': float(current_price) if current_price else None,
            'market_cap': float(market_cap) if market_cap else None,
            'price_to_book': float(price_to_book) if price_to_book else None,
            'gearing_ratio': float(gearing_ratio) if gearing_ratio is not None else None,
            'icr': float(icr) if icr is not None else None,
            'current_year_dividend_yield': current_year_dividend_yield,
            'dividend_history': dividend_history,
            'ytd_performance': float(ytd_performance) if ytd_performance is not None else None,

            # NEW: Analyst Data
            'analyst_rating': info.get('averageAnalystRating'),
            'recommendation_key': info.get('recommendationKey'),
            'recommendation_mean': float(info['recommendationMean']) if info.get('recommendationMean') else None,
            'num_analyst_opinions': info.get('numberOfAnalystOpinions'),
            'target_price_mean': float(info['targetMeanPrice']) if info.get('targetMeanPrice') else None,
            'target_price_high': float(info['targetHighPrice']) if info.get('targetHighPrice') else None,
            'target_price_low': float(info['targetLowPrice']) if info.get('targetLowPrice') else None,

            # NEW: Company Profile
            'business_summary': info.get('longBusinessSummary'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'website': info.get('website'),
            'company_officers': info.get('companyOfficers'),

            # NEW: Financial Ratios
            'debt_to_equity': float(info['debtToEquity']) if info.get('debtToEquity') else None,
            'current_ratio': float(info['currentRatio']) if info.get('currentRatio') else None,
            'quick_ratio': float(info['quickRatio']) if info.get('quickRatio') else None,
            'return_on_assets': float(info['returnOnAssets']) if info.get('returnOnAssets') else None,
            'return_on_equity': float(info['returnOnEquity']) if info.get('returnOnEquity') else None,
            'revenue_growth': float(info['revenueGrowth']) if info.get('revenueGrowth') else None,
            'earnings_growth': float(info['earningsGrowth']) if info.get('earningsGrowth') else None,
            'payout_ratio': float(info['payoutRatio']) if info.get('payoutRatio') else None,
            'beta': float(info['beta']) if info.get('beta') else None,

            # NEW: Cash Flow
            'free_cashflow': float(info['freeCashflow']) if info.get('freeCashflow') else None,
            'operating_cashflow': float(info['operatingCashflow']) if info.get('operatingCashflow') else None,

            # NEW: Ownership
            'held_percent_insiders': float(info['heldPercentInsiders']) if info.get('heldPercentInsiders') else None,
            'held_percent_institutions': float(info['heldPercentInstitutions']) if info.get('heldPercentInstitutions') else None,

            # NEW: Additional Yield/Price Data
            'five_year_avg_dividend_yield': float(info['fiveYearAvgDividendYield']) if info.get('fiveYearAvgDividendYield') else None,
            'fifty_two_week_high': float(info['fiftyTwoWeekHigh']) if info.get('fiftyTwoWeekHigh') else None,
            'fifty_two_week_low': float(info['fiftyTwoWeekLow']) if info.get('fiftyTwoWeekLow') else None,
            'fifty_two_week_change': float(info['fiftyTwoWeekChange']) if info.get('fiftyTwoWeekChange') else None,
        }

    except Exception as e:
        print(f"Error fetching structured data for {ticker}: {str(e)}")
        return None
