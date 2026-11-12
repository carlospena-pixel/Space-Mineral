"""Combinacion de mapas minerales en zonas de alteracion.

Los mapas de una zona pueden venir en unidades distintas (profundidad de banda
de EMIT L2B, mayor es mejor; angulo SAM, menor es mejor). Para juntarlos, cada
uno se lleva a su rango percentil entre los pixeles con dato, en su propia
direccion (0 = menos evidencia, 1 = mas), y la zona toma el maximo: basta una
pista fuerte para marcar el pixel.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import rankdata


def percentile_rank(mapa: np.ndarray, higher_is_better: bool) -> np.ndarray:
    """Rango percentil en (0, 1] de cada pixel con dato; NaN se conserva.

    Los empates reciben el rango promedio, asi que un mapa con muchos ceros
    no premia a ninguno de ellos sobre los demas.
    """
    salida = np.full(mapa.shape, np.nan, dtype=np.float32)
    ok = np.isfinite(mapa)
    if ok.any():
        v = mapa[ok] if higher_is_better else -mapa[ok]
        salida[ok] = rankdata(v, method="average") / ok.sum()
    return salida


def combine_zone(rangos: list[np.ndarray]) -> np.ndarray:
    """Maximo de los rangos disponibles por pixel; NaN si ninguno tiene dato."""
    pila = np.stack(rangos)
    con_dato = np.isfinite(pila).any(axis=0)
    salida = np.full(pila.shape[1:], np.nan, dtype=np.float32)
    salida[con_dato] = np.nanmax(pila[:, con_dato], axis=0)
    return salida
