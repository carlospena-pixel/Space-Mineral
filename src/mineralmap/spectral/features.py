"""Entradas para los modelos: bandas de reflectancia mas indices espectrales.

Los indices de hierro se justifican por la fisica de la absorcion, no por una
referencia verificada:

- `ferric_iron_ratio` = B4/B2 (rojo/azul). El Fe3+ absorbe fuerte en el azul
  por transferencia de carga y refleja en el rojo.
- `ferric_oxide_swir_ratio` = B11/B8A. La absorcion de campo cristalino del
  Fe3+ cerca de 0,9 um baja B8A; B11 queda fuera de ella.

El indice de hidroxilos con Sentinel-2 usa las mismas bandas que el clay ratio
(B11/B12, absorcion Al-OH ~2,2 um en B12), asi que no se duplica.
"""

from __future__ import annotations

import numpy as np

from mineralmap.spectral.indices import clay_ratio


def _cociente(
    cube: np.ndarray, band_names: list[str], numerador: str, denominador: str
) -> np.ndarray:
    faltan = [b for b in (numerador, denominador) if b not in band_names]
    if faltan:
        raise ValueError(f"El indice {numerador}/{denominador} necesita {faltan}.")
    num = cube[band_names.index(numerador)].astype(np.float64)
    den = cube[band_names.index(denominador)].astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / den
    return np.where(np.isfinite(r), r, np.nan)


def ferric_iron_ratio(cube: np.ndarray, band_names: list[str]) -> np.ndarray:
    """B4/B2: sube con oxidos de hierro ferrico."""
    return _cociente(cube, band_names, "B4", "B2")


def ferric_oxide_swir_ratio(cube: np.ndarray, band_names: list[str]) -> np.ndarray:
    """B11/B8A: sube con la absorcion del Fe3+ cerca de 0,9 um."""
    return _cociente(cube, band_names, "B11", "B8A")


INDICES = {
    "clay_ratio_b11_b12": clay_ratio,
    "ferric_iron_b4_b2": ferric_iron_ratio,
    "ferric_oxide_b11_b8a": ferric_oxide_swir_ratio,
}


def build_feature_stack(
    cube: np.ndarray, band_names: list[str]
) -> tuple[np.ndarray, list[str]]:
    """Apila las bandas y los indices: forma (n_entradas, alto, ancho).

    Un pixel queda NaN en todas las entradas si alguna no es finita, para que
    "sin dato" signifique lo mismo en todas.
    """
    capas = [cube[i].astype(np.float32) for i in range(cube.shape[0])]
    nombres = list(band_names)
    for nombre, funcion in INDICES.items():
        capas.append(funcion(cube, list(band_names)).astype(np.float32))
        nombres.append(nombre)
    pila = np.stack(capas)
    invalido = ~np.all(np.isfinite(pila), axis=0)
    pila[:, invalido] = np.nan
    return pila, nombres
