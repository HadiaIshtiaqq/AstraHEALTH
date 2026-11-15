"""Historical record import (CSV/JSON) and simulated device adapter.

Every row goes through the same validator as manual input. Rows with hard errors are
reported and skipped (never silently fixed); the remaining rows are saved as one check-in.
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter

from app.db.database import Database, utcnow
from app.schemas.models import CheckinIn, ObservationIn
from app.services.checkins import create_checkin
from app.services.validation import validate_observation

REQUIRED = ("metric_code", "value", "unit", "measured_at")
MAX_ROWS = 5000


def parse_rows(content: str, fmt: str) -> list[dict]:
    if fmt == "json":
        data = json.loads(content)
        rows = data.get("records", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("JSON must be a list of records or {\"records\": [...]}")
        return rows
    reader = csv.DictReader(io.StringIO(content.lstrip("﻿")))
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"CSV is missing required column(s): {', '.join(missing)}")
    return [dict(r) for r in reader]


def import_records(db: Database, profile_id: str, rows: list[dict], source: str, method: str, dry_run: bool) -> dict:
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Too many rows ({len(rows)}); the limit is {MAX_ROWS}.")
    accepted: list[ObservationIn] = []
    rejected: list[dict] = []
    now = utcnow()
    for i, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            rejected.append({"row": i, "errors": ["Row is not an object"]})
            continue
        value = raw.get("value")
        if isinstance(value, str) and raw.get("metric_code") != "symptom":
            value = value.strip()
        obs = ObservationIn(metric_code=str(raw.get("metric_code", "")).strip(), value=value,
                            unit=(str(raw["unit"]).strip() if raw.get("unit") not in (None, "") else None),
                            measured_at=(str(raw["measured_at"]).strip() if raw.get("measured_at") else None),
                            source=source, method=method, context=(raw.get("context") or None))
        v = validate_observation(obs, now, historical=True)
        if v["errors"]:
            rejected.append({"row": i, "metric_code": obs.metric_code, "errors": v["errors"]})
        else:
            accepted.append(obs)
    # Blood pressure rows must be paired at the same timestamp.
    pairs = Counter((o.measured_at, o.metric_code) for o in accepted if o.metric_code.startswith("bp_"))
    unpaired = {t for (t, m) in pairs if (t, "bp_diastolic" if m == "bp_systolic" else "bp_systolic") not in pairs}
    if unpaired:
        rejected += [{"row": None, "metric_code": o.metric_code, "errors": [f"Blood pressure at {o.measured_at} has no matching pair"]}
                     for o in accepted if o.metric_code.startswith("bp_") and o.measured_at in unpaired]
        accepted = [o for o in accepted if not (o.metric_code.startswith("bp_") and o.measured_at in unpaired)]
    result = {"rows": len(rows), "accepted": len(accepted), "rejected": rejected, "checkin_id": None,
              "metrics": dict(Counter(o.metric_code for o in accepted))}
    if dry_run or not accepted:
        return result
    payload = CheckinIn(profile_id=profile_id, observations=accepted, mode="import", run_analysis=True)
    from app.services.checkins import DuplicateSubmission
    try:
        result["checkin_id"] = create_checkin(db, payload, is_synthetic=True)
    except DuplicateSubmission as dup:
        result.update(checkin_id=dup.checkin_id, duplicate=True)
    return result
