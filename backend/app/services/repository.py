"""Data access helpers shared by services, agents and the API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.security import decrypt_text
from app.db.database import Database, dumps, iso, loads, new_id, parse_iso, utcnow


GENESIS = "0" * 64


def _event_hash(prev: str, event_id: str, actor: str, action: str, object_id: str | None, ts: str, meta: str) -> str:
    import hashlib
    return hashlib.sha256("|".join([prev, event_id, actor, action, object_id or "", ts, meta]).encode()).hexdigest()


def audit(db: Database, action: str, object_id: str | None = None, actor_role: str = "system", **metadata: Any) -> None:
    """Append an event to the hash-chained audit log. Never pass free-text health content here."""
    with db.transaction() as conn:
        last = conn.execute("SELECT hash FROM audit_events WHERE hash IS NOT NULL ORDER BY rowid DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else GENESIS
        event_id, ts, meta = new_id("evt"), iso(utcnow()), dumps(metadata)
        conn.execute(
            "INSERT INTO audit_events (event_id, actor_role, action, object_id, timestamp, metadata, prev_hash, hash) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (event_id, actor_role, action, object_id, ts, meta, prev,
             _event_hash(prev, event_id, actor_role, action, object_id, ts, meta)))


def verify_audit_chain(db: Database) -> dict:
    """Recompute the chain. Any edited, deleted or inserted row breaks it from that point on."""
    prev, checked = GENESIS, 0
    for r in db.query("SELECT rowid, * FROM audit_events WHERE hash IS NOT NULL ORDER BY rowid"):
        if r["prev_hash"] != prev or r["hash"] != _event_hash(prev, r["event_id"], r["actor_role"], r["action"],
                                                               r["object_id"], r["timestamp"], r["metadata"]):
            return {"intact": False, "checked": checked, "broken_at": r["event_id"]}
        prev, checked = r["hash"], checked + 1
    return {"intact": True, "checked": checked}


def get_profile(db: Database, profile_id: str) -> dict | None:
    row = db.one(
        """SELECT p.*, m.name AS mission_name, m.environment, m.mission_start, m.gravity_context,
                  m.communication_mode, m.planned_duration_days
           FROM crew_profiles p JOIN mission_contexts m ON m.mission_id = p.mission_id
           WHERE p.profile_id = ?""",
        (profile_id,),
    )
    if row is None:
        return None
    row["baseline"] = loads(row.pop("baseline_json"), {})
    row["settings"] = loads(row.pop("settings_json"), {})
    row["is_synthetic"] = bool(row["is_synthetic"])
    row["has_mission"] = row["mission_id"] != "NONE"
    start = parse_iso(row["mission_start"])
    row["mission_day"] = max(1, (utcnow().date() - start.date()).days + 1) if row["has_mission"] else None
    return row


def list_profiles(db: Database) -> list[dict]:
    ids = [r["profile_id"] for r in db.query("SELECT profile_id FROM crew_profiles ORDER BY profile_id")]
    return [p for p in (get_profile(db, i) for i in ids) if p]


def observation_row(row: dict) -> dict:
    row = dict(row)
    row["quality_flags"] = loads(row.get("quality_flags"), [])
    row["raw"] = loads(row.pop("raw_json", None), {})
    row["is_synthetic"] = bool(row.get("is_synthetic"))
    return row


def get_observations(
    db: Database,
    profile_id: str,
    metric_codes: list[str] | tuple[str, ...] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    checkin_id: str | None = None,
    analysable_only: bool = False,
) -> list[dict]:
    sql = "SELECT * FROM observations WHERE profile_id = ?"
    params: list[Any] = [profile_id]
    if metric_codes:
        sql += f" AND metric_code IN ({','.join('?' * len(metric_codes))})"
        params += list(metric_codes)
    if start:
        sql += " AND measured_at >= ?"
        params.append(iso(start))
    if end:
        sql += " AND measured_at <= ?"
        params.append(iso(end))
    if checkin_id:
        sql += " AND checkin_id = ?"
        params.append(checkin_id)
    if analysable_only:
        sql += " AND quality_status = 'valid'"
    sql += " ORDER BY measured_at ASC"
    return [observation_row(r) for r in db.query(sql, params)]


def get_checkin(db: Database, checkin_id: str) -> dict | None:
    row = db.one("SELECT * FROM checkins WHERE checkin_id = ?", (checkin_id,))
    if row is None:
        return None
    row["is_synthetic"] = bool(row["is_synthetic"])
    row["notes"] = decrypt_text(row.get("notes"))
    row["raw_input_text"] = decrypt_text(row.get("raw_input_text"))
    row.pop("fingerprint", None)
    row["observations"] = get_observations(db, row["profile_id"], checkin_id=checkin_id)
    return row


def latest_checkin_id(db: Database, profile_id: str) -> str | None:
    row = db.one(
        "SELECT checkin_id FROM checkins WHERE profile_id = ? ORDER BY submitted_at DESC, rowid DESC LIMIT 1",
        (profile_id,),
    )
    return row["checkin_id"] if row else None


def existing_observation_keys(db: Database, profile_id: str) -> set[tuple[str, str, str]]:
    rows = db.query(
        "SELECT metric_code, measured_at, normalized_value, value_text FROM observations WHERE profile_id = ?",
        (profile_id,),
    )
    return {
        (r["metric_code"], r["measured_at"], str(r["normalized_value"] if r["normalized_value"] is not None else r["value_text"]))
        for r in rows
    }


def get_run(db: Database, run_id: str) -> dict | None:
    row = db.one("SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,))
    if row is None:
        return None
    row["trace"] = loads(row.pop("trace_json"), [])
    row["assessment"] = loads(row.pop("assessment_json"), {})
    row["explanation"] = loads(row.pop("explanation_json"), None)
    row["agent_versions"] = loads(row.get("agent_versions"), {})
    results = db.query(
        "SELECT result_json FROM agent_results WHERE run_id = ? ORDER BY rowid", (run_id,)
    )
    row["agent_results"] = [loads(r["result_json"]) for r in results]
    row["alerts"] = get_alerts(db, row["profile_id"], run_id=run_id)
    return row


def latest_run(db: Database, profile_id: str) -> dict | None:
    row = db.one(
        "SELECT run_id FROM analysis_runs WHERE profile_id = ? AND status != 'running' ORDER BY started_at DESC, rowid DESC LIMIT 1",
        (profile_id,),
    )
    return get_run(db, row["run_id"]) if row else None


def get_alerts(db: Database, profile_id: str, run_id: str | None = None, state: str | None = None) -> list[dict]:
    sql = "SELECT * FROM alerts WHERE profile_id = ?"
    params: list[Any] = [profile_id]
    if run_id:
        sql += " AND run_id = ?"
        params.append(run_id)
    if state:
        sql += " AND state = ?"
        params.append(state)
    sql += " ORDER BY created_at DESC"
    rows = db.query(sql, params)
    for r in rows:
        r["rule_ids"] = loads(r["rule_ids"], [])
        r["evidence_ids"] = loads(r["evidence_ids"], [])
    return rows
