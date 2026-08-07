"""Spectral unmixing (Nivel 3)."""

from __future__ import annotations

from mineralmap.algorithms.base import Detector


class UnmixingDetector(Detector):
    def fit(self, cube, reference) -> UnmixingDetector:
        raise NotImplementedError

    def predict(self, cube):
        raise NotImplementedError
