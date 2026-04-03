"""Transform agent traces into React Flow graph data.

Builds a **real graph** showing LLM agent behavior:
  - Parallel tool calls fan out from an agent decision node to individual
    tool-result nodes, then converge back.
  - Thinking/reasoning steps appear above their decision nodes.
  - Retry loops show back-edges from error nodes to retry decisions.
  - Sub-agent invocations are wrapped in collapsible group containers.
  - Turns are visually grouped with shared Y bands.

Architecture:
  1. ``_build_structured_turns()`` — parse flat steps into structured turns
  2. ``_annotate_retries_and_subagents()`` — detect retries & sub-agent scopes
  3. ``_build_graph_ir()`` — build topology IR (nodes + edges, no positions)
  4. ``_layout_ir()`` — assign (x, y) positions + group bounding boxes
  5. ``build_agent_graph()`` — orchestrate the pipeline, emit React Flow JSON
"""

from __future__ import annotations

import re
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
# Colors & layout constants
# ---------------------------------------------------------------------------

STEP_COLORS = {
    "system": {"border": "#7B1FA2", "bg": "#F3E5F5"},
    "user": {"border": "#1565C0", "bg": "#E3F2FD"},
    "tool_calls": {"border": "#E65100", "bg": "#FFF3E0"},
    "tool_result": {"border": "#2E7D32", "bg": "#E8F5E9"},
    "tool_result_error": {"border": "#C62828", "bg": "#FFEBEE"},
    "assistant": {"border": "#2E7D32", "bg": "#E8F5E9"},
    "converge": {"border": "#546E7A", "bg": "#ECEFF1"},
    "thinking": {"border": "#78909C", "bg": "#ECEFF1"},
    "retry": {"border": "#C62828", "bg": "#FFEBEE"},
    "sub_agent": {"border": "#6A1B9A", "bg": "#F3E5F5"},
    "group": {"border": "#37474F", "bg": "#263238"},
}

CENTER_X = 300
TOOL_SPACING_X = 220
Y_STEP = 100
Y_STEP_SMALL = 80
NODE_WIDTH_WIDE = 500
GROUP_PADDING_X = 30
GROUP_PADDING_Y = 50
GROUP_HEADER_H = 36
NESTING_INDENT = 40

# Sub-agent tool name patterns
_SUBAGENT_PATTERNS = re.compile(
    r"^(agent_|sub_agent|delegate_|spawn_|invoke_agent|run_agent)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Phase 1: Structured turn builder
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
        * ``has_thinking``: bool — whether the tool_calls step has reasoning content

    Every step appears in ``turn["steps"]`` for backward compat.
    """
    turns: list[dict] = []

    # First pass: build tool_call_id → tool_calls step index for matching
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
            call_ids = {c.get("id", "") for c in step.get("tool_calls", []) if c.get("id")}

            result_steps: list[dict] = []
            j = i + 1
            while j < len(steps) and steps[j]["type"] == "tool_result":
                tc_id = steps[j].get("tool_call_id", "")
                if call_ids and tc_id and tc_id not in call_ids:
                    break
                result_steps.append(steps[j])
                j += 1

            trailing_assistant = None
            if j < len(steps) and steps[j]["type"] == "assistant":
                trailing_assistant = steps[j]
                j += 1

            all_steps = [step] + result_steps
            if trailing_assistant:
                all_steps.append(trailing_assistant)

            # Detect thinking content
            has_thinking = bool(step.get("content", "").strip())

            turns.append({
                "type": "agent_action",
                "steps": all_steps,
                "tool_calls_step": step,
                "result_steps": result_steps,
                "trailing_assistant": trailing_assistant,
                "has_thinking": has_thinking,
            })
            i = j

        elif step["type"] == "assistant":
            turns.append({"type": "assistant", "steps": [step]})
            i += 1

        elif step["type"] == "tool_result":
            turns.append({"type": "assistant", "steps": [step]})
            i += 1

        else:
            i += 1

    return turns


# ---------------------------------------------------------------------------
# Phase 1b: Annotate retries & sub-agents
# ---------------------------------------------------------------------------

def _annotate_retries_and_subagents(turns: list[dict]) -> list[dict]:
    """Second pass: detect retry loops and sub-agent invocations.

    Mutates turns in-place, adding:
      - ``retry_of``: index of the original turn this retries
      - ``retry_attempt``: 1-based attempt number
      - ``is_sub_agent``: bool — whether this turn invokes a sub-agent
      - ``sub_agent_name``: name of the sub-agent tool
    """
    for i, turn in enumerate(turns):
        if turn["type"] != "agent_action":
            continue

        # --- Retry detection ---
        error_tool_names = {
            rs.get("tool_name", "")
            for rs in turn.get("result_steps", [])
            if rs.get("is_error")
        }

        if error_tool_names and i + 1 < len(turns):
            next_turn = turns[i + 1]
            if next_turn.get("type") == "agent_action":
                next_tool_names = {
                    c.get("name", "")
                    for c in next_turn["tool_calls_step"].get("tool_calls", [])
                }
                # Retry if the next turn calls any of the same tools that errored
                if error_tool_names & next_tool_names:
                    prev_attempt = turn.get("retry_attempt", 0)
                    next_turn["retry_of"] = i
                    next_turn["retry_attempt"] = prev_attempt + 1

        # --- Sub-agent detection ---
        tc_step = turn["tool_calls_step"]
        for call in tc_step.get("tool_calls", []):
            name = call.get("name", "")
            if _SUBAGENT_PATTERNS.match(name):
                turn["is_sub_agent"] = True
                turn["sub_agent_name"] = name
                break

    return turns


# ---------------------------------------------------------------------------
# Phase 2: Graph IR
# ---------------------------------------------------------------------------

def _build_graph_ir(
    turns: list[dict],
    error_map: dict[int, dict],
) -> tuple[list[dict], list[dict]]:
    """Build the graph intermediate representation from annotated turns.

    Returns (ir_nodes, ir_edges) where each node has:
        id, type, parent, layer, depth, step, children, metadata
    and each edge has:
        source, target, type, label, metadata
    """
    ir_nodes: list[dict] = []
    ir_edges: list[dict] = []

    # Maps for lookup
    node_by_id: dict[str, dict] = {}

    prev_node_id: str | None = None
    turn_idx = 0

    for turn in turns:
        turn_type = turn["type"]

        # ---- Spine nodes: system / user / assistant ----
        if turn_type in ("system", "user", "assistant"):
            step = turn["steps"][0]
            node_id = f"step_{step['idx']}"
            ir_node = {
                "id": node_id,
                "type": step["type"],
                "parent": None,
                "layer": 0,
                "depth": 0,
                "step": step,
                "children": [],
                "metadata": {"turn_idx": turn_idx},
            }
            ir_nodes.append(ir_node)
            node_by_id[node_id] = ir_node

            if prev_node_id:
                ir_edges.append({
                    "source": prev_node_id,
                    "target": node_id,
                    "type": "sequential",
                    "label": None,
                    "metadata": {},
                })

            prev_node_id = node_id

        # ---- Agent action turn ----
        elif turn_type == "agent_action":
            tc_step = turn["tool_calls_step"]
            result_steps = turn["result_steps"]
            trailing_assistant = turn.get("trailing_assistant")
            has_thinking = turn.get("has_thinking", False)
            is_retry = "retry_of" in turn
            is_sub_agent = turn.get("is_sub_agent", False)

            # Determine group type
            if is_sub_agent:
                group_type = "sub_agent"
            elif is_retry:
                group_type = "retry_loop"
            else:
                group_type = "tool_fan"

            # Create group node to wrap this agent action
            group_id = f"group_{tc_step['idx']}"
            group_label = turn.get("sub_agent_name", "") if is_sub_agent else ""
            if is_retry:
                group_label = f"Retry #{turn.get('retry_attempt', 1)}"
            elif not group_label:
                n_tools = len(tc_step.get("tool_calls", []))
                group_label = f"Agent Action ({n_tools} tool{'s' if n_tools != 1 else ''})"

            group_node = {
                "id": group_id,
                "type": "groupNode",
                "parent": None,
                "layer": 0,
                "depth": 0,
                "step": None,
                "children": [],
                "metadata": {
                    "turn_idx": turn_idx,
                    "group_type": group_type,
                    "label": group_label,
                    "collapsed": False,
                },
            }
            ir_nodes.append(group_node)
            node_by_id[group_id] = group_node

            # Edge from previous node to group (forward/sequential, even for retries)
            if prev_node_id:
                ir_edges.append({
                    "source": prev_node_id,
                    "target": group_id,
                    "type": "sequential",
                    "label": None,
                    "metadata": {},
                })

            # --- Thinking node (if agent reasoned before tool calls) ---
            if has_thinking:
                think_id = f"think_{tc_step['idx']}"
                think_node = {
                    "id": think_id,
                    "type": "thinking",
                    "parent": group_id,
                    "layer": 0,
                    "depth": 1,
                    "step": {
                        "type": "thinking",
                        "idx": tc_step["idx"],
                        "content": tc_step.get("content", ""),
                    },
                    "children": [],
                    "metadata": {"turn_idx": turn_idx},
                }
                ir_nodes.append(think_node)
                node_by_id[think_id] = think_node
                group_node["children"].append(think_id)

            # --- Agent Decision node (tool_calls) ---
            tc_node_id = f"step_{tc_step['idx']}"
            tc_ir_type = "retry" if is_retry else "tool_calls"
            tc_node = {
                "id": tc_node_id,
                "type": tc_ir_type,
                "parent": group_id,
                "layer": 0,
                "depth": 1,
                "step": tc_step,
                "children": [],
                "metadata": {
                    "turn_idx": turn_idx,
                    "retry_attempt": turn.get("retry_attempt"),
                },
            }
            ir_nodes.append(tc_node)
            node_by_id[tc_node_id] = tc_node
            group_node["children"].append(tc_node_id)

            # Edge: thinking → decision
            if has_thinking:
                ir_edges.append({
                    "source": f"think_{tc_step['idx']}",
                    "target": tc_node_id,
                    "type": "sequential",
                    "label": None,
                    "metadata": {},
                })

            # --- Fan-out: tool result nodes ---
            n_results = len(result_steps)
            result_node_ids: list[str] = []

            for layer_i, rs in enumerate(result_steps):
                rs_id = f"step_{rs['idx']}"
                rs_node = {
                    "id": rs_id,
                    "type": "tool_result",
                    "parent": group_id,
                    "layer": layer_i + 1 if n_results > 1 else 0,
                    "depth": 1,
                    "step": rs,
                    "children": [],
                    "metadata": {"turn_idx": turn_idx},
                }
                ir_nodes.append(rs_node)
                node_by_id[rs_id] = rs_node
                group_node["children"].append(rs_id)
                result_node_ids.append(rs_id)

                ir_edges.append({
                    "source": tc_node_id,
                    "target": rs_id,
                    "type": "fanOut",
                    "label": rs.get("tool_name", ""),
                    "metadata": {},
                })

            # --- Converge node (only for multiple results) ---
            if n_results > 1:
                conv_id = f"converge_{tc_step['idx']}"
                n_err = sum(1 for rs in result_steps if rs.get("is_error"))
                n_ok = n_results - n_err
                conv_label = f"{n_ok} ok"
                if n_err:
                    conv_label += f", {n_err} err"

                conv_node = {
                    "id": conv_id,
                    "type": "converge",
                    "parent": group_id,
                    "layer": 0,
                    "depth": 1,
                    "step": None,
                    "children": [],
                    "metadata": {
                        "turn_idx": turn_idx,
                        "result_count": n_results,
                        "error_count": n_err,
                        "label": conv_label,
                    },
                }
                ir_nodes.append(conv_node)
                node_by_id[conv_id] = conv_node
                group_node["children"].append(conv_id)

                for rs_id_c in result_node_ids:
                    ir_edges.append({
                        "source": rs_id_c,
                        "target": conv_id,
                        "type": "fanIn",
                        "label": None,
                        "metadata": {},
                    })

                last_in_group = conv_id
            elif n_results == 1:
                last_in_group = result_node_ids[0]
            else:
                last_in_group = tc_node_id

            # --- Trailing assistant ---
            if trailing_assistant:
                ast_id = f"step_{trailing_assistant['idx']}"
                ast_node = {
                    "id": ast_id,
                    "type": "assistant",
                    "parent": group_id,
                    "layer": 0,
                    "depth": 1,
                    "step": trailing_assistant,
                    "children": [],
                    "metadata": {"turn_idx": turn_idx},
                }
                ir_nodes.append(ast_node)
                node_by_id[ast_id] = ast_node
                group_node["children"].append(ast_id)

                ir_edges.append({
                    "source": last_in_group,
                    "target": ast_id,
                    "type": "sequential",
                    "label": None,
                    "metadata": {},
                })
                last_in_group = ast_id

            prev_node_id = group_id

        turn_idx += 1

    # --- Retry back-edges ---
    # Connect error result nodes back to the retry group
    for turn in turns:
        if "retry_of" not in turn:
            continue
        orig_idx = turn["retry_of"]
        if orig_idx >= len(turns):
            continue
        orig_turn = turns[orig_idx]
        if orig_turn["type"] != "agent_action":
            continue

        # Find error result nodes in the original turn
        for rs in orig_turn.get("result_steps", []):
            if rs.get("is_error"):
                error_node_id = f"step_{rs['idx']}"
                retry_group_id = f"group_{turn['tool_calls_step']['idx']}"
                if error_node_id in node_by_id and retry_group_id in node_by_id:
                    ir_edges.append({
                        "source": error_node_id,
                        "target": retry_group_id,
                        "type": "retry",
                        "label": f"retry #{turn.get('retry_attempt', 1)}",
                        "metadata": {"retry_attempt": turn.get("retry_attempt", 1)},
                    })

    return ir_nodes, ir_edges


# ---------------------------------------------------------------------------
# Phase 3: Layout engine
# ---------------------------------------------------------------------------

def _layout_ir(
    ir_nodes: list[dict],
    ir_edges: list[dict],
) -> tuple[list[dict], list[dict], dict, dict]:
    """Convert IR nodes/edges into positioned React Flow nodes and edges.

    Returns (rf_nodes, rf_edges, groups, layers).
    """
    rf_nodes: list[dict] = []
    rf_edges: list[dict] = []
    groups: dict[str, dict] = {}
    layers: dict[str, dict] = {}

    # Index IR nodes by id
    ir_by_id: dict[str, dict] = {n["id"]: n for n in ir_nodes}

    # Separate top-level nodes (no parent) and child nodes
    top_level = [n for n in ir_nodes if n["parent"] is None]
    children_of: dict[str, list[dict]] = {}
    for n in ir_nodes:
        if n["parent"]:
            children_of.setdefault(n["parent"], []).append(n)

    # Build edge lookup for fan-out detection
    edges_from: dict[str, list[dict]] = {}
    edges_to: dict[str, list[dict]] = {}
    for e in ir_edges:
        edges_from.setdefault(e["source"], []).append(e)
        edges_to.setdefault(e["target"], []).append(e)

    y = 0
    active_path: list[str] = []
    node_states: dict[str, dict] = {}

    for tl_node in top_level:
        if tl_node["type"] == "groupNode":
            # Layout the group and its children
            group_id = tl_node["id"]
            group_children = children_of.get(group_id, [])
            meta = tl_node["metadata"]
            group_type = meta.get("group_type", "tool_fan")

            # Determine group colors
            gc = STEP_COLORS.get(
                "sub_agent" if group_type == "sub_agent"
                else "retry" if group_type == "retry_loop"
                else "group"
            )

            # Layout children within the group
            child_y = y + GROUP_HEADER_H + 10
            child_nodes: list[dict] = []
            child_min_x = CENTER_X
            child_max_x = CENTER_X

            # Order children: thinking → decision → results → converge → trailing assistant
            ordered = _order_group_children(group_children, ir_edges)

            for child in ordered:
                cid = child["id"]
                ctype = child["type"]
                cstep = child["step"]

                if ctype == "thinking":
                    # Thinking node: wide, above decision
                    rf_node = _make_rf_node(
                        cid, "thinkingNode",
                        {"x": CENTER_X - NODE_WIDTH_WIDE // 2 + 50, "y": child_y},
                        _make_thinking_data(cid, cstep, meta.get("turn_idx", 0)),
                    )
                    child_nodes.append(rf_node)
                    node_states[cid] = {
                        "input": {"type": "agent_reasoning"},
                        "output": {"content": cstep.get("content", "")},
                    }
                    active_path.append(cid)
                    child_y += Y_STEP_SMALL
                    child_min_x = min(child_min_x, rf_node["position"]["x"])
                    child_max_x = max(child_max_x, rf_node["position"]["x"] + NODE_WIDTH_WIDE)

                elif ctype in ("tool_calls", "retry"):
                    # Agent decision node
                    rf_type = "retryNode" if ctype == "retry" else "agentNode"
                    rf_node = _make_rf_node(
                        cid, rf_type,
                        {"x": CENTER_X - 100, "y": child_y},
                        _make_node_data(cid, cstep, meta.get("turn_idx", 0), {},
                                        is_retry=ctype == "retry",
                                        retry_attempt=child["metadata"].get("retry_attempt")),
                    )
                    child_nodes.append(rf_node)
                    node_states[cid] = _make_node_state(cstep, [])
                    active_path.append(cid)
                    child_y += Y_STEP

                elif ctype == "tool_result":
                    # Check if this is in a parallel fan-out
                    layer = child["layer"]
                    # Count siblings at the same depth that are tool_results
                    sibling_results = [
                        c for c in ordered if c["type"] == "tool_result"
                    ]
                    n_results = len(sibling_results)

                    if n_results > 1:
                        # Fan-out: spread horizontally
                        total_width = (n_results - 1) * TOOL_SPACING_X
                        start_x = CENTER_X - total_width // 2
                        result_idx = sibling_results.index(child)
                        rx = start_x + result_idx * TOOL_SPACING_X - 80

                        # Only bump Y for the first result in the fan
                        if result_idx == 0:
                            pass  # Y already set from decision node
                        rf_node = _make_rf_node(
                            cid, "agentNode",
                            {"x": rx, "y": child_y},
                            _make_node_data(cid, cstep, meta.get("turn_idx", 0), {}),
                        )
                        child_nodes.append(rf_node)
                        child_min_x = min(child_min_x, rx)
                        child_max_x = max(child_max_x, rx + 200)

                        # Only advance Y after last result
                        if result_idx == n_results - 1:
                            child_y += Y_STEP
                    else:
                        # Single result: center spine
                        rf_node = _make_rf_node(
                            cid, "agentNode",
                            {"x": CENTER_X - 80, "y": child_y},
                            _make_node_data(cid, cstep, meta.get("turn_idx", 0), {}),
                        )
                        child_nodes.append(rf_node)
                        child_y += Y_STEP_SMALL

                    node_states[cid] = _make_node_state(cstep, [])
                    active_path.append(cid)

                elif ctype == "converge":
                    # Converge node
                    cmeta = child["metadata"]
                    n_err = cmeta.get("error_count", 0)
                    has_err = n_err > 0
                    conv_colors = STEP_COLORS["tool_result_error"] if has_err else STEP_COLORS["converge"]

                    rf_node = _make_rf_node(
                        cid, "convergeNode",
                        {"x": CENTER_X - 60, "y": child_y},
                        {
                            "nodeId": cid,
                            "stepType": "converge",
                            "label": cmeta.get("label", ""),
                            "borderColor": conv_colors["border"],
                            "bgColor": conv_colors["bg"],
                            "turnIndex": meta.get("turn_idx", 0),
                            "resultCount": cmeta.get("result_count", 0),
                            "errorCount": n_err,
                            "status": "error" if has_err else "success",
                        },
                    )
                    child_nodes.append(rf_node)
                    node_states[cid] = {
                        "input": {"type": "converge"},
                        "output": {
                            "total": cmeta.get("result_count", 0),
                            "errors": n_err,
                        },
                    }
                    active_path.append(cid)
                    child_y += Y_STEP_SMALL

                elif ctype == "assistant":
                    # Trailing assistant
                    rf_node = _make_rf_node(
                        cid, "agentNodeWide",
                        {"x": CENTER_X - NODE_WIDTH_WIDE // 2 + 50, "y": child_y},
                        _make_node_data(cid, cstep, meta.get("turn_idx", 0), {}),
                    )
                    child_nodes.append(rf_node)
                    node_states[cid] = _make_node_state(cstep, [])
                    active_path.append(cid)
                    child_min_x = min(child_min_x, rf_node["position"]["x"])
                    child_max_x = max(child_max_x, rf_node["position"]["x"] + NODE_WIDTH_WIDE)
                    child_y += Y_STEP

            # Compute group bounding box
            group_width = max(child_max_x - child_min_x + GROUP_PADDING_X * 2, 400)
            group_height = (child_y - y) + GROUP_PADDING_Y
            group_x = child_min_x - GROUP_PADDING_X

            # Create the group container node
            rf_group = _make_rf_node(
                group_id, "groupNode",
                {"x": group_x, "y": y},
                {
                    "nodeId": group_id,
                    "stepType": "group",
                    "label": meta.get("label", ""),
                    "groupType": group_type,
                    "borderColor": gc["border"],
                    "bgColor": gc["bg"],
                    "turnIndex": meta.get("turn_idx", 0),
                    "childCount": len(group_children),
                    "width": group_width,
                    "height": group_height,
                    "status": "active",
                },
            )
            rf_group["style"] = {
                "width": group_width,
                "height": group_height,
            }

            # Add group node first, then children
            rf_nodes.append(rf_group)
            for cn in child_nodes:
                rf_nodes.append(cn)

            # Record group metadata
            groups[group_id] = {
                "label": meta.get("label", ""),
                "children": [c["id"] for c in group_children],
                "collapsed": False,
                "type": group_type,
            }

            # Record layer info for parallel fan-outs
            result_nodes_in_group = [c for c in ordered if c["type"] == "tool_result"]
            if len(result_nodes_in_group) > 1:
                layer_id = f"layer_{group_id}"
                layer_node_ids = [c["id"] for c in result_nodes_in_group]
                layers[layer_id] = {
                    "y_start": y + GROUP_HEADER_H + Y_STEP,
                    "y_end": y + GROUP_HEADER_H + Y_STEP + Y_STEP,
                    "node_ids": layer_node_ids,
                }

            y = child_y + 20  # gap after group

        else:
            # Non-group top-level node (system, user, standalone assistant)
            step = tl_node["step"]
            node_id = tl_node["id"]
            node_type_map = {
                "system": "agentNodeWide",
                "user": "agentNodeWide",
                "assistant": "agentNodeWide",
            }
            rf_type = node_type_map.get(tl_node["type"], "agentNode")

            rf_node = _make_rf_node(
                node_id, rf_type,
                {"x": CENTER_X - NODE_WIDTH_WIDE // 2 + 50, "y": y},
                _make_node_data(node_id, step, tl_node["metadata"].get("turn_idx", 0), {}),
            )
            rf_nodes.append(rf_node)
            node_states[node_id] = _make_node_state(step, [])
            active_path.append(node_id)
            y += Y_STEP

    # --- Build React Flow edges from IR edges ---
    for ir_edge in ir_edges:
        rf_edge = _make_rf_edge(ir_edge, ir_by_id)
        if rf_edge:
            rf_edges.append(rf_edge)

    return rf_nodes, rf_edges, groups, layers, active_path, node_states


def _order_group_children(children: list[dict], edges: list[dict]) -> list[dict]:
    """Order children within a group: thinking → decision → results → converge → assistant."""
    type_order = {
        "thinking": 0,
        "tool_calls": 1,
        "retry": 1,
        "tool_result": 2,
        "converge": 3,
        "assistant": 4,
    }
    return sorted(children, key=lambda c: (type_order.get(c["type"], 5), c.get("step", {}).get("idx", 0) if c.get("step") else 0))


def _make_rf_node(node_id: str, node_type: str, position: dict, data: dict) -> dict:
    """Create a React Flow node dict."""
    return {
        "id": node_id,
        "type": node_type,
        "position": position,
        "data": data,
    }


def _make_rf_edge(ir_edge: dict, ir_by_id: dict) -> dict | None:
    """Convert an IR edge to a React Flow edge."""
    src = ir_edge["source"]
    tgt = ir_edge["target"]
    etype = ir_edge["type"]

    src_node = ir_by_id.get(src)
    tgt_node = ir_by_id.get(tgt)
    if not src_node or not tgt_node:
        return None

    style: dict[str, Any] = {"strokeWidth": 1.5}
    edge: dict[str, Any] = {
        "id": f"e-{src}-{tgt}",
        "source": src,
        "target": tgt,
        "style": style,
    }

    if etype == "retry":
        style["stroke"] = "#C62828"
        style["strokeDasharray"] = "6,4"
        edge["type"] = "retryEdge"
        edge["animated"] = True
        if ir_edge.get("label"):
            edge["label"] = ir_edge["label"]
            edge["labelStyle"] = {"fill": "#C62828", "fontSize": 10, "fontWeight": "bold"}

    elif etype == "fanOut":
        style["stroke"] = "#E65100"
        edge["type"] = "smoothstep"
        if ir_edge.get("label"):
            edge["label"] = ir_edge["label"]
            edge["labelStyle"] = {"fill": "#E65100", "fontSize": 9}

    elif etype == "fanIn":
        # Check if the source is an error result
        src_step = src_node.get("step")
        is_err = src_step and src_step.get("is_error", False)
        style["stroke"] = "#C62828" if is_err else "#546E7A"
        if is_err:
            style["strokeDasharray"] = "5,3"
        edge["type"] = "smoothstep"

    elif etype == "sequential":
        # Color based on target type
        tgt_type = tgt_node.get("type", "")
        tgt_step = tgt_node.get("step")
        if tgt_step and tgt_step.get("is_error"):
            style["stroke"] = STEP_COLORS["tool_result_error"]["border"]
        elif tgt_type in STEP_COLORS:
            style["stroke"] = STEP_COLORS[tgt_type]["border"]
        else:
            style["stroke"] = "#546E7A"

    else:
        style["stroke"] = "#546E7A"

    return edge


# ---------------------------------------------------------------------------
# Phase 4: Main entry point
# ---------------------------------------------------------------------------

def build_agent_graph(
    agent_trace: list[dict],
    classification: dict = None,
    error_report: dict = None,
) -> dict:
    """Build a real graph from agent trace steps.

    Pipeline:
      1. Parse flat steps → structured turns
      2. Annotate retries & sub-agents
      3. Build graph IR (topology, no positions)
      4. Layout IR → positioned React Flow nodes/edges

    Returns: {nodes, edges, active_path, node_states, turns, groups, layers, retry_loops}
    """
    if not agent_trace:
        return {
            "nodes": [], "edges": [], "active_path": [], "node_states": {},
            "turns": [], "groups": {}, "layers": {}, "retry_loops": [],
        }

    # Build error lookup
    error_by_position: dict[int, dict] = {}
    if error_report:
        for err in error_report.get("tool_errors", []):
            pos = err.get("position")
            if pos is not None:
                error_by_position[pos] = err

    # Phase 1: structured turns + annotations
    turns = _build_structured_turns(agent_trace)
    turns = _annotate_retries_and_subagents(turns)

    # Phase 2: build graph IR
    ir_nodes, ir_edges = _build_graph_ir(turns, error_by_position)

    # Phase 3: layout
    rf_nodes, rf_edges, groups, layer_info, active_path, node_states = _layout_ir(ir_nodes, ir_edges)

    # Collect retry loops for frontend
    retry_loops = []
    for e in ir_edges:
        if e["type"] == "retry" and e.get("metadata", {}).get("retry_attempt"):
            retry_loops.append({
                "error_node": e["source"],
                "retry_node": e["target"],
                "attempt": e["metadata"]["retry_attempt"],
            })

    # ---- Classification node (appended at the end) ----
    if classification:
        cls_id = "classification"
        last_y = max((n["position"]["y"] for n in rf_nodes), default=0) + Y_STEP
        rf_nodes.append({
            "id": cls_id,
            "type": "agentNode",
            "position": {"x": CENTER_X - 80, "y": last_y},
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
        if active_path:
            last_id = active_path[-1]
            rf_edges.append({
                "id": f"e-{last_id}-{cls_id}",
                "source": last_id,
                "target": cls_id,
                "style": {"stroke": "#4527A0", "strokeWidth": 1.5, "strokeDasharray": "5,5"},
            })
        active_path.append(cls_id)

    return {
        "nodes": rf_nodes,
        "edges": rf_edges,
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
        "groups": groups,
        "layers": layer_info,
        "retry_loops": retry_loops,
    }


# ---------------------------------------------------------------------------
# Phase 5: Replay events
# ---------------------------------------------------------------------------

def build_replay_events(session_data: dict) -> list[dict]:
    """Build ordered trace events for WebSocket replay.

    Walks the ``active_path`` of the built graph so replay follows the real
    DAG order (including converge and group nodes).
    """
    agent_trace = session_data.get("agent_trace", [])
    if not agent_trace:
        return [{"type": "complete", "timestamp": 0}]

    classification = session_data.get("classification")
    error_report = session_data.get("error_report")
    graph = build_agent_graph(agent_trace, classification, error_report)
    ordered_ids = graph.get("active_path", [])
    edge_set = {(e["source"], e["target"]) for e in graph.get("edges", [])}
    node_state_map = graph.get("node_states", {})
    groups_meta = graph.get("groups", {})

    DELAYS = {
        "system": 50,
        "user": 120,
        "tool_calls": 80,
        "tool_result": 40,
        "converge": 30,
        "assistant": 120,
        "classification": 60,
        "thinking": 100,
        "group": 20,
    }

    events: list[dict] = []
    t = 0

    for i, nid in enumerate(ordered_ids):
        state = node_state_map.get(nid, {})

        # Determine step type
        step_type = ""
        if nid.startswith("converge"):
            step_type = "converge"
        elif nid.startswith("think_"):
            step_type = "thinking"
        elif nid.startswith("group_"):
            step_type = "group"
        elif nid == "classification":
            step_type = "classification"
        else:
            out = state.get("output", {})
            step_type = out.get("step_type", state.get("input", {}).get("type", ""))
            if "tool_name" in out:
                step_type = "tool_result"
            elif "calls" in out:
                step_type = "tool_calls"
            elif "content" in out and "tool_name" not in out:
                step_type = "assistant"

        delay = DELAYS.get(step_type, 60)

        # Group expand/collapse events
        if nid in groups_meta:
            events.append({"type": "group_expand", "node": nid, "timestamp": t})
            t += 10

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
# Node/edge data builders
# ---------------------------------------------------------------------------

def _make_node_data(
    node_id: str,
    step: dict,
    turn_idx: int,
    error_map: dict,
    is_retry: bool = False,
    retry_attempt: int | None = None,
) -> dict:
    """Build the ``data`` payload for a React Flow node from a trace step."""
    step_type = step["type"]

    if step_type == "tool_result" and step.get("is_error"):
        color_key = "tool_result_error"
    elif is_retry:
        color_key = "retry"
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
        label = f"Agent Decision ({n} tool{'s' if n != 1 else ''})"
        if is_retry and retry_attempt:
            label = f"Retry #{retry_attempt} ({n} tool{'s' if n != 1 else ''})"
        node_data["label"] = label
        node_data["toolNames"] = call_names
        node_data["preview"] = ", ".join(call_names)
        node_data["status"] = "active"
        node_data["isRetry"] = is_retry
        if retry_attempt:
            node_data["retryAttempt"] = retry_attempt

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


def _make_thinking_data(node_id: str, step: dict, turn_idx: int) -> dict:
    """Build data payload for a thinking node."""
    content = step.get("content", "")
    return {
        "nodeId": node_id,
        "stepType": "thinking",
        "label": "Agent Reasoning",
        "preview": content[:150],
        "fullContent": content,
        "borderColor": STEP_COLORS["thinking"]["border"],
        "bgColor": STEP_COLORS["thinking"]["bg"],
        "turnIndex": turn_idx,
        "status": "active",
    }


def _make_node_state(step: dict, all_steps: list[dict]) -> dict:
    """Build ``{input, output}`` for the StatePanel."""
    return {
        "input": _build_step_input(step),
        "output": _build_step_output(step),
    }


def _make_edge(source_id: str, target_id: str, target_step: dict, error_map: dict) -> dict:
    """Build an edge dict between two nodes (legacy helper)."""
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
# Helpers (input/output builders)
# ---------------------------------------------------------------------------

def _build_step_input(step: dict) -> dict:
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
    elif step_type == "thinking":
        return {"type": "agent_reasoning"}
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
    elif step_type == "thinking":
        return {"content": step.get("content", "")}
    return {}
