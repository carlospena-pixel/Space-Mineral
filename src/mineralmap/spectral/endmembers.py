"""Registro de minerales objetivo y sus firmas espectrales de referencia."""

from __future__ import annotations

import numpy as np

from mineralmap.config import BAND_ORDER

ENDMEMBERS = {
    "kaolinite": {"usgs_sample_id": "KGa-1"},
    # "alunite": {"usgs_sample_id": "..."},
    # "hematite": {"usgs_sample_id": "..."},
}


def get_reference_spectrum(
    mineral: str, band_order: list[str] = BAND_ORDER
) -> np.ndarray:
    """Firma espectral de referencia de `mineral`, remuestreada a `band_order`.

    Busca la muestra USGS asociada a `mineral` en ENDMEMBERS, la convoluciona
    con las funciones de respuesta espectral de Sentinel-2 y devuelve el
    vector de reflectancia resultante en el orden de bandas indicado.

    Parameters
    ----------
    mineral:
        Nombre del mineral objetivo (clave de ENDMEMBERS), p. ej. "kaolinite".
    band_order:
        Orden de bandas Sentinel-2 en el que debe devolverse la firma.
        Por defecto, BAND_ORDER.

    Returns
    -------
    np.ndarray
        Vector 1D de reflectancia de largo len(band_order), alineado
        posicionalmente con band_order.
    """
    raise NotImplementedError
