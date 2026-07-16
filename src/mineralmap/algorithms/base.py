"""Clase abstracta Detector: interfaz comun para todos los algoritmos de deteccion."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Detector(ABC):
    """Contrato comun a todos los detectores (SAM, Random Forest, unmixing, ...).

    El pipeline no conoce el algoritmo concreto: solo llama a predict() con
    el cubo de la escena y la firma de referencia del mineral objetivo.
    """

    @abstractmethod
    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Calcula el mapa de puntaje de deteccion del mineral en la escena.

        Parameters
        ----------
        cube:
            Cubo de reflectancia de la escena, forma (n_bandas, alto, ancho).
        reference:
            Firma espectral de referencia del mineral objetivo, forma (n_bandas,).

        Returns
        -------
        np.ndarray
            Mapa de puntaje 2D, forma (alto, ancho): a mayor valor, mayor
            probabilidad/similitud de presencia del mineral segun el algoritmo.
        """
        ...
