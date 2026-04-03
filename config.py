"""Configuration for the log analyzer pipeline."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------
# Uses OpenAI-compatible API (works with VolcEngine ARK, OpenAI, etc.)
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
)
LLM_API_KEY = os.getenv("ARK_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "doubao-seed-2-0-pro-260215")

# ---------------------------------------------------------------------------
# Classification pipeline
# ---------------------------------------------------------------------------
MAX_ITERATIONS = 3  # max self-correction retries per row
MAX_CONCURRENCY = 30  # parallel LLM calls
MAX_USER_TEXT_CHARS = 3000  # truncation limit for user message text
MAX_SYSTEM_PROMPT_CHARS = 500  # truncation limit for system prompt

# ---------------------------------------------------------------------------
# Heuristic short-circuit patterns
# ---------------------------------------------------------------------------
HEARTBEAT_PATTERNS = [
    "Read HEARTBEAT.md",
    "HEARTBEAT_OK",
    "HEARTBEAT.md if it exists",
    "(session bootstrap)",
]

# ---------------------------------------------------------------------------
# Output paths — functions so --output-dir flag works at runtime
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_output_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "output")))


def get_classifications_file() -> Path:
    return get_output_dir() / "classifications.jsonl"


def get_validation_errors_file() -> Path:
    return get_output_dir() / "validation_errors.jsonl"


def get_error_report_file() -> Path:
    return get_output_dir() / "error_report.jsonl"


def get_summary_file() -> Path:
    return get_output_dir() / "summary.json"

# ---------------------------------------------------------------------------
# Category taxonomy
# ---------------------------------------------------------------------------
CATEGORY_DESCRIPTIONS = {
    "coding": "Writing, debugging, reviewing, or refactoring code",
    "file_management": "Reading, creating, editing, or organizing files",
    "web_research": "Searching the web, fetching URLs, research tasks",
    "scheduling": "Setting up cron jobs, reminders, calendar events, timed tasks",
    "communication": "Feishu/Telegram/email messaging, bots, group chats, doc sharing",
    "data_analysis": "Analyzing data, generating reports, price tracking, analytics",
    "system_maintenance": "Heartbeat checks, status monitoring, system doctor, session management",
    "content_creation": "Writing articles, posts, reports, tweets, creative content",
    "finance_crypto": "Cryptocurrency tracking, trading, financial analysis, portfolio",
    "memory_management": "Storing/retrieving memories, preference management, knowledge base",
    "agent_orchestration": "Sub-agent management, session spawning, multi-agent coordination",
    "other": "Anything that doesn't fit the above categories",
}
