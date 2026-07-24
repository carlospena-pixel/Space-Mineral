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


def save_scene(scene: Scene, path: str) -> None:
    """Serializa un Scene completo a un unico archivo .npz.

    El cubo se guarda como float32 (la reflectancia [0,1] no necesita float64),
    la transform como sus 6 coeficientes afines, el CRS como WKT y la mascara
    como bool. Se puede recuperar un Scene equivalente con `load_scene`.
    """
    np.savez(
        path,
        cube=scene.cube.astype(np.float32),
        band_names=np.asarray(scene.band_names),
        # tuple(Affine) devuelve 9 valores (incluye la fila 0,0,1 implicita);
        # basta con los 6 coeficientes para reconstruirla.
        transform=np.asarray(tuple(scene.transform)[:6], dtype=np.float64),
        crs=scene.crs.to_wkt(),
        mask=np.asarray(scene.mask, dtype=bool),
    )


def load_scene(path: str) -> Scene:
    """Reconstruye un Scene equivalente al serializado con `save_scene`."""
    with np.load(path, allow_pickle=False) as data:
        cube = data["cube"].astype(np.float32)
        band_names = [str(b) for b in data["band_names"].tolist()]
        transform = Affine(*(float(v) for v in data["transform"].tolist()))
        crs = CRS.from_wkt(str(data["crs"].item()))
        mask = np.asarray(data["mask"], dtype=bool)

    return Scene(
        cube=cube,
        band_names=band_names,
        transform=transform,
        crs=crs,
        mask=mask,
    )
