"""Load and merge JSONL output files, index by sid."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


class DataLoader:
    """Loads pipeline output files and provides filtered access."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._classifications: dict[str, dict] = {}
        self._inner_details: dict[str, dict] = {}
        self._error_reports: dict[str, dict] = {}
        self._agent_traces: dict[str, list] = {}
        self._summary: dict = {}
        self._mtime: dict[str, float] = {}
        self.reload()

    def reload(self):
        """Load or reload all data files."""
        self._load_jsonl("classifications.jsonl", self._classifications)
        self._load_jsonl("inner_graph_details.jsonl", self._inner_details)
        self._load_jsonl("error_report.jsonl", self._error_reports)
        self._load_agent_traces()

        summary_path = self.data_dir / "summary.json"
        if summary_path.exists():
            with open(summary_path, encoding="utf-8") as f:
                self._summary = json.load(f)

    def _load_jsonl(self, filename: str, target: dict):
        path = self.data_dir / filename
        if not path.exists():
            return
        mtime = path.stat().st_mtime
        if self._mtime.get(filename) == mtime:
            return  # no change
        self._mtime[filename] = mtime
        target.clear()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                sid = record.get("sid", "")
                if sid:
                    target[sid] = record

    def _load_agent_traces(self):
        """Load agent_traces.jsonl — stores steps as list, keyed by sid."""
        filename = "agent_traces.jsonl"
        path = self.data_dir / filename
        if not path.exists():
            return
        mtime = path.stat().st_mtime
        if self._mtime.get(filename) == mtime:
            return
        self._mtime[filename] = mtime
        self._agent_traces.clear()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                sid = record.get("sid", "")
                if sid:
                    self._agent_traces[sid] = record.get("steps", [])

    def check_reload(self):
        """Check if files changed and reload if needed."""
        changed = False
        for filename in ["classifications.jsonl", "inner_graph_details.jsonl", "error_report.jsonl", "agent_traces.jsonl"]:
            path = self.data_dir / filename
            if path.exists():
                mtime = path.stat().st_mtime
                if self._mtime.get(filename) != mtime:
                    changed = True
                    break
        if changed:
            self.reload()

    @property
    def sids(self) -> list[str]:
        return list(self._classifications.keys())

    @property
    def total(self) -> int:
        return len(self._classifications)

    def get_summary(self) -> dict:
        return self._summary

    def get_session(self, sid: str) -> Optional[dict]:
        """Get merged session data."""
        cls = self._classifications.get(sid)
        if not cls:
            return None
        return {
            "classification": cls,
            "inner_graph": self._inner_details.get(sid),
            "error_report": self._error_reports.get(sid),
            "agent_trace": self._agent_traces.get(sid, []),
        }

    def get_sessions(
        self,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        model: Optional[str] = None,
        confidence: Optional[str] = None,
        has_errors: Optional[bool] = None,
        keyword: Optional[str] = None,
        annotation_status: Optional[str] = None,
        annotation_map: Optional[dict[str, str]] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        """Filter and paginate sessions. Returns (items, total_matching)."""
        results = []
        for sid, cls in self._classifications.items():
            if category and cls.get("primary_category") != category:
                continue
            if subcategory and cls.get("subcategory") != subcategory:
                continue
            if model and cls.get("model") != model:
                continue
            if confidence and cls.get("confidence") != confidence:
                continue
            if has_errors is not None:
                has_err = cls.get("tool_error_count", 0) > 0
                if has_errors != has_err:
                    continue
            if keyword:
                kw = keyword.lower()
                searchable = (
                    cls.get("user_intent_summary", "")
                    + cls.get("sid", "")
                    + cls.get("primary_category", "")
                    + cls.get("subcategory", "")
                ).lower()
                if kw not in searchable:
                    continue
            if annotation_status and annotation_map:
                ann_st = annotation_map.get(sid)
                if annotation_status == "pending":
                    if ann_st is not None:
                        continue
                elif ann_st != annotation_status:
                    continue

            ann_st = annotation_map.get(sid) if annotation_map else None
            results.append({
                "sid": sid,
                "account": cls.get("account", ""),
                "model": cls.get("model", ""),
                "event_time": cls.get("event_time", ""),
                "primary_category": cls.get("primary_category", ""),
                "subcategory": cls.get("subcategory", ""),
                "user_intent_summary": cls.get("user_intent_summary", ""),
                "language": cls.get("language", ""),
                "confidence": cls.get("confidence", ""),
                "iterations": cls.get("iterations", 0),
                "heuristic_classified": cls.get("heuristic_classified", False),
                "had_errors": cls.get("had_errors", False),
                "tool_error_count": cls.get("tool_error_count", 0),
                "error_rate": cls.get("error_rate", 0.0),
                "num_messages": cls.get("num_messages", 0),
                "annotation_status": ann_st,
            })

        total = len(results)
        # Sort by event_time desc
        results.sort(key=lambda x: x.get("event_time", ""), reverse=True)
        return results[offset : offset + limit], total

    def get_filters(self) -> dict:
        """Get available filter values."""
        categories = set()
        subcategories = set()
        models = set()
        accounts = set()
        for cls in self._classifications.values():
            categories.add(cls.get("primary_category", ""))
            sc = cls.get("subcategory", "")
            if sc:
                subcategories.add(sc)
            models.add(cls.get("model", ""))
            accounts.add(cls.get("account", ""))
        return {
            "categories": sorted(categories),
            "subcategories": sorted(subcategories),
            "models": sorted(models),
            "accounts": sorted(accounts),
            "confidences": ["high", "medium", "low"],
            "annotation_statuses": ["pending", "approved", "rejected", "flagged", "corrected"],
        }

    def get_subcategory_counts(self, category: Optional[str] = None) -> dict[str, int]:
        """Get subcategory counts, optionally filtered by primary category."""
        counts: dict[str, int] = {}
        for cls in self._classifications.values():
            if category and cls.get("primary_category") != category:
                continue
            sc = cls.get("subcategory", "")
            if sc:
                counts[sc] = counts.get(sc, 0) + 1
        return counts
