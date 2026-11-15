"""SQLite persistence (stdlib sqlite3).

SQLAlchemy is listed in the original stack, but its compiled extensions are blocked
by the Application Control policy on the target laptop, so the prototype uses the
standard-library driver with a small repository layer. The schema maps 1:1 to the
data model in the architecture document and can move to PostgreSQL later.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.core.config import settings

NO_MISSION_ID = "NONE"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mission_contexts (
    mission_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    environment TEXT NOT NULL,
    mission_start TEXT NOT NULL,
    gravity_context TEXT NOT NULL,
    communication_mode TEXT NOT NULL,
    planned_duration_days INTEGER,
    is_synthetic INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS crew_profiles (
    profile_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    role TEXT,
    mission_id TEXT NOT NULL REFERENCES mission_contexts(mission_id),
    baseline_json TEXT NOT NULL DEFAULT '{}',
    settings_json TEXT NOT NULL DEFAULT '{}',
    timezone TEXT NOT NULL DEFAULT 'UTC',
    scenario TEXT,
    is_synthetic INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
    checkin_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES crew_profiles(profile_id) ON DELETE CASCADE,
    submitted_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    notes TEXT,
    raw_input_text TEXT,
    is_synthetic INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES crew_profiles(profile_id) ON DELETE CASCADE,
    checkin_id TEXT REFERENCES checkins(checkin_id) ON DELETE CASCADE,
    metric_code TEXT NOT NULL,
    value REAL,
    value_text TEXT,
    unit TEXT NOT NULL,
    normalized_value REAL,
    normalized_unit TEXT,
    measured_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL,
    method TEXT,
    context TEXT,
    quality_status TEXT NOT NULL,
    quality_flags TEXT NOT NULL DEFAULT '[]',
    raw_json TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_obs_profile_metric ON observations(profile_id, metric_code, measured_at);
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES crew_profiles(profile_id) ON DELETE CASCADE,
    checkin_id TEXT,
    status TEXT NOT NULL,
    overall_status TEXT,
    coverage TEXT,
    model_version TEXT,
    ruleset_version TEXT,
    agent_versions TEXT,
    trace_json TEXT NOT NULL DEFAULT '[]',
    assessment_json TEXT NOT NULL DEFAULT '{}',
    explanation_status TEXT NOT NULL DEFAULT 'pending',
    explanation_json TEXT,
    correlation_id TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL REFERENCES crew_profiles(profile_id) ON DELETE CASCADE,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    reason TEXT NOT NULL,
    next_step TEXT NOT NULL,
    rule_ids TEXT NOT NULL DEFAULT '[]',
    evidence_ids TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    acknowledged_by TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    version TEXT,
    publication_date TEXT,
    local_path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    related_reference TEXT,
    document_type TEXT
);
CREATE TABLE IF NOT EXISTS evidence_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    page_or_section TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding_id INTEGER
);
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    actor_role TEXT NOT NULL,
    action TEXT NOT NULL,
    object_id TEXT,
    timestamp TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES crew_profiles(profile_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    scheduled_for TEXT NOT NULL,
    completed_at TEXT,
    completion_note TEXT
);
CREATE INDEX IF NOT EXISTS ix_tasks_profile_day ON tasks(profile_id, scheduled_for);
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES crew_profiles(profile_id) ON DELETE CASCADE,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    created_at TEXT NOT NULL,
    report_json TEXT NOT NULL
);
"""

MIGRATIONS = [
    ("alerts", "occurrences", "INTEGER NOT NULL DEFAULT 1"),
    ("alerts", "last_seen_at", "TEXT"),
    ("alerts", "dedupe_key", "TEXT"),
    ("alerts", "acknowledged_note", "TEXT"),
    ("observations", "superseded_by", "TEXT"),
    ("observations", "status_note", "TEXT"),
    ("checkins", "fingerprint", "TEXT"),
    ("audit_events", "prev_hash", "TEXT"),
    ("audit_events", "hash", "TEXT"),
]

_write_lock = threading.RLock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


_bulk = threading.local()


@contextmanager
def bulk_load() -> Iterator[None]:
    """Synthetic seeding only: relax fsync for speed (data is regenerable)."""
    _bulk.active = True
    try:
        yield
    finally:
        _bulk.active = False


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = OFF" if getattr(_bulk, "active", False) else "PRAGMA synchronous = NORMAL")
    return conn


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = _connect(self.path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with _write_lock:
            conn = _connect(self.path)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def init(self) -> None:
        with self.transaction() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            # Additive migrations for databases created by earlier versions.
            for table, column, ddl in MIGRATIONS:
                existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            # Earth-Link was removed; drop its tables from databases created by earlier versions.
            conn.execute("DROP TABLE IF EXISTS earthlink_replies")
            conn.execute("DROP TABLE IF EXISTS earthlink_packets")
            # Real (user-created) profiles are not on the fictional demo mission.
            conn.execute("INSERT OR IGNORE INTO mission_contexts VALUES (?,?,?,?,?,?,?,?)",
                         (NO_MISSION_ID, "No mission assigned", "Not set", iso(utcnow()), "Not set", "Not set", None, 0))
            conn.execute("UPDATE crew_profiles SET mission_id = ? WHERE is_synthetic = 0 AND mission_id <> ?",
                         (NO_MISSION_ID, NO_MISSION_ID))

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(settings.database_path)
    return _db


def set_db(db: Database) -> None:
    """Used by tests to point the app at a temporary database."""
    global _db
    _db = db


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def loads(value: str | None, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    return json.loads(value)
