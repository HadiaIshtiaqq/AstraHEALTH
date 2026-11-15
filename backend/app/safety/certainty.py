"""How sure is each finding? An explicit, rule-based certainty grade with its reasons.

Agents can be wrong — especially with little history, a single reading or missing context.
Instead of hiding that, every finding that needs attention gets a grade (strong / moderate /
limited / self-reported) and the plain-language reasons behind it, including whether another,
independent agent saw the same signal (corroboration).
"""
from __future__ import annotations

from app.schemas.models import SEVERITY_ORDER, Finding, Severity

SYMPTOM_CODES = {"URGENT_SYMPTOM_REPORTED", "URGENT_SYMPTOM_COMBINATION", "SYMPTOM_REQUIRES_REVIEW",
                 "CARDIO_SYMPTOM_REPORTED", "NEURO_SYMPTOM_REPORTED", "MSK_DISCOMFORT_REPORTED"}
STRUCTURAL = {"AGENT_FAILED", "AGENT_CONFLICT", "DATA_QUALITY_FLAG", "CROSS_DOMAIN_PATTERN"}


def grade(findings: list[Finding], quality_flags_by_metric: dict[str, list[str]]) -> None:
    anomaly_metrics = {c["metric_code"] for f in findings if f.code == "MULTIVARIATE_ANOMALY"
                       for c in f.data.get("contributors", [])}
    change_metrics = {c["metric_code"] for f in findings if f.code == "PERSISTENT_CHANGE_DETECTED"
                      for c in f.data.get("change_points", [])}
    for f in findings:
        if SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[Severity.MONITOR] or f.code in STRUCTURAL:
            continue
        if f.code in SYMPTOM_CODES:
            f.certainty = "self-reported"
            f.certainty_reasons = ["Based on your own report; it has not been measured or clinically assessed.",
                                   "Symptom rules act on the report itself, so certainty does not lower the escalation."]
            continue
        score, reasons = 0, []
        days = f.data.get("baseline_days")
        if days is not None:
            if days >= 21:
                score += 2; reasons.append(f"Personal baseline built from {days} days of history.")
            elif days >= 14:
                score += 1; reasons.append(f"Baseline from {days} days — moderate history.")
            else:
                reasons.append(f"Baseline from only {days} days — limited history.")
        if f.data.get("sustained") or f.code in ("SLEEP_SHORT_PATTERN", "WELLBEING_TREND_ADVERSE", "WELLBEING_MULTI_SIGNAL_DECLINE",
                                                  "EXERCISE_ADHERENCE_BELOW_PLAN", "PERSISTENT_CHANGE_DETECTED"):
            score += 2; reasons.append("Seen across several days, not a single reading.")
        elif "sustained" in f.data:
            reasons.append("Single reading — could be a one-off.")
        corroborated = [m for m in f.metric_codes if (m in anomaly_metrics or m in change_metrics) and f.agent_id != "anomaly_detect"]
        if corroborated:
            score += 1; reasons.append("Independently corroborated by AnomalyDetect.")
        if "heart_rate" in f.metric_codes:
            ctx = f.data.get("measurement_context")
            if ctx == "resting":
                score += 1; reasons.append("Measured at rest, matching how the baseline was built.")
            elif ctx is None and "measurement_context" in f.data:
                score -= 1; reasons.append("Measurement context was not recorded.")
        flagged = [m for m in f.metric_codes if quality_flags_by_metric.get(m)]
        if flagged:
            score -= 1; reasons.append("Some related measurements were flagged for data quality.")
        if f.agent_id == "anomaly_detect":
            reasons.append("Statistical model trained on synthetic personal history; it can raise false alarms.")
        f.certainty = "strong" if score >= 4 else "moderate" if score >= 2 else "limited"
        f.certainty_reasons = reasons or ["Little supporting information is available."]
