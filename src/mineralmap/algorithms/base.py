"""Clase abstracta Detector: interfaz comun para todos los algoritmos de deteccion."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Detector(ABC):
    """Contrato que SAM, Random Forest y unmixing cumplen por igual.

    El pipeline no sabe que algoritmo usa, solo llama a fit/predict.
    """

    @abstractmethod
    def fit(self, cube: np.ndarray, reference: np.ndarray) -> "Detector":
        ...

    @abstractmethod
    def predict(self, cube: np.ndarray) -> np.ndarray:
        """Devuelve un mapa de puntaje (mismo alto/ancho que cube)."""
        ...
