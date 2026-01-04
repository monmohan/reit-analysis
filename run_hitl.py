"""
Run HITL REIT analysis with simulated input
"""
import asyncio
from unittest.mock import patch
from reit_info_agent import main

# Simulated user input for preferences
simulated_input = """risk: conservative
max_pb: 1.0
"""

async def run_agent():
    """Run the agent with simulated input"""
    print("Running REIT Analysis Agent with HITL...\n")

    # Mock the input() function to provide automated input
    with patch('builtins.input', return_value=simulated_input):
        await main()

if __name__ == "__main__":
    asyncio.run(run_agent())
