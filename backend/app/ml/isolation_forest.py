"""Isolation Forest implemented with NumPy.

Follows Liu, Ting & Zhou (2008): random axis-parallel splits; anomalies are isolated
in fewer splits, so their average path length is shorter. The anomaly score is
s(x) = 2 ** (-E[h(x)] / c(psi)). Implemented locally (rather than via scikit-learn)
so the analysis runs on locked-down machines where compiled extensions are blocked,
and so every step is inspectable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MODEL_NAME = "IsolationForest(numpy)"
MODEL_VERSION = "1.0.0"
EULER_GAMMA = 0.5772156649


def c_factor(n: int) -> float:
    """Average path length of an unsuccessful BST search over n points."""
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (math.log(n - 1) + EULER_GAMMA) - 2.0 * (n - 1) / n


@dataclass
class _Node:
    size: int
    feature: int = -1
    threshold: float = 0.0
    left: "_Node | None" = None
    right: "_Node | None" = None


class IsolationForest:
    def __init__(self, n_estimators: int = 150, max_samples: int = 256, contamination: float = 0.05, random_state: int = 42):
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.contamination = contamination
        self.random_state = random_state
        self.trees: list[_Node] = []
        self.psi = 0
        self.threshold_: float | None = None

    def _build(self, X: np.ndarray, depth: int, limit: int, rng: np.random.Generator) -> _Node:
        n = X.shape[0]
        if depth >= limit or n <= 1:
            return _Node(size=n)
        spans = X.max(axis=0) - X.min(axis=0)
        candidates = np.flatnonzero(spans > 0)
        if candidates.size == 0:
            return _Node(size=n)
        feature = int(rng.choice(candidates))
        lo, hi = X[:, feature].min(), X[:, feature].max()
        threshold = float(rng.uniform(lo, hi))
        mask = X[:, feature] < threshold
        return _Node(
            size=n,
            feature=feature,
            threshold=threshold,
            left=self._build(X[mask], depth + 1, limit, rng),
            right=self._build(X[~mask], depth + 1, limit, rng),
        )

    def fit(self, X: np.ndarray) -> "IsolationForest":
        X = np.asarray(X, dtype=float)
        if X.ndim != 2 or X.shape[0] < 2:
            raise ValueError("IsolationForest needs a 2-D array with at least two rows")
        rng = np.random.default_rng(self.random_state)
        self.psi = min(self.max_samples, X.shape[0])
        limit = math.ceil(math.log2(max(self.psi, 2)))
        self.trees = []
        for _ in range(self.n_estimators):
            idx = rng.choice(X.shape[0], size=self.psi, replace=False)
            self.trees.append(self._build(X[idx], 0, limit, rng))
        train_scores = self.score_samples(X)
        self.threshold_ = float(np.quantile(train_scores, 1 - self.contamination))
        return self

    @staticmethod
    def _path_length(x: np.ndarray, node: _Node, depth: int = 0) -> float:
        while node.left is not None and node.right is not None:
            node = node.left if x[node.feature] < node.threshold else node.right
            depth += 1
        return depth + c_factor(node.size)

    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Anomaly score in (0, 1]; higher = more anomalous."""
        X = np.asarray(X, dtype=float)
        norm = c_factor(self.psi) or 1.0
        out = np.empty(X.shape[0])
        for i, row in enumerate(X):
            mean_path = np.mean([self._path_length(row, t) for t in self.trees])
            out[i] = 2.0 ** (-mean_path / norm)
        return out

    def predict(self, X: np.ndarray) -> np.ndarray:
        """-1 for anomaly, 1 for inlier (scikit-learn convention)."""
        if self.threshold_ is None:
            raise RuntimeError("fit() must be called first")
        return np.where(self.score_samples(X) > self.threshold_, -1, 1)
