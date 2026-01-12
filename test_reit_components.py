"""
Test cases for REIT analysis components
"""
import sys
from yahoo_finance_api import get_reit_data_structured, get_reit_info
from singapore_reits import get_top_reits_by_market_cap


def test_single_reit_data():
    """Test fetching data for a single REIT (both structured and formatted)"""
    print("="*80)
    print("TEST 1: Single REIT Data Fetching")
    print("="*80)

    test_ticker = "C38U.SI"
    print(f"\nTesting with ticker: {test_ticker}")

    # Test structured data
    print("\n--- Testing get_reit_data_structured() ---")
    data = get_reit_data_structured(test_ticker)

    if data is None:
        print("❌ FAILED: Structured data returned None")
        return False

    # Check required fields
    required_fields = ['ticker', 'company_name', 'current_price', 'market_cap',
                       'price_to_book', 'current_year_dividend_yield', 'ytd_performance']

    print("\nStructured data fields:")
    for field in required_fields:
        value = data.get(field)
        status = "✓" if value is not None else "✗"
        print(f"  {status} {field}: {value}")

    structured_ok = (data.get('ticker') and data.get('company_name') and data.get('current_price'))

    # Test formatted string
    print("\n--- Testing get_reit_info() ---")
    info = get_reit_info(test_ticker)

    if "Error" in info:
        print(f"❌ FAILED: Formatted data returned error: {info}")
        return False

    print("\nFormatted string output:")
    print("-" * 80)
    print(info)
    print("-" * 80)

    # Check if output contains key information
    checks = [
        ("REIT Information" in info, "Contains header"),
        ("Current Price" in info, "Contains price"),
        ("Market Cap" in info, "Contains market cap"),
        ("YTD Performance" in info, "Contains YTD performance")
    ]

    print("\nFormatted string checks:")
    formatted_ok = True
    for check, description in checks:
        status = "✓" if check else "✗"
        print(f"  {status} {description}")
        if not check:
            formatted_ok = False

    if structured_ok and formatted_ok:
        print("\n✅ PASSED: Both structured and formatted data work correctly")
        return True
    else:
        print("\n❌ FAILED: Some checks failed")
        return False


def test_get_top_reits_by_market_cap():
    """Test fetching top REITs by market cap"""
    print("\n" + "="*80)
    print("TEST 2: get_top_reits_by_market_cap()")
    print("="*80)

    limit = 5
    print(f"\nTesting with limit: {limit}")
    print("-" * 80)

    top_reits = get_top_reits_by_market_cap(limit)

    print("-" * 80)

    if not top_reits:
        print("❌ FAILED: Returned empty list")
        return False

    if len(top_reits) > limit:
        print(f"❌ FAILED: Returned {len(top_reits)} REITs, expected max {limit}")
        return False

    # Check data structure
    print(f"\nReturned {len(top_reits)} REITs")
    print("\nData structure check:")

    all_valid = True
    for ticker, market_cap, company_name in top_reits[:3]:  # Check first 3
        valid = (isinstance(ticker, str) and
                 isinstance(market_cap, (int, float)) and
                 isinstance(company_name, str))

        status = "✓" if valid else "✗"
        print(f"  {status} {ticker}: ${market_cap/1e9:.2f}B - {company_name}")

        if not valid:
            all_valid = False

    if all_valid:
        print("\n✅ PASSED: Data structure is valid")
        return True
    else:
        print("\n❌ FAILED: Invalid data structure")
        return False


def test_multi_reit_analysis():
    """Test analyzing multiple REITs"""
    print("\n" + "="*80)
    print("TEST 3: Multi-REIT Analysis Flow")
    print("="*80)

    print("\nStep 1: Get top 3 REITs")
    top_reits = get_top_reits_by_market_cap(3)

    if not top_reits:
        print("❌ FAILED: Could not get top REITs")
        return False

    print(f"✓ Got {len(top_reits)} REITs")

    print("\nStep 2: Fetch structured data for each REIT")
    reit_data_list = []

    for ticker, _, _ in top_reits:
        print(f"  Fetching {ticker}...", end=" ")
        data = get_reit_data_structured(ticker)
        if data:
            reit_data_list.append(data)
            print("✓")
        else:
            print("✗")

    if len(reit_data_list) == 0:
        print("\n❌ FAILED: Could not fetch any REIT data")
        return False

    print(f"\n✓ Successfully fetched {len(reit_data_list)} REITs")

    print("\nStep 3: Test ranking by different metrics")

    # Test P/B ranking
    reits_with_pb = [r for r in reit_data_list if r.get('price_to_book')]
    if reits_with_pb:
        sorted_by_pb = sorted(reits_with_pb, key=lambda x: x['price_to_book'])
        print(f"\n✓ P/B Ranking: {len(sorted_by_pb)} REITs")
        print(f"  Best P/B: {sorted_by_pb[0]['ticker']} ({sorted_by_pb[0]['price_to_book']:.2f})")

    # Test dividend yield ranking
    reits_with_yield = [r for r in reit_data_list if r.get('current_year_dividend_yield')]
    if reits_with_yield:
        sorted_by_yield = sorted(reits_with_yield, key=lambda x: x['current_year_dividend_yield'], reverse=True)
        print(f"✓ Yield Ranking: {len(sorted_by_yield)} REITs")
        print(f"  Highest Yield: {sorted_by_yield[0]['ticker']} ({sorted_by_yield[0]['current_year_dividend_yield']:.2f}%)")

    # Test YTD ranking
    reits_with_ytd = [r for r in reit_data_list if r.get('ytd_performance') is not None]
    if reits_with_ytd:
        sorted_by_ytd = sorted(reits_with_ytd, key=lambda x: x['ytd_performance'], reverse=True)
        print(f"✓ YTD Ranking: {len(sorted_by_ytd)} REITs")
        print(f"  Best YTD: {sorted_by_ytd[0]['ticker']} ({sorted_by_ytd[0]['ytd_performance']:+.2f}%)")

    print("\n✅ PASSED: Multi-REIT analysis flow works")
    return True


def test_expanded_yahoo_finance_fields():
    """Test that get_reit_data_structured returns all expected fields including new ones."""
    print("\n" + "="*80)
    print("TEST 4: Expanded Yahoo Finance Fields")
    print("="*80)

    from yahoo_finance_api import get_reit_data_structured

    # Test with BUOU.SI (Frasers Logistics & Commercial Trust)
    test_ticker = 'BUOU.SI'
    print(f"\nTesting with ticker: {test_ticker}")

    data = get_reit_data_structured(test_ticker)

    if data is None:
        print("❌ FAILED: Should return data for valid ticker")
        return False

    # Original fields (10)
    original_fields = [
        'ticker', 'company_name', 'current_price', 'market_cap', 'price_to_book',
        'gearing_ratio', 'icr', 'current_year_dividend_yield', 'dividend_history',
        'ytd_performance'
    ]

    # New fields (25)
    new_fields = [
        # Analyst data
        'analyst_rating', 'recommendation_key', 'recommendation_mean',
        'num_analyst_opinions', 'target_price_mean', 'target_price_high', 'target_price_low',
        # Company profile
        'business_summary', 'sector', 'industry', 'website', 'company_officers',
        # Financial ratios
        'debt_to_equity', 'current_ratio', 'quick_ratio', 'return_on_assets',
        'return_on_equity', 'revenue_growth', 'earnings_growth', 'payout_ratio', 'beta',
        # Cash flow
        'free_cashflow', 'operating_cashflow',
        # Ownership
        'held_percent_insiders', 'held_percent_institutions',
        # Additional
        'five_year_avg_dividend_yield', 'fifty_two_week_high', 'fifty_two_week_low',
        'fifty_two_week_change'
    ]

    all_fields = original_fields + new_fields

    # Check all fields exist in returned data
    print("\nChecking field presence:")
    missing_fields = []
    for field in all_fields:
        if field not in data:
            missing_fields.append(field)

    if missing_fields:
        print(f"❌ Missing fields: {missing_fields}")
        return False

    print(f"  ✓ All {len(all_fields)} fields present")

    # Check total field count
    total_fields = len(data)
    print(f"  ✓ Total fields: {total_fields}")

    if total_fields < 35:
        print(f"❌ FAILED: Expected 35+ fields, got {total_fields}")
        return False

    # Check specific new fields have values (not all None)
    fields_with_values = [f for f in new_fields if data.get(f) is not None]
    print(f"  ✓ New fields with values: {len(fields_with_values)}/{len(new_fields)}")

    if len(fields_with_values) < 20:
        print(f"❌ FAILED: Expected at least 20 new fields with values, got {len(fields_with_values)}")
        return False

    # Check specific important fields
    print("\nChecking key fields:")
    checks = [
        (data.get('business_summary'), "business_summary has content"),
        (data.get('website'), "website has a URL"),
        (data.get('industry'), "industry is set"),
        (data.get('analyst_rating'), "analyst_rating has value"),
    ]

    all_ok = True
    for value, description in checks:
        status = "✓" if value else "✗"
        print(f"  {status} {description}")
        if not value:
            all_ok = False

    # Print some sample values
    print("\nSample new field values:")
    sample_fields = ['analyst_rating', 'industry', 'beta', 'recommendation_key', 'debt_to_equity']
    for field in sample_fields:
        value = data.get(field)
        if isinstance(value, str) and len(value) > 50:
            value = value[:50] + "..."
        print(f"  {field}: {value}")

    if all_ok:
        print("\n✅ PASSED: All expanded Yahoo Finance fields present and populated")
        return True
    else:
        print("\n❌ FAILED: Some key fields missing values")
        return False


if __name__ == "__main__":
    print("\n" + "="*80)
    print("REIT COMPONENT TESTING SUITE")
    print("="*80 + "\n")

    tests = [
        test_single_reit_data,
        test_get_top_reits_by_market_cap,
        test_multi_reit_analysis,
        test_expanded_yahoo_finance_fields
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ EXCEPTION: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append(False)

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(results)
    total = len(results)

    print(f"\nPassed: {passed}/{total}")

    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  Test {i}: {status}")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} TEST(S) FAILED")
        sys.exit(1)
