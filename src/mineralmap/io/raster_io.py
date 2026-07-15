"""Lectura/escritura de rasters GeoTIFF y la clase Scene (cubo de bandas + metadatos geograficos)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Scene:
    """Cubo de bandas (bands, rows, cols) junto a su CRS, transform y nombres de banda."""

    data: np.ndarray
    crs: str
    transform: tuple
    band_names: list[str]


def read_scene(path: str) -> Scene:
    raise NotImplementedError


def write_geotiff(path: str, array: np.ndarray, scene: Scene) -> None:
    raise NotImplementedError
