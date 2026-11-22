"""Clasificador Random Forest (Nivel 2).

Detector supervisado: se entrena con la verdad de terreno (pixeles 0/1) sobre
bandas e indices. Ver `mineralmap.algorithms.supervised`.
"""

from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier

from mineralmap.algorithms.supervised import SupervisedDetector


class RandomForestDetector(SupervisedDetector):
    """Bosque aleatorio con pesos de clase balanceados. Mayor es mejor."""

    def __init__(
        self, n_estimators: int = 200, min_samples_leaf: int = 1, seed: int = 42
    ):
        super().__init__(seed)
        self.n_estimators = n_estimators
        self.min_samples_leaf = min_samples_leaf

    def _build(self, y):
        return RandomForestClassifier(
            n_estimators=self.n_estimators,
            min_samples_leaf=self.min_samples_leaf,
            class_weight="balanced",
            random_state=self.seed,
            n_jobs=-1,
        )
