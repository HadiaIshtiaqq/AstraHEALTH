"""BoneGuard — countermeasure exercise adherence and musculoskeletal self-reports."""
from __future__ import annotations

from datetime import timedelta

from app.agents.base import AgentContext, BaseAgent
from app.domain.metrics import SYMPTOMS
from app.schemas.models import Finding, MetricAssessment

ADHERENCE_WINDOW = 7
ADHERENCE_FLAG = 0.8  # fraction of the *mission plan* completed; a plan-adherence measure, not clinical


class BoneGuardAgent(BaseAgent):
    agent_id = "bone_guard"
    name = "BoneGuard"
    scope = "Exercise countermeasure adherence vs the mission plan; musculoskeletal discomfort reports"
    metrics = ("exercise_duration", "resistance_exercise", "msk_discomfort")
    method = "7-day adherence against the configured countermeasure plan; missing days counted separately"
    must_not = "Claim bone density loss or fracture risk without valid measurements"

    def analyze(self, ctx: AgentContext):
        settings = ctx.profile.get("settings", {})
        target_min = float(settings.get("exercise_target_min", 120))
        target_resistance = int(settings.get("resistance_sessions_per_week", 6))
        present = ctx.checkin_metrics() & set(self.metrics)
        findings: list[Finding] = []
        assessments: list[MetricAssessment] = []
        limitations = [
            "No bone-density or muscle-strength measurements are available; bone health cannot be assessed from exercise logs.",
            f"Plan targets ({target_min:g} min/day, {target_resistance} resistance sessions/week) come from the simulated mission plan.",
        ]

        days = {ctx.today - timedelta(days=i) for i in range(ADHERENCE_WINDOW)}
        exercise = {d: v for d, v in ctx.daily("exercise_duration", days=ADHERENCE_WINDOW, include_current=True).items() if d in days}
        resistance = {d: v for d, v in ctx.daily("resistance_exercise", days=ADHERENCE_WINDOW, include_current=True).items() if d in days}
        logged_days = len(exercise)
        missing_days = sorted(d.isoformat() for d in days - set(exercise))

        output: dict = {"target_min_per_day": target_min, "logged_days": logged_days, "missing_days": missing_days}
        if logged_days >= 3:
            adherence = sum(exercise.values()) / (logged_days * target_min)
            output["adherence_logged_days"] = round(adherence, 2)
            prior = ctx.daily("exercise_duration", days=ADHERENCE_WINDOW * 2, include_current=False)
            prior_vals = [v for d, v in prior.items() if d not in days]
            output["prior_week_mean_min"] = round(sum(prior_vals) / len(prior_vals), 1) if prior_vals else None
            output["this_week_mean_min"] = round(sum(exercise.values()) / logged_days, 1)
            if adherence < ADHERENCE_FLAG:
                findings.append(Finding(
                    code="EXERCISE_ADHERENCE_BELOW_PLAN",
                    summary=f"Exercise logged on {logged_days} of the last {ADHERENCE_WINDOW} days averaged "
                            f"{output['this_week_mean_min']:g} min/day, {adherence:.0%} of the planned {target_min:g} min/day.",
                    statement_type="observation",
                    metric_codes=["exercise_duration"],
                    evidence_observation_ids=[o["observation_id"] for o in ctx.current("exercise_duration")],
                    data={"adherence": round(adherence, 2), **output},
                    limitations=["Adherence describes routine completion only; it is not a measure of bone or muscle health."],
                ))
                assessments.append(MetricAssessment(metric_code="exercise_duration", assessment="changed", detail=f"adherence {adherence:.0%}"))
            else:
                assessments.append(MetricAssessment(metric_code="exercise_duration", assessment="stable", detail=f"adherence {adherence:.0%}"))
        else:
            assessments.append(MetricAssessment(metric_code="exercise_duration", assessment="unknown", detail="fewer than 3 logged days"))

        if len(missing_days) >= 2:
            findings.append(Finding(
                code="EXERCISE_RECORDS_INCOMPLETE",
                summary=f"No exercise record for {len(missing_days)} of the last {ADHERENCE_WINDOW} days. "
                        "Missing records are not treated as zero exercise.",
                statement_type="limitation",
                metric_codes=["exercise_duration"],
                data={"missing_days": missing_days},
            ))

        sessions = sum(1 for v in resistance.values() if v >= 1)
        expected = round(target_resistance * ADHERENCE_WINDOW / 7)
        output["resistance_sessions"] = sessions
        if resistance and len(resistance) >= 4 and sessions < expected - 1:
            findings.append(Finding(
                code="RESISTANCE_SESSIONS_MISSED",
                summary=f"{sessions} resistance session(s) logged in the last {ADHERENCE_WINDOW} days; the plan schedules {expected}.",
                statement_type="observation",
                metric_codes=["resistance_exercise"],
                evidence_observation_ids=[o["observation_id"] for o in ctx.current("resistance_exercise")],
                data={"sessions": sessions, "planned": expected},
            ))

        discomfort = ctx.current_value("msk_discomfort")
        back = "back_pain" in ctx.symptoms()
        if (discomfort is not None and discomfort >= 3) or back:
            findings.append(Finding(
                code="MSK_DISCOMFORT_REPORTED",
                summary="Musculoskeletal discomfort reported"
                        + (f" ({int(discomfort)}/5)" if discomfort is not None else "")
                        + (f"; {SYMPTOMS['back_pain']['label'].lower()}" if back else "") + ".",
                statement_type="observation",
                metric_codes=["msk_discomfort"] + (["symptom"] if back else []),
                evidence_observation_ids=[o["observation_id"] for o in ctx.valid_checkin_observations
                                          if o["metric_code"] == "msk_discomfort"
                                          or (o["metric_code"] == "symptom" and o["value_text"] == "back_pain")],
            ))

        ids = [o["observation_id"] for o in ctx.valid_checkin_observations
               if o["metric_code"] in self.metrics or (o["metric_code"] == "symptom" and o["value_text"] == "back_pain")]
        status = "completed" if logged_days >= 3 or discomfort is not None else "insufficient_data"
        return self.result(ctx, status, findings, ids, assessments, limitations,
                           activation_reason="Submitted: " + ", ".join(sorted(present)) if present else "Routed by symptom report",
                           output=output)
