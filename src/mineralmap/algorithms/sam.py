"""Spectral Angle Mapper (Nivel 1)."""

from __future__ import annotations

import numpy as np

from mineralmap.algorithms.base import Detector


class SAM(Detector):
    def __init__(self, angle_threshold_rad: float = 0.1):
        self.angle_threshold_rad = angle_threshold_rad
        self._reference: np.ndarray | None = None

    def fit(self, cube: np.ndarray, reference: np.ndarray) -> "SAM":
        self._reference = reference
        return self

    def predict(self, cube: np.ndarray) -> np.ndarray:
        raise NotImplementedError
