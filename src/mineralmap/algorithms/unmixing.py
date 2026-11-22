"""Spectral unmixing (Nivel 3): desmezcla lineal totalmente restringida (FCLS).

Cada pixel se modela como una mezcla lineal de componentes puros (la firma de
referencia del mineral mas otros componentes que se pasan al construir el
detector). FCLS resuelve las proporciones con dos restricciones: no negativas
y que sumen 1. El puntaje es la proporcion del componente de referencia, mayor
es mejor.

La suma igual a 1 se impone con el truco del renglon aumentado (Heinz y Chang,
2001): se agrega una fila de `delta` a los componentes y `delta` al pixel, y se
resuelve minimos cuadrados no negativos (`scipy.optimize.nnls`).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import nnls

from mineralmap.algorithms.base import Detector


class UnmixingDetector(Detector):
    """FCLS: proporcion de la firma de referencia en cada pixel."""

    higher_is_better = True
    bands = None

    def __init__(
        self,
        otros_componentes: np.ndarray,
        nombres: list[str] | None = None,
        delta: float = 10.0,
    ):
        """
        Parameters
        ----------
        otros_componentes:
            (n_componentes, n_bandas), alineados con las bandas del cubo. Una
            fila de ceros es el componente de sombra.
        """
        self.otros = np.atleast_2d(np.asarray(otros_componentes, dtype=np.float64))
        self.nombres = nombres
        self.delta = delta

    def fit(self, cube=None, reference=None) -> UnmixingDetector:
        """Sin entrenamiento: los componentes vienen fijados."""
        return self

    def proportions(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Proporciones (1 + n_otros, alto, ancho); la 0 es la referencia."""
        cube = np.asarray(cube, dtype=np.float64)
        reference = np.asarray(reference, dtype=np.float64)
        n, alto, ancho = cube.shape
        if reference.shape != (n,) or self.otros.shape[1] != n:
            raise ValueError(
                f"Cubo con {n} bandas, firma {reference.shape} y componentes "
                f"{self.otros.shape}: tienen que compartir las bandas."
            )
        E = np.vstack([reference, self.otros]).T  # (n_bandas, n_comp)
        A = np.vstack([self.delta * np.ones((1, E.shape[1])), E])
        X = cube.reshape(n, -1).T
        salida = np.full((X.shape[0], E.shape[1]), np.nan)
        for i in np.flatnonzero(np.all(np.isfinite(X), axis=1)):
            b = np.concatenate([[self.delta], X[i]])
            salida[i], _ = nnls(A, b)
        return salida.T.reshape(E.shape[1], alto, ancho)

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        return self.proportions(cube, reference)[0]
