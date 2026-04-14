"""SQLite database schema and query helpers."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    external_id   TEXT,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    location      TEXT,
    url           TEXT UNIQUE NOT NULL,
    description   TEXT,
    score         REAL DEFAULT 0,
    status        TEXT DEFAULT 'new',   -- new | saved | rejected | skipped
    discovered_at TEXT,
    notes         TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_job(
    source: str,
    title: str,
    company: str,
    url: str,
    score: float,
    *,
    external_id: Optional[str] = None,
    location: Optional[str] = None,
    description: Optional[str] = None,
) -> int:
    """Insert or update a job. Returns the row id."""
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE url = ?", (url,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE jobs SET title=?, company=?, location=?, description=?,
                   score=?, source=?, external_id=?
                   WHERE url=?""",
                (title, company, location, description, score, source, external_id, url),
            )
            return existing["id"]
        cur = conn.execute(
            """INSERT INTO jobs
               (source, external_id, title, company, location, url, description,
                score, status, discovered_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (source, external_id, title, company, location, url, description,
             score, "new", now),
        )
        return cur.lastrowid


def get_pending(min_score: float = 60) -> list[sqlite3.Row]:
    """Return jobs with status='new' above min_score, ordered by score desc."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM jobs
               WHERE status='new' AND score >= ?
               ORDER BY score DESC""",
            (min_score,),
        ).fetchall()


def get_saved() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE status='saved' ORDER BY score DESC"
        ).fetchall()


def update_status(job_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))


def get_stats() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}
