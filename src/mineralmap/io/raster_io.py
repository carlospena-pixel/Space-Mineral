"""Lectura/escritura de rasters GeoTIFF y la clase Scene (cubo de bandas + metadatos geograficos)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from affine import Affine
from rasterio.crs import CRS


@dataclass
class Scene:
    """Escena Sentinel-2 preprocesada: cubo de bandas en reflectancia junto a
    su georreferenciacion y una mascara de pixeles validos.

    Es el objeto que produce `preprocessing/` y que consumen `spectral/` y
    `algorithms/`; no conoce formatos de archivo, solo datos en memoria.
    """

    cube: np.ndarray        # (n_bandas, alto, ancho), reflectancia [0,1]
    band_names: list[str]   # == BAND_ORDER
    transform: Affine
    crs: CRS
    mask: np.ndarray        # (alto, ancho) bool, True = pixel valido


def read_scene(path: str) -> Scene:
    raise NotImplementedError


def write_geotiff(path: str, array: np.ndarray, scene: Scene) -> None:
    raise NotImplementedError
