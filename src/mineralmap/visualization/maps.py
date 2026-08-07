"""Heatmaps georreferenciados y overlays sobre la escena base."""

from __future__ import annotations

import numpy as np

from mineralmap.io.raster_io import Scene

# Percentiles del realce de contraste. Una escena de desierto ocupa una franja
# estrecha del rango [0,1], asi que mostrarla sin estirar la deja casi negra.
P_LOW_DEFAULT = 2
P_HIGH_DEFAULT = 98

# Bandas del compuesto en color verdadero, en orden R, G, B.
TRUE_COLOR_BANDS = ("B4", "B3", "B2")


def percentile_stretch(
    band: np.ndarray, p_low: int = P_LOW_DEFAULT, p_high: int = P_HIGH_DEFAULT
) -> np.ndarray:
    """Recorta una banda a sus percentiles [p_low, p_high] y la reescala a [0,1].

    Los percentiles se calculan ignorando los NaN. Es lo que permite realzar un
    cubo ya enmascarado: con `np.percentile`, un solo pixel invalido devuelve
    NaN como percentil y la imagen entera sale negra, sin ningun error de por
    medio.

    Parameters
    ----------
    band:
        Capa 2D de reflectancia. Puede traer NaN.
    p_low, p_high:
        Percentiles inferior y superior del recorte.

    Returns
    -------
    np.ndarray
        Capa reescalada a [0,1], con los NaN preservados. Si la banda es
        constante (o entera NaN) devuelve ceros: no hay contraste que estirar.
    """
    capa = np.asarray(band, dtype=float)

    if not np.any(np.isfinite(capa)):
        return np.zeros_like(capa)

    lo, hi = np.nanpercentile(capa, (p_low, p_high))
    if hi <= lo:
        return np.zeros_like(capa)

    return np.clip((capa - lo) / (hi - lo), 0, 1)


def rgb_composite(
    scene: Scene,
    bands: tuple[str, str, str] = TRUE_COLOR_BANDS,
    p_low: int = P_LOW_DEFAULT,
    p_high: int = P_HIGH_DEFAULT,
) -> np.ndarray:
    """Arma un compuesto RGB del AOI con realce por percentiles banda a banda.

    Cada banda se estira por separado: es un balance de blancos implicito, y sin
    el, el compuesto de una escena arida sale con dominante amarilla porque B4
    es sistematicamente mas brillante que B2 sobre suelo desnudo.

    Las bandas se buscan por nombre y no por indice. Es la unica capa del
    proyecto que lo hace (ver `docs/es/decisiones_tecnicas.md`, seccion 1.1):
    el resto trabaja posicionalmente, pero un compuesto en color tiene que
    saber cual banda es el rojo.

    Parameters
    ----------
    scene:
        Scene con el cubo y sus `band_names`. Sirve tanto el cubo crudo como
        uno ya enmascarado con `apply_mask`.
    bands:
        Nombres canonicos de las bandas a usar como R, G y B.
    p_low, p_high:
        Percentiles del realce, pasados a `percentile_stretch`.

    Returns
    -------
    np.ndarray
        Arreglo (alto, ancho, 3) en [0,1], listo para `imshow`.

    Raises
    ------
    ValueError
        Si alguna de las bandas pedidas no esta en el Scene.
    """
    faltantes = [banda for banda in bands if banda not in scene.band_names]
    if faltantes:
        raise ValueError(
            f"Las bandas {faltantes} no estan en el Scene "
            f"(band_names={scene.band_names})."
        )

    return np.dstack(
        [
            percentile_stretch(scene.cube[scene.band_names.index(banda)], p_low, p_high)
            for banda in bands
        ]
    )


def plot_score_map(score_map, scene, title: str = ""):
    raise NotImplementedError
