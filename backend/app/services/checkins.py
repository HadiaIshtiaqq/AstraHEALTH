"""Check-in submission: validate every observation, then persist raw + normalized values."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.security import encrypt_text
from app.db.database import Database, dumps, iso, new_id, utcnow
from app.domain.metrics import METRICS
from app.schemas.models import CheckinIn
from app.services import repository as repo
from app.services.validation import QUALITY_MESSAGES, checkin_level_errors, validate_observation


class DuplicateSubmission(Exception):
    """The same check-in was submitted again within the replay window (e.g. a double click)."""

    def __init__(self, checkin_id: str):
        super().__init__(checkin_id)
        self.checkin_id = checkin_id


REPLAY_WINDOW_S = 120


def fingerprint(payload: CheckinIn) -> str:
    import hashlib
    items = sorted(f"{o.metric_code}|{o.value}|{o.unit}|{o.measured_at}|{o.context}" for o in payload.observations)
    return hashlib.sha256(("\n".join(items) + f"|{payload.mode}").encode()).hexdigest()[:32]


class CheckinRejected(ValueError):
    def __init__(self, errors: list[dict]):
        super().__init__("Check-in rejected")
        self.errors = errors


def preview(db: Database, payload: CheckinIn, reference_time: datetime | None = None) -> dict:
    reference_time = reference_time or utcnow()
    keys = repo.existing_observation_keys(db, payload.profile_id)
    items = []
    historical = payload.mode == "import"  # imported history feeds baselines; it is not "stale"
    for i, obs in enumerate(payload.observations):
        v = validate_observation(obs, reference_time, keys, historical=historical)
        items.append({
            "index": i,
            "metric_code": obs.metric_code,
            "label": METRICS[obs.metric_code].label if obs.metric_code in METRICS else obs.metric_code,
            "quality_status": v["quality_status"],
            "errors": v["errors"],
            "flags": v["flags"],
            "messages": [QUALITY_MESSAGES[f] for f in v["flags"] if f in QUALITY_MESSAGES and f != "self_report"],
            "normalized_value": v["normalized_value"],
            "normalized_unit": v["normalized_unit"],
            "_validated": v,
        })
    checkin_errors = checkin_level_errors(payload.observations)
    ok = not checkin_errors and all(not it["errors"] for it in items)
    return {"ok": ok, "checkin_errors": checkin_errors, "observations": items}


def public_preview(result: dict) -> dict:
    return {**result, "observations": [{k: v for k, v in it.items() if k != "_validated"} for it in result["observations"]]}


def create_checkin(db: Database, payload: CheckinIn, is_synthetic: bool = True, submitted_at: datetime | None = None,
                   audit: bool = True) -> str:
    profile = repo.get_profile(db, payload.profile_id)
    if profile is None:
        raise LookupError("Profile not found")
    submitted = submitted_at or utcnow()
    result = preview(db, payload, reference_time=submitted)
    if not result["ok"]:
        errors = [{"index": None, "message": m} for m in result["checkin_errors"]]
        errors += [{"index": it["index"], "metric_code": it["metric_code"], "message": e}
                   for it in result["observations"] for e in it["errors"]]
        raise CheckinRejected(errors)

    fp = fingerprint(payload)
    if payload.mode != "simulated":
        recent = db.one("SELECT checkin_id FROM checkins WHERE profile_id = ? AND fingerprint = ? AND submitted_at >= ?",
                        (payload.profile_id, fp, iso(utcnow() - timedelta(seconds=REPLAY_WINDOW_S))))
        if recent:
            raise DuplicateSubmission(recent["checkin_id"])
    checkin_id = new_id("chk")
    recorded_at = iso(utcnow())
    synthetic = bool(profile["is_synthetic"]) or payload.mode == "simulated"
    rows = []
    for it in result["observations"]:
        v = it["_validated"]
        rows.append((
            new_id("obs"), payload.profile_id, checkin_id, v["metric_code"], v["value"], v["value_text"], v["unit"],
            v["normalized_value"], v["normalized_unit"], v["measured_at"], recorded_at, v["source"], v["method"],
            v["context"], v["quality_status"], dumps(v["flags"]), dumps(v["raw"]), 1 if synthetic else 0,
        ))
    with db.transaction() as conn:
        conn.execute("INSERT INTO checkins (checkin_id, profile_id, submitted_at, mode, notes, raw_input_text, is_synthetic, "
                     "fingerprint) VALUES (?,?,?,?,?,?,?,?)",
                     (checkin_id, payload.profile_id, iso(submitted), payload.mode, encrypt_text(payload.notes),
                      encrypt_text(payload.raw_input_text), 1 if synthetic else 0, fp))
        conn.executemany(
            "INSERT INTO observations (observation_id, profile_id, checkin_id, metric_code, value, value_text, unit, "
            "normalized_value, normalized_unit, measured_at, recorded_at, source, method, context, quality_status, "
            "quality_flags, raw_json, is_synthetic) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    # Free text is never written to the audit log.
    if audit:
        repo.audit(db, "checkin.created", checkin_id, actor_role="crew", observations=len(rows), mode=payload.mode)
    if payload.mode in ("manual", "conversation"):
        from app.services.tasks import complete_checkin_task
        complete_checkin_task(db, profile, submitted)
    return checkin_id
