"""Deterministic input validation (used by the API and by the DataGuard agent).

Hard errors reject the submission (malformed value, unknown unit, missing required
field). Soft flags keep the observation but change its quality status so it is
visible yet excluded from analysis (implausible, stale, duplicate, unconfirmed).
Raw submitted values are preserved untouched; normalized values are stored separately.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from app.db.database import iso, parse_iso
from app.domain.metrics import METRICS, SYMPTOMS, VALID_SOURCES, normalize
from app.schemas.models import ObservationIn

STALE_AFTER = timedelta(hours=36)
FUTURE_TOLERANCE = timedelta(minutes=10)
ANALYSABLE = {"valid"}


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def validate_observation(
    obs: ObservationIn,
    reference_time: datetime,
    existing_keys: set[tuple[str, str, str]] | None = None,
    historical: bool = False,
) -> dict[str, Any]:
    """Return {errors, flags, quality_status, normalized fields...} for one observation."""
    errors: list[str] = []
    flags: list[str] = []
    metric = METRICS.get(obs.metric_code)
    result: dict[str, Any] = {
        "metric_code": obs.metric_code,
        "raw": obs.model_dump(),
        "value": None,
        "value_text": None,
        "unit": obs.unit,
        "normalized_value": None,
        "normalized_unit": None,
        "measured_at": None,
        "source": obs.source,
        "method": obs.method,
        "context": obs.context,
    }
    if metric is None:
        errors.append(f"Unknown metric '{obs.metric_code}'.")
        return {**result, "errors": errors, "flags": flags, "quality_status": "invalid"}

    label = metric.label

    # Source
    if obs.source not in VALID_SOURCES:
        errors.append(f"{label}: source must be one of {sorted(VALID_SOURCES)}.")

    # Timestamp
    if not obs.measured_at:
        errors.append(f"{label}: measurement timestamp is required.")
    else:
        try:
            measured = parse_iso(obs.measured_at)
            result["measured_at"] = iso(measured)
            if measured - reference_time > FUTURE_TOLERANCE:
                errors.append(f"{label}: timestamp is in the future.")
            elif reference_time - measured > STALE_AFTER and not historical:
                flags.append("stale")
        except ValueError:
            errors.append(f"{label}: timestamp '{obs.measured_at}' is not a valid ISO-8601 time.")

    # Value + unit
    if metric.value_type == "categorical":
        if obs.value is None or not isinstance(obs.value, str):
            errors.append(f"{label}: a symptom code is required.")
        elif obs.metric_code == "symptom" and obs.value not in SYMPTOMS:
            errors.append(f"{label}: unknown symptom code '{obs.value}'.")
        else:
            result["value_text"] = obs.value
            result["unit"] = obs.unit or "code"
            result["normalized_unit"] = "code"
        flags.append("self_report")
    else:
        if obs.unit is None or str(obs.unit).strip() == "":
            errors.append(f"{label}: unit is required (accepted: {', '.join(metric.units)}).")
        elif obs.unit not in metric.units:
            errors.append(
                f"{label}: unknown unit '{obs.unit}' (accepted: {', '.join(metric.units)}). "
                "Values are never converted from an unknown unit."
            )
        number = _as_number(obs.value)
        if obs.value is None or (isinstance(obs.value, str) and obs.value.strip() == ""):
            errors.append(f"{label}: value is required.")
        elif number is None:
            errors.append(f"{label}: '{obs.value}' is not a number.")
        if number is not None and obs.unit in metric.units:
            result["value"] = number
            norm, norm_unit = normalize(obs.metric_code, number, obs.unit)
            result["normalized_value"] = norm
            result["normalized_unit"] = norm_unit
            if metric.value_type in ("scale", "boolean"):
                lo, hi = metric.plausible_range or (0, 1)
                if norm != int(norm) or not lo <= norm <= hi:
                    errors.append(f"{label}: must be a whole number from {int(lo)} to {int(hi)}.")
                if metric.value_type == "scale":
                    flags.append("self_report")
            elif metric.plausible_range:
                lo, hi = metric.plausible_range
                if not lo <= norm <= hi:
                    flags.append("implausible")

    if obs.metric_code == "heart_rate" and not obs.context:
        flags.append("context_missing")

    if not obs.confirmed:
        flags.append("unconfirmed")

    # Symptoms are never treated as duplicates: a repeated report of an urgent symptom must always be evaluated.
    if existing_keys is not None and result["measured_at"] is not None and not errors and metric.value_type != "categorical":
        key = (obs.metric_code, result["measured_at"], str(result["normalized_value"] or result["value_text"]))
        if key in existing_keys:
            flags.append("duplicate")
        existing_keys.add(key)

    if errors:
        status = "invalid"
    elif "duplicate" in flags:
        status = "duplicate"
    elif "implausible" in flags:
        status = "implausible"
    elif "stale" in flags:
        status = "stale"
    elif "unconfirmed" in flags:
        status = "pending_confirmation"
    else:
        status = "valid"
    return {**result, "errors": errors, "flags": flags, "quality_status": status}


def checkin_level_errors(observations: list[ObservationIn]) -> list[str]:
    codes = [o.metric_code for o in observations]
    errors = []
    if ("bp_systolic" in codes) != ("bp_diastolic" in codes):
        errors.append("Blood pressure requires both systolic and diastolic values in the same check-in.")
    return errors


QUALITY_MESSAGES = {
    "implausible": "Value is outside the physically plausible range for this measurement. Please confirm or re-measure; it is kept but excluded from analysis.",
    "stale": "Measurement is older than 36 hours and is excluded from the current status.",
    "duplicate": "An identical measurement already exists; this copy is excluded from analysis.",
    "unconfirmed": "Extracted from free text and not yet confirmed by the crew member.",
    "context_missing": "Measurement context (e.g. resting or post-exercise) was not recorded.",
    "self_report": "Self-reported value.",
}
