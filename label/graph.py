"""LangGraph definitions for the label-only pipeline."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from .nodes import (
    classify,
    decide_to_finish,
    extract_signal,
    fan_out_to_classify,
    format_result,
    load_csv,
    route_after_extract,
    save_to_csv,
    validate,
)
from .schemas import LabelPipelineState, LabelRowState


def build_inner_graph() -> StateGraph:
    """Per-row classification graph with self-correction loop.

        START -> extract_signal -> [already_classified? -> format_result -> END]
                                   [needs_llm? -> classify -> validate
                                       -> [end -> format_result -> END]
                                          [retry -> classify (loop)]]
    """
    builder = StateGraph(LabelRowState)

    retry = RetryPolicy(
        max_attempts=3,
        initial_interval=1.0,
        backoff_factor=2.0,
    )
    builder.add_node("extract_signal", extract_signal)
    builder.add_node("classify", classify, retry=retry)
    builder.add_node("validate", validate)
    builder.add_node("format_result", format_result)

    builder.add_edge(START, "extract_signal")
    builder.add_conditional_edges(
        "extract_signal",
        route_after_extract,
        {
            "already_classified": "format_result",
            "needs_llm": "classify",
        },
    )
    builder.add_edge("classify", "validate")
    builder.add_conditional_edges(
        "validate",
        decide_to_finish,
        {
            "end": "format_result",
            "retry": "classify",
        },
    )
    builder.add_edge("format_result", END)

    return builder


def build_pipeline() -> StateGraph:
    """Outer pipeline: load CSV -> classify rows -> save back to CSV.

        START -> load_csv -> fan_out (Send per row)
            -> classify_row (inner subgraph) -> save_to_csv -> END
    """
    inner = build_inner_graph()
    inner_compiled = inner.compile()

    builder = StateGraph(LabelPipelineState)
    builder.add_node("load_csv", load_csv)
    builder.add_node("classify_row", inner_compiled)
    builder.add_node("save_to_csv", save_to_csv)

    builder.add_edge(START, "load_csv")
    builder.add_conditional_edges("load_csv", fan_out_to_classify)
    builder.add_edge("classify_row", "save_to_csv")
    builder.add_edge("save_to_csv", END)

    return builder


def create_graph(use_checkpointer: bool = True):
    """Create the label pipeline graph."""
    pipeline = build_pipeline()
    checkpointer = MemorySaver() if use_checkpointer else None
    return pipeline.compile(checkpointer=checkpointer)
