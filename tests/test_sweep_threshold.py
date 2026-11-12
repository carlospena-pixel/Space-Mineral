"""Pruebas de la lectura de verdad de terreno en `scripts/sweep_threshold.py`.

Cubren el bug por el que el script binarizaba la verdad con ``> 0``: los
pixeles ambiguos (255) entraban como positivos. Los scripts no son un paquete,
asi que el modulo se carga desde su ruta.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from mineralmap.pipeline import DETECTORS

RUTA_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sweep_threshold.py"


@pytest.fixture(scope="module")
def sweep():
    spec = importlib.util.spec_from_file_location("sweep_threshold", RUTA_SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# Fila unica de seis pixeles. Los tres primeros caen bajo el umbral de 0,1 rad.
MAPA = np.array([[0.05, 0.05, 0.05, 0.30, 0.30, 0.30]])
VERDAD = np.array([[1, 1, 255, 0, 0, 255]], dtype=np.float32)


def _escribir_verdad(ruta, datos):
    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=datos.shape[0],
        width=datos.shape[1],
        count=1,
        dtype=datos.dtype,
        crs="EPSG:32719",
        transform=from_origin(460_000, 7_780_000, 20, 20),
    ) as dst:
        dst.write(datos, 1)
    return str(ruta)


def test_leer_verdad_no_convierte_los_ambiguos_en_positivos(sweep, tmp_path):
    ruta = _escribir_verdad(tmp_path / "verdad.tif", VERDAD)
    validos = np.ones(MAPA.shape, dtype=bool)

    positivos, validos_verdad = sweep._leer_verdad(ruta, MAPA.shape, validos)

    assert positivos.tolist() == [[True, True, False, False, False, False]]
    assert validos_verdad.tolist() == [[True, True, False, True, True, False]]


def test_leer_verdad_aborta_con_valores_que_no_son_clases(sweep, tmp_path):
    ruta = _escribir_verdad(
        tmp_path / "rara.tif", np.array([[0, 1, 7]], dtype=np.float32)
    )

    with pytest.raises(SystemExit):
        sweep._leer_verdad(ruta, (1, 3), np.ones((1, 3), dtype=bool))


def test_las_metricas_del_barrido_excluyen_los_ambiguos(sweep, tmp_path):
    ruta = _escribir_verdad(tmp_path / "verdad.tif", VERDAD)
    validos = np.ones(MAPA.shape, dtype=bool)
    positivos, validos_verdad = sweep._leer_verdad(ruta, MAPA.shape, validos)

    fila = sweep._fila_del_barrido(
        0.1, MAPA, validos, positivos, DETECTORS["sam"](), validos_verdad
    )

    # Con `> 0`, el ambiguo detectado (pixel 2) contaba como TP y el no
    # detectado (pixel 5) como FN: recall 3/4. Excluidos, la deteccion es exacta.
    assert fila["precision"] == 1.0
    assert fila["recall"] == 1.0
    assert fila["f1"] == 1.0
    # El porcentaje del AOI sigue contando contra todos los validos.
    assert fila["pixeles"] == 3
    assert fila["pct_aoi_valido"] == pytest.approx(50.0)
