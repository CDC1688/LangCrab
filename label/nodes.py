"""Graph node functions for the label-only pipeline."""

from __future__ import annotations

import csv
import json
import sys
import threading
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from ..config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_ITERATIONS,
)
from ..parser import is_heartbeat_or_bootstrap, parse_csv
from ..prompts import CLASSIFY_SYSTEM_PROMPT, CLASSIFY_USER_TEMPLATE
from ..schemas import Classification

from .schemas import LabelPipelineState, LabelRowState

csv.field_size_limit(sys.maxsize)

# ---------------------------------------------------------------------------
# Progress bar (thread-safe)
# ---------------------------------------------------------------------------
_progress_bar = None
_progress_lock = threading.Lock()


def _init_progress(total: int) -> None:
    global _progress_bar
    from tqdm import tqdm
    _progress_bar = tqdm(total=total, desc="Labelling", unit="row", dynamic_ncols=True)


def _tick_progress() -> None:
    global _progress_bar
    if _progress_bar is not None:
        with _progress_lock:
            _progress_bar.update(1)


def _close_progress() -> None:
    global _progress_bar
    if _progress_bar is not None:
        _progress_bar.close()
        _progress_bar = None


# ---------------------------------------------------------------------------
# LLM client (lazy init)
# ---------------------------------------------------------------------------
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            timeout=120,
            max_retries=3,
        )
    return _client


# ===================================================================
# OUTER GRAPH NODES
# ===================================================================


def load_csv(state: LabelPipelineState) -> dict:
    """Load and parse the CSV, skip rows that already have a classification."""
    csv_path = state["csv_path"]
    limit = state.get("limit", 0)
    rows = parse_csv(csv_path, limit=limit)
    print(f"Loaded {len(rows)} rows from {csv_path}")

    # Read existing classifications from the CSV to skip already-labelled rows
    existing: dict[str, str] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            sid = raw.get("sid", "")
            classification = raw.get("Classification", "").strip()
            if sid and classification:
                existing[sid] = classification

    if existing:
        before = len(rows)
        rows = [r for r in rows if r["sid"] not in existing]
        print(f"Skipped {before - len(rows)} already-labelled rows, {len(rows)} remaining")

    _init_progress(len(rows))
    return {"rows": rows}


def fan_out_to_classify(state: LabelPipelineState) -> list[Send]:
    """Fan out each row to the classify_row subgraph."""
    sends = []
    for row in state["rows"]:
        sends.append(
            Send(
                "classify_row",
                {
                    "sid": row["sid"],
                    "system_prompt_summary": row["system_prompt_summary"],
                    "user_messages_text": row["user_messages_text"],
                    "tool_names_used": row["tool_names_used"],
                    "num_messages": row["num_messages"],
                    "num_user_messages": row.get("num_user_messages", 0),
                    "is_cron_triggered": row["is_cron_triggered"],
                    "is_subagent": row["is_subagent"],
                    "error": "no",
                    "messages": [],
                    "classification": None,
                    "iterations": 0,
                    "classifications": [],
                },
            )
        )
    return sends


def save_to_csv(state: LabelPipelineState) -> dict:
    """Write classification labels back to the original CSV based on sid."""
    _close_progress()

    csv_path = state["csv_path"]
    classifications = state.get("classifications", [])

    if not classifications:
        print("No new classifications to save.")
        return {}

    # Build sid -> classification map
    sid_to_label: dict[str, dict] = {}
    for c in classifications:
        sid_to_label[c["sid"]] = c

    # Read original CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Add Classification column if not present
    label_fields = [
        "Classification",
        "subcategory",
        "user_intent_summary",
        "language",
        "confidence",
    ]
    for field in label_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    # Merge classifications into rows
    updated = 0
    for row in rows:
        sid = row.get("sid", "")
        if sid in sid_to_label:
            label = sid_to_label[sid]
            row["Classification"] = label.get("primary_category", "")
            row["subcategory"] = label.get("subcategory", "")
            row["user_intent_summary"] = label.get("user_intent_summary", "")
            row["language"] = label.get("language", "")
            row["confidence"] = label.get("confidence", "")
            updated += 1

    # Write back to CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {updated} classifications back to {csv_path}")
    return {}


# ===================================================================
# INNER GRAPH NODES (self-correction loop)
# ===================================================================


def extract_signal(state: LabelRowState) -> dict:
    """Prepare the classification prompt, or short-circuit for obvious cases."""
    user_text = state["user_messages_text"]

    if is_heartbeat_or_bootstrap(user_text):
        return {
            "classification": Classification(
                primary_category="system_maintenance",
                subcategory="heartbeat",
                user_intent_summary="Automated heartbeat check or session bootstrap",
                language="en",
                is_cron_triggered=state["is_cron_triggered"],
                is_subagent=state["is_subagent"],
                confidence="high",
            ),
            "error": "no",
            "iterations": 0,
        }

    user_prompt = CLASSIFY_USER_TEMPLATE.format(
        system_prompt_summary=state["system_prompt_summary"][:500],
        user_messages_text=user_text,
        tool_names_used=", ".join(state["tool_names_used"]) or "none",
        num_messages=state["num_messages"],
        num_user_messages=state.get("num_user_messages", 0),
        is_cron_triggered=state["is_cron_triggered"],
        is_subagent=state["is_subagent"],
    )

    return {
        "messages": [
            SystemMessage(content=CLASSIFY_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ],
        "error": "no",
        "iterations": 0,
    }


def route_after_extract(state: LabelRowState) -> str:
    if state.get("classification") is not None:
        return "already_classified"
    return "needs_llm"


def classify(state: LabelRowState) -> dict:
    """Call LLM to classify the log entry."""
    messages = state["messages"]
    iterations = state["iterations"]

    client = _get_client()

    oai_messages = []
    for msg in messages:
        if hasattr(msg, "type"):
            role = "system" if msg.type == "system" else "user"
        else:
            role = "user"
        oai_messages.append({"role": role, "content": msg.content})

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=oai_messages,
        temperature=0,
    )
    raw_content = response.choices[0].message.content

    classification = _parse_classification(raw_content)

    attempt_msg = HumanMessage(
        content=f"Classification attempt #{iterations + 1}: {classification.model_dump_json()}"
    )

    return {
        "classification": classification,
        "messages": [attempt_msg],
        "iterations": iterations + 1,
    }


def _parse_classification(raw: str) -> Classification:
    """Extract JSON from LLM response and parse into Classification."""
    import re

    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
        if brace_match:
            json_str = brace_match.group(0)
        else:
            json_str = raw

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        for match in re.finditer(r"\{[^{}]+\}", raw):
            try:
                parsed = json.loads(match.group(0))
                if "primary_category" in parsed:
                    break
            except json.JSONDecodeError:
                continue
        else:
            return Classification(
                primary_category="other",
                subcategory="parse_failed",
                user_intent_summary=f"Failed to parse LLM response: {raw[:100]}",
                language="mixed",
                is_cron_triggered=False,
                is_subagent=False,
                confidence="low",
            )

    valid_categories = {
        "coding", "file_management", "web_research", "scheduling",
        "communication", "data_analysis", "system_maintenance",
        "content_creation", "finance_crypto", "memory_management",
        "agent_orchestration", "other",
    }
    if parsed.get("primary_category") not in valid_categories:
        parsed["primary_category"] = "other"
    if not parsed.get("language"):
        parsed["language"] = "unknown"
    if parsed.get("confidence") not in ("high", "medium", "low"):
        parsed["confidence"] = "medium"

    return Classification(**parsed)


def validate(state: LabelRowState) -> dict:
    """Programmatic consistency checks on the classification."""
    import unicodedata

    classification = state["classification"]
    tools = state["tool_names_used"]
    errors: list[str] = []

    # Tool-category consistency for feishu
    if any("feishu" in t for t in tools):
        if classification.primary_category != "communication":
            errors.append(
                f"Tools include feishu_* but category is "
                f"'{classification.primary_category}', expected 'communication'"
            )

    # Cron detection consistency
    if state["is_cron_triggered"] and not classification.is_cron_triggered:
        errors.append("Message starts with [cron:] but is_cron_triggered=False")

    # Language detection vs character ratio
    user_text = state["user_messages_text"]
    if user_text:
        cjk_count = sum(
            1 for ch in user_text if unicodedata.category(ch).startswith("Lo")
        )
        cjk_ratio = cjk_count / max(len(user_text), 1)
        if cjk_ratio > 0.3 and classification.language in ("en", "english"):
            errors.append(
                f"Text is {cjk_ratio:.0%} CJK characters but language='{classification.language}'"
            )
        if cjk_ratio < 0.05 and classification.language in ("zh", "chinese"):
            errors.append(
                f"Text is only {cjk_ratio:.0%} CJK characters but language='{classification.language}'"
            )

    # Intent summary quality
    if len(classification.user_intent_summary) < 10:
        errors.append("Intent summary too short (< 10 chars)")

    # Category-tool plausibility
    coding_tools = {"exec", "read", "write", "edit"}
    if classification.primary_category == "coding" and not (set(tools) & coding_tools):
        if tools:
            errors.append(
                f"Category is 'coding' but no coding tools used "
                f"(tools: {', '.join(tools)})"
            )

    if errors:
        error_msg = HumanMessage(
            content=(
                "Classification failed validation:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\n\nReflect on these errors and reclassify. "
                "Pay attention to the tool names and message content."
            )
        )
        return {"messages": [error_msg], "error": "yes"}

    return {"error": "no"}


def decide_to_finish(state: LabelRowState) -> str:
    if state["error"] == "no" or state["iterations"] >= MAX_ITERATIONS:
        return "end"
    return "retry"


def format_result(state: LabelRowState) -> dict:
    """Package classification result for the outer graph."""
    classification = state["classification"]
    result = classification.model_dump() if classification else {}
    result["sid"] = state["sid"]

    _tick_progress()
    return {"classifications": [result]}
