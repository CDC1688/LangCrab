"""StateGraph definitions — inner self-correction loop + outer pipeline."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from .nodes import (
    aggregate_results,
    classify,
    decide_to_finish,
    extract_signal,
    fan_out_to_classify,
    format_result,
    load_csv,
    route_after_extract,
    validate,
)
from .schemas import PipelineState, RowState


def build_inner_graph() -> StateGraph:
    """Build the per-row classification graph with self-correction loop.

    Graph structure (mirrors the code_assistant notebook):

        START -> extract_signal -> [already_classified? -> format_result -> END]
                                   [needs_llm? -> classify -> validate
                                       -> [end -> format_result -> END]
                                          [retry -> classify (loop)]]
    """
    builder = StateGraph(RowState)

    # Nodes — retry policy on classify node for LLM API failures
    retry = RetryPolicy(
        max_attempts=3,
        initial_interval=1.0,
        backoff_factor=2.0,
    )
    builder.add_node("extract_signal", extract_signal)
    builder.add_node("classify", classify, retry=retry)
    builder.add_node("validate", validate)
    builder.add_node("format_result", format_result)

    # Edges
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
            "retry": "classify",  # <-- self-correction loop
        },
    )
    builder.add_edge("format_result", END)

    return builder


def build_pipeline() -> StateGraph:
    """Build the outer pipeline graph.

    Graph structure:
        START -> load_csv -> fan_out (Send per row)
            -> classify_row (inner subgraph) -> aggregate -> END
    """
    inner = build_inner_graph()
    inner_compiled = inner.compile()

    # Outer graph
    builder = StateGraph(PipelineState)
    builder.add_node("load_csv", load_csv)
    builder.add_node("classify_row", inner_compiled)
    builder.add_node("aggregate", aggregate_results)

    builder.add_edge(START, "load_csv")
    builder.add_conditional_edges("load_csv", fan_out_to_classify)
    builder.add_edge("classify_row", "aggregate")
    builder.add_edge("aggregate", END)

    return builder


def create_graph(use_checkpointer: bool = True):
    """Create the full pipeline graph, optionally with checkpointing."""
    pipeline = build_pipeline()
    checkpointer = MemorySaver() if use_checkpointer else None
    return pipeline.compile(checkpointer=checkpointer)
