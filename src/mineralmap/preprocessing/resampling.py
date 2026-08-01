"""Lleva todas las bandas de una Scene a una grilla comun (por defecto 20 m)."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.windows import from_bounds


def resampling_for(
    src_res_m: float, target_res_m: float, categorical: bool = False
) -> Resampling:
    """Elige el metodo de remuestreo segun las resoluciones de origen y destino.

    Parameters
    ----------
    src_res_m:
        Resolucion nativa de la banda, en metros (10, 20 o 60 en Sentinel-2).
    target_res_m:
        Resolucion de la grilla destino, en metros.
    categorical:
        True si la banda es una etiqueta (SCL) y no una medida continua.

    Returns
    -------
    Resampling
        - `nearest` siempre que `categorical` sea True: SCL es una etiqueta y
          promediar clases produce clases que no existen (el promedio de
          "agua" y "nube" no es "vegetacion", pero eso es lo que saldria).
        - `average` al submuestrear (10 -> 20 m): promediar los 4 pixeles que
          caen dentro conserva la radiometria mejor que quedarse con uno.
        - `bilinear` al sobremuestrear (60 -> 20 m): interpolar suaviza el
          bloque en vez de replicarlo en escalones.
        - `nearest` cuando las resoluciones coinciden: es la identidad, no
          tiene sentido interpolar.
    """
    if categorical:
        return Resampling.nearest
    if src_res_m < target_res_m:
        return Resampling.average
    if src_res_m > target_res_m:
        return Resampling.bilinear
    return Resampling.nearest


def read_band_on_grid(
    path: str,
    bounds: tuple[float, float, float, float],
    target_shape: tuple[int, int],
    resampling: Resampling = Resampling.bilinear,
    *,
    expected_crs: CRS | None = None,
) -> np.ndarray:
    """Lee una banda recortada a `bounds` y remuestreada a `target_shape`.

    El remuestreo se hace en la propia lectura: se traduce `bounds` a una
    ventana en la grilla nativa de la banda y se pide a GDAL que la entregue
    ya con la forma de la grilla destino. Es el mismo codigo para 10, 20 y
    60 m y no necesita `warp`.

    Premisa (valida dentro de un tile Sentinel-2 L2A): todas las bandas
    comparten CRS y origen de tile, y sus resoluciones son multiplos exactos
    entre si. Por eso alcanza con recortar por coordenadas y reescalar. Si esa
    premisa dejara de cumplirse -- p. ej. al combinar tiles o sensores
    distintos -- habria que reproyectar de verdad, y para eso esta
    `resample_to_common_grid`.

    Parameters
    ----------
    path:
        Ruta al archivo de la banda (.jp2 o cualquiera que lea rasterio).
    bounds:
        (left, bottom, right, top) en el CRS de la escena.
    target_shape:
        (alto, ancho) de la grilla destino, en pixeles.
    resampling:
        Metodo de remuestreo (ver `resampling_for`).
    expected_crs:
        Si se pasa, se verifica que el archivo este en ese CRS.

    Returns
    -------
    np.ndarray
        Banda con forma `target_shape` y el dtype nativo del archivo.

    Raises
    ------
    ValueError
        Si `expected_crs` no coincide con el CRS del archivo. Se falla en vez
        de leer igual, porque el recorte por coordenadas en el CRS equivocado
        no da error: da basura en silencio.
    """
    with rasterio.open(path) as src:
        if expected_crs is not None and src.crs != expected_crs:
            raise ValueError(
                f"{path} esta en {src.crs}, pero la escena usa {expected_crs}. "
                "Recortar por coordenadas entre CRS distintos produce un "
                "recorte incorrecto sin avisar; abortando."
            )

        ventana = from_bounds(*bounds, transform=src.transform)
        return src.read(
            1, window=ventana, out_shape=target_shape, resampling=resampling
        )


def resample_to_common_grid(scene, target_resolution_m: int = 20):
    """Lleva un `Scene` ya construido a otra resolucion. NO es el camino en uso.

    Hoy el remuestreo ocurre a nivel de archivo, dentro de
    `read_band_on_grid`: cada banda se lee directamente sobre la grilla
    destino, asi que el `Scene` nace ya homogeneo a 20 m y nunca existe un
    cubo con bandas de resoluciones mezcladas. Remuestrear despues seria
    interpolar dos veces.

    Esta funcion queda reservada para Nivel 2, cuando haya que combinar
    objetos `Scene` que vengan de grillas distintas (varios tiles, otra fecha
    u otro sensor) y ya no se pueda resolver en la lectura.

    # TODO Nivel 2
    """
    raise NotImplementedError
