"""NutriTrack — logged fluid intake, appetite, body mass and optional glucose."""
from __future__ import annotations

from datetime import timedelta

from app.agents.base import AgentContext, BaseAgent
from app.agents.common import deviation_signal
from app.schemas.models import Finding


class NutriTrackAgent(BaseAgent):
    agent_id = "nutri_track"
    name = "NutriTrack"
    scope = "Nutrition and hydration logs: fluid intake, appetite, body mass, optional glucose"
    metrics = ("fluid_intake", "appetite", "body_mass", "blood_glucose")
    method = "Daily intake totals vs personal baseline; log completeness; body-mass deviation"
    must_not = "Infer dehydration or nutritional deficiency from intake logs alone"

    def analyze(self, ctx: AgentContext):
        present = ctx.checkin_metrics() & set(self.metrics)
        findings: list[Finding] = []
        assessments = []
        limitations = ["Intake is logged, not measured physiologically; hydration status is not inferred."]

        for code, finding_code, adverse in (
            ("fluid_intake", "FLUID_INTAKE_BELOW_BASELINE", "down"),
            ("appetite", "APPETITE_BELOW_BASELINE", "down"),
            ("body_mass", "BODY_MASS_CHANGE", "both"),
        ):
            if code not in present:
                continue
            finding, assessment, lims = deviation_signal(ctx, code, finding_code, adverse=adverse)
            assessments.append(assessment)
            limitations += lims
            if finding:
                if code == "fluid_intake":
                    finding.limitations.append("Today's total may be incomplete if more intake is logged later.")
                findings.append(finding)

        if "blood_glucose" in present:
            findings.append(Finding(
                code="GLUCOSE_RECORDED",
                summary="Blood glucose recorded. Interpretation requires a defined device, measurement timing "
                        "and qualified review, so no comparison is made in this prototype.",
                statement_type="limitation",
                metric_codes=["blood_glucose"],
                evidence_observation_ids=[o["observation_id"] for o in ctx.current("blood_glucose")],
            ))

        week = ctx.daily("fluid_intake", days=7, include_current=True)
        missing = sorted(d.isoformat() for d in {ctx.today - timedelta(days=i) for i in range(7)} - set(week))
        if len(missing) >= 2:
            findings.append(Finding(
                code="NUTRITION_LOGS_INCOMPLETE",
                summary=f"No fluid-intake log for {len(missing)} of the last 7 days.",
                statement_type="limitation",
                metric_codes=["fluid_intake"],
                data={"missing_days": missing},
            ))

        ids = [o["observation_id"] for o in ctx.valid_checkin_observations if o["metric_code"] in self.metrics]
        if not ids:
            return self.result(ctx, "insufficient_data", findings, [], limitations=limitations,
                               activation_reason="Routed but no nutrition data")
        status = "completed" if any(a.assessment != "unknown" for a in assessments) else "insufficient_data"
        return self.result(ctx, status, findings, ids, assessments, limitations,
                           activation_reason="Submitted: " + ", ".join(sorted(present)))
