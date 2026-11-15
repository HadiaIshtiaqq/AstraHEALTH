"""CardioGuard — heart rate, blood pressure, temperature and cardiovascular symptoms."""
from __future__ import annotations

from app.agents.base import AgentContext, BaseAgent, fmt
from app.agents.common import deviation_signal
from app.domain.metrics import SYMPTOMS
from app.schemas.models import Finding

CARDIO_SYMPTOMS = {"chest_pain", "shortness_of_breath", "palpitations", "dizziness", "fainting"}


class CardioGuardAgent(BaseAgent):
    agent_id = "cardio_guard"
    name = "CardioGuard"
    scope = "Cardiovascular-related indicators: heart rate, blood pressure, temperature, related symptoms"
    metrics = ("heart_rate", "bp_systolic", "bp_diastolic", "body_temperature")
    method = "Personal-baseline robust z-scores, sustained-change check, completeness and context checks"
    must_not = "Diagnose arrhythmia or cardiovascular disease"

    def analyze(self, ctx: AgentContext):
        findings: list[Finding] = []
        assessments = []
        limitations: list[str] = []
        present = ctx.checkin_metrics()
        symptoms = ctx.symptoms() & CARDIO_SYMPTOMS
        ids = [o["observation_id"] for o in ctx.valid_checkin_observations
               if o["metric_code"] in self.metrics or (o["metric_code"] == "symptom" and o["value_text"] in CARDIO_SYMPTOMS)]

        for code, finding_code in (
            ("heart_rate", "HR_BASELINE_DEVIATION"),
            ("bp_systolic", "BP_BASELINE_DEVIATION"),
            ("bp_diastolic", "BP_BASELINE_DEVIATION"),
            ("body_temperature", "TEMP_BASELINE_DEVIATION"),
        ):
            if code not in present:
                continue
            finding, assessment, lims = deviation_signal(ctx, code, finding_code)
            assessments.append(assessment)
            limitations += lims
            if finding:
                if code == "heart_rate":
                    hr_obs = ctx.current("heart_rate")
                    context = hr_obs[-1].get("context") if hr_obs else None
                    finding.data["measurement_context"] = context
                    if context == "post_exercise":
                        finding.limitations.append("Measured after exercise; the baseline is built mostly from resting readings.")
                findings.append(finding)

        # Describe current values even when no baseline exists (never label them normal).
        described = [f"{label} {fmt(ctx.current_value(c), c)}" for c, label in (
            ("heart_rate", "heart rate"), ("bp_systolic", "systolic"), ("bp_diastolic", "diastolic"),
            ("body_temperature", "temperature")) if c in present]
        if described:
            findings.insert(0, Finding(
                code="CARDIO_VALUES_RECORDED",
                summary="Recorded " + ", ".join(described) + ".",
                statement_type="observation",
                metric_codes=[c for c in self.metrics if c in present],
                evidence_observation_ids=[i for i in ids],
            ))

        if symptoms:
            sym_ids = [o["observation_id"] for o in ctx.valid_checkin_observations
                       if o["metric_code"] == "symptom" and o["value_text"] in symptoms]
            findings.append(Finding(
                code="CARDIO_SYMPTOM_REPORTED",
                summary="Self-reported symptom(s) relevant to cardiovascular monitoring: "
                        + ", ".join(SYMPTOMS[s]["label"].lower() for s in sorted(symptoms)) + ".",
                statement_type="observation",
                metric_codes=["symptom"],
                evidence_observation_ids=sym_ids,
                data={"symptoms": sorted(symptoms)},
                limitations=["Symptoms are self-reported and have not been clinically assessed."],
            ))

        if not ids:
            return self.result(ctx, "insufficient_data", [], [], limitations=["No valid cardiovascular observations."],
                               activation_reason="Routed but no valid cardiovascular data")
        comparable = any(a.assessment != "unknown" for a in assessments)
        status = "completed" if comparable or symptoms else "insufficient_data"
        reason = "Submitted: " + ", ".join(sorted((present & set(self.metrics)) | ({"symptoms"} if symptoms else set())))
        return self.result(ctx, status, findings, ids, assessments, limitations, activation_reason=reason)
