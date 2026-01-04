# Human-in-the-Loop (HITL) Implementation

## Overview

Successfully implemented interactive preference collection for the Singapore REIT Analysis Agent using LangGraph's checkpointing and interrupt capabilities.

## What Changed

### Core Features Added

1. **Interactive Preference Collection**
   - Agent pauses before analysis to gather user investment preferences
   - 4 simple questions: Investment Objective, Risk Tolerance, Min Yield, Max P/B
   - User provides structured input in key:value format

2. **LangGraph Checkpointing**
   - Uses `MemorySaver` for state persistence
   - Implements `interrupt_before=["preference_collector"]` to pause execution
   - State can be resumed with `app.update_state()`

3. **Preference-Aware Analysis**
   - User preferences are injected into LLM context
   - AI tailors recommendations based on user profile
   - Analysis explicitly acknowledges and applies preferences

## Files Modified

### 1. `reit_info_agent.py` - Main implementation

**Added imports:**
```python
import uuid
from typing import Optional, Literal, Dict
from langgraph.checkpoint.memory import MemorySaver
```

**New State Definitions:**
- `UserPreferences` TypedDict - Stores investment preferences
- Enhanced `AgentState` - Adds preference tracking fields

**New Nodes:**
- `preference_collector_node()` - Displays preference questions
- `preference_parser_node()` - Parses and validates user input
- Enhanced `agent_node()` - Injects preferences into LLM context

**Modified Graph:**
```
Entry → preference_collector → preference_parser → agent → router → [tools → agent] → END
          ↑ INTERRUPT HERE
```

**New Execution Flow:**
- Pauses at preference collection
- Collects user input via `input()`
- Resumes with `app.update_state()`
- Generates preference-aware analysis

### 2. `requirements.txt` - Dependencies

Updated LangGraph version:
```
langgraph>=0.2.0  # (was 0.0.40)
```
Version 0.2.0+ required for checkpointing support.

## How to Use

### Running the Agent

```bash
python3 reit_info_agent.py
```

### User Interaction Flow

**Step 1:** Agent displays preference questions:
```
Before I analyze Singapore REITs for you, I need to understand your investment profile:

1. Investment Objective: What are you primarily seeking?
   - income: High dividend yield, regular payouts
   - preservation: Capital safety, defensive assets
   - growth: Capital appreciation potential
   - balanced: Mix of income and growth

2. Risk Tolerance:
   - conservative: Minimize volatility, prefer blue-chip sponsors
   - moderate: Balanced risk-reward
   - aggressive: Higher risk acceptable for better returns

3. Minimum Dividend Yield (% or 'none'):
   - Example: 6.0 for 6% minimum yield

4. Maximum Price-to-Book (ratio or 'none'):
   - Example: 1.0 for value investing focus

Please provide your preferences in this format:
objective: [your choice]
risk: [your choice]
min_yield: [number or none]
max_pb: [number or none]
```

**Step 2:** User enters preferences:
```
objective: income
risk: conservative
min_yield: 6.0
max_pb: 1.0
```

**Step 3:** Agent processes and generates analysis

## Example Output

The AI explicitly acknowledges user preferences in the analysis:

> "I'll then apply your conservative-income brief (min_yield 6.0, max_pb 1.0) in the qualitative ranking."

The analysis is then tailored to match the specified investment profile, prioritizing:
- High dividend yields (≥6.0%)
- Value investing (P/B ≤1.0)
- Conservative risk profile
- Income generation over growth

## Technical Details

### State Persistence

Each conversation has a unique `thread_id` generated with `uuid.uuid4()`:
```python
thread_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}
```

State persists through the checkpointer and can be resumed after interrupts.

### Preference Injection

User preferences are prepended to the message history before each LLM call:

```python
if state["preferences_collected"] and preferences:
    pref_context = """
CRITICAL INSTRUCTION: USER INVESTMENT PROFILE
============================================
Investment Objective: {objective}
Risk Tolerance: {risk}
Minimum Dividend Yield: {min_yield}%
Maximum Price-to-Book: {max_pb}
============================================
"""
    enriched_messages = [HumanMessage(content=pref_context)] + messages
    response = llm_with_tools.invoke(enriched_messages)
```

This ensures the LLM always has access to user preferences when generating responses.

### Input Validation

The `preference_parser_node` validates user input:
- Checks for valid enum values (objective, risk)
- Converts numeric values with try/except
- Handles malformed input gracefully
- Provides warnings for invalid values

## Testing

### Verified Functionality

✅ Graph interrupts at preference_collector node
✅ User input is collected synchronously during async stream
✅ State persists through checkpointer
✅ Preferences are parsed correctly
✅ Agent receives preference context
✅ Analysis reflects user preferences
✅ Markdown report is generated successfully
✅ Invalid input handled gracefully

### Test Results

Successfully tested with:
- Valid complete input (all 4 fields)
- Partial input (missing optional fields)
- Invalid input (wrong enum values, non-numeric values)
- Empty input (defaults applied)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ User starts agent                                           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ preference_collector_node                                   │
│ - Displays questions                                        │
│ ⚠️  INTERRUPT: Execution pauses here                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼ User provides input
┌─────────────────────────────────────────────────────────────┐
│ preference_parser_node                                      │
│ - Parses key:value pairs                                   │
│ - Validates input                                           │
│ - Stores in state["user_preferences"]                      │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ agent_node (enhanced)                                       │
│ - Injects preference context into messages                 │
│ - Calls LLM with enriched context                          │
│ - Decides to call tools                                     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ tools (analyze_top_singapore_reits)                        │
│ - Fetches REIT data from Yahoo Finance                    │
│ - Returns quantitative table                               │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ agent_node (synthesis)                                      │
│ - Analyzes data with preference awareness                  │
│ - Generates tailored recommendations                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Markdown Report Generation                                  │
│ - Saves to reit_analysis_YYYYMMDD_HHMMSS.md               │
└─────────────────────────────────────────────────────────────┘
```

## Future Enhancements

Potential Phase 2 features (not yet implemented):

1. **Mid-Analysis Clarifications**
   - `clarification_check_node` to ask adaptive questions
   - Detect anomalies (yield traps, constraint conflicts)
   - Additional interrupt points

2. **Tool-Level Filtering**
   - Filter REITs in `analyze_top_singapore_reits` based on preferences
   - Apply min_yield and max_pb thresholds early

3. **Natural Language Parsing**
   - Use LLM to parse free-form preference input
   - Convert conversational input to structured preferences

4. **Preference Profiles**
   - Save common preference profiles
   - Quick-select presets (e.g., "Conservative Retiree", "Growth Investor")

5. **Interactive CLI**
   - Use `rich` or `questionary` for better UX
   - Progress bars, formatted tables, colored output

## Notes

- **Backward Compatibility:** Original functionality preserved; preferences optional
- **Error Handling:** Robust validation with graceful degradation
- **Performance:** No significant overhead; checkpoint operations are fast
- **Scalability:** `MemorySaver` is in-memory; consider SQLite for production

## Success Criteria - All Met ✅

✅ Functional:
- Graph pauses for user input at preference_collector
- User provides 4 simple preferences
- Preferences are parsed and stored in state
- Agent analysis reflects user preferences
- Report generation works as before

✅ Non-functional:
- No breaking changes to existing autonomous mode
- Error handling for invalid inputs
- Clear user prompts and instructions
- Async execution maintained
