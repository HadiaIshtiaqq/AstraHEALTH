"""MissionContext — spaceflight hazard context for interpreting monitoring results."""
from __future__ import annotations

from datetime import timedelta

from app.agents.base import AgentContext, BaseAgent
from app.db.database import parse_iso
from app.schemas.models import Finding


class MissionContextAgent(BaseAgent):
    agent_id = "mission_context"
    name = "MissionContext"
    scope = "Mission phase, gravity, communication delay, dosimeter records and routine changes (RIDGE hazards)"
    metrics = ("radiation_dose",)
    method = "Descriptive aggregation of mission records; co-occurrence only, never causal attribution"
    must_not = "Claim that an environmental hazard caused a health change"

    def analyze(self, ctx: AgentContext):
        p = ctx.profile
        findings: list[Finding] = []
        mission_day = p.get("mission_day")
        comm = p.get("communication_mode", "unknown")
        has_mission = p.get("has_mission", True)
        if has_mission:
            summary = (f"Mission {p.get('mission_name', p.get('mission_id'))}, day {mission_day}; environment: {p.get('environment')}. "
                       f"Gravity context: {p.get('gravity_context')}. Communication: {comm}.")
        else:
            summary = ("No mission is assigned to this profile, so no mission phase, gravity or communication context "
                       "is applied. Dosimeter and routine records are still summarised.")
        findings.append(Finding(
            code="MISSION_CONTEXT_SUMMARY",
            summary=summary,
            statement_type="observation",
            data={"mission_day": mission_day, "gravity_context": p.get("gravity_context"), "has_mission": has_mission,
                  "communication_mode": comm, "environment": p.get("environment")},
        ))
        if has_mission and "delay" in comm.lower():
            findings.append(Finding(
                code="COMM_DELAY_NOTE",
                summary="Ground medical consultation is subject to communication delay; onboard escalation paths "
                        "should be used first for anything time-sensitive.",
                statement_type="interpretation",
            ))

        # Radiation dosimeter records (descriptive only).
        rad = [o for o in ctx.history if o["metric_code"] == "radiation_dose" and o["normalized_value"] is not None]
        output: dict = {}
        if rad:
            total = sum(o["normalized_value"] for o in rad)
            week_start = ctx.reference_time - timedelta(days=7)
            week = sum(o["normalized_value"] for o in rad if parse_iso(o["measured_at"]) >= week_start)
            output.update(cumulative_mSv=round(total, 3), last_7_days_mSv=round(week, 3), records=len(rad))
            findings.append(Finding(
                code="RADIATION_RECORD_SUMMARY",
                summary=f"Dosimeter records: {total:.2f} mSv cumulative ({len(rad)} records), "
                        f"{week:.3f} mSv in the last 7 days" + (" (simulated data)." if p.get("is_synthetic") else "."),
                statement_type="observation",
                metric_codes=["radiation_dose"],
                evidence_observation_ids=[o["observation_id"] for o in ctx.current("radiation_dose")],
                data=output.copy(),
                limitations=["Dose records are descriptive; no individual health effect is inferred from them."],
            ))

        # Routine change: exercise this week vs prior week (context for other agents' findings).
        ex = ctx.daily("exercise_duration", days=14, include_current=True)
        this_week = [v for d, v in ex.items() if d > ctx.today - timedelta(days=7)]
        prior_week = [v for d, v in ex.items() if d <= ctx.today - timedelta(days=7)]
        if len(this_week) >= 3 and len(prior_week) >= 3:
            a, b = sum(this_week) / len(this_week), sum(prior_week) / len(prior_week)
            if b > 0 and abs(a - b) / b >= 0.25:
                findings.append(Finding(
                    code="ROUTINE_CHANGE_NOTED",
                    summary=f"Exercise routine changed this week (mean {a:.0f} min/day vs {b:.0f} min/day the week before). "
                            "Other trends this week should be read in that context; co-occurrence does not establish cause.",
                    statement_type="interpretation",
                    metric_codes=["exercise_duration"],
                    data={"this_week_mean": round(a, 1), "prior_week_mean": round(b, 1)},
                ))

        ids = [o["observation_id"] for o in ctx.current("radiation_dose")]
        return self.result(ctx, "completed", findings, ids,
                           limitations=["Context is descriptive; it does not attribute cause to any hazard."],
                           activation_reason=ctx.settings.get("mission_activation_reason", "Mission record or multi-system check-in"),
                           output=output)
