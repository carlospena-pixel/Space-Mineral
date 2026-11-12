"""Matched Filtering (MF).

Proyecta cada pixel, centrado en la media del fondo, sobre la direccion de la
firma "blanqueada" por la covarianza del fondo. Vale ~1 donde el pixel es la
firma pura y ~0 en el fondo tipico. Mayor es mejor.

El fondo se estima con los pixeles validos de la propia escena, sin etiquetas:
es un metodo no supervisado y no usa la verdad de terreno.
"""

from __future__ import annotations

import numpy as np

from mineralmap.algorithms.base import Detector
from mineralmap.config import SAM_BANDS


class MatchedFilter(Detector):
    """Filtro adaptado clasico con fondo estimado de la escena."""

    higher_is_better = True
    bands = tuple(SAM_BANDS)

    def __init__(self, seed: int = 42, max_fondo: int = 200_000, ridge: float = 1e-6):
        self.seed = seed
        self.max_fondo = max_fondo
        self.ridge = ridge

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        cube = np.asarray(cube, dtype=np.float64)
        reference = np.asarray(reference, dtype=np.float64)
        if cube.ndim != 3 or reference.ndim != 1 or cube.shape[0] != reference.size:
            raise ValueError(
                f"MatchedFilter espera cubo (n, alto, ancho) y firma (n,); recibi "
                f"{cube.shape} y {reference.shape}."
            )
        n, alto, ancho = cube.shape
        X = cube.reshape(n, -1).T
        validos = np.all(np.isfinite(X), axis=1)
        if validos.sum() < n + 1:
            raise ValueError("No hay suficientes pixeles validos para estimar el fondo.")

        idx = np.flatnonzero(validos)
        if idx.size > self.max_fondo:
            idx = np.random.default_rng(self.seed).choice(idx, self.max_fondo, replace=False)
        fondo = X[idx]
        mu = fondo.mean(axis=0)
        cov = np.cov(fondo, rowvar=False) + self.ridge * np.eye(n)
        cov_inv = np.linalg.inv(cov)

        d = reference - mu
        w = cov_inv @ d / (d @ cov_inv @ d)
        puntaje = np.full(X.shape[0], np.nan)
        puntaje[validos] = (X[validos] - mu) @ w
        return puntaje.reshape(alto, ancho)
