"""
State definitions for the REIT Analysis Agent.
"""
import operator
from typing import TypedDict, Annotated, List, Optional, Literal

from langchain_core.messages import BaseMessage


class UserPreferences(TypedDict):
    """Structured storage for user investment preferences"""
    risk_tolerance: Optional[Literal["conservative", "moderate"]]
    max_price_to_book: Optional[float]


class AgentState(TypedDict):
    """Extended state with HITL and reflection support"""
    messages: Annotated[List[BaseMessage], operator.add]
    user_preferences: UserPreferences
    preferences_collected: bool
    needs_clarification: bool
    clarification_question: Optional[str]
    # Reflection tracking
    reflection_count: int               # Current retry count (starts at 0)
    max_reflections: int                # Max retries allowed (default: 2)
    reflection_feedback: Optional[str]  # Feedback for agent if needs improvement
    analysis_approved: bool             # True when reflection approves
