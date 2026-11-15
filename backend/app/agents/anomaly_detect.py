"""AnomalyDetect — multivariate and per-signal statistical anomaly detection.

Three complementary methods, all reported with their inputs and limitations:
1. Isolation Forest over daily multi-signal feature vectors (unusual combinations).
2. Rolling robust z-score of each signal's recent 3-day mean vs its prior history.
3. Two-sided CUSUM change-point detection on each signal over the last 21 days.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np

from app.agents.base import AgentContext, BaseAgent
from app.domain.metrics import METRICS
from app.ml.isolation_forest import MODEL_NAME, MODEL_VERSION, IsolationForest
from app.ml.stats import cusum_change_point, robust_summary, robust_z
from app.schemas.models import Finding, MetricAssessment

FEATURES = ("heart_rate", "sleep_duration", "mood", "stress", "fatigue", "exercise_duration", "fluid_intake")
HISTORY_DAYS = 60
CONTAMINATION = 0.01      # chosen by scripts/evaluate_anomaly.py (best F1, lowest FPR); see docs/ML_EVALUATION.md
CONTRIBUTOR_Z = 1.5
ROLLING_DAYS = 3
ROLLING_Z = 2.0
CUSUM_WINDOW = 21
CUSUM_H = 5.0


class AnomalyDetectAgent(BaseAgent):
    agent_id = "anomaly_detect"
    name = "AnomalyDetect"
    version = "1.0.0"
    scope = "Statistical deviation across configured time series (multi-signal)"
    metrics = FEATURES
    method = f"{MODEL_NAME} v{MODEL_VERSION} (contamination={CONTAMINATION}) + rolling robust z + CUSUM"
    must_not = "Call an anomaly a medical emergency by itself"

    def analyze(self, ctx: AgentContext):
        min_days = int(ctx.settings.get("min_anomaly_days", 14))
        series = {f: ctx.daily(f, days=HISTORY_DAYS, include_current=True) for f in FEATURES}
        today = ctx.today
        # Use features that have a value today.
        active = [f for f in FEATURES if today in series[f]]
        limitations = [
            "Trained only on this crew member's own synthetic history; no clinical validity is claimed.",
            "Days with any missing selected signal are excluded; gaps are not interpolated.",
        ]
        model_meta = {"model": MODEL_NAME, "model_version": MODEL_VERSION, "contamination": CONTAMINATION,
                      "features": active, "history_window_days": HISTORY_DAYS}
        if len(active) < 2:
            return self.result(ctx, "insufficient_data", [], [], limitations=limitations + [
                "Fewer than two signals recorded today; multivariate analysis needs at least two."],
                activation_reason="Multi-signal check-in", output={"model": model_meta})

        from app.agents.baseline_iq import RECENT_EXCLUDE_DAYS
        cutoff = today - timedelta(days=RECENT_EXCLUDE_DAYS)
        # Same reference window as BaselineIQ (recent days excluded) so the agents do not disagree by construction.
        train_days = sorted(d for d in set.intersection(*(set(series[f]) for f in active)) if d < cutoff)
        if len(train_days) < min_days:
            return self.result(
                ctx, "insufficient_data", [], [],
                limitations=limitations + [f"Only {len(train_days)} complete day(s) of history for {', '.join(active)}; "
                                           f"{min_days} required for reliable anomaly analysis."],
                activation_reason="Multi-signal check-in", output={"model": model_meta, "training_days": len(train_days)})

        X = np.array([[series[f][d] for f in active] for d in train_days], dtype=float)
        stats = [robust_summary(list(X[:, i]), f) for i, f in enumerate(active)]
        med = np.array([s["median"] for s in stats])
        spread = np.array([s["robust_spread"] for s in stats])
        Xs = (X - med) / spread
        current = np.array([series[f][today] for f in active], dtype=float)
        cs = (current - med) / spread

        forest = IsolationForest(contamination=CONTAMINATION, random_state=42).fit(Xs)
        score = float(forest.score_samples(cs.reshape(1, -1))[0])
        is_anomaly = bool(score > (forest.threshold_ or 1.0))
        contributors = sorted(
            [{"metric_code": f, "label": METRICS[f].label, "current": round(float(current[i]), 2),
              "baseline_median": round(float(med[i]), 2), "robust_z": round(float(cs[i]), 2)}
             for i, f in enumerate(active)],
            key=lambda c: -abs(c["robust_z"]),
        )
        top = [c for c in contributors if abs(c["robust_z"]) >= CONTRIBUTOR_Z][:4]
        findings: list[Finding] = []
        assessments: list[MetricAssessment] = []
        input_ids = [o["observation_id"] for o in ctx.valid_checkin_observations if o["metric_code"] in active]
        window = {"start": train_days[0].isoformat(), "end": today.isoformat(), "training_days": len(train_days)}

        if is_anomaly:
            findings.append(Finding(
                code="MULTIVARIATE_ANOMALY",
                summary="Today's combination of signals is unusual compared with this crew member's own history"
                        + (": " + "; ".join(f"{c['label'].split(' (')[0]} z = {c['robust_z']:+.1f}" for c in top) if top else "")
                        + ". An anomaly flags a pattern for follow-up; it is not a diagnosis or an emergency by itself.",
                statement_type="observation",
                metric_codes=[c["metric_code"] for c in top] or active,
                evidence_observation_ids=input_ids,
                data={"anomaly_score": round(score, 3), "threshold": round(forest.threshold_ or 0, 3),
                      "contributors": top, "input_window": window, **model_meta},
                limitations=limitations.copy(),
            ))

        # Rolling robust z on the last ROLLING_DAYS mean, per signal (vs. history before that window).
        rolling = []
        for f in active:
            s = series[f]
            recent = [v for d, v in s.items() if d > today - timedelta(days=ROLLING_DAYS)]
            past = [v for d, v in s.items() if d <= today - timedelta(days=ROLLING_DAYS)]
            if len(recent) >= 2 and len(past) >= min_days:
                summ = robust_summary(past, f)
                rz = robust_z(float(np.mean(recent)), summ["median"], summ["robust_spread"])
                rolling.append({"metric_code": f, "rolling_mean": round(float(np.mean(recent)), 2),
                                "baseline_median": summ["median"], "rolling_z": round(rz, 2)})
        rolling_flags = [r for r in rolling if abs(r["rolling_z"]) >= ROLLING_Z]

        # CUSUM change points over the last CUSUM_WINDOW days.
        change_points = []
        for f in active:
            s = series[f]
            window_items = [(d, v) for d, v in s.items() if d > today - timedelta(days=CUSUM_WINDOW)]
            if len(window_items) < 10:
                continue
            vals = [v for _, v in window_items]
            spread_f = stats[active.index(f)]["robust_spread"]
            cp = cusum_change_point(vals, spread_f, h=CUSUM_H)
            recent_shift = (float(np.mean(vals[-3:])) - cp["reference_median"]) / spread_f if cp else 0.0
            # Require the shift to persist: the last three days must still sit >= 1 robust SD from the reference.
            if cp and cp["index"] >= len(vals) // 2 and abs(recent_shift) >= 1.0:
                change_points.append({"metric_code": f, "label": METRICS[f].label, "since": window_items[cp["index"]][0].isoformat(),
                                      "direction": cp["direction"], "reference_median": cp["reference_median"]})

        if change_points:
            findings.append(Finding(
                code="PERSISTENT_CHANGE_DETECTED",
                summary="Persistent shift detected (CUSUM) in: "
                        + "; ".join(f"{c['label'].split(' (')[0]} ({c['direction']} since {c['since']})" for c in change_points) + ".",
                statement_type="observation",
                metric_codes=[c["metric_code"] for c in change_points],
                evidence_observation_ids=input_ids,
                data={"change_points": change_points, "rolling": rolling_flags, "method": f"two-sided tabular CUSUM, k=0.5, h={CUSUM_H:g} (robust-SD units), persistence >= 1 SD over last 3 days"},
                limitations=["Change-point parameters are demonstration settings, not validated detection limits."],
            ))

        # Directional read used for cross-agent conflict checks: only strong multivariate contributors.
        flagged = {c["metric_code"] for c in top if abs(c["robust_z"]) >= 3.0} if is_anomaly else set()
        # Not being flagged is absence of evidence, not a claim of stability, so only "changed" is asserted.
        for f in sorted(flagged):
            assessments.append(MetricAssessment(metric_code=f, assessment="changed",
                                                detail="strong multivariate contributor (|z| >= 3)"))

        if not findings:
            findings.append(Finding(
                code="ANOMALY_NONE",
                summary=f"No unusual multi-signal pattern detected across {len(active)} signals "
                        f"({len(train_days)} days of history).",
                statement_type="observation",
                evidence_observation_ids=input_ids,
                data={"anomaly_score": round(score, 3), "threshold": round(forest.threshold_ or 0, 3), "input_window": window, **model_meta},
                limitations=limitations.copy(),
            ))

        return self.result(
            ctx, "completed", findings, input_ids, assessments, limitations,
            activation_reason=f"Multi-signal check-in with {len(train_days)} days of history",
            output={"model": model_meta, "anomaly_score": round(score, 3), "threshold": round(forest.threshold_ or 0, 3),
                    "is_anomaly": is_anomaly, "contributors": contributors, "rolling": rolling,
                    "change_points": change_points, "input_window": window},
        )
