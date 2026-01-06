"""
Singapore REIT Analysis Agent

Main entry point that orchestrates the LangGraph agent for analyzing Singapore REITs.
"""
import os
import sys
import asyncio
import uuid
from datetime import datetime
from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from azure_auth import get_azure_ad_token
from state import AgentState
from tools import all_tools
from nodes import (
    collect_user_preferences,
    preference_collector_node,
    preference_parser_node,
    create_reflection_aware_agent_node,
    create_reflection_node,
    tool_router,
    reflection_router,
)

# 1. SETUP & AUTH
load_dotenv()

llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_ad_token_provider=get_azure_ad_token,
    temperature=1
)

# 2. BIND TOOLS TO LLM
llm_with_tools = llm.bind_tools(all_tools)

# Create ToolNode using built-in
tool_node = ToolNode(all_tools)

# Create agent node with reflection awareness
agent_node = create_reflection_aware_agent_node(llm_with_tools)

# Create reflection node (uses base LLM without tools)
reflection_node = create_reflection_node(llm)

# 3. GRAPH CONSTRUCTION
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("preference_collector", preference_collector_node)
workflow.add_node("preference_parser", preference_parser_node)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.add_node("reflection", reflection_node)

# Define flow with reflection loop
workflow.set_entry_point("preference_collector")
workflow.add_edge("preference_collector", "preference_parser")
workflow.add_edge("preference_parser", "agent")
workflow.add_conditional_edges("agent", tool_router, ["tools", "reflection"])
workflow.add_edge("tools", "agent")
workflow.add_conditional_edges("reflection", reflection_router, ["agent", END])

# Compile with checkpointer and interrupt
memory = MemorySaver()
app = workflow.compile(
    checkpointer=memory,
    interrupt_after=["preference_collector"]
)


# 4. PROMPT LOADING
def load_prompt(prompt_file='prompts/reit_audit_prompt.txt', limit=20):
    """
    Load prompt template from file and format with parameters.

    Args:
        prompt_file: Path to prompt template file
        limit: Number of REITs to analyze

    Returns:
        Formatted prompt string
    """
    try:
        with open(prompt_file, 'r') as f:
            template = f.read()
        return template.format(limit=limit)
    except FileNotFoundError:
        print(f"Error: Prompt file '{prompt_file}' not found")
        raise
    except Exception as e:
        print(f"Error loading prompt: {e}")
        raise


# 5. EXECUTION
async def main():
    print("--- REIT ANALYSIS AGENT WITH HUMAN-IN-THE-LOOP ---\n")

    # Generate unique thread ID for state persistence
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Get number of REITs from command line (default: 5)
    num_reits = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"[CONFIG] Analyzing top {num_reits} REITs\n")

    # Load base prompt
    base_prompt = load_prompt(limit=num_reits)

    # Initialize state
    initial_state = {
        "messages": [HumanMessage(content=base_prompt)],
        "user_preferences": {},
        "preferences_collected": False,
        "needs_clarification": False,
        "clarification_question": None,
        # Reflection tracking
        "reflection_count": 0,
        "max_reflections": 2,
        "reflection_feedback": None,
        "analysis_approved": False,
    }

    # Step 1: Start graph execution - will run until interrupt
    print("[AGENT] Initializing...\n")
    async for event in app.astream(initial_state, config, stream_mode="values"):
        # Graph will stop at the interrupt point
        # The preference_collector_node has executed and added its message
        pass

    # Step 2: THE INTERRUPT HAPPENED! Graph is paused.
    # Now collect user preferences with sequential prompts
    user_preferences = collect_user_preferences()

    # Step 3: Resume graph with collected preferences
    # Use update_state to inject preferences into the paused graph
    app.update_state(
        config,
        {
            "user_preferences": user_preferences,
            "preferences_collected": False  # Will be set to True by preference_parser_node
        }
    )

    # Step 4: Continue graph execution to completion
    tool_output = ""
    final_response = ""
    last_reflection_count = 0

    print("[AGENT] Processing analysis...\n")
    async for event in app.astream(None, config, stream_mode="values"):
        last_msg = event["messages"][-1]

        # Track reflection iterations
        current_reflection_count = event.get("reflection_count", 0)
        if current_reflection_count > last_reflection_count:
            print(f"[REFLECTION] Analysis needs improvement (iteration {current_reflection_count})")
            if event.get("reflection_feedback"):
                print(f"[REFLECTION] Feedback: {event['reflection_feedback'][:200]}...\n")
            last_reflection_count = current_reflection_count

        # Log when analysis is approved
        if event.get("analysis_approved") and not final_response:
            print("[REFLECTION] Analysis approved!\n")

        # Capture tool output (contains raw rankings data)
        if hasattr(last_msg, "name") and last_msg.name == "analyze_top_singapore_reits":
            tool_output = last_msg.content
            print("[TOOLS] Data collection complete\n")

        # Store the final agent response (synthesis)
        # Check if tool_calls is empty or doesn't exist
        elif hasattr(last_msg, "content"):
            has_tool_calls = hasattr(last_msg, "tool_calls") and last_msg.tool_calls
            if not has_tool_calls:
                final_response = last_msg.content
                print(f"[AGENT] Analysis complete\n")

    # Generate markdown report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_filename = f"reit_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    markdown_content = f"""# Singapore REIT Analysis Report

**Generated:** {timestamp}
**Query:** Analyze top 20 Singapore REITs with user preferences

---

## Raw Data Table

```
{tool_output if tool_output else "No tool output captured"}
```

---

## AI Analysis & Audit

{final_response if final_response else "No AI analysis captured"}

---

## About This Report

This analysis was generated by an AI agent that:
1. Fetched the top Singapore REITs by market capitalization from Yahoo Finance
2. Collected detailed financial metrics for each REIT
3. Ranked them by multiple performance indicators

**Data Source:** Yahoo Finance
**Analysis Date:** {datetime.now().strftime("%Y-%m-%d")}

### Disclaimer
This report is for informational purposes only and should not be considered as financial advice.
Always conduct your own research and consult with a qualified financial advisor before making investment decisions.
"""

    # Write to file
    with open(output_filename, 'w') as f:
        f.write(markdown_content)

    print("\n" + "="*80)
    print(f"✅ Analysis complete! Report saved to: {output_filename}")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
