"""Parser de archivos ASCIIdata de la libreria USGS splib07 -> firma espectral numpy."""

from __future__ import annotations

import numpy as np

# La libreria USGS marca los "no dato" con valores muy negativos (p. ej. -1.23e34).
NODATA_THRESHOLD = -1.0e30

N_BANDS_SENTINEL2_RAW = 13  # B1..B9, B10, B11, B12 (incluye B10, antes de descartarla)


def load_usgs_rs_sentinel2(path: str) -> np.ndarray:
    """Lee un archivo de resampling a Sentinel-2 de la libreria USGS splib07.

    El archivo es texto plano: la primera linea es un encabezado
    ("S07SNTL2 Record=...") que se ignora, y las 13 lineas siguientes traen
    un valor de reflectancia por banda, en el orden
    B1, B2, B3, B4, B5, B6, B7, B8, B8A, B9, B10, B11, B12 (incluye B10, que
    se descarta mas adelante ya que no existe en el producto L2A). Los
    valores "no dato" (muy negativos, p. ej. -1.23e34) se convierten a NaN.

    Parameters
    ----------
    path:
        Ruta al archivo .txt de la libreria USGS (formato S07SNTL2).

    Returns
    -------
    np.ndarray
        Vector 1D de 13 valores de reflectancia, en el orden descrito arriba,
        con NaN donde el dato original era "no dato".
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    _header, *data_lines = lines
    if len(data_lines) < N_BANDS_SENTINEL2_RAW:
        raise ValueError(
            f"Se esperaban {N_BANDS_SENTINEL2_RAW} valores de reflectancia en "
            f"{path}, se encontraron {len(data_lines)}."
        )

    values = np.array(
        [float(v) for v in data_lines[:N_BANDS_SENTINEL2_RAW]], dtype=float
    )
    values[values < NODATA_THRESHOLD] = np.nan
    return values
