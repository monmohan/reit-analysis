"""
Test that preference questions are displayed before user input prompt
"""
import asyncio
from unittest.mock import patch
import sys

async def test_preference_display():
    """Capture output before input prompt to verify questions are displayed"""
    output_lines = []

    # Patch print to capture output
    original_print = print
    def capture_print(*args, **kwargs):
        output_lines.append(' '.join(str(arg) for arg in args))
        original_print(*args, **kwargs)

    # Patch input to provide automated response
    test_input = """objective: income
risk: moderate
min_yield: 5.5
max_pb: 1.0"""

    with patch('builtins.print', side_effect=capture_print):
        with patch('builtins.input', return_value=test_input):
            from reit_info_agent import main
            try:
                await main()
            except Exception as e:
                # We expect it might error on API calls, that's fine
                # We just want to check the initial display
                pass

    # Check that preference questions were displayed
    full_output = '\n'.join(output_lines)

    print("\n" + "="*80)
    print("VERIFICATION: Checking if preference questions were displayed")
    print("="*80)

    checks = [
        ("Investment Objective", "Investment Objective" in full_output),
        ("Risk Tolerance", "Risk Tolerance" in full_output),
        ("Minimum Dividend Yield", "Minimum Dividend Yield" in full_output or "Min" in full_output),
        ("Maximum Price-to-Book", "Maximum Price-to-Book" in full_output or "Max" in full_output),
        ("Format example", "objective:" in full_output),
        ("income option", "income:" in full_output),
        ("conservative option", "conservative:" in full_output),
    ]

    all_passed = True
    for check_name, result in checks:
        status = "✅" if result else "❌"
        print(f"{status} {check_name}: {'Found' if result else 'NOT FOUND'}")
        if not result:
            all_passed = False

    print("="*80)
    if all_passed:
        print("✅ SUCCESS: All preference questions are being displayed!")
    else:
        print("❌ FAILED: Some preference questions are missing")
        print("\nFirst 2000 chars of output:")
        print(full_output[:2000])
    print("="*80)

    return all_passed

if __name__ == "__main__":
    result = asyncio.run(test_preference_display())
    sys.exit(0 if result else 1)
