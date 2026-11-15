"""Unit tests for the statistics and Isolation Forest implementations."""
import numpy as np

from app.ml.isolation_forest import IsolationForest, c_factor
from app.ml.stats import cusum_change_point, robust_summary, robust_z


def test_isolation_forest_scores_outlier_higher():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, size=(200, 3))
    model = IsolationForest(random_state=1).fit(X)
    scores = model.score_samples(np.array([[0, 0, 0], [6, -6, 6]]))
    assert scores[1] > scores[0]
    assert model.predict(np.array([[6, -6, 6]]))[0] == -1
    assert c_factor(256) > c_factor(16) > 0


def test_robust_summary_and_floor():
    s = robust_summary([60, 60, 60, 60], "heart_rate")
    assert s["median"] == 60 and s["robust_spread"] == 2.0  # floor prevents divide-by-zero
    assert robust_z(66, s["median"], s["robust_spread"]) == 3.0


def test_cusum_detects_shift_and_ignores_flat():
    flat = [7.0] * 20
    assert cusum_change_point(flat, 0.3) is None
    shifted = [7.0] * 12 + [5.5] * 8
    cp = cusum_change_point(shifted, 0.3)
    assert cp and cp["direction"] == "decrease"
