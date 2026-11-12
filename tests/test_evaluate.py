"""Pruebas de punta a punta de `scripts/evaluate.py`.

Arman dos GeoTIFF diminutos (50x50 px de 20 m en EPSG:32719) en un directorio
temporal y corren el CLI como subproceso, igual que lo correria una persona.
Los porfidos del fixture son **sinteticos**: salen de centros de pixel de esta
grilla inventada, convertidos a lat/lon. No son coordenadas de ningun deposito
real.

El mapa imita al de SAM (menor es mejor): 0,05 rad en las filas 0-9, que la
verdad marca como positivo, y 0,30 rad en el resto, mas un ruido chico.
"""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin, xy
from rasterio.warp import transform as reproyectar

from mineralmap.validation.evaluation import (
    AlignmentError,
    check_alignment,
    decode_truth,
    lonlat_to_rowcol,
    read_band,
    resolve_direction,
)

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "evaluate.py"

CRS_UTM = CRS.from_epsg(32719)
TRANSFORM = from_origin(460_000.0, 7_780_000.0, 20.0, 20.0)
FORMA = (50, 50)

CLAVES_RAIZ = {
    "inputs",
    "git",
    "grid",
    "higher_is_better",
    "direction_source",
    "warnings",
    "threshold",
    "seed",
    "pixel",
    "capture",
    "blocks",
}


def _escribir_tif(ruta, datos, transform=TRANSFORM, crs=CRS_UTM, descripcion=None):
    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=datos.shape[0],
        width=datos.shape[1],
        count=1,
        dtype=datos.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(datos, 1)
        if descripcion:
            dst.set_band_description(1, descripcion)
    return str(ruta)


def _puntaje() -> np.ndarray:
    rng = np.random.default_rng(0)
    mapa = 0.30 + 0.01 * rng.random(FORMA)
    mapa[:10, :] = 0.05 + 0.01 * rng.random((10, 50))
    mapa[20, 20] = np.nan
    return mapa.astype(np.float32)


def _verdad() -> np.ndarray:
    # float32 como la escribe `write_geotiff`, con las tres clases de geology.
    verdad = np.zeros(FORMA, dtype=np.float32)
    verdad[:10, :] = 1
    verdad[40:, :] = 255
    return verdad


def _centro_lonlat(fila: int, columna: int) -> tuple[float, float]:
    x, y = xy(TRANSFORM, fila, columna, offset="center")
    lon, lat = reproyectar(CRS_UTM, CRS.from_epsg(4326), [x], [y])
    return lon[0], lat[0]


@pytest.fixture
def rasteres(tmp_path):
    return {
        "score": _escribir_tif(tmp_path / "score.tif", _puntaje()),
        "score_sam": _escribir_tif(
            tmp_path / "score_sam.tif", _puntaje(), descripcion="sam_angle_rad_x"
        ),
        "truth": _escribir_tif(tmp_path / "truth.tif", _verdad()),
    }


@pytest.fixture
def porfidos_csv(tmp_path):
    """Cinco puntos sinteticos: 3 en el top, 1 sobre NaN y 1 fuera de la grilla."""
    pixeles = [(2, 3), (5, 30), (8, 45), (20, 20)]
    filas = [_centro_lonlat(f, c) for f, c in pixeles]
    filas.append(_centro_lonlat(-30, 10))  # 600 m al norte del raster

    ruta = tmp_path / "porfidos.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as salida:
        escritor = csv.writer(salida)
        escritor.writerow(["nombre", "Latitude", "Longitude"])
        for i, (lon, lat) in enumerate(filas):
            escritor.writerow([f"sintetico_{i}", lat, lon])
    return str(ruta), pixeles


def _correr(*args, cwd=None):
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = (
        str(RAIZ / "src") + os.pathsep + entorno.get("PYTHONPATH", "")
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        cwd=cwd or RAIZ,
        env=entorno,
        timeout=180,
    )


def _leer_json(ruta: Path) -> dict:
    def _sin_nan(constante):
        raise AssertionError(f"metrics.json trae el literal {constante}")

    return json.loads(ruta.read_text(encoding="utf-8"), parse_constant=_sin_nan)


# --------------------------------------------------------------------------
# CLI de punta a punta
# --------------------------------------------------------------------------


def test_cli_escribe_metrics_json_y_roc_csv(tmp_path, rasteres, porfidos_csv):
    salida = tmp_path / "metricas"
    ruta_puntos, _ = porfidos_csv

    r = _correr(
        "--score", rasteres["score"],
        "--truth", rasteres["truth"],
        "--lower-is-better",
        "--threshold", 0.1,
        "--porphyries", ruta_puntos,
        "--top-fraction", 0.2,
        "--block-km", 0.5,
        "--out", salida,
    )  # fmt: skip

    assert r.returncode == 0, r.stdout + r.stderr
    assert "AUC" in r.stdout and "Captura" in r.stdout

    m = _leer_json(salida / "metrics.json")
    assert CLAVES_RAIZ <= set(m)
    assert m["higher_is_better"] is False
    assert m["threshold"] == 0.1 and m["seed"] == 42
    assert m["inputs"]["score"].endswith("score.tif")

    conteos = m["pixel"]["counts"]
    # 50x50 = 2500; filas 40-49 ambiguas (500); un NaN en (20,20).
    assert conteos["total"] == 2500
    assert conteos["valid"] == 2500 - 500 - 1
    assert conteos["positive"] == 500
    assert conteos["negative"] == 2500 - 500 - 500 - 1

    # El puntaje separa perfecto: positivos ~0,05, negativos ~0,30.
    assert m["pixel"]["auc"] == pytest.approx(1.0)
    umbral = m["pixel"]["at_threshold"]
    assert umbral["f1"] == pytest.approx(1.0)
    assert set(umbral) >= {
        "confusion",
        "precision",
        "recall",
        "iou",
        "kappa",
        "spatial_enrichment",
    }
    # La enrichment es inf (cero detecciones fuera): se serializa como cadena.
    assert umbral["spatial_enrichment"] == "inf"

    azar = m["pixel"]["random_baseline"]
    assert azar["n_detected"] == umbral["n_detected"]
    assert azar["f1"] < 0.5
    assert azar["auc"] == pytest.approx(0.5, abs=0.1)

    captura = m["capture"]
    assert captura["n_points"] == 5
    assert captura["n_outside"] == 1
    assert captura["n_invalid"] == 1
    assert captura["n_evaluated"] == 3
    assert captura["capture"] == 1.0  # las filas 0-9 son el 20 % mejor
    assert captura["area_valid_km2"] == pytest.approx(2499 * 0.0004)

    bloques = m["blocks"]
    assert bloques["block_px"] == [25, 25]
    assert bloques["n_blocks"] == 4
    assert {"mean", "std", "n_defined"} <= set(bloques["auc"])
    assert len(bloques["per_block"]) == 4

    with open(salida / "roc.csv", encoding="utf-8") as entrada:
        cabecera = entrada.readline().strip()
    assert cabecera == "fpr,tpr,threshold"
    roc = np.loadtxt(salida / "roc.csv", delimiter=",", skiprows=1)
    assert roc.shape[1] == 3
    assert roc[0, 0] == 0.0 and roc[-1, 1] == 1.0


def test_cli_aborta_si_los_transforms_no_coinciden(tmp_path, rasteres):
    corrido = from_origin(460_020.0, 7_780_000.0, 20.0, 20.0)  # un pixel al este
    verdad = _escribir_tif(tmp_path / "truth_corrida.tif", _verdad(), corrido)

    r = _correr(
        "--score", rasteres["score"], "--truth", verdad,
        "--lower-is-better", "--out", tmp_path / "x",
    )  # fmt: skip

    assert r.returncode == 1
    assert "[ABORTADO]" in r.stdout
    assert "transform" in r.stdout
    assert not (tmp_path / "x" / "metrics.json").exists()


def test_cli_aborta_si_la_forma_y_el_crs_no_coinciden(tmp_path, rasteres):
    otra = _escribir_tif(
        tmp_path / "truth_chica.tif",
        _verdad()[:40, :],
        crs=CRS.from_epsg(32718),
    )

    r = _correr(
        "--score", rasteres["score"], "--truth", otra,
        "--lower-is-better", "--out", tmp_path / "x",
    )  # fmt: skip

    assert r.returncode == 1
    assert "forma" in r.stdout and "CRS" in r.stdout


def test_cli_aborta_sin_direccion_declarada_ni_deducible(tmp_path, rasteres):
    r = _correr(
        "--score", rasteres["score"], "--truth", rasteres["truth"],
        "--out", tmp_path / "x",
    )  # fmt: skip

    assert r.returncode == 1
    assert "--lower-is-better" in r.stdout


def test_cli_deduce_la_direccion_de_la_banda_del_pipeline(tmp_path, rasteres):
    salida = tmp_path / "deducido"
    r = _correr(
        "--score", rasteres["score_sam"], "--truth", rasteres["truth"],
        "--block-km", 0, "--out", salida,
    )  # fmt: skip

    assert r.returncode == 0, r.stdout + r.stderr
    m = _leer_json(salida / "metrics.json")
    assert m["higher_is_better"] is False
    assert "sam" in m["direction_source"]
    assert m["blocks"] is None
    assert m["pixel"]["auc"] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Piezas de evaluation.py
# --------------------------------------------------------------------------


def test_declarar_la_direccion_contraria_a_la_banda_deja_advertencia():
    direccion, fuente, avisos = resolve_direction(True, "sam_angle_rad_kaolinite")

    assert direccion is True
    assert fuente == "argumento de la CLI"
    assert len(avisos) == 1 and "1 - AUC" in avisos[0]


def test_decode_truth_excluye_ambiguos_y_nan():
    verdad = np.array([[1, 0, 255, np.nan]], dtype=np.float32)

    positivos, evaluables = decode_truth(verdad)

    assert positivos.tolist() == [[True, False, False, False]]
    assert evaluables.tolist() == [[True, True, False, False]]


def test_decode_truth_rechaza_valores_que_no_son_clases():
    with pytest.raises(ValueError, match="fuera de las clases"):
        decode_truth(np.array([[0, 1, 0.7]]))


def test_check_alignment_lista_todas_las_diferencias(tmp_path, rasteres):
    otra = _escribir_tif(
        tmp_path / "otra.tif",
        _verdad()[:40, :],
        transform=from_origin(0, 0, 30, 30),
        crs=CRS.from_epsg(4326),
    )

    with pytest.raises(AlignmentError) as error:
        check_alignment(read_band(rasteres["score"]), read_band(otra))

    mensaje = str(error.value)
    assert "forma" in mensaje and "CRS" in mensaje and "transform" in mensaje


def test_lonlat_to_rowcol_recupera_el_pixel_que_contiene_al_punto():
    pixeles = [(0, 0), (2, 3), (49, 49), (17, 8)]
    lon, lat = zip(*(_centro_lonlat(f, c) for f, c in pixeles))

    filas_columnas = lonlat_to_rowcol(np.array(lon), np.array(lat), CRS_UTM, TRANSFORM)

    assert filas_columnas.tolist() == [list(p) for p in pixeles]
