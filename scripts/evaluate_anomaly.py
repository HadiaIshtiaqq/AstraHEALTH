"""ML evaluation for AnomalyDetect's Isolation Forest (test plan 5.5).

Builds a labelled synthetic dataset (stable days, abrupt multi-signal deviations, gradual drift,
missing readings, sensor noise), trains one model per simulated profile on that profile's own
history (as the agent does), and scores held-out days. Profiles are split into a selection set
(used to choose the contamination setting) and a separate holdout set (reported), so no profile
contributes to both.

Usage:  backend\\.venv\\Scripts\\python.exe scripts\\evaluate_anomaly.py
Results are synthetic and say nothing about clinical sensitivity or specificity.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.ml.isolation_forest import IsolationForest  # noqa: E402

FEATURES = ["heart_rate", "sleep_duration", "mood", "stress", "fatigue", "exercise_duration", "fluid_intake"]
MEANS = np.array([62, 7.2, 4, 2, 2, 125, 2350], dtype=float)
SDS = np.array([2.3, 0.35, 0.35, 0.35, 0.35, 9, 160], dtype=float)
# Direction of an adverse multi-signal deviation (HR up, sleep down, mood down, stress/fatigue up, exercise/fluid down)
ADVERSE = np.array([1, -1, -1, 1, 1, -1, -1], dtype=float)
TRAIN_DAYS, TEST_DAYS = 40, 20
CONTAMINATIONS = [0.01, 0.03, 0.05, 0.10]


def make_profile(seed: int, realistic: bool = False):
    rng = np.random.default_rng(seed)
    mean = MEANS + rng.normal(0, SDS * 0.8)
    days = TRAIN_DAYS + TEST_DAYS
    if not realistic:
        X = rng.normal(mean, SDS, size=(days, len(FEATURES)))
    else:
        # Stress test: heavy-tailed noise (Student t, 3 dof), day-to-day autocorrelation (AR(1), phi=0.6),
        # a weekly rhythm (lighter exercise on rest days) and occasional sensor outliers — assumptions the
        # Isolation Forest was NOT built around.
        noise = rng.standard_t(3, size=(days, len(FEATURES))) * SDS / np.sqrt(3)
        for i in range(1, days):
            noise[i] = 0.6 * noise[i - 1] + np.sqrt(1 - 0.36) * noise[i]
        weekly = np.zeros((days, len(FEATURES)))
        weekly[np.arange(days) % 7 == 6, FEATURES.index("exercise_duration")] = -2.5 * SDS[FEATURES.index("exercise_duration")]
        X = mean + noise + weekly
    labels = np.zeros(days, dtype=int)
    kinds = np.array(["stable"] * days, dtype=object)
    test_idx = np.arange(TRAIN_DAYS, days)
    # Abrupt multi-signal deviations (3–5 SD on 2–4 signals)
    for d in rng.choice(test_idx, size=3, replace=False):
        k = rng.integers(2, 5)
        cols = rng.choice(len(FEATURES), size=k, replace=False)
        X[d, cols] += ADVERSE[cols] * SDS[cols] * rng.uniform(3, 5, size=k)
        labels[d], kinds[d] = 1, "abrupt"
    # Gradual drift over the last 6 days (labelled anomalous only once it exceeds ~2.5 SD on average)
    if seed % 2 == 0:
        ramp = np.linspace(0, 3.5, 6)
        for i, d in enumerate(range(days - 6, days)):
            X[d] += ADVERSE * SDS * ramp[i]
            if ramp[i] >= 2.5:
                labels[d], kinds[d] = 1, "gradual"
            elif kinds[d] == "stable":
                kinds[d] = "gradual_early"
    # Sensor noise: isolated single-signal spikes of ~2 SD — labelled normal (should not alarm)
    for d in rng.choice([i for i in test_idx if labels[i] == 0], size=2, replace=False):
        c = rng.integers(len(FEATURES))
        X[d, c] += rng.choice([-1, 1]) * 2 * SDS[c]
        kinds[d] = "noise"
    # Missing readings: drop a signal on some days (rows with gaps are excluded, never interpolated)
    missing = np.zeros(days, dtype=bool)
    missing[rng.choice(days, size=4, replace=False)] = True
    return X, labels, kinds, missing


def evaluate(seeds, contamination, realistic=False):
    tp = fp = tn = fn = 0
    by_kind: dict[str, list[int]] = {}
    for seed in seeds:
        X, y, kinds, missing = make_profile(seed, realistic)
        train = [i for i in range(TRAIN_DAYS) if not missing[i]]
        test = [i for i in range(TRAIN_DAYS, len(y)) if not missing[i]]
        med = np.median(X[train], axis=0)
        spread = np.maximum(1.4826 * np.median(np.abs(X[train] - med), axis=0), SDS * 0.25)
        model = IsolationForest(contamination=contamination, random_state=42).fit((X[train] - med) / spread)
        pred = model.predict((X[test] - med) / spread) == -1
        for i, p in zip(test, pred):
            by_kind.setdefault(kinds[i], []).append(int(p))
            if y[i] and p: tp += 1
            elif y[i]: fn += 1
            elif p: fp += 1
            else: tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {"contamination": contamination, "tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": precision,
            "recall": recall, "f1": f1, "fpr": fpr, "flag_rate_by_kind": {k: float(np.mean(v)) for k, v in by_kind.items()}}


def main():
    selection, holdout = range(100, 115), range(200, 215)
    print("Selection set (15 profiles) — choose contamination")
    print("| contamination | precision | recall | F1 | false-positive rate |\n|---|---|---|---|---|")
    results = [evaluate(selection, c) for c in CONTAMINATIONS]
    for r in results:
        print(f"| {r['contamination']:.2f} | {r['precision']:.2f} | {r['recall']:.2f} | {r['f1']:.2f} | {r['fpr']:.3f} |")
    best = max(results, key=lambda r: r["f1"])
    print(f"\nSelected contamination = {best['contamination']} (highest F1 on the selection set)")
    h = evaluate(holdout, best["contamination"])
    print("\nHoldout set (15 different profiles)")
    print(f"precision {h['precision']:.2f} · recall {h['recall']:.2f} · F1 {h['f1']:.2f} · FPR {h['fpr']:.3f}")
    print(f"confusion matrix: TP {h['tp']}  FN {h['fn']}  FP {h['fp']}  TN {h['tn']}")
    print("flag rate by case type:", {k: round(v, 2) for k, v in sorted(h["flag_rate_by_kind"].items())})
    s = evaluate(holdout, best["contamination"], realistic=True)
    print("\nStress-test holdout (heavy tails + autocorrelation + weekly rhythm, same 15 profiles)")
    print(f"precision {s['precision']:.2f} · recall {s['recall']:.2f} · F1 {s['f1']:.2f} · FPR {s['fpr']:.3f}")
    print(f"confusion matrix: TP {s['tp']}  FN {s['fn']}  FP {s['fp']}  TN {s['tn']}")
    print("flag rate by case type:", {k: round(v, 2) for k, v in sorted(s["flag_rate_by_kind"].items())})


if __name__ == "__main__":
    main()
