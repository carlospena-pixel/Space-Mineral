"""Pruebas de la ortorrectificacion EMIT y del puntaje por profundidad de banda.

Todo sintetico: no necesita el netCDF descargado.
"""

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from mineralmap.io.emit import apply_glt, reproject_to_scene
from mineralmap.io.raster_io import Scene
from mineralmap.spectral.emit_scores import band_depth_score, resolve_library_ids


def test_apply_glt_usa_indices_1_based_y_columna_fila():
    datos = np.array([[10.0, 11.0], [20.0, 21.0]])
    # glt[..., 0] = columna, glt[..., 1] = fila, 1-based; 0 = sin dato.
    glt = np.array([[[2, 1], [1, 2]], [[0, 0], [2, 2]]])
    salida = apply_glt(datos, glt)
    assert salida[0, 0] == 11.0  # fila 1, columna 2
    assert salida[0, 1] == 20.0  # fila 2, columna 1
    assert np.isnan(salida[1, 0])
    assert salida[1, 1] == 21.0


def test_apply_glt_rechaza_formas_invalidas():
    with pytest.raises(ValueError):
        apply_glt(np.zeros((2, 2)), np.zeros((2, 2), dtype=int))


def test_puntaje_es_band_depth_en_el_conjunto_cero_fuera_y_nan_sin_dato():
    ids = np.array([[5.0, 7.0], [0.0, np.nan]])
    bd = np.array([[0.2, 0.3], [0.0, 0.1]])
    puntaje = band_depth_score(ids, bd, [5])
    assert puntaje[0, 0] == pytest.approx(0.2)
    assert puntaje[0, 1] == 0.0
    assert puntaje[1, 0] == 0.0
    assert np.isnan(puntaje[1, 1])


def test_puntaje_trata_el_fill_de_emit_como_sin_dato():
    puntaje = band_depth_score(np.array([[-9999.0]]), np.array([[-9999.0]]), [5])
    assert np.isnan(puntaje[0, 0])


def test_resolver_ids_usa_index_y_no_la_posicion():
    library = {
        "index": np.array([1, 96, 133]),
        "group": np.array([1, 2, 2]),
        "name": np.array(["a", "b", "kaolgrp_kaolinite_wxl"]),
    }
    assert resolve_library_ids(library, ["kaolgrp_kaolinite_wxl"], 2) == [133]


def test_resolver_ids_aborta_si_el_nombre_no_esta_en_el_grupo():
    library = {
        "index": np.array([1]),
        "group": np.array([1]),
        "name": np.array(["kaolgrp_kaolinite_wxl"]),
    }
    with pytest.raises(KeyError):
        resolve_library_ids(library, ["kaolgrp_kaolinite_wxl"], 2)


def test_reproyectar_a_la_misma_grilla_conserva_valores_y_nan():
    crs = CRS.from_epsg(32719)
    transform = Affine(20.0, 0.0, 453960.0, 0.0, -20.0, 7787040.0)
    datos = np.array([[1.0, np.nan], [3.0, 4.0]], dtype=np.float32)
    scene = Scene(
        cube=np.zeros((1, 2, 2)), band_names=["B1"], transform=transform,
        crs=crs, mask=np.ones((2, 2), dtype=bool),
    )
    salida = reproject_to_scene(datos, transform, crs, scene)
    np.testing.assert_array_equal(np.isnan(salida), np.isnan(datos))
    np.testing.assert_allclose(salida[~np.isnan(salida)], [1.0, 3.0, 4.0])
