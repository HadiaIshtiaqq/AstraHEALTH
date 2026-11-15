# AnomalyDetect — ML evaluation

Reproduce with: `backend\.venv\Scripts\python.exe scripts\evaluate_anomaly.py`

**Dataset (synthetic, labelled).** 30 simulated profiles × 60 days × 7 signals. The first 40 days are training
history. The last 20 days are scored and contain: abrupt multi-signal deviations (3–5 SD on 2–4 signals, labelled
anomalous), gradual 6-day drift (labelled anomalous once it exceeds 2.5 SD), single-signal sensor noise (~2 SD,
labelled normal), and missing readings (excluded, never interpolated).

**Split by profile, not by row.** Profiles 100–114 are used to choose the contamination setting; profiles 200–214
are a separate holdout set. No profile contributes to both.

| contamination | precision | recall | F1 | false-positive rate |
|---|---|---|---|---|
| 0.01 | 0.69 | 0.72 | 0.71 | 0.088 |
| 0.03 | 0.62 | 0.79 | 0.70 | 0.130 |
| 0.05 | 0.61 | 0.83 | 0.70 | 0.144 |
| 0.10 | 0.50 | 0.91 | 0.65 | 0.241 |

**Selected: 0.01.** It has the highest F1 and the lowest false-positive rate on the selection set. In this
prototype an anomaly alone only reaches MONITOR, so a low false-alarm rate is preferred over recall.

**Holdout (15 unseen profiles):** precision 0.71 · recall 0.79 · F1 0.75 · FPR 0.075
(TP 41, FN 11, FP 17, TN 211).

**Flag rate by case type:**

| Case type | Flag rate |
|---|---|
| Abrupt deviation | 0.70 |
| Gradual drift (labelled) | 1.00 |
| Early drift (not yet labelled) | 0.33 |
| Sensor noise | 0.21 |
| Stable | 0.02 |

**Complementary detectors** in the agent: rolling robust z-score (3-day mean vs prior history) and two-sided CUSUM
(k = 0.5, h = 5 robust-SD units, and the shift must persist ≥ 1 SD over the last 3 days). Both are demonstration
parameters.

**What this does not show.** These are synthetic data. No clinical sensitivity, specificity or predictive validity
is claimed.

## Stress test (added after review)

The original test data was generated with the same Gaussian assumptions the model is built around, which
flatters it. The holdout profiles were therefore regenerated with:
- heavy-tailed noise (Student t, 3 degrees of freedom)
- day-to-day autocorrelation (AR(1), φ = 0.6)
- a weekly rhythm (light exercise on rest days)

| Holdout | Precision | Recall | F1 | False-positive rate |
|---|---|---|---|---|
| Original (Gaussian) | 0.71 | 0.79 | 0.75 | 0.075 |
| Stress test | 0.76 | 0.72 | 0.74 | 0.054 |

Performance holds up. Recall drops on abrupt deviations (0.70 → 0.63) because heavy-tailed history widens what
counts as "normal". Sensor-noise false alarms fall (0.21 → 0.07).

This is still synthetic. Real wearable data would need its own evaluation.
