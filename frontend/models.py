"""Pydantic models for the frontend API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class SessionSummary(BaseModel):
    sid: str
    account: str
    model: str
    event_time: str
    primary_category: str
    subcategory: str
    user_intent_summary: str
    language: str
    confidence: str
    iterations: int
    heuristic_classified: bool
    had_errors: bool
    tool_error_count: int
    error_rate: float
    num_messages: int
    annotation_status: Optional[str] = None


class SessionDetail(BaseModel):
    classification: dict
    inner_graph: Optional[dict] = None
    error_report: Optional[dict] = None


class TraceNode(BaseModel):
    id: str
    type: str
    data: dict
    position: dict


class TraceEdge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None
    animated: bool = False
    style: Optional[dict] = None


class TraceGraph(BaseModel):
    nodes: list[TraceNode]
    edges: list[TraceEdge]
    active_path: list[str]
    node_states: dict[str, dict]
    groups: dict[str, dict] = {}
    layers: dict[str, dict] = {}
    retry_loops: list[dict] = []


class TraceEvent(BaseModel):
    type: Literal["node_enter", "node_exit", "edge_traverse", "complete"]
    node: Optional[str] = None
    edge: Optional[dict] = None
    state: Optional[dict] = None
    timestamp: float = 0


class AnnotationCreate(BaseModel):
    status: Literal["approved", "rejected", "flagged", "corrected"]
    corrected_category: Optional[str] = None
    corrected_subcategory: Optional[str] = None
    corrected_confidence: Optional[str] = None
    corrected_language: Optional[str] = None
    notes: Optional[str] = None
    reviewer: Optional[str] = None


class AnnotationRead(BaseModel):
    sid: str
    status: str
    corrected_category: Optional[str] = None
    corrected_subcategory: Optional[str] = None
    corrected_confidence: Optional[str] = None
    corrected_language: Optional[str] = None
    notes: Optional[str] = None
    reviewer: Optional[str] = None
    created_at: str
    updated_at: str


class AnnotationProgress(BaseModel):
    total_sessions: int
    annotated: int
    approved: int
    rejected: int
    flagged: int
    corrected: int
    pending: int
