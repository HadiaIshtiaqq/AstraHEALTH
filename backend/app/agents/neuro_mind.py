"""NeuroMind — self-reported behavioural wellbeing (mood, stress, fatigue)."""
from __future__ import annotations

from app.agents.base import AgentContext, BaseAgent, fmt
from app.agents.common import deviation_signal
from app.domain.metrics import METRICS, SYMPTOMS
from app.ml.stats import robust_z, slope_per_day
from app.schemas.models import Finding

# Adverse direction for each scale (mood down, stress/fatigue up).
ADVERSE = {"mood": "down", "stress": "up", "fatigue": "up"}
NEURO_SYMPTOMS = {"confusion", "headache", "severe_headache", "vision_change", "low_energy"}
TREND_DAYS = 5
TREND_SLOPE = 0.2      # scale points per day over the trend window (demonstration parameter)
TREND_CURRENT_Z = 1.5  # current value must also differ from the personal baseline


class NeuroMindAgent(BaseAgent):
    agent_id = "neuro_mind"
    name = "NeuroMind"
    scope = "Behavioural wellbeing from self-reports: mood, stress, fatigue and related symptoms"
    metrics = ("mood", "stress", "fatigue")
    method = "Personal-baseline deviation plus multi-day least-squares trend on self-report scales"
    must_not = "Diagnose depression, anxiety or cognitive impairment"

    def analyze(self, ctx: AgentContext):
        present = ctx.checkin_metrics() & set(self.metrics)
        symptoms = ctx.symptoms() & NEURO_SYMPTOMS
        findings: list[Finding] = []
        assessments = []
        limitations = ["Self-report scales in this prototype are not validated psychological instruments.",
                       "Wellbeing data is private to the crew member and medical officer by default."]
        adverse_trends = []

        for code in sorted(present):
            finding, assessment, lims = deviation_signal(ctx, code, "WELLBEING_SINGLE_DAY_CHANGE", adverse=ADVERSE[code])
            assessments.append(assessment)
            limitations += lims
            b = ctx.baselines.get(code, {})
            series = ctx.daily(code, days=TREND_DAYS + 1, include_current=True)
            points = list(series.items())[-TREND_DAYS:]
            slope = slope_per_day(points)
            z = b.get("robust_z")
            adverse_slope = slope is not None and (slope <= -TREND_SLOPE if ADVERSE[code] == "down" else slope >= TREND_SLOPE)
            adverse_now = z is not None and (z <= -TREND_CURRENT_Z if ADVERSE[code] == "down" else z >= TREND_CURRENT_Z)
            if b.get("available") and adverse_slope and adverse_now and len(points) >= 4:
                adverse_trends.append({
                    "metric_code": code, "slope_per_day": slope, "days": len(points),
                    "current": b.get("current"), "baseline_median": b.get("median"), "robust_z": z,
                    "values": [(d.isoformat(), v) for d, v in points],
                })
            elif finding:
                findings.append(finding)

        for t in adverse_trends:
            m = METRICS[t["metric_code"]]
            word = "lower" if ADVERSE[t["metric_code"]] == "down" else "higher"
            findings.append(Finding(
                code="WELLBEING_TREND_ADVERSE",
                summary=f"Self-reported {m.label.split(' (')[0].lower()} has trended {word} over {t['days']} check-ins "
                        f"(now {fmt(t['current'], t['metric_code'])}, usual {fmt(t['baseline_median'], t['metric_code'])}).",
                statement_type="observation",
                metric_codes=[t["metric_code"]],
                evidence_observation_ids=[o["observation_id"] for o in ctx.current(t["metric_code"])],
                data=t,
                limitations=["Trend is based on a short window of self-reports."],
            ))
        if len(adverse_trends) >= 2:
            findings.append(Finding(
                code="WELLBEING_MULTI_SIGNAL_DECLINE",
                summary="Several self-reported wellbeing measures are moving in a less favourable direction together ("
                        + ", ".join(METRICS[t['metric_code']].label.split(' (')[0].lower() for t in adverse_trends)
                        + "). This is a pattern worth a supportive conversation, not a diagnosis.",
                statement_type="interpretation",
                metric_codes=[t["metric_code"] for t in adverse_trends],
                evidence_observation_ids=[i for t in adverse_trends for i in
                                          (o["observation_id"] for o in ctx.current(t["metric_code"]))],
                data={"signals": [t["metric_code"] for t in adverse_trends]},
            ))

        if symptoms:
            findings.append(Finding(
                code="NEURO_SYMPTOM_REPORTED",
                summary="Self-reported: " + ", ".join(SYMPTOMS[s]["label"].lower() for s in sorted(symptoms)) + ".",
                statement_type="observation",
                metric_codes=["symptom"],
                evidence_observation_ids=[o["observation_id"] for o in ctx.valid_checkin_observations
                                          if o["metric_code"] == "symptom" and o["value_text"] in symptoms],
                data={"symptoms": sorted(symptoms)},
            ))

        ids = [o["observation_id"] for o in ctx.valid_checkin_observations
               if o["metric_code"] in self.metrics or (o["metric_code"] == "symptom" and o["value_text"] in symptoms)]
        if not ids:
            return self.result(ctx, "insufficient_data", [], [], limitations=limitations,
                               activation_reason="Routed but no wellbeing self-reports")
        status = "completed" if any(a.assessment != "unknown" for a in assessments) or symptoms else "insufficient_data"
        return self.result(ctx, status, findings, ids, assessments, limitations,
                           activation_reason="Submitted: " + ", ".join(sorted(present | ({"symptoms"} if symptoms else set()))),
                           output={"adverse_trends": adverse_trends})
