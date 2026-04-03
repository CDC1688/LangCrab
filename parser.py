"""CSV parsing and conversation signal extraction."""

from __future__ import annotations

import csv
import json
import sys
from typing import Any

from .config import (
    HEARTBEAT_PATTERNS,
    MAX_SYSTEM_PROMPT_CHARS,
    MAX_USER_TEXT_CHARS,
)


csv.field_size_limit(sys.maxsize)


def parse_csv(path: str, limit: int = 0, workers: int = 0) -> list[dict]:
    """Read the CSV and return a list of pre-parsed row dicts.

    Uses multiprocessing when workers > 1 and row count is large enough.
    """
    import os
    from concurrent.futures import ProcessPoolExecutor
    from pathlib import Path

    source_file = Path(path).name

    # Read raw rows first (single thread — CSV reading is I/O bound)
    raw_rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader):
            if limit and i >= limit:
                break
            raw_rows.append(dict(raw))

    if workers <= 0:
        workers = min(os.cpu_count() or 1, 64)

    # Multiprocess parse for large datasets, single-thread for small ones
    if len(raw_rows) > 100 and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_parse_row, raw_rows, chunksize=50))
    else:
        rows = [_parse_row(raw) for raw in raw_rows]

    for row in rows:
        row["source_file"] = source_file

    return rows


def parse_multiple_csvs(paths: list[str], limit: int = 0, workers: int = 0) -> list[dict]:
    """Read multiple CSV files and return combined pre-parsed rows."""
    import time

    all_rows: list[dict] = []
    for path in paths:
        t0 = time.time()
        rows = parse_csv(path, limit=limit, workers=workers)
        elapsed = time.time() - t0
        print(f"  Parsed {len(rows)} rows from {path} ({elapsed:.1f}s)")
        all_rows.extend(rows)
    return all_rows


def _parse_row(raw: dict) -> dict:
    """Parse a single CSV row into a structured dict for the graph."""
    sid = raw.get("sid", "")
    account = raw.get("account", "")
    model = raw.get("model", "")
    event_time = raw.get("event_time", "")

    try:
        request = json.loads(raw.get("request", "{}"))
    except (json.JSONDecodeError, TypeError):
        request = {}

    try:
        response = json.loads(raw.get("response", "{}"))
    except (json.JSONDecodeError, TypeError):
        response = {}

    try:
        extra = json.loads(raw.get("extra", "{}"))
    except (json.JSONDecodeError, TypeError):
        extra = {}

    signal = extract_conversation_signal(request)
    tool_errors = extract_tool_errors(request)
    token_usage = extract_token_usage(extra)
    finish_reason = _extract_finish_reason(response)

    return {
        "sid": sid,
        "account": account,
        "model": model,
        "event_time": event_time,
        **signal,
        **tool_errors,
        "token_usage": token_usage,
        "finish_reason": finish_reason,
    }


def extract_conversation_signal(request: dict[str, Any]) -> dict:
    """Extract the classification-relevant signal from a request JSON.

    Returns a dict with: system_prompt_summary, user_messages_text,
    tool_names_used, num_messages, num_user_messages, is_cron_triggered,
    is_subagent.
    """
    messages = request.get("messages", [])
    num_messages = len(messages)

    system_prompt = ""
    user_texts: list[str] = []
    tool_names: set[str] = set()
    is_cron = False
    is_subagent = False

    for msg in messages:
        role = msg.get("role", "")
        content = _extract_text(msg.get("content", ""))

        if role == "system" and not system_prompt:
            system_prompt = content

        if role in ("user", "human"):
            # Skip noise
            if content.strip() == "(session bootstrap)":
                continue
            user_texts.append(content)

            # Detect cron trigger
            if content.strip().startswith("[cron:"):
                is_cron = True
            # Detect subagent
            if "Subagent" in content or "sub-agent" in content.lower():
                is_subagent = True

        if role == "assistant":
            # Extract tool names from tool_calls
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "") if isinstance(fn, dict) else ""
                if name:
                    tool_names.add(name)

    # Also check tools defined in the request
    for tool_def in request.get("tools", []):
        fn = tool_def.get("function", {})
        name = fn.get("name", "") if isinstance(fn, dict) else ""
        if name:
            tool_names.add(name)

    # Truncate system prompt
    system_summary = system_prompt[:MAX_SYSTEM_PROMPT_CHARS]

    # Build user text: prioritize first + last messages
    user_messages_text = _truncate_user_messages(user_texts, MAX_USER_TEXT_CHARS)

    return {
        "system_prompt_summary": system_summary,
        "user_messages_text": user_messages_text,
        "tool_names_used": sorted(tool_names),
        "num_messages": num_messages,
        "num_user_messages": len(user_texts),
        "is_cron_triggered": is_cron,
        "is_subagent": is_subagent,
    }


# ---------------------------------------------------------------------------
# Tool error extraction
# ---------------------------------------------------------------------------

_ERROR_KEYWORDS = (
    "error", "traceback", "exception", "exit code",
    "exited with code", "command failed", "permission denied",
    "no such file", "cannot access", "not found",
    "timed out", "connection refused", "fatal",
)

# Tools that return file/page content — keywords in their output are often
# part of the content being read, not actual tool failures.
_CONTENT_TOOLS = frozenset({
    "read", "read_file", "web_fetch", "web_search",
    "memory_get", "memory_search", "memory_recall",
    "feishu_fetch_doc", "feishu_search_doc_wiki",
    "feishu_im_user_get_messages", "feishu_im_user_search_messages",
})


def _is_tool_error(content: str, text_lower: str, tool_name: str) -> bool:
    """Determine if a tool result is an error.

    Handles three cases:
    1. Structural errors: result starts with error indicator (Error:, {"status":"error"})
    2. Exec errors: non-zero exit codes
    3. Keyword errors: error keywords in content, with false-positive filtering
       for content-returning tools (read, web_fetch, etc.)
    """
    # Case 1: structural error indicators (high confidence, any tool)
    stripped = content.strip()
    if stripped.startswith("Error:") or stripped.startswith("error:"):
        return True
    if stripped.startswith("{"):
        # JSON error objects: {"status":"error",...} or {"error":"..."} at top level
        head = content[:300]
        if '"status": "error"' in head or '"status":"error"' in head:
            return True
        if '"error":' in head or '"error" :' in head:
            return True

    # Case 2: non-zero exit codes (exec tool)
    if "exited with code" in text_lower:
        return "exited with code 0)" not in text_lower

    # Case 3: keyword matching
    has_keyword = any(kw in text_lower for kw in _ERROR_KEYWORDS)
    if not has_keyword:
        return False

    # For content-returning tools, filter out false positives where keywords
    # appear inside file/page content rather than being the tool's error.
    if tool_name in _CONTENT_TOOLS:
        # Results starting with file/code content markers are false positives
        # (the keyword appears inside the content being read, not a tool error)
        if stripped.startswith(("1|", "1: ", "#", "---", "import ", "from ",
                                "def ", "class ", "<", "//", "/*", "```")):
            return False
        # JSON/XML content with error keywords inside are false positives
        if stripped.startswith(("{", "[", "<?xml")):
            # Unless the JSON itself IS the error
            head = content[:300]
            if '"status": "error"' in head or '"error":' in head:
                return True
            return False
        return True

    return True


def extract_tool_errors(request: dict[str, Any]) -> dict:
    """Extract tool execution errors from the conversation messages.

    Walks through all tool-result messages, detects errors, categorizes them,
    and tracks recovery patterns (did the agent retry and succeed?).
    """
    messages = request.get("messages", [])

    # Build a map of tool_call_id -> tool_name from assistant messages
    tc_id_to_name: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                tc_id = tc.get("id", "")
                fn = tc.get("function", {})
                name = fn.get("name", "") if isinstance(fn, dict) else ""
                if tc_id and name:
                    tc_id_to_name[tc_id] = name

    tool_errors: list[dict] = []
    tool_success_count = 0
    consecutive_errors = 0
    max_consecutive = 0
    # Track per-tool: last status to determine recovery
    tool_last_error_idx: dict[str, int] = {}  # tool_name -> index of last error
    tool_recovered: dict[str, bool] = {}

    for idx, msg in enumerate(messages):
        role = msg.get("role", "")
        if role != "tool":
            continue

        content = _extract_text(msg.get("content", ""))
        text_lower = content[:800].lower()

        # Resolve tool name
        tool_name = msg.get("name", "")
        if not tool_name:
            tc_id = msg.get("tool_call_id", "")
            tool_name = tc_id_to_name.get(tc_id, "")

        is_error = _is_tool_error(content, text_lower, tool_name)

        if is_error:
            error_type = _classify_error(text_lower, content)
            # Build previous_summary and current_summary
            prev_summary, curr_summary = _build_error_context(
                messages, idx
            )
            tool_errors.append({
                "tool": tool_name,
                "error_type": error_type,
                "error_text": content[:300],
                "position": idx,
                "recovered": False,
                "recovery_message": "",
                "recovery_position": None,
                "previous_summary": prev_summary,
                "current_summary": curr_summary,
            })
            consecutive_errors += 1
            max_consecutive = max(max_consecutive, consecutive_errors)
            tool_last_error_idx[tool_name] = len(tool_errors) - 1
            tool_recovered[tool_name] = False
        else:
            tool_success_count += 1
            consecutive_errors = 0
            # Mark recovery if this tool had a previous error
            if tool_name in tool_last_error_idx and not tool_recovered.get(tool_name):
                err_idx = tool_last_error_idx[tool_name]
                tool_errors[err_idx]["recovered"] = True
                tool_errors[err_idx]["recovery_message"] = content[:300]
                tool_errors[err_idx]["recovery_position"] = idx
                tool_recovered[tool_name] = True

    # Collect unique error types
    error_types = sorted(set(e["error_type"] for e in tool_errors))

    tool_error_count = len(tool_errors)
    total_tool_calls = tool_error_count + tool_success_count
    error_rate = tool_error_count / max(total_tool_calls, 1)

    return {
        "tool_errors": tool_errors,
        "tool_error_count": tool_error_count,
        "tool_success_count": tool_success_count,
        "error_rate": round(error_rate, 3),
        "error_types": error_types,
        "consecutive_error_max": max_consecutive,
    }


def _build_error_context(messages: list[dict], error_idx: int) -> tuple[str, str]:
    """Build previous_summary and current_summary for a tool error.

    - previous_summary: what the agent accomplished before this error
      (from earlier assistant messages — the work context leading up to the error)
    - current_summary: what the agent was trying to do when the error happened
      (from the assistant message that triggered the failing tool call)
    """
    # current_summary: find the assistant message right before this tool result
    # (the one that made the tool_call that failed)
    current_summary = ""
    for i in range(error_idx - 1, -1, -1):
        if messages[i].get("role") == "assistant":
            content = _extract_text(messages[i].get("content", ""))
            if content.strip():
                current_summary = content[:300]
            else:
                # Assistant message has no text content (just tool_calls).
                # Describe what tool was called and with what args.
                tool_calls = messages[i].get("tool_calls", [])
                parts = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "") if isinstance(fn, dict) else ""
                    args = fn.get("arguments", "") if isinstance(fn, dict) else ""
                    if isinstance(args, str) and len(args) > 200:
                        args = args[:200] + "..."
                    parts.append(f"{name}({args})")
                current_summary = "Tool calls: " + "; ".join(parts) if parts else ""
                current_summary = current_summary[:300]
            break

    # previous_summary: collect assistant messages before the current one,
    # walking backwards to find substantive context about what was done
    previous_summary = ""
    assistant_texts = []
    # Start from before the "current" assistant message
    search_start = error_idx - 1
    for i in range(search_start, -1, -1):
        if messages[i].get("role") == "assistant":
            if i == search_start:
                continue  # skip the current one (already captured above)
            content = _extract_text(messages[i].get("content", ""))
            if content.strip() and len(content.strip()) > 10:
                assistant_texts.append(content.strip())
                if len(assistant_texts) >= 3:
                    break

    if assistant_texts:
        # Most recent first, join with separator
        previous_summary = " | ".join(
            t[:150] for t in assistant_texts
        )[:500]

    return previous_summary, current_summary


def _classify_error(text_lower: str, text_full: str) -> str:
    """Categorize a tool error into a type."""
    # Permission / access
    if "permission" in text_lower or "权限" in text_full or "access denied" in text_lower:
        return "permission_error"
    if "cannot access" in text_lower or "eacces" in text_lower or "eperm" in text_lower:
        return "permission_error"
    # File / path not found
    if "not found" in text_lower or "no such file" in text_lower or "does not exist" in text_lower:
        return "not_found"
    if "enoent" in text_lower:
        return "not_found"
    # Timeout
    if "timeout" in text_lower or "timed out" in text_lower:
        return "timeout"
    # Python errors
    if "traceback" in text_lower or "exception" in text_lower:
        return "python_exception"
    # Command / shell errors
    if "exit code" in text_lower or "exited with code" in text_lower:
        return "command_failed"
    # API / auth
    if "api_key" in text_lower or "api key" in text_lower or "missing_brave" in text_lower:
        return "missing_api_key"
    # Rate limiting
    if "rate limit" in text_lower or "rate_limit" in text_lower or "too many" in text_lower:
        return "rate_limit"
    if "http 429" in text_lower or "429 too many" in text_lower:
        return "rate_limit"
    # Network / connection
    if ("connection refused" in text_lower or "connection reset" in text_lower
            or "connection timed out" in text_lower or "couldn't connect" in text_lower
            or "failed to connect" in text_lower):
        return "connection_error"
    # Syntax
    if "syntax" in text_lower and "error" in text_lower:
        return "syntax_error"
    # Fatal
    if "fatal" in text_lower:
        return "fatal_error"
    return "other_error"


# ---------------------------------------------------------------------------
# Token usage extraction
# ---------------------------------------------------------------------------


def extract_token_usage(extra: dict[str, Any]) -> dict:
    """Extract token usage from the extra field."""
    usage = extra.get("usage", "")
    if isinstance(usage, str):
        try:
            usage = json.loads(usage)
        except (json.JSONDecodeError, TypeError):
            usage = {}
    if not isinstance(usage, dict):
        usage = {}

    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


# ---------------------------------------------------------------------------
# Finish reason extraction
# ---------------------------------------------------------------------------


def _extract_finish_reason(response: dict[str, Any]) -> str:
    """Extract finish_reason from the response JSON."""
    choices = response.get("choices", [])
    if choices:
        return choices[0].get("finish_reason", "unknown")
    return "unknown"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _extract_text(content: Any) -> str:
    """Extract text from message content (string or multimodal array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content) if content else ""


def _truncate_user_messages(texts: list[str], max_chars: int) -> str:
    """Combine user messages, prioritizing first and last for intent signal."""
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0][:max_chars]

    # First message (initial intent) + last message (most recent context)
    first = texts[0]
    last = texts[-1]
    half = max_chars // 2

    first_trunc = first[:half]
    last_trunc = last[:half]

    combined = f"[First user message]\n{first_trunc}"
    if len(texts) > 2:
        combined += f"\n\n[... {len(texts) - 2} more messages ...]\n\n"
    else:
        combined += "\n\n"
    combined += f"[Last user message]\n{last_trunc}"

    return combined[:max_chars]


def is_heartbeat_or_bootstrap(user_text: str) -> bool:
    """Check if this is a heartbeat/bootstrap session that can skip LLM."""
    text = user_text.strip()
    if not text:
        return True
    for pattern in HEARTBEAT_PATTERNS:
        if pattern in text:
            return True
    return False
