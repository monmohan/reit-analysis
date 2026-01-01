import os
import asyncio
import operator
from typing import TypedDict, Annotated, List
from dotenv import load_dotenv

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

from azure_auth import get_azure_ad_token

# 1. SETUP & AUTH
load_dotenv()

llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_ad_token_provider=get_azure_ad_token,
    temperature=0
)

# 2. DEFINING TOOLS
@tool
def multiply(a: int, b: int) -> int:
    """Multiplies two integers."""
    return a * b

@tool
def get_weather(city: str) -> str:
    """Returns weather info for a city."""
    return f"The weather in {city} is 25C and Sunny."

tools = [multiply, get_weather]
tool_map = {t.name: t for t in tools}

# Bind tools to LLM (The Schema)
llm_with_tools = llm.bind_tools(tools)

# 3. STATE DEFINITION
class AgentState(TypedDict):
    # This is the "Whiteboard". We APPEND messages to it.
    messages: Annotated[List[BaseMessage], operator.add]

# 4. NODES (The Workers)
def agent_node(state: AgentState):
    """The Brain: Decides what to do."""
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def tool_node(state: AgentState):
    """The Hands: Executes the tool."""
    last_message = state["messages"][-1]

    results = []
    for tool_call in last_message.tool_calls:
        print(f"  [System] Executing Tool: {tool_call['name']} with args: {tool_call['args']}")

        # Execute Python function
        action = tool_map[tool_call["name"]]
        output = action.invoke(tool_call["args"])

        # Create ToolMessage (Result)
        results.append(ToolMessage(
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
            content=str(output)
        ))

    return {"messages": results}

# 5. EDGES (The Router)
def router(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# 6. GRAPH CONSTRUCTION
workflow = StateGraph(AgentState)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("agent")

workflow.add_conditional_edges("agent", router, ["tools", END])
workflow.add_edge("tools", "agent")  # Automatic feedback loop

app = workflow.compile()

# 7. EXECUTION
async def main():
    print("--- STARTING AGENT V1 ---")
    user_input = "Calculate 15 * 4, and then tell me the weather in Singapore."
    inputs = {"messages": [HumanMessage(content=user_input)]}

    # We stream the output to see the steps
    async for event in app.astream(inputs):
        for key, value in event.items():
            print(f"\n[Node: {key}]")
            last_msg = value["messages"][-1]
            
            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                print(f"  -> Decision: Call Tools ({len(last_msg.tool_calls)})")
            elif isinstance(last_msg, ToolMessage):
                print(f"  -> Result: {last_msg.content}")
            else:
                print(f"  -> Response: {last_msg.content}")

if __name__ == "__main__":
    asyncio.run(main())