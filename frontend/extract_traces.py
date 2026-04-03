"""Extract full agent conversation traces from raw CSV files.

Reads the CSV, finds sessions by SID, and saves the full message flow
(user messages, tool calls, tool results, agent responses) into agent_traces.jsonl.

Usage:
    python -m openclaw_log_analyzer.frontend.extract_traces \
        --csv data/logs2_oc_0320.csv \
        --classifications output/output_new/classifications.jsonl \
        --output output/output_new/agent_traces.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

csv.field_size_limit(sys.maxsize)


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


_ERROR_KEYWORDS = (
    "error", "traceback", "exception", "exit code",
    "exited with code", "command failed", "permission denied",
    "no such file", "cannot access", "not found",
    "timed out", "connection refused", "fatal",
)

_CONTENT_TOOLS = frozenset({
    "read", "read_file", "web_fetch", "web_search",
    "memory_get", "memory_search", "memory_recall",
    "feishu_fetch_doc", "feishu_search_doc_wiki",
    "feishu_im_user_get_messages", "feishu_im_user_search_messages",
})


def _is_tool_error(content: str, text_lower: str, tool_name: str) -> bool:
    """Determine if a tool result is an error, with false-positive filtering."""
    stripped = content.strip()
    if stripped.startswith("Error:") or stripped.startswith("error:"):
        return True
    if stripped.startswith("{"):
        head = content[:300]
        if '"status": "error"' in head or '"status":"error"' in head:
            return True
        if '"error":' in head or '"error" :' in head:
            return True
    if "exited with code" in text_lower:
        return "exited with code 0)" not in text_lower
    has_keyword = any(kw in text_lower for kw in _ERROR_KEYWORDS)
    if not has_keyword:
        return False
    if tool_name in _CONTENT_TOOLS:
        if stripped.startswith(("1|", "1: ", "#", "---", "import ", "from ",
                                "def ", "class ", "<", "//", "/*", "```")):
            return False
        if stripped.startswith(("{", "[", "<?xml")):
            head = content[:300]
            if '"status": "error"' in head or '"error":' in head:
                return True
            return False
        return True
    return True


def extract_agent_trace(request: dict) -> list[dict]:
    """Extract the agent conversation flow from a request JSON.

    Returns a list of trace steps, each representing one message in the conversation.
    Each step has: type, role, content (truncated), tool_name, tool_args, is_error, etc.
    """
    messages = request.get("messages", [])
    if not messages:
        return []

    # Build tool_call_id → tool_name map from assistant messages
    tc_id_to_name: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                tc_id = tc.get("id", "")
                fn = tc.get("function", {})
                name = fn.get("name", "") if isinstance(fn, dict) else ""
                if tc_id and name:
                    tc_id_to_name[tc_id] = name

    steps = []
    for idx, msg in enumerate(messages):
        role = msg.get("role", "")
        content_raw = msg.get("content", "")
        content = _extract_text(content_raw)

        if role == "system":
            steps.append({
                "idx": idx,
                "type": "system",
                "content": content[:500],
            })

        elif role in ("user", "human"):
            steps.append({
                "idx": idx,
                "type": "user",
                "content": content[:1000],
            })

        elif role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                # Assistant making tool calls
                calls = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "") if isinstance(fn, dict) else ""
                    args_raw = fn.get("arguments", "") if isinstance(fn, dict) else ""
                    # Parse args if string
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except (json.JSONDecodeError, TypeError):
                            args = {"raw": args_raw[:200]}
                    else:
                        args = args_raw
                    # Truncate large arg values
                    if isinstance(args, dict):
                        args = {k: (v[:200] if isinstance(v, str) and len(v) > 200 else v) for k, v in args.items()}
                    calls.append({
                        "id": tc.get("id", ""),
                        "name": name,
                        "args": args,
                    })
                steps.append({
                    "idx": idx,
                    "type": "tool_calls",
                    "content": content[:300] if content.strip() else "",
                    "tool_calls": calls,
                })
            else:
                # Assistant text response
                steps.append({
                    "idx": idx,
                    "type": "assistant",
                    "content": content[:1000],
                })

        elif role == "tool":
            tool_name = msg.get("name", "")
            if not tool_name:
                tc_id = msg.get("tool_call_id", "")
                tool_name = tc_id_to_name.get(tc_id, "unknown")

            content_lower = content[:800].lower()
            is_error = _is_tool_error(content, content_lower, tool_name)

            steps.append({
                "idx": idx,
                "type": "tool_result",
                "tool_name": tool_name,
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": content[:500],
                "is_error": is_error,
            })

    return steps


def extract_traces_from_csv(
    csv_path: str,
    target_sids: set[str],
) -> dict[str, list[dict]]:
    """Read CSV and extract agent traces for target SIDs."""
    traces = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("sid", "")
            if sid not in target_sids:
                continue
            try:
                request = json.loads(row.get("request", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue

            steps = extract_agent_trace(request)
            if steps:
                traces[sid] = steps

            # Early exit if we found all
            if len(traces) == len(target_sids):
                break

    return traces


def main():
    parser = argparse.ArgumentParser(description="Extract agent traces from CSV")
    parser.add_argument("--csv", required=True, nargs="+", help="CSV file(s)")
    parser.add_argument("--classifications", required=True, help="classifications.jsonl")
    parser.add_argument("--output", required=True, help="Output agent_traces.jsonl")
    args = parser.parse_args()

    # Load target SIDs from classifications
    target_sids = set()
    with open(args.classifications, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            sid = record.get("sid", "")
            if sid:
                target_sids.add(sid)

    print(f"Looking for {len(target_sids)} sessions across {len(args.csv)} CSV file(s)")

    all_traces = {}
    for csv_path in args.csv:
        remaining = target_sids - set(all_traces.keys())
        if not remaining:
            break
        print(f"  Scanning {csv_path}...")
        traces = extract_traces_from_csv(csv_path, remaining)
        all_traces.update(traces)
        print(f"    Found {len(traces)} sessions (total: {len(all_traces)})")

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for sid, steps in all_traces.items():
            record = {"sid": sid, "steps": steps}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    found = len(all_traces)
    missing = len(target_sids) - found
    print(f"\nDone. Wrote {found} traces to {args.output}")
    if missing > 0:
        print(f"  Warning: {missing} sessions not found in CSV files")


if __name__ == "__main__":
    main()
