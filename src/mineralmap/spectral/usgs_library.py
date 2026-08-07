"""Parser de archivos ASCIIdata de la libreria USGS splib07 -> firma espectral numpy."""

from __future__ import annotations

import numpy as np

# La libreria USGS marca los "no dato" con valores muy negativos (p. ej. -1.23e34).
NODATA_THRESHOLD = -1.0e30

N_BANDS_SENTINEL2_RAW = 13  # B1..B9, B10, B11, B12 (incluye B10, antes de descartarla)

# splib07 expresa las longitudes de onda en micrometros; el resto del proyecto
# trabaja en nanometros (config.BAND_WAVELENGTHS_NM). La conversion ocurre en
# un solo lugar, al leer, para que ningun consumidor tenga que acordarse de en
# que unidad venia el archivo.
MICRONS_TO_NM = 1000.0

# Rango plausible para una longitud de onda de Sentinel-2, en nm. No es una
# validacion fisica sino un control de unidades: si el archivo viniera ya en
# nanometros, multiplicar por 1000 daria valores del orden de 10^6 y el error
# pasaria inadvertido hasta que un grafico saliera vacio.
_RANGO_PLAUSIBLE_NM = (300.0, 2600.0)


def _leer_valores(path: str, n_esperados: int) -> np.ndarray:
    """Parsea un ASCIIdata de splib07: salta el encabezado y lee `n_esperados` valores.

    Es el formato comun de la libreria: primera linea de encabezado, y despues
    un numero por linea. Los "no dato" (muy negativos) se convierten a NaN.
    """
    with open(path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    _header, *data_lines = lines
    if len(data_lines) < n_esperados:
        raise ValueError(
            f"Se esperaban {n_esperados} valores en {path}, se encontraron "
            f"{len(data_lines)}."
        )

    values = np.array([float(v) for v in data_lines[:n_esperados]], dtype=float)
    values[values < NODATA_THRESHOLD] = np.nan
    return values


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
    return _leer_valores(path, N_BANDS_SENTINEL2_RAW)


def load_usgs_wavelengths(path: str) -> np.ndarray:
    """Lee el archivo de longitudes de onda de splib07 y las devuelve en nm.

    Es el companero de `load_usgs_rs_sentinel2`: mismo formato ASCIIdata
    (encabezado + un valor por linea), mismo manejo de "no dato", y las mismas
    13 posiciones en el mismo orden. Lo que este archivo aporta es el ancla:
    dice a que longitud de onda corresponde cada una de las 13 posiciones de la
    firma, y sin el, el orden de `_RAW_BAND_ORDER` es una suposicion.

    splib07 guarda las longitudes de onda en micrometros; se convierten a
    nanometros aca para que el resto del proyecto trabaje en una sola unidad.

    Parameters
    ----------
    path:
        Ruta al archivo de longitudes de onda del paquete rsSentinel2 de
        splib07.

    Returns
    -------
    np.ndarray
        Vector 1D de 13 longitudes de onda en nanometros, con NaN donde el
        dato original era "no dato".

    Raises
    ------
    ValueError
        Si el archivo trae menos de 13 valores, o si las longitudes de onda
        resultantes caen fuera del rango plausible de Sentinel-2 (control de
        unidades: atrapa un archivo que ya viniera en nanometros).
    """
    valores = _leer_valores(path, N_BANDS_SENTINEL2_RAW) * MICRONS_TO_NM

    finitos = valores[np.isfinite(valores)]
    minimo, maximo = _RANGO_PLAUSIBLE_NM
    if finitos.size and (finitos.min() < minimo or finitos.max() > maximo):
        raise ValueError(
            f"Las longitudes de onda de {path} quedaron en "
            f"[{finitos.min():.1f}, {finitos.max():.1f}] nm tras convertir de "
            f"micrometros, fuera del rango plausible "
            f"[{minimo:.0f}, {maximo:.0f}] nm. ¿El archivo ya venia en nm?"
        )

    return valores
