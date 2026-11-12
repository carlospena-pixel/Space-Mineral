"""Mapas de puntaje a partir de la identificacion de minerales de EMIT L2B.

El puntaje de un pixel para un conjunto de entradas de la biblioteca es su
profundidad de banda si el mineral identificado esta en el conjunto, 0 si el
pixel tiene dato pero otro mineral (o ninguno), y NaN si no hay dato. Mayor es
mejor.
"""

from __future__ import annotations

import numpy as np

EMIT_FILL = -9999


def resolve_library_ids(
    library: dict[str, np.ndarray], names: list[str], group: int
) -> list[int]:
    """Traduce `path_name` de la biblioteca a los `index` que usa mineral_id.

    Raises
    ------
    KeyError
        Si un nombre no existe en el grupo, o existe mas de una vez: un nombre
        ambiguo marcaria un mineral que nadie pidio.
    """
    en_grupo = library["group"] == group
    ids: list[int] = []
    for nombre in names:
        coincide = en_grupo & (library["name"] == nombre)
        n = int(coincide.sum())
        if n != 1:
            raise KeyError(
                f"'{nombre}' aparece {n} veces en el grupo {group} de la "
                f"biblioteca EMIT; se esperaba exactamente 1."
            )
        ids.append(int(library["index"][coincide][0]))
    return ids


def band_depth_score(
    mineral_id: np.ndarray, band_depth: np.ndarray, ids: list[int]
) -> np.ndarray:
    """Profundidad de banda donde el mineral esta en `ids`, 0 si no, NaN sin dato.

    Sin dato es mineral_id o band_depth NaN o igual a EMIT_FILL.
    """
    if mineral_id.shape != band_depth.shape:
        raise ValueError(
            f"mineral_id {mineral_id.shape} y band_depth {band_depth.shape} "
            f"no tienen la misma forma."
        )
    mid = mineral_id.astype(np.float64)
    bd = band_depth.astype(np.float64)
    sin_dato = np.isnan(mid) | np.isnan(bd) | (mid == EMIT_FILL) | (bd == EMIT_FILL)
    en_conjunto = np.isin(mid, np.asarray(ids, dtype=np.float64))
    puntaje = np.where(en_conjunto, bd, 0.0)
    return np.where(sin_dato, np.nan, puntaje).astype(np.float32)
