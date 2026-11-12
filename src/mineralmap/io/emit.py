"""Lectura de productos EMIT L2B (netCDF), ortorrectificacion y alineacion.

EMIT entrega sus mapas en la geometria del sensor (filas = downtrack,
columnas = crosstrack), sin ortorrectificar. Cada archivo trae una tabla de
geometria (GLT, `location/glt_x` y `location/glt_y`) que dice, para cada pixel
de una grilla regular en WGS84, de que pixel del sensor sale su valor.

`apply_glt` reproduce la funcion homonima de `emit_tools.py` de
nasa/EMIT-Data-Resources: GLT con indices 1-based y 0 como "sin dato". Se
reimplementa en vez de importar ese modulo porque arrastra dependencias
(spectral, scikit-image, rioxarray, netCDF4, s3fs) que el proyecto no usa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import h5py
import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.warp import Resampling, reproject

from mineralmap.io.raster_io import Scene

EMIT_FILL = -9999
GLT_NODATA = 0


@dataclass
class EmitL2BMin:
    """Contenido de un EMIT_L2B_MIN_*.nc en la geometria del sensor."""

    mineral_id: dict[int, np.ndarray]  # grupo -> (downtrack, crosstrack) int
    band_depth: dict[int, np.ndarray]  # grupo -> (downtrack, crosstrack) float
    glt: np.ndarray  # (alto, ancho, 2): [..., 0] = columna, [..., 1] = fila
    transform: Affine  # de la grilla de la GLT (esquina superior izquierda)
    crs: CRS
    library: dict[str, np.ndarray] = field(default_factory=dict)
    attrs: dict[str, str] = field(default_factory=dict)


def _texto(valores) -> np.ndarray:
    return np.array([v.decode() if isinstance(v, bytes) else str(v) for v in valores])


def read_emit_l2b_min(path: str) -> EmitL2BMin:
    """Lee mineral_id, band_depth, GLT y biblioteca de un EMIT_L2B_MIN_*.nc.

    Raises
    ------
    ValueError
        Si el archivo no trae `geotransform` o la GLT no tiene la forma esperada.
    """
    with h5py.File(path, "r") as f:
        if "geotransform" not in f.attrs:
            raise ValueError(f"{path} no trae el atributo global 'geotransform'.")
        gt = [float(v) for v in f.attrs["geotransform"]]
        crs = CRS.from_wkt(_texto([f.attrs["spatial_ref"]])[0])

        grupos = sorted(
            int(k.split("_")[1]) for k in f.keys() if k.endswith("_mineral_id")
        )
        mineral_id = {g: f[f"group_{g}_mineral_id"][:] for g in grupos}
        band_depth = {g: f[f"group_{g}_band_depth"][:] for g in grupos}

        glt = np.stack([f["location/glt_x"][:], f["location/glt_y"][:]], axis=-1)

        meta = f["mineral_metadata"]
        library = {
            "index": meta["index"][:].astype(int),
            "group": meta["group"][:].astype(int),
            "name": _texto(meta["name"][:]),
            "sample_name": _texto(meta["sample_name"][:]),
        }
        attrs = {
            k: _texto([f.attrs[k]])[0]
            for k in ("product_version", "flight_line", "time_coverage_start", "title")
            if k in f.attrs
        }

    return EmitL2BMin(
        mineral_id=mineral_id,
        band_depth=band_depth,
        glt=glt,
        transform=Affine.from_gdal(*gt),
        crs=crs,
        library=library,
        attrs=attrs,
    )


@dataclass
class EmitL2ARfl:
    """Metadatos de un EMIT_L2A_RFL_*.nc; la reflectancia se lee por trozos."""

    path: str
    shape: tuple[int, int, int]  # (downtrack, crosstrack, bandas)
    wavelengths: np.ndarray  # nm
    fwhm: np.ndarray  # nm
    good: np.ndarray  # bool: False en las absorciones de agua y bandas malas
    glt: np.ndarray
    transform: Affine
    crs: CRS


def read_emit_l2a_meta(path: str) -> EmitL2ARfl:
    """Lee longitudes de onda, FWHM, bandas buenas, GLT y georreferencia."""
    with h5py.File(path, "r") as f:
        sbp = f["sensor_band_parameters"]
        return EmitL2ARfl(
            path=path,
            shape=tuple(f["reflectance"].shape),
            wavelengths=sbp["wavelengths"][:].astype(np.float64),
            fwhm=sbp["fwhm"][:].astype(np.float64),
            good=sbp["good_wavelengths"][:] == 1,
            glt=np.stack([f["location/glt_x"][:], f["location/glt_y"][:]], axis=-1),
            transform=Affine.from_gdal(*[float(v) for v in f.attrs["geotransform"]]),
            crs=CRS.from_wkt(_texto([f.attrs["spatial_ref"]])[0]),
        )


def iter_reflectance(path: str, bands: np.ndarray, filas_por_trozo: int = 128):
    """Recorre la reflectancia por trozos de filas del sensor.

    Devuelve (fila_inicio, fila_fin, cubo) con el cubo en forma
    (n_bandas, filas, columnas), solo las `bands` pedidas (mascara booleana), y
    NaN donde el producto trae su fill (-9999). Un trozo de 128 filas pesa
    ~180 MB en float32: el cubo entero (1,8 GB) nunca se carga.
    """
    with h5py.File(path, "r") as f:
        ds = f["reflectance"]
        for r0 in range(0, ds.shape[0], filas_por_trozo):
            r1 = min(r0 + filas_por_trozo, ds.shape[0])
            trozo = ds[r0:r1, :, :][:, :, bands].astype(np.float32)
            trozo[trozo == EMIT_FILL] = np.nan
            yield r0, r1, np.transpose(trozo, (2, 0, 1))


def apply_glt(
    array: np.ndarray, glt: np.ndarray, fill_value: float = np.nan
) -> np.ndarray:
    """Lleva un arreglo 2D de la geometria del sensor a la grilla de la GLT.

    Parameters
    ----------
    array:
        (downtrack, crosstrack).
    glt:
        (alto, ancho, 2) con indices 1-based; [..., 0] es la columna y
        [..., 1] la fila del pixel de origen. 0 en cualquiera = sin dato.
    fill_value:
        Valor para los pixeles sin dato de la GLT.

    Returns
    -------
    np.ndarray
        (alto, ancho) float32.
    """
    if array.ndim != 2 or glt.ndim != 3 or glt.shape[-1] != 2:
        raise ValueError(
            f"apply_glt espera array 2D y glt (alto, ancho, 2); recibi "
            f"{array.shape} y {glt.shape}."
        )
    salida = np.full(glt.shape[:2], fill_value, dtype=np.float32)
    validos = np.all(glt != GLT_NODATA, axis=-1)
    columnas = glt[..., 0][validos] - 1
    filas = glt[..., 1][validos] - 1
    salida[validos] = array[filas, columnas]
    return salida


def reproject_to_scene(
    array: np.ndarray, src_transform: Affine, src_crs: CRS, scene: Scene
) -> np.ndarray:
    """Reproyecta un mapa a la grilla exacta del Scene (vecino mas cercano).

    Vecino mas cercano y no bilineal: el puntaje sale de una identificacion
    categorica (que mineral calzo), y promediar puntajes de pixeles vecinos
    inventaria valores intermedios que ningun pixel de EMIT tuvo. NaN es el
    sin dato en origen y destino.
    """
    alto, ancho = scene.mask.shape
    destino = np.full((alto, ancho), np.nan, dtype=np.float32)
    reproject(
        source=array.astype(np.float32),
        destination=destino,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=np.nan,
        dst_transform=scene.transform,
        dst_crs=scene.crs,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    return destino
