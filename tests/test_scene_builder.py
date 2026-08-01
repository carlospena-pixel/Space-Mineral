"""Pruebas del constructor de Scene sobre la escena Sentinel-2 real.

Son los unicos tests del proyecto que necesitan el producto .SAFE descargado;
en una copia limpia del repo se omiten en vez de fallar.
"""

import glob

import numpy as np
import pytest
from rasterio.windows import Window

from mineralmap.config import BAND_ORDER
from mineralmap.io.raster_io import find_band_file, find_safe_dir
from mineralmap.preprocessing.scene_builder import build_scene_from_safe

pytestmark = pytest.mark.skipif(
    not glob.glob("data/raw/**/*.SAFE", recursive=True),
    reason="requiere la escena Sentinel-2 en data/raw/",
)

# Ventana chica: alcanza para validar el contrato sin leer 40x40 km.
VENTANA_PRUEBA = Window(col_off=1000, row_off=1000, width=64, height=64)


@pytest.fixture(scope="module")
def scene():
    """Scene de 12 bandas sobre una ventana de 64x64 px."""
    return build_scene_from_safe(aoi=VENTANA_PRUEBA, verbose=False)


def test_find_band_file_resuelve_la_resolucion_nativa_de_cada_banda():
    """B8 solo existe a 10 m y B9 solo a 60 m; el resto es nativo a 20 m."""
    safe_dir = find_safe_dir("data/raw/")

    assert find_band_file(safe_dir, "B8")[1] == 10
    assert find_band_file(safe_dir, "B9")[1] == 60
    for banda in ("B2", "B11", "B12", "SCL"):
        assert find_band_file(safe_dir, banda)[1] == 20


def test_scene_cumple_el_contrato_de_bandas_y_georreferenciacion(scene):
    """Cubo (12, 64, 64) float32, bandas en el orden del contrato, UTM 19S."""
    assert scene.cube.shape == (12, 64, 64)
    assert scene.cube.dtype == np.float32
    assert scene.band_names == BAND_ORDER
    assert scene.crs.to_epsg() == 32719

    assert scene.mask.shape == (64, 64)
    assert scene.mask.dtype == np.bool_

    assert scene.meta["tile_id"] == "T19KDT"
    assert scene.meta["processing_baseline"]
    assert scene.meta["aoi_window"] == [1000, 1000, 64, 64]
    assert scene.meta["bands_source"]["B8"] == 10
    assert scene.meta["bands_source"]["B9"] == 60


def test_todas_las_bandas_traen_senal_en_rango(scene):
    """Reflectancia en [0,1] o NaN, y ninguna banda constante cero.

    Una banda entera en cero es la firma de una lectura fallida silenciosa
    (ventana fuera del raster, resolucion equivocada), no de un dato real.
    """
    for indice, banda in enumerate(scene.band_names):
        capa = scene.cube[indice]
        finitos = capa[~np.isnan(capa)]

        assert finitos.size > 0, f"{banda} quedo enteramente NaN"
        assert finitos.min() >= 0.0, f"{banda} tiene reflectancia negativa"
        assert finitos.max() <= 1.0, f"{banda} tiene reflectancia > 1"
        assert np.any(finitos > 0.0), f"{banda} es constante cero"
