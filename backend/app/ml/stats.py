"""Robust, transparent statistics used by BaselineIQ and the specialist agents."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np

from app.db.database import parse_iso
from app.domain.metrics import METRICS

MAD_SCALE = 1.4826  # makes MAD consistent with the SD for normally distributed data

# Minimum spread per metric so a perfectly flat history does not create infinite z-scores.
# These are numerical-stability floors in the metric's normalized unit, not clinical limits.
MIN_SPREAD = {
    "heart_rate": 2.0, "bp_systolic": 3.0, "bp_diastolic": 2.0, "body_temperature": 0.1,
    "sleep_duration": 0.25, "fluid_intake": 100.0, "exercise_duration": 5.0, "body_mass": 0.3,
    "blood_glucose": 3.0, "radiation_dose": 0.01,
}
SCALE_MIN_SPREAD = 0.75  # one scale point = 1.33 robust SD


def min_spread(metric_code: str) -> float:
    metric = METRICS.get(metric_code)
    if metric and metric.value_type in ("scale", "boolean"):
        return SCALE_MIN_SPREAD
    return MIN_SPREAD.get(metric_code, 1e-6)


def robust_summary(values: list[float], metric_code: str) -> dict:
    arr = np.asarray(values, dtype=float)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    spread = max(MAD_SCALE * mad, min_spread(metric_code))
    return {
        "n": int(arr.size),
        "mean": round(float(arr.mean()), 3),
        "median": round(median, 3),
        "std": round(float(arr.std(ddof=1)) if arr.size > 1 else 0.0, 3),
        "mad": round(mad, 3),
        "robust_spread": round(spread, 3),
        "min": round(float(arr.min()), 3),
        "max": round(float(arr.max()), 3),
        "p10": round(float(np.percentile(arr, 10)), 3),
        "p90": round(float(np.percentile(arr, 90)), 3),
    }


def robust_z(value: float, median: float, spread: float) -> float:
    return (value - median) / spread if spread > 0 else 0.0


def ewma(values: list[float], alpha: float = 0.3) -> float | None:
    if not values:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return round(float(acc), 3)


def slope_per_day(points: list[tuple[date, float]]) -> float | None:
    """Ordinary least-squares slope in units/day; None when fewer than 3 points."""
    if len(points) < 3:
        return None
    origin = points[0][0]
    x = np.array([(d - origin).days for d, _ in points], dtype=float)
    y = np.array([v for _, v in points], dtype=float)
    if np.ptp(x) == 0:
        return None
    return round(float(np.polyfit(x, y, 1)[0]), 4)


def local_date(iso_ts: str, tz: str = "UTC") -> date:
    return parse_iso(iso_ts).astimezone(zone(tz)).date()


def zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def daily_series(observations: list[dict], metric_code: str, tz: str = "UTC") -> dict[date, float]:
    """Aggregate valid observations of one metric into one value per *local* day of the crew profile."""
    metric = METRICS[metric_code]
    buckets: dict[date, list[tuple[str, float]]] = defaultdict(list)
    for obs in observations:
        if obs["metric_code"] != metric_code or obs["normalized_value"] is None:
            continue
        if obs.get("quality_status", "valid") != "valid":
            continue
        buckets[local_date(obs["measured_at"], tz)].append((obs["measured_at"], float(obs["normalized_value"])))
    out: dict[date, float] = {}
    for day, items in buckets.items():
        vals = [v for _, v in sorted(items)]
        if metric.aggregate == "sum":
            out[day] = float(sum(vals))
        elif metric.aggregate == "last":
            out[day] = vals[-1]
        elif metric.aggregate == "max":
            out[day] = max(vals)
        else:
            out[day] = float(np.mean(vals))
    return dict(sorted(out.items()))


def cusum_change_point(values: list[float], spread: float, k: float = 0.5, h: float = 4.0) -> dict | None:
    """Two-sided tabular CUSUM on standardized values against the first-half median.

    Returns the index where a persistent shift was first signalled, or None.
    `k` (slack) and `h` (decision interval) are in robust-SD units and are
    demonstration parameters, documented in the ML evaluation notes.
    """
    if len(values) < 8 or spread <= 0:
        return None
    ref = float(np.median(values[: len(values) // 2]))
    pos = neg = 0.0
    for i, v in enumerate(values):
        z = (v - ref) / spread
        pos = max(0.0, pos + z - k)
        neg = max(0.0, neg - z - k)
        if pos > h or neg > h:
            return {"index": i, "direction": "increase" if pos > h else "decrease", "reference_median": round(ref, 3)}
    return None


def safe_round(value: float | None, digits: int = 2) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(value, digits)
