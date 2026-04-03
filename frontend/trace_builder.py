"""Transform agent traces into React Flow graph data.

Builds a **real DAG** showing agent behavior:
  - Parallel tool calls fan out from an agent decision node to individual
    tool-result nodes, then converge back.
  - Error results branch into a retry path vs. normal continuation.
  - Turns are visually grouped with shared Y bands.

Node layout strategy (X axis):
  x=300  center spine: system, user, assistant, agent-decision, converge
  x=<spread>  tool results fan out symmetrically around center
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Outer pipeline graph (unchanged)
# ---------------------------------------------------------------------------

OUTER_NODE_POSITIONS = {
    "start": {"x": 250, "y": 0},
    "load_csv": {"x": 250, "y": 100},
    "fan_out": {"x": 250, "y": 220},
    "classify_row": {"x": 250, "y": 360},
    "aggregate": {"x": 250, "y": 500},
    "end": {"x": 250, "y": 600},
}


def build_outer_graph(summary: dict, session_count: int) -> dict:
    """Build React Flow graph data for the outer pipeline."""
    nodes = []
    for node_id, pos in OUTER_NODE_POSITIONS.items():
        node_data = {
            "label": node_id.replace("_", " ").title() if node_id not in ("start", "end") else node_id.upper(),
            "status": "success",
            "nodeId": node_id,
        }
        if node_id == "classify_row":
            node_data["label"] = "Classify Row"
            node_data["sessionCount"] = session_count
            heur = summary.get("heuristic_count", 0)
            llm = summary.get("llm_count", 0)
            retries = summary.get("retry_count", 0)
            node_data["preview"] = f"{heur} heuristic, {llm} LLM, {retries} retries"
            node_data["isExpandable"] = True
        if node_id == "load_csv":
            node_data["preview"] = f"{session_count} rows loaded"
        if node_id == "aggregate":
            cats = summary.get("category_counts", {})
            top = sorted(cats.items(), key=lambda x: -x[1])[:3]
            node_data["preview"] = ", ".join(f"{c}({n})" for c, n in top)

        nodes.append({
            "id": node_id,
            "type": "graphNode" if node_id not in ("start", "end") else "startEnd",
            "position": pos,
            "data": node_data,
        })

    edges = [
        {"id": "e-start-load", "source": "start", "target": "load_csv", "style": {"stroke": "#4CAF50", "strokeWidth": 2}},
        {"id": "e-load-fan", "source": "load_csv", "target": "fan_out", "style": {"stroke": "#4CAF50", "strokeWidth": 2}},
        {"id": "e-fan-classify", "source": "fan_out", "target": "classify_row", "label": f"Send × {session_count}", "style": {"stroke": "#2196F3", "strokeWidth": 2}},
        {"id": "e-classify-agg", "source": "classify_row", "target": "aggregate", "style": {"stroke": "#4CAF50", "strokeWidth": 2}},
        {"id": "e-agg-end", "source": "aggregate", "target": "end", "style": {"stroke": "#4CAF50", "strokeWidth": 2}},
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "active_path": list(OUTER_NODE_POSITIONS.keys()),
        "node_states": {},
    }


# ---------------------------------------------------------------------------
# Agent behavior graph — real DAG
# ---------------------------------------------------------------------------

STEP_COLORS = {
    "system": {"border": "#7B1FA2", "bg": "#F3E5F5"},
    "user": {"border": "#1565C0", "bg": "#E3F2FD"},
    "tool_calls": {"border": "#E65100", "bg": "#FFF3E0"},
    "tool_result": {"border": "#2E7D32", "bg": "#E8F5E9"},
    "tool_result_error": {"border": "#C62828", "bg": "#FFEBEE"},
    "assistant": {"border": "#2E7D32", "bg": "#E8F5E9"},
    "converge": {"border": "#546E7A", "bg": "#ECEFF1"},
}

# Layout constants
CENTER_X = 300         # spine x position
TOOL_SPACING_X = 220   # horizontal spread between parallel tool result nodes
Y_STEP = 100           # vertical step for sequential nodes
Y_STEP_SMALL = 80      # vertical step within a fan-out band
NODE_WIDTH_WIDE = 500   # wide node width (for centering calculation)


def build_agent_graph(
    agent_trace: list[dict],
    classification: dict = None,
    error_report: dict = None,
) -> dict:
    """Build a real DAG from agent trace steps.

    Structure per agent-decision turn:

        ... prev_node ...
              │
        ┌─────────────┐
        │ Agent Decision│  (tool_calls step — the decision point)
        └──┬──┬──┬──┬──┘
           │  │  │  │      fan-out edges
         ┌─┘  │  │  └─┐
        res₁ res₂ res₃ res₄   (individual tool_result nodes)
         └─┐  │  │  ┌─┘
           │  │  │  │      converge edges
        ┌──┴──┴──┴──┴──┐
        │   Converge    │  (synthetic join point)
        └──────┬────────┘
               │
        ... next node ...

    For single tool calls the fan-out still happens (1 child), keeping the
    topology consistent.  Error results get red edges and an ``errorBranch``
    flag so the frontend can highlight retry paths.

    Returns: {nodes, edges, active_path, node_states, turns}
    """
    if not agent_trace:
        return {"nodes": [], "edges": [], "active_path": [], "node_states": {}, "turns": []}

    # Build error lookup by message position from error_report
    error_by_position: dict[int, dict] = {}
    if error_report:
        for err in error_report.get("tool_errors", []):
            pos = err.get("position")
            if pos is not None:
                error_by_position[pos] = err

    # Pre-process: build structured turns from the flat step list.
    turns = _build_structured_turns(agent_trace)

    nodes: list[dict] = []
    edges: list[dict] = []
    node_states: dict[str, dict] = {}
    active_path: list[str] = []
    y = 0

    # Track the *last emitted node id* so we can wire sequential edges.
    prev_node_id: str | None = None

    for turn_idx, turn in enumerate(turns):
        turn_type = turn["type"]

        # ---- simple single-step turns: system / user / assistant ----
        if turn_type in ("system", "user", "assistant"):
            step = turn["steps"][0]
            node_id = f"step_{step['idx']}"
            node_data = _make_node_data(node_id, step, turn_idx, error_by_position)
            node_type = "agentNodeWide"

            nodes.append({
                "id": node_id,
                "type": node_type,
                "position": {"x": CENTER_X - NODE_WIDTH_WIDE // 2 + 50, "y": y},
                "data": node_data,
            })
            active_path.append(node_id)
            node_states[node_id] = _make_node_state(step, agent_trace, error_by_position)

            if prev_node_id:
                edges.append(_make_edge(prev_node_id, node_id, step, error_by_position))

            prev_node_id = node_id
            y += Y_STEP

        # ---- agent action turn: tool_calls + tool_results (+ optional trailing assistant) ----
        elif turn_type == "agent_action":
            tc_step = turn["tool_calls_step"]
            result_steps = turn["result_steps"]
            trailing_assistant = turn.get("trailing_assistant")

            # 1) Agent Decision node (the tool_calls message)
            tc_node_id = f"step_{tc_step['idx']}"
            tc_data = _make_node_data(tc_node_id, tc_step, turn_idx, error_by_position)
            nodes.append({
                "id": tc_node_id,
                "type": "agentNode",
                "position": {"x": CENTER_X - 100, "y": y},
                "data": tc_data,
            })
            active_path.append(tc_node_id)
            node_states[tc_node_id] = _make_node_state(tc_step, agent_trace, error_by_position)

            if prev_node_id:
                edges.append(_make_edge(prev_node_id, tc_node_id, tc_step, error_by_position))

            y += Y_STEP

            # 2) Fan-out: individual tool result nodes
            n_results = len(result_steps)
            result_node_ids: list[str] = []

            if n_results == 0:
                # Edge case: tool_calls with no results (truncated trace)
                prev_node_id = tc_node_id
            elif n_results == 1:
                # Single tool — keep it on the center spine
                rs = result_steps[0]
                rs_id = f"step_{rs['idx']}"
                rs_data = _make_node_data(rs_id, rs, turn_idx, error_by_position)
                nodes.append({
                    "id": rs_id,
                    "type": "agentNode",
                    "position": {"x": CENTER_X - 80, "y": y},
                    "data": rs_data,
                })
                active_path.append(rs_id)
                node_states[rs_id] = _make_node_state(rs, agent_trace, error_by_position)

                # Edge: decision → result
                edges.append(_make_edge(tc_node_id, rs_id, rs, error_by_position))
                result_node_ids.append(rs_id)
                y += Y_STEP_SMALL
                prev_node_id = rs_id
            else:
                # Multiple tools — fan out horizontally
                total_width = (n_results - 1) * TOOL_SPACING_X
                start_x = CENTER_X - total_width // 2

                for i, rs in enumerate(result_steps):
                    rs_id = f"step_{rs['idx']}"
                    rs_data = _make_node_data(rs_id, rs, turn_idx, error_by_position)
                    rx = start_x + i * TOOL_SPACING_X - 80
                    nodes.append({
                        "id": rs_id,
                        "type": "agentNode",
                        "position": {"x": rx, "y": y},
                        "data": rs_data,
                    })
                    active_path.append(rs_id)
                    node_states[rs_id] = _make_node_state(rs, agent_trace, error_by_position)

                    # Edge: decision → this result (fan-out)
                    e = _make_edge(tc_node_id, rs_id, rs, error_by_position)
                    e["type"] = "smoothstep"
                    edges.append(e)
                    result_node_ids.append(rs_id)

                y += Y_STEP

                # 3) Converge node — synthetic join point after parallel results
                has_any_error = any(
                    rs.get("is_error") for rs in result_steps
                )
                conv_id = f"converge_{tc_step['idx']}"
                conv_colors = STEP_COLORS["tool_result_error"] if has_any_error else STEP_COLORS["converge"]

                n_ok = sum(1 for rs in result_steps if not rs.get("is_error"))
                n_err = n_results - n_ok
                conv_label = f"{n_ok} ok"
                if n_err:
                    conv_label += f", {n_err} err"

                nodes.append({
                    "id": conv_id,
                    "type": "convergeNode",
                    "position": {"x": CENTER_X - 60, "y": y},
                    "data": {
                        "nodeId": conv_id,
                        "stepType": "converge",
                        "label": conv_label,
                        "borderColor": conv_colors["border"],
                        "bgColor": conv_colors["bg"],
                        "turnIndex": turn_idx,
                        "resultCount": n_results,
                        "errorCount": n_err,
                        "status": "error" if has_any_error else "success",
                    },
                })
                active_path.append(conv_id)
                node_states[conv_id] = {
                    "input": {
                        "type": "converge",
                        "results": [
                            {
                                "tool": rs.get("tool_name", "?"),
                                "ok": not rs.get("is_error", False),
                            }
                            for rs in result_steps
                        ],
                    },
                    "output": {"total": n_results, "errors": n_err},
                }

                # Edges: each result → converge
                for rs_id_c in result_node_ids:
                    rs_node_data = node_states[rs_id_c]["output"]
                    is_err = rs_node_data.get("is_error", False)
                    style = {
                        "stroke": "#C62828" if is_err else "#546E7A",
                        "strokeWidth": 1.5,
                    }
                    if is_err:
                        style["strokeDasharray"] = "5,3"
                    edges.append({
                        "id": f"e-{rs_id_c}-{conv_id}",
                        "source": rs_id_c,
                        "target": conv_id,
                        "type": "smoothstep",
                        "style": style,
                    })

                y += Y_STEP_SMALL
                prev_node_id = conv_id

            # 4) Trailing assistant response (if this turn ends with text)
            if trailing_assistant:
                ast_step = trailing_assistant
                ast_id = f"step_{ast_step['idx']}"
                ast_data = _make_node_data(ast_id, ast_step, turn_idx, error_by_position)
                nodes.append({
                    "id": ast_id,
                    "type": "agentNodeWide",
                    "position": {"x": CENTER_X - NODE_WIDTH_WIDE // 2 + 50, "y": y},
                    "data": ast_data,
                })
                active_path.append(ast_id)
                node_states[ast_id] = _make_node_state(ast_step, agent_trace, error_by_position)

                if prev_node_id:
                    edges.append(_make_edge(prev_node_id, ast_id, ast_step, error_by_position))
                prev_node_id = ast_id
                y += Y_STEP

    # ---- Classification node (appended at the end) ----
    if classification:
        cls_id = "classification"
        nodes.append({
            "id": cls_id,
            "type": "agentNode",
            "position": {"x": CENTER_X - 80, "y": y},
            "data": {
                "nodeId": cls_id,
                "stepType": "classification",
                "label": f"Classification: {classification.get('primary_category', '?')}",
                "preview": classification.get("user_intent_summary", ""),
                "status": "active",
                "borderColor": "#4527A0",
                "bgColor": "#EDE7F6",
            },
        })
        node_states[cls_id] = {"input": {}, "output": classification}
        if prev_node_id:
            edges.append({
                "id": f"e-{prev_node_id}-{cls_id}",
                "source": prev_node_id,
                "target": cls_id,
                "style": {"stroke": "#4527A0", "strokeWidth": 1.5, "strokeDasharray": "5,5"},
            })
        active_path.append(cls_id)

    return {
        "nodes": nodes,
        "edges": edges,
        "active_path": active_path,
        "node_states": node_states,
        "turns": [
            {
                "turn_index": i,
                "step_count": len(t.get("steps", [])),
                "type": t["type"],
            }
            for i, t in enumerate(turns)
        ],
    }


def build_replay_events(session_data: dict) -> list[dict]:
    """Build ordered trace events for WebSocket replay.

    Walks the ``active_path`` of the built graph so replay follows the real
    DAG order (including converge nodes).
    """
    agent_trace = session_data.get("agent_trace", [])
    if not agent_trace:
        return [{"type": "complete", "timestamp": 0}]

    # Build the graph to get the authoritative node order
    classification = session_data.get("classification")
    error_report = session_data.get("error_report")
    graph = build_agent_graph(agent_trace, classification, error_report)
    ordered_ids = graph.get("active_path", [])
    edge_set = {(e["source"], e["target"]) for e in graph.get("edges", [])}
    node_state_map = graph.get("node_states", {})

    DELAYS = {
        "system": 50,
        "user": 120,
        "tool_calls": 80,
        "tool_result": 40,
        "converge": 30,
        "assistant": 120,
        "classification": 60,
    }

    events: list[dict] = []
    t = 0

    for i, nid in enumerate(ordered_ids):
        state = node_state_map.get(nid, {})
        # Determine step type from output or node id
        step_type = ""
        if nid.startswith("converge"):
            step_type = "converge"
        elif nid == "classification":
            step_type = "classification"
        else:
            out = state.get("output", {})
            step_type = out.get("step_type", state.get("input", {}).get("type", ""))
            # Fallback: check if output has tool_name → tool_result, calls → tool_calls, etc.
            if "tool_name" in out:
                step_type = "tool_result"
            elif "calls" in out:
                step_type = "tool_calls"
            elif "content" in out and "tool_name" not in out:
                step_type = "assistant"

        delay = DELAYS.get(step_type, 60)

        events.append({"type": "node_enter", "node": nid, "timestamp": t})
        t += delay
        events.append({
            "type": "node_exit",
            "node": nid,
            "state": state.get("output", {}),
            "timestamp": t,
        })
        t += delay // 3

        # Edges to next node(s)
        if i < len(ordered_ids) - 1:
            next_id = ordered_ids[i + 1]
            if (nid, next_id) in edge_set:
                events.append({
                    "type": "edge_traverse",
                    "edge": {"source": nid, "target": next_id},
                    "timestamp": t,
                })
                t += delay // 4

    events.append({"type": "complete", "timestamp": t})
    return events


# ---------------------------------------------------------------------------
# Structured turn builder
# ---------------------------------------------------------------------------

def _build_structured_turns(steps: list[dict]) -> list[dict]:
    """Parse the flat step list into structured turns.

    Returns a list of turn dicts.  Each has a ``type`` field:

    - ``"system"``    – single system prompt step
    - ``"user"``      – single user message step
    - ``"assistant"``  – standalone assistant response (no preceding tool_calls)
    - ``"agent_action"`` – an agent decision with tool results:
        * ``tool_calls_step``: the tool_calls step
        * ``result_steps``:    list of tool_result steps (matched by tool_call_id)
        * ``trailing_assistant``: optional assistant step following the results

    Every step appears in ``turn["steps"]`` for backward compat.
    """
    turns: list[dict] = []

    # First pass: build tool_call_id → tool_calls step index for matching
    # results back to their parent tool_calls message.
    tc_step_by_call_id: dict[str, dict] = {}
    for step in steps:
        if step["type"] == "tool_calls":
            for call in step.get("tool_calls", []):
                call_id = call.get("id", "")
                if call_id:
                    tc_step_by_call_id[call_id] = step

    i = 0
    while i < len(steps):
        step = steps[i]

        if step["type"] == "system":
            turns.append({"type": "system", "steps": [step]})
            i += 1

        elif step["type"] == "user":
            turns.append({"type": "user", "steps": [step]})
            i += 1

        elif step["type"] == "tool_calls":
            # Gather the tool_call ids from this decision
            call_ids = {c.get("id", "") for c in step.get("tool_calls", []) if c.get("id")}

            # Collect subsequent tool_result steps that belong to this call
            result_steps: list[dict] = []
            j = i + 1
            while j < len(steps) and steps[j]["type"] == "tool_result":
                tc_id = steps[j].get("tool_call_id", "")
                if call_ids and tc_id and tc_id not in call_ids:
                    # Result belongs to a different tool_calls — stop
                    break
                result_steps.append(steps[j])
                j += 1

            # Check for trailing assistant (text response after results)
            trailing_assistant = None
            if j < len(steps) and steps[j]["type"] == "assistant":
                trailing_assistant = steps[j]
                j += 1

            all_steps = [step] + result_steps
            if trailing_assistant:
                all_steps.append(trailing_assistant)

            turns.append({
                "type": "agent_action",
                "steps": all_steps,
                "tool_calls_step": step,
                "result_steps": result_steps,
                "trailing_assistant": trailing_assistant,
            })
            i = j

        elif step["type"] == "assistant":
            # Standalone assistant response (not preceded by tool_calls)
            turns.append({"type": "assistant", "steps": [step]})
            i += 1

        elif step["type"] == "tool_result":
            # Orphan tool_result not preceded by tool_calls (shouldn't happen
            # normally but handle gracefully).
            turns.append({"type": "assistant", "steps": [step]})
            i += 1

        else:
            i += 1

    return turns


# ---------------------------------------------------------------------------
# Node/edge builders
# ---------------------------------------------------------------------------

def _make_node_data(node_id: str, step: dict, turn_idx: int, error_map: dict) -> dict:
    """Build the ``data`` payload for a React Flow node from a trace step."""
    step_type = step["type"]

    if step_type == "tool_result" and step.get("is_error"):
        color_key = "tool_result_error"
    else:
        color_key = step_type
    colors = STEP_COLORS.get(color_key, STEP_COLORS["assistant"])

    node_data: dict[str, Any] = {
        "nodeId": node_id,
        "stepType": step_type,
        "turnIndex": turn_idx,
        "borderColor": colors["border"],
        "bgColor": colors["bg"],
    }

    if step_type == "system":
        node_data["label"] = "System Prompt"
        node_data["preview"] = step["content"][:80]
        node_data["status"] = "active"

    elif step_type == "user":
        node_data["label"] = "User"
        node_data["preview"] = step["content"][:120]
        node_data["status"] = "active"

    elif step_type == "tool_calls":
        call_names = [c["name"] for c in step.get("tool_calls", [])]
        n = len(call_names)
        node_data["label"] = f"Agent Decision ({n} tool{'s' if n != 1 else ''})"
        node_data["toolNames"] = call_names
        node_data["preview"] = ", ".join(call_names)
        node_data["status"] = "active"
        if step.get("content"):
            node_data["agentText"] = step["content"][:200]

    elif step_type == "tool_result":
        tool_name = step.get("tool_name", "?")
        is_error = step.get("is_error", False)
        node_data["label"] = f"{tool_name}"
        node_data["toolName"] = tool_name
        node_data["isError"] = is_error
        node_data["preview"] = step["content"][:120]
        node_data["status"] = "error" if is_error else "success"

        err_detail = error_map.get(step.get("idx"))
        if err_detail:
            node_data["errorType"] = err_detail.get("error_type", "")
            node_data["recovered"] = err_detail.get("recovered", False)

    elif step_type == "assistant":
        node_data["label"] = "Agent Response"
        node_data["preview"] = step["content"][:120]
        node_data["status"] = "success"

    return node_data


def _make_node_state(step: dict, all_steps: list[dict], error_map: dict) -> dict:
    """Build ``{input, output}`` for the StatePanel."""
    step_output = _build_step_output(step)
    err_detail = error_map.get(step.get("idx"))
    if err_detail:
        step_output["error_detail"] = {
            "error_type": err_detail.get("error_type", ""),
            "error_text": err_detail.get("error_text", ""),
            "recovered": err_detail.get("recovered", False),
            "recovery_message": err_detail.get("recovery_message", ""),
            "previous_summary": err_detail.get("previous_summary", ""),
            "current_summary": err_detail.get("current_summary", ""),
            "position": err_detail.get("position", 0),
        }
    return {
        "input": _build_step_input(step, all_steps),
        "output": step_output,
    }


def _make_edge(source_id: str, target_id: str, target_step: dict, error_map: dict) -> dict:
    """Build an edge dict between two nodes."""
    step_type = target_step.get("type", "")
    is_error = target_step.get("is_error", False)

    if is_error:
        color_key = "tool_result_error"
    elif step_type in STEP_COLORS:
        color_key = step_type
    else:
        color_key = "assistant"
    colors = STEP_COLORS.get(color_key, STEP_COLORS["assistant"])

    style: dict[str, Any] = {"stroke": colors["border"], "strokeWidth": 1.5}
    edge: dict[str, Any] = {
        "id": f"e-{source_id}-{target_id}",
        "source": source_id,
        "target": target_id,
        "style": style,
    }

    if is_error:
        style["strokeDasharray"] = "5,3"
        edge["label"] = "error"
        edge["labelStyle"] = {"fill": "#C62828", "fontSize": 10}

    return edge


# ---------------------------------------------------------------------------
# Helpers (input/output builders — unchanged logic)
# ---------------------------------------------------------------------------

def _build_step_input(step: dict, all_steps: list[dict]) -> dict:
    """Build the 'input' state for a step (what went into it)."""
    step_type = step["type"]

    if step_type == "system":
        return {"type": "system_prompt"}
    elif step_type == "user":
        return {"type": "user_message"}
    elif step_type == "tool_calls":
        return {
            "type": "agent_decision",
            "tools_called": [c["name"] for c in step.get("tool_calls", [])],
            "tool_details": step.get("tool_calls", []),
        }
    elif step_type == "tool_result":
        tc_id = step.get("tool_call_id", "")
        return {
            "type": "tool_execution",
            "tool_name": step.get("tool_name", ""),
            "tool_call_id": tc_id,
        }
    elif step_type == "assistant":
        return {"type": "agent_response"}
    return {}


def _build_step_output(step: dict) -> dict:
    """Build the 'output' state for a step (what it produced)."""
    step_type = step["type"]

    if step_type == "system":
        return {"content": step.get("content", "")}
    elif step_type == "user":
        return {"content": step.get("content", "")}
    elif step_type == "tool_calls":
        result: dict[str, Any] = {"calls": []}
        for c in step.get("tool_calls", []):
            result["calls"].append({
                "name": c.get("name", ""),
                "args": c.get("args", {}),
            })
        if step.get("content"):
            result["agent_text"] = step["content"]
        return result
    elif step_type == "tool_result":
        return {
            "tool_name": step.get("tool_name", ""),
            "content": step.get("content", ""),
            "is_error": step.get("is_error", False),
        }
    elif step_type == "assistant":
        return {"content": step.get("content", "")}
    return {}
