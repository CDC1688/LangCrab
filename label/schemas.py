"""State schemas for the label-only pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph.message import AnyMessage, add_messages

from ..schemas import Classification


class LabelRowState(TypedDict):
    """Per-row state for classification."""
    sid: str
    system_prompt_summary: str
    user_messages_text: str
    tool_names_used: list[str]
    num_messages: int
    num_user_messages: int
    is_cron_triggered: bool
    is_subagent: bool

    # Self-correction loop
    error: str
    messages: Annotated[list[AnyMessage], add_messages]
    classification: Classification | None
    iterations: int

    # Output
    classifications: Annotated[list[dict], operator.add]


class LabelPipelineState(TypedDict):
    """Pipeline-level state."""
    csv_path: str
    limit: int
    rows: list[dict]
    classifications: Annotated[list[dict], operator.add]
