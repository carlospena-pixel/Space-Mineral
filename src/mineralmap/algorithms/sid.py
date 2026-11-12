"""Spectral Information Divergence (SID).

Trata el espectro del pixel y la firma como distribuciones de probabilidad
(cada uno dividido por su suma) y mide la divergencia simetrica de
Kullback-Leibler entre ambas. Menor es mas parecido, igual que SAM.
"""

from __future__ import annotations

import numpy as np

from mineralmap.algorithms.base import Detector
from mineralmap.config import SAM_BANDS

EPS = 1e-6


class SID(Detector):
    """Divergencia de informacion espectral contra una firma de referencia."""

    higher_is_better = False
    bands = tuple(SAM_BANDS)

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        cube = np.asarray(cube, dtype=np.float64)
        reference = np.asarray(reference, dtype=np.float64)
        if cube.ndim != 3 or reference.ndim != 1 or cube.shape[0] != reference.size:
            raise ValueError(
                f"SID espera cubo (n, alto, ancho) y firma (n,); recibi "
                f"{cube.shape} y {reference.shape}."
            )
        if not np.isfinite(reference).all() or reference.sum() <= 0:
            raise ValueError("La firma de referencia debe ser finita y de suma positiva.")

        q = np.clip(reference, EPS, None)
        q = q / q.sum()
        p = np.clip(cube, EPS, None)
        with np.errstate(invalid="ignore"):
            p = p / p.sum(axis=0, keepdims=True)
        qb = q[:, None, None]
        sid = np.sum(p * np.log(p / qb), axis=0) + np.sum(qb * np.log(qb / p), axis=0)
        invalido = ~np.all(np.isfinite(cube), axis=0)
        return np.where(invalido, np.nan, sid)
