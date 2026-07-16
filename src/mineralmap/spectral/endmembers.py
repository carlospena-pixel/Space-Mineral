"""Registro de minerales objetivo y sus firmas espectrales de referencia."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mineralmap.config import BAND_ORDER
from mineralmap.spectral.usgs_library import load_usgs_rs_sentinel2

# Orden en que load_usgs_rs_sentinel2 devuelve las 13 bandas (incluye B10).
_RAW_BAND_ORDER = [
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B10", "B11", "B12",
]

# Raiz del repositorio: src/mineralmap/spectral/endmembers.py -> repo_root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

ENDMEMBERS = {
    "kaolinite": {
        "usgs_sample_id": "KGa-1",
        "usgs_file": "S07SNTL2_Kaolinite_CM9_BECKb_AREF.txt",
    },
    # "alunite": {"usgs_sample_id": "..."},
    # "hematite": {"usgs_sample_id": "..."},
}


def get_reference_spectrum(
    mineral: str, band_order: list[str] = BAND_ORDER
) -> np.ndarray:
    """Firma espectral de referencia de `mineral`, remuestreada a `band_order`.

    Busca el archivo USGS asociado a `mineral` en ENDMEMBERS (bajo
    data/external/), lo carga con load_usgs_rs_sentinel2, descarta la banda
    B10 (no existe en el producto L2A) y reordena los 12 valores restantes
    segun `band_order`.

    Parameters
    ----------
    mineral:
        Nombre del mineral objetivo (clave de ENDMEMBERS), p. ej. "kaolinite".
    band_order:
        Orden de bandas Sentinel-2 en el que debe devolverse la firma.
        Por defecto, BAND_ORDER (12 bandas, sin B10).

    Returns
    -------
    np.ndarray
        Vector 1D de reflectancia de largo len(band_order), alineado
        posicionalmente con band_order.
    """
    if mineral not in ENDMEMBERS:
        raise KeyError(f"No hay firma USGS registrada para el mineral '{mineral}'.")

    usgs_path = _REPO_ROOT / "data" / "external" / ENDMEMBERS[mineral]["usgs_file"]
    raw_values = load_usgs_rs_sentinel2(str(usgs_path))

    raw_by_band = dict(zip(_RAW_BAND_ORDER, raw_values))
    raw_by_band.pop("B10", None)  # B10 no viene en L2A.

    spectrum = np.array([raw_by_band[band] for band in band_order], dtype=float)

    if len(spectrum) != len(band_order):
        raise ValueError(
            f"La firma resultante tiene {len(spectrum)} valores, se esperaban "
            f"{len(band_order)} (largo de band_order)."
        )

    return spectrum
