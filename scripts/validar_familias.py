"""CLI: validacion dejando una familia de roca fuera (Parte 3).

Para cada familia de positivos, entrena sin sus bloques y mide el AUC de sus
positivos contra los negativos de esos bloques. Compara:
  - indices sin entrenamiento: clay ratio (B11/B12) y B11/B8A;
  - referencias: SAM en Sentinel-2 y SAM en EMIT;
  - regresion logistica, Random Forest y SVM con dos juegos de entradas:
      (a) solo Sentinel-2 (bandas + indices)
      (b) Sentinel-2 + pistas minerales de EMIT (outputs/maps/pistas/emit_*.tif).
Todos sobre los MISMOS pixeles (los que tienen dato en todas las fuentes).

Reporta el AUC por familia (solo si la familia cumple el minimo del config) y
el AUC macro: el promedio simple entre familias evaluables, para que cada una
pese lo mismo.

Uso
---
    python scripts/validar_familias.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import yaml
from rasterio.features import rasterize
from sklearn.metrics import roc_auc_score

from mineralmap.algorithms.random_forest import RandomForestDetector
from mineralmap.algorithms.supervised import LogisticDetector, SVMDetector
from mineralmap.io.raster_io import load_scene
from mineralmap.preprocessing.masking import apply_mask
from mineralmap.spectral.features import build_feature_stack
from mineralmap.validation.familias import block_ids, is_evaluable, leave_one_family_out
from mineralmap.validation.geology import (
    cargar_config_verdad,
    clasificar_unidades,
    load_geology_polygons,
)

RUTA_CONFIG = "configs/familias_cerro_colorado.yaml"
RUTA_VERDAD_CFG = "configs/verdad_terreno_cerro_colorado.yaml"
SALIDA = Path("outputs/metrics/familias")


def mapa_de_familias(cfg: dict, scene, forma) -> tuple[np.ndarray, dict[int, str]]:
    g = cargar_config_verdad(RUTA_VERDAD_CFG)
    campo = g["fuente"]["campo_unidad"]
    capas = [load_geology_polygons(r).to_crs(scene.crs) for r in g["_archivos"].values()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gdf = clasificar_unidades(
            gpd.GeoDataFrame(pd.concat(capas, ignore_index=True), geometry="geometry", crs=scene.crs), g)
    pos = gdf[gdf["clase"] == 1].copy()
    pos["u"] = pos[campo].astype(str).str.strip()
    nombres = {i + 1: f for i, f in enumerate(cfg["familias"])}
    unidad_a_codigo = {u: i + 1 for i, f in enumerate(cfg["familias"]) for u in cfg["familias"][f]}
    faltan = sorted(set(pos.u) - set(unidad_a_codigo))
    if faltan:
        raise ValueError(f"Unidades positivas sin familia en el config: {faltan}")
    figuras = [(geo, unidad_a_codigo[u]) for geo, u in zip(pos.geometry, pos.u)
               if geo is not None and not geo.is_empty]
    fam = rasterize(figuras, out_shape=forma, transform=scene.transform, fill=0,
                    all_touched=False, dtype="int32")
    return fam, nombres


def leer(ruta: str) -> np.ndarray:
    with rasterio.open(ruta) as src:
        return src.read(1).astype(np.float64)


def muestrear(idx: np.ndarray, y: np.ndarray, cfg: dict, semilla: int) -> np.ndarray:
    rng = np.random.default_rng(semilla)
    elegidos = []
    for clase, tope in ((1, cfg["muestreo"]["max_positivos"]), (0, cfg["muestreo"]["max_negativos"])):
        de = idx[y[idx] == clase]
        if de.size > tope:
            de = rng.choice(de, tope, replace=False)
        elegidos.append(de)
    return np.sort(np.concatenate(elegidos))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=RUTA_CONFIG)
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    semilla = int(cfg["semilla"])

    scene = load_scene(cfg["scene"])
    verdad = leer(cfg["verdad"])
    forma = verdad.shape
    familia, nombres = mapa_de_familias(cfg, scene, forma)
    bloques = block_ids(forma, int(cfg["bloque_px"]))

    pila, nombres_s2 = build_feature_stack(apply_mask(scene.cube, scene.mask), list(scene.band_names))
    X_s2 = pila.reshape(pila.shape[0], -1).T
    pistas = sorted(Path(cfg["pistas_dir"]).glob("emit_*.tif"))
    X_emit = np.column_stack([leer(str(p)).ravel() for p in pistas])
    sam_s2 = leer(cfg["sam_s2"]).ravel()
    sam_emit = leer(cfg["sam_emit"]).ravel()

    valido = (np.all(np.isfinite(X_s2), axis=1) & np.all(np.isfinite(X_emit), axis=1)
              & np.isfinite(sam_s2) & np.isfinite(sam_emit)).reshape(forma)
    entradas = {"a_s2": X_s2, "b_s2_emit": np.column_stack([X_s2, X_emit])}
    print(f"Pistas EMIT en (b): {[p.stem for p in pistas]}")
    print(f"Pixeles etiquetados comunes: {int((np.isin(verdad, (0, 1)) & valido).sum()):,}")

    sin_entrenar = {
        "clay_ratio": X_s2[:, nombres_s2.index("clay_ratio_b11_b12")],
        "ferric_oxide_swir": X_s2[:, nombres_s2.index("ferric_oxide_b11_b8a")],
        "sam_s2": -sam_s2,
        "sam_emit": -sam_emit,
    }
    fabricas = {
        "logistica": lambda: LogisticDetector(C=cfg["modelos"]["logistica"]["C"], seed=semilla),
        "random_forest": lambda: RandomForestDetector(
            min_samples_leaf=cfg["modelos"]["random_forest"]["min_samples_leaf"], seed=semilla),
        "svm": lambda: SVMDetector(C=cfg["modelos"]["svm"]["C"], seed=semilla),
    }

    splits = leave_one_family_out(verdad, familia, nombres, bloques, valido)
    y_plano = verdad.ravel()
    resultados = {"pistas_emit": [p.stem for p in pistas], "familias": {}, "tiempos_s": {}}
    for s in splits:
        evaluable = is_evaluable(s, cfg["minimo"]["pixeles"], cfg["minimo"]["bloques"])
        idx_pos, idx_neg = np.flatnonzero(s.prueba_pos.ravel()), np.flatnonzero(s.prueba_neg.ravel())
        idx_te = np.concatenate([idx_pos, idx_neg])
        y_te = np.r_[np.ones(idx_pos.size), np.zeros(idx_neg.size)]
        fila = {"n_pos": s.n_pos, "n_neg": s.n_neg, "bloques": s.bloques_prueba,
                "evaluable": evaluable, "auc": {}}
        print(f"\n== {s.familia}: {s.n_pos:,} pos / {s.n_neg:,} neg en bloques {s.bloques_prueba} "
              f"-> {'evaluable' if evaluable else 'INSUFICIENTE'}")
        for nombre, puntaje in sin_entrenar.items():
            fila["auc"][nombre] = float(roc_auc_score(y_te, puntaje[idx_te]))
        idx_tr = np.flatnonzero(s.entrenamiento.ravel())
        tr = muestrear(idx_tr, y_plano, cfg, semilla)
        for juego, X in entradas.items():
            for modelo, fabrica in fabricas.items():
                t0 = time.perf_counter()
                det = fabrica().fit_table(X[tr], y_plano[tr].astype(int))
                fila["auc"][f"{modelo}_{juego}"] = float(roc_auc_score(y_te, det.score_table(X[idx_te])))
                clave = f"{modelo}_{juego}"
                resultados["tiempos_s"][clave] = resultados["tiempos_s"].get(clave, 0) + time.perf_counter() - t0
        for k, v in fila["auc"].items():
            print(f"   {k:28s} {v:.4f}")
        resultados["familias"][s.familia] = fila

    evaluables = [f for f, r in resultados["familias"].items() if r["evaluable"]]
    modelos = list(next(iter(resultados["familias"].values()))["auc"])
    resultados["auc_macro"] = {m: float(np.mean([resultados["familias"][f]["auc"][m] for f in evaluables]))
                               for m in modelos}
    resultados["familias_evaluables"] = evaluables
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "resultados.json").write_text(json.dumps(resultados, indent=2), encoding="utf-8")
    print(f"\nFamilias evaluables: {evaluables}")
    print(f"Escrito {SALIDA / 'resultados.json'}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
