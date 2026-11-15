"""Observation corrections. Raw submissions stay immutable: a correction creates a new
observation and marks the old one 'superseded'; a retraction marks it 'retracted'.
Both stay visible in history and reports, and are excluded from analysis."""
from __future__ import annotations

from app.core.security import require_medical_officer_pin
from datetime import timedelta

from app.db.database import Database, dumps, iso, loads, new_id, parse_iso, utcnow
from app.schemas.models import ObservationIn
from app.services import repository as repo
from app.services.validation import validate_observation

CONFIRMABLE = {"implausible", "pending_confirmation"}


def _get(db: Database, observation_id: str) -> dict:
    row = db.one("SELECT * FROM observations WHERE observation_id = ?", (observation_id,))
    if row is None:
        raise LookupError("Observation not found")
    return row


def confirm(db: Database, observation_id: str, note: str | None, pin: str | None, actor_role: str) -> dict:
    """Confirm a flagged value so it enters analysis. Implausible values need the medical officer."""
    row = _get(db, observation_id)
    if row["quality_status"] not in CONFIRMABLE:
        raise ValueError(f"Only implausible or unconfirmed values can be confirmed (status is {row['quality_status']}).")
    if row["quality_status"] == "implausible":
        require_medical_officer_pin(pin)
        actor_role = "medical_officer"
    flags = loads(row["quality_flags"], []) + ["confirmed"]
    with db.transaction() as conn:
        conn.execute("UPDATE observations SET quality_status = 'valid', quality_flags = ?, status_note = ? WHERE observation_id = ?",
                     (dumps(flags), f"Confirmed by {actor_role} at {iso(utcnow())}" + (f": {note}" if note else ""), observation_id))
    repo.audit(db, "observation.confirmed", observation_id, actor_role=actor_role, previous=row["quality_status"])
    return repo.observation_row(db.one("SELECT * FROM observations WHERE observation_id = ?", (observation_id,)))


CREW_EDIT_WINDOW = timedelta(hours=24)


def _needs_officer(row: dict) -> str | None:
    """Why this change needs the medical officer, or None if the crew member may make it."""
    if row["metric_code"] == "symptom":
        return "Symptom reports can only be withdrawn by the medical officer."
    if utcnow() - parse_iso(row["recorded_at"]) > CREW_EDIT_WINDOW:
        return "Values older than 24 hours can only be changed by the medical officer."
    return None


def correct(db: Database, observation_id: str, value, unit: str, reason: str, actor_role: str = "crew",
            pin: str | None = None) -> dict:
    row = _get(db, observation_id)
    if row["quality_status"] in ("superseded", "retracted"):
        raise ValueError("This observation has already been corrected or retracted.")
    if _needs_officer(row):
        require_medical_officer_pin(pin)
        actor_role = "medical_officer"
    candidate = ObservationIn(metric_code=row["metric_code"], value=value, unit=unit, measured_at=row["measured_at"],
                              source=row["source"], method="correction", context=row["context"])
    v = validate_observation(candidate, max(utcnow(), parse_iso(row["measured_at"])))
    if v["errors"]:
        raise ValueError("; ".join(v["errors"]))
    new = new_id("obs")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO observations (observation_id, profile_id, checkin_id, metric_code, value, value_text, unit, "
            "normalized_value, normalized_unit, measured_at, recorded_at, source, method, context, quality_status, "
            "quality_flags, raw_json, is_synthetic, status_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new, row["profile_id"], row["checkin_id"], row["metric_code"], v["value"], v["value_text"], v["unit"],
             v["normalized_value"], v["normalized_unit"], v["measured_at"], iso(utcnow()), row["source"], "correction",
             row["context"], v["quality_status"], dumps(v["flags"] + ["correction"]), dumps(v["raw"]), row["is_synthetic"],
             f"Corrects {observation_id}: {reason}"))
        conn.execute("UPDATE observations SET quality_status = 'superseded', superseded_by = ?, status_note = ? WHERE observation_id = ?",
                     (new, f"Superseded by {new} at {iso(utcnow())}: {reason}", observation_id))
    repo.audit(db, "observation.corrected", observation_id, actor_role=actor_role, replacement=new)
    return repo.observation_row(db.one("SELECT * FROM observations WHERE observation_id = ?", (new,)))


def retract(db: Database, observation_id: str, reason: str, actor_role: str = "crew", pin: str | None = None) -> dict:
    row = _get(db, observation_id)
    if row["quality_status"] in ("superseded", "retracted"):
        raise ValueError("This observation has already been corrected or retracted.")
    if _needs_officer(row):
        require_medical_officer_pin(pin)
        actor_role = "medical_officer"
    # Retraction is always audited; an alert already raised stays open until it is acknowledged.
    with db.transaction() as conn:
        conn.execute("UPDATE observations SET quality_status = 'retracted', status_note = ? WHERE observation_id = ?",
                     (f"Retracted at {iso(utcnow())}: {reason}", observation_id))
    repo.audit(db, "observation.retracted", observation_id, actor_role=actor_role, metric=row["metric_code"])
    return repo.observation_row(db.one("SELECT * FROM observations WHERE observation_id = ?", (observation_id,)))
