"""Construye el Scene de Track A desde un producto Sentinel-2 L2A (.SAFE).

Es el orquestador del preprocesamiento: localiza las bandas, las lleva todas a
la grilla de 20 m del AOI, las pasa a reflectancia y arma la mascara de
validez. Entrega el cubo y su mascara; no compara nada contra ninguna firma.

Vive en `preprocessing/` y no en `io/` porque el orden de capas del proyecto es
io (conoce disco) -> preprocessing (transforma) -> spectral/algorithms. Este
modulo necesita las tres funciones de transformacion, asi que ponerlo en `io/`
obligaria a que `io` importara `preprocessing` e invertiria la dependencia.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import warnings
from typing import Any

import numpy as np
import rasterio
from rasterio import windows
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from mineralmap.config import BAND_ORDER
from mineralmap.io.raster_io import Scene, find_band_file, find_safe_dir
from mineralmap.preprocessing.masking import (
    DEFAULT_INVALID_CLASSES,
    build_cloud_mask,
    mask_summary,
)
from mineralmap.preprocessing.reflectance import dn_to_reflectance, read_l2a_scaling
from mineralmap.preprocessing.resampling import read_band_on_grid, resampling_for

# AOI por defecto: ventana en la grilla de 20 m del tile. 2000x2000 px a 20 m
# son 40x40 km. Es la definicion autoritativa de la zona de estudio; el bbox en
# WGS84 de los configs es su equivalente informativo.
#
# Tiene que seguir a `configs/cerro_colorado_kaolinite.yaml`: un Scene
# construido sin config usa esta ventana, asi que si las dos divergen el
# proyecto produce dos zonas de estudio distintas segun por donde se entre, y
# ninguna de las dos falla.
DEFAULT_AOI_WINDOW = Window(col_off=2700, row_off=650, width=2000, height=2000)

# Grilla objetivo del proyecto. 20 m es la resolucion de las bandas SWIR
# (B11/B12), que son las que llevan la firma de la caolinita: subir a 10 m no
# agregaria informacion espectral, solo interpolacion.
TARGET_RESOLUTION_M = 20

# Banda usada para fijar la grilla de referencia (CRS + transform del tile).
# B2 existe siempre a 20 m en un producto L2A, independientemente de que
# bandas pida el llamador.
GRID_REFERENCE_BAND = "B2"

# Patron del nombre de una carpeta .SAFE, del que se extraen tile y fecha:
# S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE
_SAFE_NAME_RE = re.compile(
    r"^(?P<mision>S2[AB])_MSIL2A_(?P<sensado>\d{8}T\d{6})_"
    r"N(?P<baseline>\d+)_R(?P<orbita>\d+)_(?P<tile>T\w+?)_"
)


def _describir_safe(safe_dir: str) -> dict[str, str]:
    """Extrae tile y fecha de sensado del nombre de la carpeta .SAFE."""
    nombre = os.path.basename(str(safe_dir).rstrip("/\\"))
    coincidencia = _SAFE_NAME_RE.match(nombre)

    if coincidencia is None:
        # El nombre no sigue la convencion de ESA (carpeta renombrada a mano).
        # No es motivo para abortar: solo se pierde trazabilidad.
        warnings.warn(
            f"El nombre {nombre} no sigue la convencion de ESA; no puedo "
            "deducir tile ni fecha de sensado para meta.",
            stacklevel=2,
        )
        return {"safe_name": nombre, "tile_id": "", "sensing_date": ""}

    sensado = coincidencia.group("sensado")
    fecha = dt.datetime.strptime(sensado, "%Y%m%dT%H%M%S").isoformat()
    return {
        "safe_name": nombre,
        "tile_id": coincidencia.group("tile"),
        "sensing_date": fecha,
    }


def _resolver_ventana(
    aoi: Window | tuple[float, float, float, float] | None,
    src: rasterio.DatasetReader,
) -> Window:
    """Traduce el AOI pedido a una ventana entera dentro de la grilla del tile.

    `aoi` puede ser None (ventana por defecto), una `Window` ya expresada en la
    grilla de 20 m, o un bbox (min_lon, min_lat, max_lon, max_lat) en WGS84.
    """
    if aoi is None:
        ventana = DEFAULT_AOI_WINDOW
    elif isinstance(aoi, Window):
        ventana = aoi
    else:
        if len(aoi) != 4:
            raise ValueError(
                f"El AOI como bbox debe tener 4 valores "
                f"(min_lon, min_lat, max_lon, max_lat); recibi {aoi!r}."
            )
        # El bbox llega en lon/lat y el tile esta en UTM: hay que reproyectar
        # antes de convertirlo a ventana, o el recorte cae en cualquier parte.
        izq, abajo, der, arriba = transform_bounds("EPSG:4326", src.crs, *aoi)
        ventana = (
            from_bounds(izq, abajo, der, arriba, transform=src.transform)
            .round_offsets()
            .round_lengths()
        )

    tile = Window(col_off=0, row_off=0, width=src.width, height=src.height)

    if not windows.intersect(ventana, tile):
        raise ValueError(
            f"El AOI pedido {ventana} no intersecta el tile "
            f"({src.width}x{src.height} px a {TARGET_RESOLUTION_M} m)."
        )

    recortada = ventana.intersection(tile)
    if (recortada.width, recortada.height) != (ventana.width, ventana.height):
        warnings.warn(
            f"El AOI pedido {ventana} se sale del tile "
            f"({src.width}x{src.height} px); lo recorte a {recortada}.",
            stacklevel=2,
        )

    return recortada


def build_scene_from_safe(
    root: str = "data/raw/",
    band_names: list[str] = BAND_ORDER,
    aoi: Window | tuple[float, float, float, float] | None = None,
    invalid_scl_classes: list[int] | None = None,
    verbose: bool = True,
) -> Scene:
    """Construye un Scene de 20 m recortado al AOI desde el producto .SAFE.

    Parameters
    ----------
    root:
        Directorio donde buscar la carpeta .SAFE.
    band_names:
        Bandas a incluir, en el orden exacto en que quedaran en el cubo.
        Por defecto BAND_ORDER (las 12 bandas del contrato).
    aoi:
        Ventana en la grilla de 20 m, bbox (min_lon, min_lat, max_lon, max_lat)
        en WGS84, o None para usar DEFAULT_AOI_WINDOW.
    invalid_scl_classes:
        Clases SCL a descartar; None usa DEFAULT_INVALID_CLASSES.
    verbose:
        Si True, imprime una linea por banda con su resolucion nativa y el
        metodo de remuestreo aplicado.

    Returns
    -------
    Scene
        Cubo (n_bandas, alto, ancho) float32 en reflectancia SIN enmascarar,
        con la validez en `mask` y la trazabilidad en `meta`. El cubo se
        entrega sin enmascarar a proposito: aplicar la mascara es decision del
        pipeline, no del constructor (ver `masking.apply_mask`).

    Raises
    ------
    FileNotFoundError
        Si falta la carpeta .SAFE o alguna de las bandas pedidas.
    """
    band_names = list(band_names)
    clases_invalidas = (
        list(invalid_scl_classes)
        if invalid_scl_classes is not None
        else list(DEFAULT_INVALID_CLASSES)
    )

    safe_dir = find_safe_dir(root)
    baseline, offset, quantification = read_l2a_scaling(safe_dir)

    # Grilla de referencia: CRS y transform del tile completo a 20 m.
    ruta_referencia, _ = find_band_file(
        safe_dir, GRID_REFERENCE_BAND, prefer=(TARGET_RESOLUTION_M,)
    )
    with rasterio.open(ruta_referencia) as src:
        crs = src.crs
        transform_tile = src.transform
        ventana = _resolver_ventana(aoi, src)
        transform_aoi = src.window_transform(ventana)

    bounds = windows.bounds(ventana, transform_tile)
    target_shape = (int(ventana.height), int(ventana.width))

    if verbose:
        print(
            f"--- Scene desde {os.path.basename(safe_dir)} "
            f"(baseline {baseline}, offset {offset:+.0f}, "
            f"quantification {quantification:.0f}) ---"
        )

    capas: list[np.ndarray] = []
    bands_source: dict[str, int] = {}

    for banda in band_names:
        ruta, resolucion = find_band_file(safe_dir, banda)
        metodo = resampling_for(resolucion, TARGET_RESOLUTION_M, categorical=False)
        dn = read_band_on_grid(
            ruta, bounds, target_shape, resampling=metodo, expected_crs=crs
        )
        capas.append(
            dn_to_reflectance(
                dn,
                baseline=baseline,
                offset=offset,
                quantification=quantification,
            )
        )
        bands_source[banda] = resolucion
        if verbose:
            print(f"  {banda:<4} R{resolucion}m {metodo.name:<8} -> {target_shape}")

    cube = np.stack(capas, axis=0).astype(np.float32)

    # SCL siempre con nearest: es una etiqueta, interpolarla inventa clases.
    ruta_scl, resolucion_scl = find_band_file(safe_dir, "SCL")
    metodo_scl = resampling_for(resolucion_scl, TARGET_RESOLUTION_M, categorical=True)
    scl = read_band_on_grid(
        ruta_scl, bounds, target_shape, resampling=metodo_scl, expected_crs=crs
    )
    if verbose:
        print(f"  {'SCL':<4} R{resolucion_scl}m {metodo_scl.name:<8} -> {target_shape}")

    # Un pixel es valido si SCL lo aprueba Y si ninguna banda quedo sin dato
    # (nodata) tras el escalado. Lo segundo es lo que atrapa los bordes del
    # tile, donde SCL puede decir "suelo" pero la banda no tiene senal.
    mask_scl = build_cloud_mask(scl, clases_invalidas)
    mask_final = mask_scl & ~np.isnan(cube).any(axis=0)

    meta: dict[str, Any] = {
        **_describir_safe(safe_dir),
        "processing_baseline": baseline,
        "boa_offset": float(offset),
        "quantification": float(quantification),
        "aoi_window": [
            int(ventana.col_off),
            int(ventana.row_off),
            int(ventana.width),
            int(ventana.height),
        ],
        "bands_source": bands_source,
        "invalid_scl_classes": clases_invalidas,
        # Resumen de la composicion SCL del AOI: es el control de cordura del
        # preprocesamiento y viaja con el Scene para no tener que releer SCL.
        "scl_summary": mask_summary(scl, clases_invalidas),
        "created_at": dt.datetime.now().astimezone().isoformat(),
    }

    return Scene(
        cube=cube,
        band_names=band_names,
        transform=transform_aoi,
        crs=crs,
        mask=mask_final,
        meta=meta,
    )
