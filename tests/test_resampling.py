"""Pruebas del remuestreo por lectura: read_band_on_grid y resampling_for.

Los rasters son sinteticos y se escriben en tmp_path: estos tests no dependen
de que la escena Sentinel-2 este descargada.
"""

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling

from mineralmap.preprocessing.resampling import read_band_on_grid, resampling_for

# Esquina superior izquierda comun a todos los rasters de prueba, en UTM 19S.
ORIGEN_E = 300000.0
ORIGEN_N = 6000000.0
CRS_ESCENA = CRS.from_epsg(32719)


def _escribir_raster(ruta, datos, resolucion_m, crs=CRS_ESCENA):
    """Escribe un GeoTIFF de una banda con origen conocido y devuelve la ruta."""
    alto, ancho = datos.shape
    transform = Affine(resolucion_m, 0.0, ORIGEN_E, 0.0, -resolucion_m, ORIGEN_N)

    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=alto,
        width=ancho,
        count=1,
        dtype=datos.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(datos, 1)

    return str(ruta)


def test_submuestreo_de_10m_a_20m_promedia_el_bloque(tmp_path):
    """Un bloque 2x2 de [10,20,30,40] a 10 m da 25 en la celda de 20 m."""
    datos = np.array(
        [
            [10.0, 20.0, 1.0, 1.0],
            [30.0, 40.0, 1.0, 1.0],
            [7.0, 7.0, 7.0, 7.0],
            [7.0, 7.0, 7.0, 7.0],
        ],
        dtype=np.float32,
    )
    ruta = _escribir_raster(tmp_path / "b10m.tif", datos, resolucion_m=10)

    # Celda de 20 m que cubre exactamente el bloque 2x2 superior izquierdo.
    bounds = (ORIGEN_E, ORIGEN_N - 20.0, ORIGEN_E + 20.0, ORIGEN_N)
    salida = read_band_on_grid(
        ruta, bounds, (1, 1), resampling=Resampling.average, expected_crs=CRS_ESCENA
    )

    assert salida.shape == (1, 1)
    assert salida[0, 0] == pytest.approx(25.0)


def test_sobremuestreo_de_60m_a_20m_conserva_forma_y_valor(tmp_path):
    """Una banda de 60 m constante leida a 20 m sigue siendo constante."""
    datos = np.full((4, 4), 1234.0, dtype=np.float32)
    ruta = _escribir_raster(tmp_path / "b60m.tif", datos, resolucion_m=60)

    # 2x2 celdas de 60 m = 120x120 m = 6x6 celdas de 20 m.
    bounds = (ORIGEN_E, ORIGEN_N - 120.0, ORIGEN_E + 120.0, ORIGEN_N)
    salida = read_band_on_grid(
        ruta, bounds, (6, 6), resampling=Resampling.bilinear, expected_crs=CRS_ESCENA
    )

    assert salida.shape == (6, 6)
    assert np.allclose(salida, 1234.0)


def test_lectura_a_la_misma_resolucion_es_la_identidad(tmp_path):
    """A 20 m sobre grilla de 20 m no se interpola nada: valores identicos."""
    datos = np.arange(64, dtype=np.float32).reshape(8, 8)
    ruta = _escribir_raster(tmp_path / "b20m.tif", datos, resolucion_m=20)

    # Ventana de filas 2..5 y columnas 3..6 en la grilla de 20 m.
    bounds = (
        ORIGEN_E + 3 * 20.0,
        ORIGEN_N - 6 * 20.0,
        ORIGEN_E + 7 * 20.0,
        ORIGEN_N - 2 * 20.0,
    )
    salida = read_band_on_grid(
        ruta, bounds, (4, 4), resampling=Resampling.nearest, expected_crs=CRS_ESCENA
    )

    assert np.array_equal(salida, datos[2:6, 3:7])


def test_resampling_for_elige_el_metodo_segun_la_escala():
    """Categorico siempre nearest; promedio al bajar, bilineal al subir."""
    # SCL es una etiqueta: promediar clases inventaria clases inexistentes.
    assert resampling_for(10, 20, categorical=True) is Resampling.nearest
    assert resampling_for(60, 20, categorical=True) is Resampling.nearest
    assert resampling_for(20, 20, categorical=True) is Resampling.nearest

    assert resampling_for(10, 20) is Resampling.average
    assert resampling_for(60, 20) is Resampling.bilinear
    assert resampling_for(20, 20) is Resampling.nearest


def test_crs_distinto_al_esperado_lanza_valueerror(tmp_path):
    """Recortar por coordenadas en otro CRS daria basura: hay que abortar."""
    datos = np.ones((4, 4), dtype=np.float32)
    ruta = _escribir_raster(
        tmp_path / "otro_crs.tif", datos, resolucion_m=20, crs=CRS.from_epsg(32718)
    )

    bounds = (ORIGEN_E, ORIGEN_N - 40.0, ORIGEN_E + 40.0, ORIGEN_N)
    with pytest.raises(ValueError, match="EPSG:32719"):
        read_band_on_grid(ruta, bounds, (2, 2), expected_crs=CRS_ESCENA)
