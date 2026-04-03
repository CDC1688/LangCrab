"""SQLite annotation database with WAL mode."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from .models import AnnotationCreate, AnnotationProgress, AnnotationRead

SCHEMA = """
CREATE TABLE IF NOT EXISTS annotations (
    sid                   TEXT PRIMARY KEY,
    status                TEXT CHECK(status IN ('pending','approved','rejected','flagged','corrected')),
    corrected_category    TEXT,
    corrected_subcategory TEXT,
    corrected_confidence  TEXT,
    corrected_language    TEXT,
    notes                 TEXT,
    reviewer              TEXT,
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS annotation_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sid       TEXT NOT NULL,
    action    TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reviewer  TEXT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


class AnnotationDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert(self, sid: str, annotation: AnnotationCreate) -> None:
        with self._conn() as conn:
            # Get old value for history
            old = conn.execute("SELECT * FROM annotations WHERE sid = ?", (sid,)).fetchone()
            if old:
                conn.execute(
                    "INSERT INTO annotation_history (sid, action, old_value, new_value, reviewer) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sid, "update", old["status"], annotation.status, annotation.reviewer),
                )

            conn.execute(
                """INSERT INTO annotations (sid, status, corrected_category, corrected_subcategory,
                   corrected_confidence, corrected_language, notes, reviewer)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(sid) DO UPDATE SET
                   status=excluded.status,
                   corrected_category=excluded.corrected_category,
                   corrected_subcategory=excluded.corrected_subcategory,
                   corrected_confidence=excluded.corrected_confidence,
                   corrected_language=excluded.corrected_language,
                   notes=excluded.notes,
                   reviewer=excluded.reviewer,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now')""",
                (
                    sid,
                    annotation.status,
                    annotation.corrected_category,
                    annotation.corrected_subcategory,
                    annotation.corrected_confidence,
                    annotation.corrected_language,
                    annotation.notes,
                    annotation.reviewer,
                ),
            )

    def get(self, sid: str) -> Optional[AnnotationRead]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM annotations WHERE sid = ?", (sid,)).fetchone()
            if row:
                return AnnotationRead(**dict(row))
            return None

    def get_all(self) -> list[AnnotationRead]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM annotations ORDER BY updated_at DESC").fetchall()
            return [AnnotationRead(**dict(r)) for r in rows]

    def get_status_map(self) -> dict[str, str]:
        """Return {sid: status} for all annotations."""
        with self._conn() as conn:
            rows = conn.execute("SELECT sid, status FROM annotations").fetchall()
            return {r["sid"]: r["status"] for r in rows}

    def delete(self, sid: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM annotations WHERE sid = ?", (sid,))
            return cur.rowcount > 0

    def progress(self, total_sessions: int) -> AnnotationProgress:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM annotations GROUP BY status"
            ).fetchall()
            counts = {r["status"]: r["cnt"] for r in rows}
            annotated = sum(counts.values())
            return AnnotationProgress(
                total_sessions=total_sessions,
                annotated=annotated,
                approved=counts.get("approved", 0),
                rejected=counts.get("rejected", 0),
                flagged=counts.get("flagged", 0),
                corrected=counts.get("corrected", 0),
                pending=total_sessions - annotated,
            )

    def export_jsonl(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM annotations ORDER BY sid").fetchall()
            return [dict(r) for r in rows]
