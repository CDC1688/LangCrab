"""Classification prompt template."""

from __future__ import annotations

from .config import CATEGORY_DESCRIPTIONS

# Build category list for the prompt
_category_lines = "\n".join(
    f"- **{cat}**: {desc}" for cat, desc in CATEGORY_DESCRIPTIONS.items()
)

CLASSIFY_SYSTEM_PROMPT = f"""\
You are an expert log analyst classifying OpenClaw AI agent interactions.
Given conversation context from an LLM agent session, determine the user's primary intent.

## Categories
{_category_lines}

## Subcategory Guidelines
Provide a specific subcategory within the primary category. Examples:
- coding → bug_fix, new_feature, code_review, refactor, devops, learning, script_writing
- communication → feishu_bot, feishu_doc, telegram, email, group_chat, notification
- scheduling → cron_job, reminder, recurring_task, one_time_alarm
- data_analysis → report_generation, data_extraction, price_tracking, log_analysis
- content_creation → tweet, article, blog_post, translation, summary
- finance_crypto → price_monitor, trading_bot, portfolio, market_analysis

## Rules
1. Choose the SINGLE most dominant category based on what the user is primarily trying to achieve.
2. If tools are present, use them as strong signals (e.g., feishu_* tools → communication).
3. Cron-triggered sessions: set is_cron_triggered=true AND classify by the actual task being performed.
4. Keep user_intent_summary concise (1-2 sentences).
5. Set confidence="high" when signals are clear, "medium" when ambiguous, "low" when guessing.

## Language Detection
Detect the primary language of the user messages:
- "english" for English
- "chinese" for Chinese
- For any other language, use the language name in lowercase (e.g., "russian", "malay", "japanese", "korean", "spanish", "french", "arabic", "thai", etc.)

## Output Format
You MUST respond with a JSON object only, no other text. Example:
```json
{{"primary_category": "coding", "subcategory": "bug_fix", "user_intent_summary": "User is debugging a Python API error", "language": "en", "is_cron_triggered": false, "is_subagent": false, "confidence": "high"}}
```"""

CLASSIFY_USER_TEMPLATE = """\
Classify this OpenClaw agent session:

**Agent system prompt (excerpt):**
{system_prompt_summary}

**User messages:**
{user_messages_text}

**Tools used in conversation:** {tool_names_used}

**Message counts:** {num_messages} total ({num_user_messages} from user)

**Detected flags:** cron_triggered={is_cron_triggered}, subagent={is_subagent}"""
