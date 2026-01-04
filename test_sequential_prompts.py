"""
Test the new sequential prompts with interrupt mechanism
"""
import asyncio
from unittest.mock import patch
import sys

async def test_sequential_prompts():
    """Test the sequential prompt flow with mocked input"""
    print("Testing sequential prompts with interrupt mechanism...")
    print("=" * 80)

    # Simulate user input for the 2 sequential prompts
    user_inputs = iter([
        "conservative", # Risk tolerance
        "1.0"          # Max P/B
    ])

    # Mock input() to provide automated responses
    with patch('builtins.input', side_effect=user_inputs):
        from reit_info_agent import main
        try:
            await main()
            print("\n" + "=" * 80)
            print("✅ Test completed successfully!")
            print("=" * 80)
            return True
        except Exception as e:
            print(f"\n❌ Error during test: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    result = asyncio.run(test_sequential_prompts())
    sys.exit(0 if result else 1)
