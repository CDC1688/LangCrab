"""Graph node functions — extract, classify, validate, aggregate."""

from __future__ import annotations

import json
import threading
import unicodedata
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from .config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_ITERATIONS,
    get_classifications_file,
    get_error_report_file,
    get_output_dir,
    get_summary_file,
    get_validation_errors_file,
)
from .parser import is_heartbeat_or_bootstrap, parse_csv, parse_multiple_csvs
from .prompts import CLASSIFY_SYSTEM_PROMPT, CLASSIFY_USER_TEMPLATE
from .schemas import Classification, PipelineState, RowState

# ---------------------------------------------------------------------------
# Progress bar (thread-safe, module-level)
# ---------------------------------------------------------------------------
_progress_bar = None
_progress_lock = threading.Lock()


def _init_progress(total: int) -> None:
    """Create a tqdm progress bar for classification."""
    global _progress_bar
    from tqdm import tqdm

    _progress_bar = tqdm(total=total, desc="Classifying", unit="row", dynamic_ncols=True)


def _tick_progress() -> None:
    """Advance the progress bar by one."""
    global _progress_bar
    if _progress_bar is not None:
        with _progress_lock:
            _progress_bar.update(1)


def _close_progress() -> None:
    """Close the progress bar."""
    global _progress_bar
    if _progress_bar is not None:
        _progress_bar.close()
        _progress_bar = None


# ---------------------------------------------------------------------------
# LLM setup (lazy init) — uses raw OpenAI client like ark_model.py
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


def load_csv(state: PipelineState) -> dict:
    """Load and parse CSV file(s). In continue mode, load prior results and skip done sids."""
    csv_paths = state["csv_paths"]
    limit = state.get("limit", 0)
    continue_mode = state.get("continue_mode", False)
    rows = parse_multiple_csvs(csv_paths, limit=limit)
    print(f"Loaded {len(rows)} rows total from {len(csv_paths)} file(s)")

    prior_classifications: list[dict] = []

    if continue_mode and get_classifications_file().exists():
        # Load already-classified sids from previous run
        with open(get_classifications_file(), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        prior_classifications.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        done_sids = {c["sid"] for c in prior_classifications if "sid" in c}
        before = len(rows)
        rows = [r for r in rows if r["sid"] not in done_sids]
        print(f"Continue mode: {len(done_sids)} already classified, {before - len(rows)} skipped, {len(rows)} remaining")
    else:
        # Fresh run — truncate incremental output files
        get_output_dir().mkdir(parents=True, exist_ok=True)
        for f in [get_classifications_file(), get_output_dir() / "inner_graph_details.jsonl",
                  get_error_report_file(), get_validation_errors_file()]:
            f.write_text("")

    _init_progress(len(rows))
    return {"rows": rows, "prior_classifications": prior_classifications}


def fan_out_to_classify(state: PipelineState) -> list[Send]:
    """Fan out each row to the classify_row subgraph via Send."""
    sends = []
    for row in state["rows"]:
        sends.append(
            Send(
                "classify_row",
                {
                    "sid": row["sid"],
                    "account": row["account"],
                    "model": row["model"],
                    "event_time": row["event_time"],
                    "source_file": row.get("source_file", ""),
                    "system_prompt_summary": row["system_prompt_summary"],
                    "user_messages_text": row["user_messages_text"],
                    "tool_names_used": row["tool_names_used"],
                    "num_messages": row["num_messages"],
                    "num_user_messages": row.get("num_user_messages", 0),
                    "is_cron_triggered": row["is_cron_triggered"],
                    "is_subagent": row["is_subagent"],
                    "tool_errors": row.get("tool_errors", []),
                    "tool_error_count": row.get("tool_error_count", 0),
                    "tool_success_count": row.get("tool_success_count", 0),
                    "error_rate": row.get("error_rate", 0.0),
                    "error_types": row.get("error_types", []),
                    "consecutive_error_max": row.get("consecutive_error_max", 0),
                    "token_usage": row.get("token_usage", {}),
                    "finish_reason": row.get("finish_reason", "unknown"),
                    "error": "no",
                    "messages": [],
                    "classification": None,
                    "iterations": 0,
                    "classifications": [],
                },
            )
        )
    return sends


def aggregate_results(state: PipelineState) -> dict:
    """Aggregate all classifications and write output files."""
    _close_progress()
    prior = state.get("prior_classifications", [])
    new_classifications = state.get("classifications", [])
    classifications = prior + new_classifications
    if prior:
        print(f"\nMerging {len(prior)} prior + {len(new_classifications)} new = {len(classifications)} total")
    print(f"\nAggregating {len(classifications)} classifications...")

    # Ensure output dir exists
    get_output_dir().mkdir(parents=True, exist_ok=True)

    # Rewrite full classifications.jsonl (prior + new) so it's consistent with summary
    if prior:
        with open(get_classifications_file(), "w", encoding="utf-8") as f:
            for c in classifications:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Build summary
    summary = _build_summary(classifications)

    with open(get_summary_file(), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Print summary
    print("\n=== Classification Summary ===")
    print(f"Total classified: {summary['total']}")
    print(f"Heuristic short-circuit: {summary['heuristic_count']}")
    print(f"LLM classified: {summary['llm_count']}")
    print(f"Needed retries: {summary['retry_count']}")
    print("\nCategory distribution:")
    for cat, count in sorted(
        summary["category_counts"].items(), key=lambda x: -x[1]
    ):
        pct = count / max(summary["total"], 1) * 100
        print(f"  {cat:25s} {count:5d}  ({pct:.1f}%)")

    # Error stats
    es = summary.get("error_stats", {})
    if es.get("sessions_with_errors"):
        print(f"\n=== Agent Error Analysis ===")
        print(f"Sessions with tool errors: {es['sessions_with_errors']}")
        print(f"  Recovered (finish=stop): {es['sessions_recovered']}")
        print(f"  Stuck (never finished):  {es['sessions_stuck']}")
        print(f"  Error loops (3+ consecutive): {es['error_loops']}")
        print(f"  Total tool errors: {es['total_tool_errors']}")
        if es.get("error_type_counts"):
            print("\nError types:")
            for etype, count in sorted(
                es["error_type_counts"].items(), key=lambda x: -x[1]
            ):
                print(f"  {etype:25s} {count:5d}")

    return {"summary": summary}


def _build_summary(classifications: list[dict]) -> dict:
    """Build analytics summary from classifications."""
    total = len(classifications)
    category_counts: dict[str, int] = {}
    model_category: dict[str, dict[str, int]] = {}
    language_counts: dict[str, int] = {}
    heuristic_count = 0
    retry_count = 0
    confidence_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}

    # Error stats
    sessions_with_errors = 0
    sessions_recovered = 0
    sessions_stuck = 0
    error_loops = 0
    error_type_counts: dict[str, int] = {}
    tool_error_counts: dict[str, int] = {}
    total_tool_errors = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for c in classifications:
        cat = c.get("primary_category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1

        model = c.get("model", "unknown")
        if model not in model_category:
            model_category[model] = {}
        model_category[model][cat] = model_category[model].get(cat, 0) + 1

        lang = c.get("language", "unknown")
        language_counts[lang] = language_counts.get(lang, 0) + 1

        conf = c.get("confidence", "medium")
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

        if c.get("heuristic_classified"):
            heuristic_count += 1
        if c.get("iterations", 1) > 1:
            retry_count += 1

        # Error stats
        err_count = c.get("tool_error_count", 0)
        if err_count > 0:
            sessions_with_errors += 1
            total_tool_errors += err_count
            if c.get("finish_reason") == "stop":
                sessions_recovered += 1
            else:
                sessions_stuck += 1
            if c.get("consecutive_error_max", 0) >= 3:
                error_loops += 1

        for etype in c.get("error_types", []):
            error_type_counts[etype] = error_type_counts.get(etype, 0) + 1

        # Token usage
        usage = c.get("token_usage", {})
        total_prompt_tokens += usage.get("prompt_tokens", 0)
        total_completion_tokens += usage.get("completion_tokens", 0)

    return {
        "total": total,
        "heuristic_count": heuristic_count,
        "llm_count": total - heuristic_count,
        "retry_count": retry_count,
        "category_counts": category_counts,
        "model_category": model_category,
        "language_counts": language_counts,
        "confidence_counts": confidence_counts,
        # Error analysis
        "error_stats": {
            "sessions_with_errors": sessions_with_errors,
            "sessions_recovered": sessions_recovered,
            "sessions_stuck": sessions_stuck,
            "error_loops": error_loops,
            "total_tool_errors": total_tool_errors,
            "error_type_counts": error_type_counts,
        },
        # Token usage
        "token_usage": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
        },
    }


# ===================================================================
# INNER GRAPH NODES (self-correction loop)
# ===================================================================


def extract_signal(state: RowState) -> dict:
    """Prepare the initial classification prompt, or short-circuit for obvious cases."""
    user_text = state["user_messages_text"]

    # Heuristic short-circuit
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

    # Build initial classification prompt
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


def route_after_extract(state: RowState) -> str:
    """Route: skip LLM if heuristic already classified."""
    if state.get("classification") is not None:
        return "already_classified"
    return "needs_llm"


def classify(state: RowState) -> dict:
    """Call LLM to classify the log entry — uses raw OpenAI client + JSON parsing."""
    messages = state["messages"]
    iterations = state["iterations"]

    client = _get_client()

    # Convert LangChain messages to OpenAI format
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

    # Parse JSON from the LLM response
    classification = _parse_classification(raw_content)

    # Append attempt to message history (like the code_assistant notebook)
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

    # Try to find JSON block (```json ... ``` or bare { ... })
    json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Find the first { ... } block (non-greedy to avoid matching multiple objects)
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
        if brace_match:
            json_str = brace_match.group(0)
        else:
            json_str = raw

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback: try to find any valid JSON object in the string
        for match in re.finditer(r"\{[^{}]+\}", raw):
            try:
                parsed = json.loads(match.group(0))
                if "primary_category" in parsed:
                    break
            except json.JSONDecodeError:
                continue
        else:
            # Last resort: return a default classification
            return Classification(
                primary_category="other",
                subcategory="parse_failed",
                user_intent_summary=f"Failed to parse LLM response: {raw[:100]}",
                language="mixed",
                is_cron_triggered=False,
                is_subagent=False,
                confidence="low",
            )

    # Fix invalid enum values before Pydantic validation
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


def validate(state: RowState) -> dict:
    """Programmatic consistency checks — the 'code_check' equivalent."""
    classification = state["classification"]
    tools = state["tool_names_used"]
    errors: list[str] = []

    # Check 1: Tool-category consistency for feishu
    if any("feishu" in t for t in tools):
        if classification.primary_category != "communication":
            errors.append(
                f"Tools include feishu_* but category is "
                f"'{classification.primary_category}', expected 'communication'"
            )

    # Check 2: Cron detection consistency
    if state["is_cron_triggered"] and not classification.is_cron_triggered:
        errors.append(
            "Message starts with [cron:] but is_cron_triggered=False"
        )

    # Check 3: Language detection vs actual character ratio
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

    # Check 4: Intent summary quality
    if len(classification.user_intent_summary) < 10:
        errors.append("Intent summary too short (< 10 chars)")

    # Check 5: Category-tool plausibility
    coding_tools = {"exec", "read", "write", "edit"}
    if classification.primary_category == "coding" and not (
        set(tools) & coding_tools
    ):
        if tools:  # only flag if there are tools at all
            errors.append(
                f"Category is 'coding' but no coding tools used "
                f"(tools: {', '.join(tools)})"
            )

    if errors:
        # Log validation errors
        _log_validation_error(state, errors)

        error_msg = HumanMessage(
            content=(
                "Classification failed validation:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\n\nReflect on these errors and reclassify. "
                "Pay attention to the tool names and message content."
            )
        )
        return {
            "messages": [error_msg],
            "error": "yes",
        }

    return {"error": "no"}


def _log_validation_error(state: RowState, errors: list[str]) -> None:
    """Append validation errors to the JSONL log with full context."""
    get_output_dir().mkdir(parents=True, exist_ok=True)

    classification = state["classification"]

    # Extract the classification prompt we sent to the LLM
    # messages[0] = SystemMessage (prompt), messages[1] = HumanMessage (user data)
    raw_messages = state.get("messages", [])
    prompt_sent = ""
    for msg in raw_messages:
        if hasattr(msg, "type") and msg.type == "system":
            prompt_sent = msg.content
            break
        elif isinstance(msg, dict) and msg.get("type") == "system":
            prompt_sent = msg.get("content", "")
            break

    entry = {
        "sid": state["sid"],
        "account": state["account"],
        "model": state["model"],
        "event_time": state["event_time"],
        "iteration": state["iterations"],
        "errors": errors,
        # --- The LLM's full classification attempt ---
        "attempted_classification": classification.model_dump()
        if classification
        else None,
        # --- The original user request from the CSV ---
        "user_messages_text": state["user_messages_text"],
        # --- The agent's system prompt excerpt ---
        "system_prompt_summary": state["system_prompt_summary"],
        # --- What tools the agent used ---
        "tool_names_used": state["tool_names_used"],
        # --- Detected flags ---
        "is_cron_triggered": state["is_cron_triggered"],
        "is_subagent": state["is_subagent"],
        "num_messages": state["num_messages"],
        # --- The exact prompt sent to the classification LLM ---
        "classification_prompt": prompt_sent[:1000],
        # --- Full retry conversation history ---
        "message_history": [
            {
                "role": getattr(msg, "type", "unknown"),
                "content": msg.content[:500]
                if hasattr(msg, "content")
                else str(msg)[:500],
            }
            for msg in raw_messages
        ],
    }
    with open(get_validation_errors_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def decide_to_finish(state: RowState) -> str:
    """Conditional edge: finish or retry (mirrors notebook's decide_to_finish)."""
    if state["error"] == "no" or state["iterations"] >= MAX_ITERATIONS:
        return "end"
    return "retry"


def format_result(state: RowState) -> dict:
    """Package classification for the outer graph's operator.add reducer.
    Also writes inner graph details to a separate JSONL file."""
    classification = state["classification"]
    result = classification.model_dump() if classification else {}
    result.update(
        {
            "sid": state["sid"],
            "account": state["account"],
            "model": state["model"],
            "event_time": state["event_time"],
            "source_file": state.get("source_file", ""),
            "iterations": state["iterations"],
            "had_errors": state["error"] == "yes",
            "heuristic_classified": state["iterations"] == 0,
            "tool_names_used": state["tool_names_used"],
            "num_messages": state["num_messages"],
            # Agent error summary fields
            "tool_error_count": state.get("tool_error_count", 0),
            "tool_success_count": state.get("tool_success_count", 0),
            "error_rate": state.get("error_rate", 0.0),
            "error_types": state.get("error_types", []),
            "consecutive_error_max": state.get("consecutive_error_max", 0),
            "finish_reason": state.get("finish_reason", "unknown"),
            "token_usage": state.get("token_usage", {}),
        }
    )

    # Write classification immediately (incremental, not batched)
    _append_classification(result)

    # Write inner graph details
    _log_inner_graph_details(state, result)

    # Write error report for rows with tool errors
    if state.get("tool_error_count", 0) > 0:
        _write_error_report(state, result)

    _tick_progress()
    return {"classifications": [result]}


_classify_write_lock = threading.Lock()


def _append_classification(result: dict) -> None:
    """Append a single classification to classifications.jsonl immediately."""
    get_output_dir().mkdir(parents=True, exist_ok=True)
    with _classify_write_lock:
        with open(get_classifications_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")


def _log_inner_graph_details(state: RowState, result: dict) -> None:
    """Write full inner graph trace for each row."""
    get_output_dir().mkdir(parents=True, exist_ok=True)
    details_file = get_output_dir() / "inner_graph_details.jsonl"

    raw_messages = state.get("messages", [])

    detail = {
        # --- Row identity ---
        "sid": state["sid"],
        "account": state["account"],
        "model": state["model"],
        "event_time": state["event_time"],
        "source_file": state.get("source_file", ""),
        # --- Input signal (what extract_signal produced) ---
        "input": {
            "system_prompt_summary": state["system_prompt_summary"],
            "user_messages_text": state["user_messages_text"],
            "tool_names_used": state["tool_names_used"],
            "num_messages": state["num_messages"],
            "num_user_messages": state.get("num_user_messages", 0),
            "is_cron_triggered": state["is_cron_triggered"],
            "is_subagent": state["is_subagent"],
        },
        # --- Classification result ---
        "result": {
            "primary_category": result.get("primary_category"),
            "subcategory": result.get("subcategory"),
            "user_intent_summary": result.get("user_intent_summary"),
            "language": result.get("language"),
            "confidence": result.get("confidence"),
        },
        # --- Self-correction loop details ---
        "loop": {
            "iterations": state["iterations"],
            "had_errors": state["error"] == "yes",
            "heuristic_classified": state["iterations"] == 0,
        },
        # --- Full message history (all prompts, attempts, error feedback) ---
        "message_history": [
            {
                "role": getattr(msg, "type", "unknown"),
                "content": msg.content if hasattr(msg, "content") else str(msg),
            }
            for msg in raw_messages
        ],
    }

    with open(details_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(detail, ensure_ascii=False) + "\n")


def _write_error_report(state: RowState, result: dict) -> None:
    """Write detailed error report for rows where the agent had tool errors."""
    get_output_dir().mkdir(parents=True, exist_ok=True)

    tool_errors = state.get("tool_errors", [])
    finish_reason = state.get("finish_reason", "unknown")
    error_count = state.get("tool_error_count", 0)
    success_count = state.get("tool_success_count", 0)

    report = {
        # --- Identity ---
        "sid": state["sid"],
        "account": state["account"],
        "model": state["model"],
        "event_time": state["event_time"],
        "source_file": state.get("source_file", ""),
        # --- Classification context ---
        "primary_category": result.get("primary_category"),
        "subcategory": result.get("subcategory"),
        "user_intent_summary": result.get("user_intent_summary"),
        # --- Error severity indicators ---
        "finish_reason": finish_reason,
        "agent_recovered": finish_reason == "stop",
        "tool_error_count": error_count,
        "tool_success_count": success_count,
        "error_rate": round(error_count / max(error_count + success_count, 1), 3),
        "consecutive_error_max": state.get("consecutive_error_max", 0),
        "error_loop_detected": state.get("consecutive_error_max", 0) >= 3,
        # --- Error details ---
        "error_types": state.get("error_types", []),
        "tool_errors": [
            {
                "tool": e.get("tool", ""),
                "error_type": e.get("error_type", ""),
                "error_text": e.get("error_text", "")[:500],
                "position": e.get("position", 0),
                "recovered": e.get("recovered", False),
                "recovery_message": e.get("recovery_message", "")[:500],
                "recovery_position": e.get("recovery_position"),
                "previous_summary": e.get("previous_summary", ""),
                "current_summary": e.get("current_summary", ""),
            }
            for e in tool_errors
        ],
        # --- Context for debugging ---
        "user_messages_text": state["user_messages_text"],
        "system_prompt_summary": state["system_prompt_summary"],
        "tool_names_used": state["tool_names_used"],
        "num_messages": state["num_messages"],
        "token_usage": state.get("token_usage", {}),
    }

    with open(get_error_report_file(), "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")
