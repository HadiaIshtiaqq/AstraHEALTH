"""SleepSense — sleep duration and self-reported quality trends."""
from __future__ import annotations

from datetime import timedelta

from app.agents.base import AgentContext, BaseAgent, fmt
from app.agents.common import deviation_signal
from app.ml.stats import robust_z
from app.schemas.models import Finding

PATTERN_WINDOW = 5
PATTERN_MIN_SHORT = 3
SHORT_Z = -1.5  # a period this far below the personal median counts as "short" (demonstration parameter)


class SleepSenseAgent(BaseAgent):
    agent_id = "sleep_sense"
    name = "SleepSense"
    scope = "Sleep duration and self-reported sleep quality; record completeness"
    metrics = ("sleep_duration", "sleep_quality")
    method = "Personal-baseline deviation, short-sleep pattern count over the last 5 periods, 7-day completeness"
    must_not = "Diagnose sleep disorders"

    def analyze(self, ctx: AgentContext):
        present = ctx.checkin_metrics() & set(self.metrics)
        findings: list[Finding] = []
        assessments = []
        limitations = ["Sleep timing (bedtime/wake time) is not captured in the MVP, so schedule consistency is not assessed."]

        for code in sorted(present):
            finding, assessment, lims = deviation_signal(ctx, code, "SLEEP_BELOW_BASELINE", adverse="down")
            assessments.append(assessment)
            limitations += lims
            if finding:
                findings.append(finding)

        b = ctx.baselines.get("sleep_duration")
        if b and b.get("available"):
            series = ctx.daily("sleep_duration", days=PATTERN_WINDOW + 1, include_current=True)
            last = list(series.items())[-PATTERN_WINDOW:]
            short = [(d.isoformat(), v) for d, v in last if robust_z(v, b["median"], b["robust_spread"]) <= SHORT_Z]
            if len(short) >= PATTERN_MIN_SHORT:
                avg = sum(v for _, v in last) / len(last)
                findings = [f for f in findings if f.code != "SLEEP_BELOW_BASELINE"]
                findings.append(Finding(
                    code="SLEEP_SHORT_PATTERN",
                    summary=f"{len(short)} of the last {len(last)} sleep periods were shorter than usual "
                            f"(average {fmt(avg, 'sleep_duration')} vs usual {fmt(b['median'], 'sleep_duration')}).",
                    statement_type="observation",
                    metric_codes=["sleep_duration"],
                    evidence_observation_ids=[o["observation_id"] for o in ctx.current("sleep_duration")],
                    data={"short_periods": short, "window": len(last), "average_h": round(avg, 2),
                          "baseline_median_h": b["median"]},
                    limitations=["Duration only; sleep quality and timing need separate review."],
                ))

        # Completeness over 7 days
        week = ctx.daily("sleep_duration", days=7, include_current=True)
        expected_days = {ctx.today - timedelta(days=i) for i in range(7)}
        missing = sorted(d.isoformat() for d in expected_days - set(week))
        if len(missing) >= 2:
            findings.append(Finding(
                code="SLEEP_RECORDS_INCOMPLETE",
                summary=f"No sleep record for {len(missing)} of the last 7 days; trends may be unreliable.",
                statement_type="limitation",
                metric_codes=["sleep_duration"],
                data={"missing_days": missing},
            ))

        if "fatigue" in ctx.checkin_metrics() and "sleep_duration" not in present:
            limitations.append("Fatigue reported without a sleep record for the same period.")

        ids = [o["observation_id"] for o in ctx.valid_checkin_observations if o["metric_code"] in self.metrics]
        if not ids:
            return self.result(ctx, "insufficient_data", findings, [], limitations=limitations,
                               activation_reason="Routed by fatigue report; no sleep record submitted")
        status = "completed" if any(a.assessment != "unknown" for a in assessments) else "insufficient_data"
        return self.result(ctx, status, findings, ids, assessments, limitations,
                           activation_reason="Submitted: " + ", ".join(sorted(present)))
