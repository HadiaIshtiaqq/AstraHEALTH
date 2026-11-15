"""Shared statistical signal logic for specialist agents.

The z-score parameters below define when an agent *reports a statistical signal*.
They are demonstration parameters relative to the crew member's own history, not
clinical thresholds; clinical severity is assigned only by the versioned rule set.
"""
from __future__ import annotations

from datetime import timedelta

from app.agents.base import AgentContext, baseline_ids, fmt
from app.domain.metrics import METRICS
from app.ml.stats import robust_z
from app.schemas.models import Finding, MetricAssessment

SIGNAL_PARAMS = {
    "single_reading_z": 3.0,   # one reading this far from the personal median is reported
    "sustained_z": 2.0,        # consecutive days this far, same direction, count as sustained
    "sustained_days": 3,
}


def recent_daily_z(ctx: AgentContext, code: str, days: int) -> list[tuple[str, float]]:
    b = ctx.baselines.get(code)
    if not b or not b.get("available"):
        return []
    series = ctx.daily(code, days=days + 1, include_current=True)
    cutoff = ctx.today - timedelta(days=days - 1)
    return [
        (d.isoformat(), round(robust_z(v, b["median"], b["robust_spread"]), 2))
        for d, v in series.items() if d >= cutoff
    ]


def deviation_signal(
    ctx: AgentContext,
    code: str,
    finding_code: str,
    adverse: str = "both",  # "up", "down" or "both": which direction is reported
) -> tuple[Finding | None, MetricAssessment, list[str]]:
    metric = METRICS[code]
    b = ctx.baselines.get(code)
    limitations: list[str] = []
    if not b or not b.get("available"):
        reason = b.get("reason") if b else "No baseline computed."
        limitations.append(f"{metric.label}: baseline comparison unavailable — {reason}")
        return None, MetricAssessment(metric_code=code, assessment="unknown", detail="no baseline"), limitations

    z = b.get("robust_z")
    if z is None:
        return None, MetricAssessment(metric_code=code, assessment="unknown", detail="no current value"), limitations

    n_days = SIGNAL_PARAMS["sustained_days"]
    recent = recent_daily_z(ctx, code, n_days)
    same_sign = [rz for _, rz in recent if abs(rz) >= SIGNAL_PARAMS["sustained_z"] and (rz > 0) == (z > 0)]
    sustained = len(recent) >= n_days and len(same_sign) >= n_days
    direction_ok = adverse == "both" or (adverse == "up" and z > 0) or (adverse == "down" and z < 0)
    flagged = direction_ok and (abs(z) >= SIGNAL_PARAMS["single_reading_z"] or sustained)

    if b["n_days"] < 14:
        limitations.append(f"{metric.label}: baseline built from only {b['n_days']} days (low confidence).")

    if not flagged:
        detail = f"within the usual personal range (z = {z:+.1f})"
        return None, MetricAssessment(metric_code=code, assessment="stable", detail=detail), limitations

    direction = "above" if z > 0 else "below"
    summary = (
        f"{metric.label} {fmt(b['current'], code)} is {direction} the personal baseline "
        f"(median {fmt(b['median'], code)}, robust z = {z:+.1f})"
        + (f"; {direction} baseline for {n_days} consecutive days." if sustained else "; single reading.")
    )
    finding = Finding(
        code=finding_code,
        summary=summary,
        statement_type="observation",
        metric_codes=[code],
        evidence_observation_ids=baseline_ids(ctx, code),
        data={
            "metric_code": code,
            "current": b["current"],
            "baseline_median": b["median"],
            "robust_spread": b["robust_spread"],
            "robust_z": z,
            "direction": "increase" if z > 0 else "decrease",
            "sustained": sustained,
            "recent_daily_z": recent,
            "baseline_days": b["n_days"],
            "baseline_confidence": b.get("confidence"),
        },
        limitations=(["Single measurement — a repeat measurement with recorded context is needed."] if not sustained else [])
        + ["Statistical deviation from personal history is not a diagnosis."],
    )
    return finding, MetricAssessment(metric_code=code, assessment="changed", detail=f"z = {z:+.1f}"), limitations
