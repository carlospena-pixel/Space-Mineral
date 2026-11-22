"""Remuestreo de una firma de laboratorio a las bandas de un sensor.

Cada banda se modela como una respuesta gaussiana centrada en su longitud de
onda central, con ancho a media altura (FWHM) dado:

    sigma = FWHM / (2 * sqrt(2 * ln 2))

El valor de la banda es el promedio de la firma pesado por esa gaussiana,
usando solo las muestras validas de la firma (la libreria USGS marca sin dato
con -1.23e34). Una banda sin muestras validas bajo su gaussiana sale NaN.
"""

from __future__ import annotations

import numpy as np

USGS_NODATA_LIMITE = -1e30


def load_splib_ascii(path: str) -> np.ndarray:
    """Lee un ASCIIdata de splib07 de cualquier largo (encabezado + un valor por
    linea). El "no dato" de USGS (-1.23e34) sale NaN.

    Sirve para firmas y para archivos de longitudes de onda de cualquier
    instrumento; `usgs_library.load_usgs_wavelengths` en cambio esta atado a
    las 13 posiciones de rsSentinel2.
    """
    valores = np.loadtxt(path, skiprows=1, dtype=np.float64, ndmin=1)
    valores[valores < USGS_NODATA_LIMITE] = np.nan
    return valores


def load_splib_signature(
    firma_path: str, lambdas_path: str
) -> tuple[np.ndarray, np.ndarray]:
    """Firma splib07b y sus longitudes de onda en nm.

    Raises
    ------
    ValueError
        Si firma y longitudes de onda no tienen el mismo numero de canales (son
        de instrumentos distintos), o si las longitudes de onda no parecen
        micrometros.
    """
    valores = load_splib_ascii(firma_path)
    lambdas_um = load_splib_ascii(lambdas_path)
    if valores.size != lambdas_um.size:
        raise ValueError(
            f"{firma_path} trae {valores.size} canales y {lambdas_path} "
            f"{lambdas_um.size}: son de instrumentos distintos."
        )
    if np.nanmax(lambdas_um) > 300:
        raise ValueError(f"{lambdas_path} no parece estar en micrometros.")
    return lambdas_um * 1000.0, valores


def resample_to_bands(
    lib_wavelengths_nm: np.ndarray,
    lib_values: np.ndarray,
    centers_nm: np.ndarray,
    fwhm_nm: np.ndarray,
    n_sigmas: float = 3.0,
) -> np.ndarray:
    """Firma (n_lib,) -> valores en las bandas (n_bandas,)."""
    wl = np.asarray(lib_wavelengths_nm, dtype=np.float64)
    v = np.asarray(lib_values, dtype=np.float64)
    centros = np.asarray(centers_nm, dtype=np.float64)
    fwhm = np.asarray(fwhm_nm, dtype=np.float64)
    if wl.shape != v.shape or centros.shape != fwhm.shape:
        raise ValueError("Longitudes de onda y valores, o centros y FWHM, no calzan.")
    if np.any(fwhm <= 0):
        raise ValueError("Todos los FWHM deben ser positivos.")

    valido = np.isfinite(wl) & np.isfinite(v) & (v > USGS_NODATA_LIMITE)
    wl, v = wl[valido], v[valido]
    sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    salida = np.full(centros.shape, np.nan)
    for i, (c, s) in enumerate(zip(centros, sigma)):
        cerca = np.abs(wl - c) <= n_sigmas * s
        if not cerca.any():
            continue
        w = np.exp(-0.5 * ((wl[cerca] - c) / s) ** 2)
        salida[i] = np.sum(w * v[cerca]) / np.sum(w)
    return salida
