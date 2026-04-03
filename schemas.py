"""State schemas and Pydantic classification model."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import AnyMessage, add_messages
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Structured LLM output — Classification
# ---------------------------------------------------------------------------

CATEGORIES = [
    "coding",
    "file_management",
    "web_research",
    "scheduling",
    "communication",
    "data_analysis",
    "system_maintenance",
    "content_creation",
    "finance_crypto",
    "memory_management",
    "agent_orchestration",
    "other",
]

CategoryType = Literal[
    "coding",
    "file_management",
    "web_research",
    "scheduling",
    "communication",
    "data_analysis",
    "system_maintenance",
    "content_creation",
    "finance_crypto",
    "memory_management",
    "agent_orchestration",
    "other",
]


class Classification(BaseModel):
    """Structured classification output from the LLM."""

    primary_category: CategoryType = Field(
        description="The main category of the user's intent"
    )
    subcategory: str = Field(
        description="Fine-grained subcategory within the primary category"
    )
    user_intent_summary: str = Field(
        description="1-2 sentence summary of what the user is trying to do"
    )
    language: str = Field(
        description="Primary language of the user messages: 'english', 'chinese', or language name in lowercase for others (e.g., 'russian', 'malay', 'japanese')"
    )
    is_cron_triggered: bool = Field(
        description="Whether this session was triggered by a cron/scheduled task"
    )
    is_subagent: bool = Field(
        description="Whether this is a sub-agent session spawned by another agent"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence in the classification"
    )


# ---------------------------------------------------------------------------
# Inner graph state — per-row, mirrors the code_assistant notebook pattern
# ---------------------------------------------------------------------------


class RowState(TypedDict):
    # Input fields (set once by extract_signal)
    sid: str
    account: str
    model: str
    event_time: str
    source_file: str
    system_prompt_summary: str
    user_messages_text: str
    tool_names_used: list[str]
    num_messages: int
    num_user_messages: int
    is_cron_triggered: bool
    is_subagent: bool

    # Agent error fields (from parser.extract_tool_errors)
    tool_errors: list[dict]
    tool_error_count: int
    tool_success_count: int
    error_rate: float
    error_types: list[str]
    consecutive_error_max: int
    token_usage: dict
    finish_reason: str

    # Self-correction loop fields
    error: str  # "yes" / "no" control flow flag
    messages: Annotated[list[AnyMessage], add_messages]
    classification: Classification | None
    iterations: int

    # Output field — maps to PipelineState.classifications via subgraph key matching
    classifications: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# Outer graph state — pipeline
# ---------------------------------------------------------------------------


class PipelineState(TypedDict):
    csv_paths: list[str]  # one or more CSV files
    limit: int  # 0 = all rows, per file
    continue_mode: bool  # resume from previous run
    rows: list[dict]
    classifications: Annotated[list[dict], operator.add]
    prior_classifications: list[dict]  # loaded from previous run
    summary: dict | None
