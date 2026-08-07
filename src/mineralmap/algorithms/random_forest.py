"""Clasificador Random Forest (Nivel 2)."""

from __future__ import annotations

from mineralmap.algorithms.base import Detector


class RandomForestDetector(Detector):
    def fit(self, cube, reference) -> RandomForestDetector:
        raise NotImplementedError

    def predict(self, cube):
        raise NotImplementedError
