#!/usr/bin/env python3
"""Generate sample classification output for dashboard testing.

Run this to create sample data without needing an LLM API key:
    python -m openclaw_log_analyzer.generate_sample
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .config import get_classifications_file, get_output_dir, get_summary_file, get_validation_errors_file
from .parser import parse_csv

# Sample subcategories per category
SUBCATEGORIES = {
    "coding": ["bug_fix", "new_feature", "code_review", "refactor", "script_writing", "devops"],
    "file_management": ["file_read", "file_write", "file_organize", "backup"],
    "web_research": ["web_search", "url_fetch", "info_gathering", "documentation"],
    "scheduling": ["cron_job", "reminder", "recurring_task", "one_time_alarm"],
    "communication": ["feishu_bot", "feishu_doc", "telegram", "group_chat", "notification"],
    "data_analysis": ["report_generation", "data_extraction", "price_tracking", "log_analysis"],
    "system_maintenance": ["heartbeat", "status_check", "session_bootstrap", "system_doctor"],
    "content_creation": ["tweet", "article", "blog_post", "translation", "summary"],
    "finance_crypto": ["price_monitor", "trading_bot", "portfolio", "market_analysis"],
    "memory_management": ["memory_store", "memory_recall", "preference_update"],
    "agent_orchestration": ["subagent_spawn", "session_manage", "multi_agent_coord"],
    "other": ["misc", "unclear", "mixed_intent"],
}

INTENTS_ZH = {
    "coding": ["编写Python函数处理数据", "调试API接口错误", "重构数据库查询逻辑", "写一个爬虫脚本"],
    "communication": ["发送飞书消息给团队", "创建飞书文档分享", "发送Telegram通知", "设置群聊机器人"],
    "scheduling": ["设置每日定时提醒", "创建定时推文分析任务", "配置系统监控定时检查"],
    "data_analysis": ["生成每日推文分析报告", "提取价格数据并分析趋势", "分析日志错误分布"],
    "system_maintenance": ["自动心跳检查", "系统状态监控", "会话初始化"],
    "content_creation": ["撰写技术博客文章", "生成推文内容", "翻译英文文档"],
    "finance_crypto": ["监控BTC价格变动", "分析加密货币市场", "追踪投资组合表现"],
    "web_research": ["搜索最新技术资讯", "获取API文档", "调研竞品功能"],
    "memory_management": ["保存用户偏好设置", "回忆之前的讨论内容"],
    "agent_orchestration": ["启动子代理处理任务", "协调多个代理完成工作"],
    "file_management": ["读取配置文件", "整理项目文件结构", "创建备份"],
    "other": ["一般性对话", "询问功能使用方法"],
}

MODELS = [
    "deepseek-v3-2-251201",
    "doubao-seed-2-0-code-preview-260215",
    "doubao-seed-2-0-pro-260215",
    "glm-4-7-251222",
    "kimi-k2-5-260127",
    "minimax-m2-5-260212",
]


def generate_sample_data(csv_path: str, limit: int = 200):
    """Parse real CSV and generate plausible classifications."""
    rows = parse_csv(csv_path, limit=limit)
    random.seed(42)

    get_output_dir().mkdir(parents=True, exist_ok=True)

    # Clear previous
    for f in [get_classifications_file(), get_validation_errors_file()]:
        if f.exists():
            f.unlink()

    classifications = []
    validation_errors = []

    # Category distribution weights (realistic for OpenClaw)
    category_weights = {
        "coding": 0.25,
        "communication": 0.15,
        "system_maintenance": 0.15,
        "scheduling": 0.10,
        "data_analysis": 0.08,
        "content_creation": 0.07,
        "web_research": 0.06,
        "finance_crypto": 0.04,
        "memory_management": 0.03,
        "agent_orchestration": 0.03,
        "file_management": 0.02,
        "other": 0.02,
    }
    categories = list(category_weights.keys())
    weights = list(category_weights.values())

    for row in rows:
        # Use heuristics when possible
        cat = None
        subcat = None
        heuristic = False
        iterations = 1

        if "HEARTBEAT" in row["user_messages_text"] or not row["user_messages_text"].strip():
            cat = "system_maintenance"
            subcat = "heartbeat"
            heuristic = True
            iterations = 0
        elif row["is_cron_triggered"]:
            cat = "scheduling"
            subcat = "cron_job"
        elif any("feishu" in t for t in row["tool_names_used"]):
            cat = "communication"
            subcat = random.choice(["feishu_bot", "feishu_doc", "notification"])
        else:
            cat = random.choices(categories, weights=weights, k=1)[0]
            subcat = random.choice(SUBCATEGORIES[cat])

        # Determine language
        cjk = sum(1 for c in row["user_messages_text"] if ord(c) > 0x4E00)
        total = max(len(row["user_messages_text"]), 1)
        if cjk / total > 0.3:
            lang = "zh"
        elif cjk / total > 0.05:
            lang = "mixed"
        else:
            lang = "en"

        # Confidence
        if heuristic:
            conf = "high"
        else:
            conf = random.choices(["high", "medium", "low"], weights=[0.6, 0.3, 0.1])[0]

        # Simulate retries for some entries
        had_errors = False
        if not heuristic and random.random() < 0.15:
            iterations = random.choice([2, 3])
            had_errors = True
            validation_errors.append({
                "sid": row["sid"],
                "iteration": 1,
                "errors": [random.choice([
                    "Tools include feishu_* but category is 'coding'",
                    "Text is 80% CJK characters but language='en'",
                    "Intent summary too short (< 10 chars)",
                    "Category is 'coding' but no coding tools used",
                    "Message starts with [cron:] but is_cron_triggered=False",
                ])],
                "attempted_category": random.choice(categories),
            })

        intent_options = INTENTS_ZH.get(cat, ["General interaction"])
        intent = random.choice(intent_options)

        entry = {
            "sid": row["sid"],
            "account": row["account"],
            "model": row["model"],
            "event_time": row["event_time"],
            "primary_category": cat,
            "subcategory": subcat,
            "user_intent_summary": intent,
            "language": lang,
            "is_cron_triggered": row["is_cron_triggered"],
            "is_subagent": row["is_subagent"],
            "confidence": conf,
            "iterations": iterations,
            "had_errors": had_errors,
            "heuristic_classified": heuristic,
            "tool_names_used": row["tool_names_used"],
            "num_messages": row["num_messages"],
        }
        classifications.append(entry)

    # Write outputs
    with open(get_classifications_file(), "w", encoding="utf-8") as f:
        for c in classifications:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    with open(get_validation_errors_file(), "w", encoding="utf-8") as f:
        for e in validation_errors:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # Summary
    from .nodes import _build_summary
    summary = _build_summary(classifications)
    with open(get_summary_file(), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(classifications)} sample classifications")
    print(f"Generated {len(validation_errors)} sample validation errors")
    print(f"Output: {get_output_dir()}/")
    return classifications


if __name__ == "__main__":
    generate_sample_data("data/logs2_oc_0320.csv", limit=200)
