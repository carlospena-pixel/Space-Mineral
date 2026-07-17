"""Spectral Angle Mapper (SAM): deteccion por angulo espectral entre cada pixel
y una firma de referencia.
"""

from __future__ import annotations

import numpy as np

from mineralmap.algorithms.base import Detector


class SAM(Detector):
    """Detector basado en el angulo espectral (Spectral Angle Mapper).

    Mide la similitud entre cada pixel del cubo y una firma de referencia
    como el angulo entre ambos vectores en el espacio de bandas. Al depender
    solo de la direccion del vector (no de su magnitud), es invariante a
    variaciones de iluminacion/albedo.
    """

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Calcula el mapa de angulo espectral entre `cube` y `reference`.

        Parameters
        ----------
        cube:
            Cubo de reflectancia de la escena, forma (n_bandas, alto, ancho).
        reference:
            Firma espectral de referencia del mineral objetivo, forma (n_bandas,).

        Returns
        -------
        np.ndarray
            Mapa de angulo espectral en radianes, forma (alto, ancho). Los
            pixeles invalidos (NaN en `cube`) devuelven NaN.
        """
        reference = np.asarray(reference, dtype=np.float64)

        producto_punto = np.einsum("bhw,b->hw", cube, reference)
        norma_pixel = np.linalg.norm(cube, axis=0)
        norma_referencia = np.linalg.norm(reference)

        with np.errstate(invalid="ignore", divide="ignore"):
            coseno = producto_punto / (norma_pixel * norma_referencia)
        coseno = np.clip(coseno, -1.0, 1.0)

        return np.arccos(coseno)


def threshold(angle_map: np.ndarray, max_angle: float) -> np.ndarray:
    """Genera una mascara booleana de deteccion a partir del mapa de angulos.

    Parameters
    ----------
    angle_map:
        Mapa de angulo espectral en radianes, forma (alto, ancho).
    max_angle:
        Angulo maximo (en radianes) por debajo del cual se considera deteccion.

    Returns
    -------
    np.ndarray
        Mascara booleana, forma (alto, ancho): True donde angle_map <= max_angle.
    """
    return angle_map <= max_angle
