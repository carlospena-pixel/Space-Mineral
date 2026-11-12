"""CLI: compara las familias de algoritmos del Charter V3 con validacion espacial.

Modo comparacion (por defecto)
    Escribe un mapa por modelo en outputs/maps/modelo_<nombre>.tif con
    predicciones FUERA DE MUESTRA en los bloques de validacion cruzada y NaN en
    los bloques de PRUEBA FINAL, mas outputs/metrics/modelos/resumen_cv.json
    (direccion, umbral, tiempo e hiperparametro elegido de cada modelo).

Modo final (--final NOMBRE)
    Entrena ese modelo con TODOS los bloques de validacion y escribe
    outputs/maps/final_<nombre>.tif con valores solo en los bloques de prueba.

Todo se configura en configs/modelos_cerro_colorado.yaml.

Uso
---
    python scripts/comparar_modelos.py
    python scripts/comparar_modelos.py --final xgboost
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import yaml
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

from mineralmap.algorithms.matched_filter import MatchedFilter
from mineralmap.algorithms.random_forest import RandomForestDetector
from mineralmap.algorithms.sam import SAM
from mineralmap.algorithms.sid import SID
from mineralmap.algorithms.supervised import (
    HistGradientBoostingDetector,
    KNNDetector,
    LogisticDetector,
    SVMDetector,
    XGBoostDetector,
)
from mineralmap.algorithms.unmixing import UnmixingDetector
from mineralmap.io.raster_io import load_scene, write_geotiff
from mineralmap.preprocessing.masking import apply_mask
from mineralmap.spectral.endmembers import get_reference_spectrum
from mineralmap.spectral.features import build_feature_stack
from mineralmap.spectral.usgs_library import load_usgs_rs_sentinel2

RUTA_CONFIG = "configs/modelos_cerro_colorado.yaml"
DIR_RESUMEN = Path("outputs/metrics/modelos")

SUPERVISADOS = {
    "logistica": ("C", lambda v, s: LogisticDetector(C=v, seed=s)),
    "knn": ("k", lambda v, s: KNNDetector(k=int(v), seed=s)),
    "svm": ("C", lambda v, s: SVMDetector(C=v, seed=s)),
    "random_forest": (
        "min_samples_leaf",
        lambda v, s: RandomForestDetector(min_samples_leaf=int(v), seed=s),
    ),
    "hist_gradient_boosting": (
        "learning_rate",
        lambda v, s: HistGradientBoostingDetector(learning_rate=v, seed=s),
    ),
    "xgboost": ("max_depth", lambda v, s: XGBoostDetector(max_depth=int(v), seed=s)),
}
ARBOLES = ("random_forest", "hist_gradient_boosting", "xgboost")
INDICES = {
    "clay_ratio": "clay_ratio_b11_b12",
    "ferric_iron": "ferric_iron_b4_b2",
    "ferric_oxide_swir": "ferric_oxide_b11_b8a",
}


# --------------------------------------------------------------------------- datos
def preparar(cfg: dict) -> dict:
    semilla = int(cfg["semilla"])
    scene = load_scene(cfg["scene"])
    with rasterio.open(cfg["verdad"]) as src:
        verdad = src.read(1)
    alto, ancho = verdad.shape
    bpx = int(cfg["bloques"]["tamano_px"])
    filas, cols = np.indices((alto, ancho))
    bloque = (filas // bpx) * (ancho // bpx) + cols // bpx
    prueba = np.isin(bloque, cfg["bloques"]["prueba_final"])

    cubo = apply_mask(scene.cube, scene.mask)
    pila, nombres = build_feature_stack(cubo, list(scene.band_names))
    X = pila.reshape(pila.shape[0], -1).T
    con_dato = np.all(np.isfinite(X), axis=1) & scene.mask.ravel()
    etiquetado = np.isin(verdad.ravel(), (0, 1)) & con_dato

    idx_cv = np.flatnonzero(etiquetado & ~prueba.ravel())
    idx_te = np.flatnonzero(etiquetado & prueba.ravel())
    y_cv = verdad.ravel()[idx_cv].astype(int)
    g_cv = bloque.ravel()[idx_cv]
    folds = list(
        StratifiedGroupKFold(
            n_splits=int(cfg["validacion_cruzada"]["n_folds"]),
            shuffle=True,
            random_state=semilla,
        ).split(X[idx_cv], y_cv, g_cv)
    )
    return dict(
        semilla=semilla, scene=scene, verdad=verdad, prueba=prueba, cubo=cubo,
        X=X, nombres=nombres, idx_cv=idx_cv, idx_te=idx_te, y_cv=y_cv, g_cv=g_cv,
        y_te=verdad.ravel()[idx_te].astype(int), folds=folds, forma=(alto, ancho),
    )


def muestrear(idx: np.ndarray, y: np.ndarray, cfg: dict, semilla: int) -> np.ndarray:
    """Hasta max_positivos y max_negativos de `idx`, sorteados con la semilla."""
    rng = np.random.default_rng(semilla)
    m = cfg["muestreo"]
    elegidos = []
    for clase, tope in ((1, int(m["max_positivos"])), (0, int(m["max_negativos"]))):
        de_clase = idx[y[idx] == clase]
        if de_clase.size > tope:
            de_clase = rng.choice(de_clase, tope, replace=False)
        elegidos.append(de_clase)
    return np.sort(np.concatenate(elegidos))


def umbral_top(valores: np.ndarray, fraccion: float, mayor_es_mejor: bool) -> float:
    v = valores[np.isfinite(valores)]
    return float(np.quantile(v, 1 - fraccion if mayor_es_mejor else fraccion))


def escribir(nombre: str, mapa: np.ndarray, d: dict, mayor: bool, prefijo="modelo") -> str:
    ruta = f"outputs/maps/{prefijo}_{nombre}.tif"
    sentido = "higher" if mayor else "lower"
    write_geotiff(ruta, mapa, d["scene"], band_descriptions=[f"{nombre}_{sentido}_is_better"])
    return ruta


def mapa_de_tabla(valores: np.ndarray, idx: np.ndarray, forma) -> np.ndarray:
    mapa = np.full(forma[0] * forma[1], np.nan, dtype=np.float32)
    mapa[idx] = valores
    return mapa.reshape(forma)


# ------------------------------------------------------------------- reglas (A, B)
def reglas(cfg: dict, d: dict) -> dict:
    """Mapas de las reglas espectrales y los indices sobre todo el AOI."""
    scene, cubo = d["scene"], d["cubo"]
    salida = {}
    for nombre, det in (("sam", SAM()), ("sid", SID()), ("matched_filter", MatchedFilter(seed=d["semilla"]))):
        bandas = list(det.bands)
        sub = cubo[[scene.band_names.index(b) for b in bandas]]
        ref = get_reference_spectrum(cfg["mineral"], band_order=bandas)
        t0 = time.perf_counter()
        mapa = det.predict(sub, ref)
        salida[nombre] = dict(familia="A reglas", mapa=mapa, mayor=det.higher_is_better,
                              tiempo_s=time.perf_counter() - t0, hp=None)
    for nombre, entrada in INDICES.items():
        t0 = time.perf_counter()
        mapa = d["X"][:, d["nombres"].index(entrada)].reshape(d["forma"])
        salida[nombre] = dict(familia="A indices", mapa=mapa, mayor=True,
                              tiempo_s=time.perf_counter() - t0, hp=None)

    comp = cfg.get("fcls", {}).get("componentes") or {}
    if comp:
        bandas = list(scene.band_names)
        otros = [load_usgs_rs_sentinel2(str(ruta)) for ruta in comp.values()]
        otros = np.array([_a_bandas(o, bandas) for o in otros])
        if cfg["fcls"].get("sombra", True):
            otros = np.vstack([otros, np.zeros(len(bandas))])
        ref = get_reference_spectrum(cfg["mineral"], band_order=bandas)
        det = UnmixingDetector(otros, nombres=list(comp) + ["sombra"])
        # FCLS por pixel es lento en Python: se resuelve solo en los pixeles
        # etiquetados, que son los unicos que evalua evaluate.py.
        idx = np.concatenate([d["idx_cv"], d["idx_te"]])
        tabla = cubo.reshape(cubo.shape[0], -1)[:, idx][:, None, :]
        t0 = time.perf_counter()
        prop = det.predict(tabla, ref)[0]
        salida["fcls"] = dict(familia="B mezcla", mapa=mapa_de_tabla(prop, idx, d["forma"]),
                              mayor=True, tiempo_s=time.perf_counter() - t0, hp=list(comp))
    else:
        print("FCLS omitido: faltan los componentes USGS en fcls.componentes del config.")
    return salida


def _a_bandas(valores13: np.ndarray, bandas: list[str]) -> np.ndarray:
    """El archivo rsSentinel2 trae 13 posiciones con B10; se reordena a `bandas`
    con el mismo orden crudo que usa `get_reference_spectrum`."""
    from mineralmap.spectral.endmembers import _RAW_BAND_ORDER

    return np.array([valores13[_RAW_BAND_ORDER.index(b)] for b in bandas])


# --------------------------------------------------------------- supervisados (C)
def oof(hacer, d: dict, cfg: dict, X: np.ndarray | None = None) -> tuple[np.ndarray, list, float]:
    X = d["X"][d["idx_cv"]] if X is None else X
    y = d["y_cv"]
    pred = np.full(y.size, np.nan)
    aucs = []
    t0 = time.perf_counter()
    for k, (tr, va) in enumerate(d["folds"]):
        tr_m = muestrear(tr, y, cfg, d["semilla"] + k)
        det = hacer().fit_table(X[tr_m], y[tr_m])
        pred[va] = det.score_table(X[va])
        aucs.append(float(roc_auc_score(y[va], pred[va])))
    return pred, aucs, time.perf_counter() - t0


def supervisados(cfg: dict, d: dict) -> dict:
    salida = {}
    for nombre, (param, fabrica) in SUPERVISADOS.items():
        mejor = None
        for valor in cfg["hiperparametros"][nombre][param]:
            pred, aucs, seg = oof(lambda: fabrica(valor, d["semilla"]), d, cfg)
            print(f"  {nombre:24s} {param}={valor:<6} AUC medio por fold {np.mean(aucs):.4f}  ({seg:.1f} s)")
            if mejor is None or np.mean(aucs) > np.mean(mejor[1]):
                mejor = (pred, aucs, seg, valor)
        pred, aucs, seg, valor = mejor
        salida[nombre] = dict(familia="C aprendizaje", pred=pred, mayor=True, tiempo_s=seg,
                              hp={param: valor}, aucs_fold=aucs,
                              mapa=mapa_de_tabla(pred, d["idx_cv"], d["forma"]))
    return salida


def stacking(sup: dict, d: dict, cfg: dict) -> tuple[dict, list[str]]:
    ranking = sorted(sup, key=lambda n: roc_auc_score(d["y_cv"], sup[n]["pred"]), reverse=True)
    base = ranking[:3]
    Z = np.column_stack([sup[n]["pred"] for n in base])
    pred, aucs, seg = oof(lambda: LogisticDetector(C=1.0, seed=d["semilla"]), d, cfg, X=Z)
    seg += sum(sup[n]["tiempo_s"] for n in base)
    return dict(familia="D combinacion", pred=pred, mayor=True, tiempo_s=seg,
                hp={"base": base}, aucs_fold=aucs,
                mapa=mapa_de_tabla(pred, d["idx_cv"], d["forma"])), base


def importancias(nombre: str, hp: dict, d: dict, cfg: dict) -> dict:
    """Importancia por permutacion (caida de AUC) en cada fold de validacion."""
    param, fabrica = SUPERVISADOS[nombre]
    X, y = d["X"][d["idx_cv"]], d["y_cv"]
    rng = np.random.default_rng(d["semilla"])
    caidas = []
    for k, (tr, va) in enumerate(d["folds"]):
        tr_m = muestrear(tr, y, cfg, d["semilla"] + k)
        det = fabrica(hp[param], d["semilla"]).fit_table(X[tr_m], y[tr_m])
        va_m = va if va.size <= 20000 else np.sort(rng.choice(va, 20000, replace=False))
        r = permutation_importance(det.model_, X[va_m], y[va_m], scoring="roc_auc",
                                   n_repeats=5, random_state=d["semilla"], n_jobs=1)
        caidas.append(r.importances_mean)
    caidas = np.array(caidas)
    return {n: {"media": float(m), "desv": float(s)}
            for n, m, s in zip(d["nombres"], caidas.mean(0), caidas.std(0))}


# ---------------------------------------------------------------------- modos
def comparar(cfg: dict, d: dict) -> None:
    print(f"Bloques de prueba: {cfg['bloques']['prueba_final']}")
    print(f"Validacion cruzada: {d['idx_cv'].size:,} px etiquetados "
          f"({int(d['y_cv'].sum()):,} positivos) | prueba: {d['idx_te'].size:,} px "
          f"({int(d['y_te'].sum()):,} positivos)")
    for k, (tr, va) in enumerate(d["folds"]):
        print(f"  fold {k}: bloques {sorted(set(d['g_cv'][va].tolist()))} | "
              f"positivos {int(d['y_cv'][va].sum()):,} de {va.size:,}")

    modelos = reglas(cfg, d)
    print("Supervisados (validacion cruzada):")
    sup = supervisados(cfg, d)
    modelos.update(sup)
    modelos["stacking"], base = stacking(sup, d, cfg)
    print(f"Stacking sobre: {base}")

    arbol = max(ARBOLES, key=lambda n: roc_auc_score(d["y_cv"], sup[n]["pred"]))
    imp = importancias(arbol, sup[arbol]["hp"], d, cfg)

    fraccion = float(cfg["umbral"]["fraccion_top"])
    evaluable_cv = np.zeros(d["forma"][0] * d["forma"][1], dtype=bool)
    evaluable_cv[d["idx_cv"]] = True
    resumen = {"semilla": d["semilla"], "prueba_final": cfg["bloques"]["prueba_final"],
               "mejor_arbol": arbol, "importancias": imp, "modelos": {}}
    for nombre, m in modelos.items():
        mapa = np.array(m["mapa"], dtype=np.float32)
        mapa[d["prueba"]] = np.nan
        ruta = escribir(nombre, mapa, d, m["mayor"])
        resumen["modelos"][nombre] = {
            "familia": m["familia"], "archivo": ruta, "higher_is_better": bool(m["mayor"]),
            "umbral_top": umbral_top(mapa.ravel()[evaluable_cv], fraccion, m["mayor"]),
            "tiempo_s": round(float(m["tiempo_s"]), 2), "hiperparametro": m["hp"],
            "auc_por_fold": m.get("aucs_fold"),
        }
        print(f"Escrito {ruta}  ({m['tiempo_s']:.1f} s)")
    DIR_RESUMEN.mkdir(parents=True, exist_ok=True)
    (DIR_RESUMEN / "resumen_cv.json").write_text(json.dumps(resumen, indent=2), encoding="utf-8")
    print(f"Resumen: {DIR_RESUMEN / 'resumen_cv.json'}")


def final(cfg: dict, d: dict, nombre: str) -> None:
    resumen = json.loads((DIR_RESUMEN / "resumen_cv.json").read_text(encoding="utf-8"))
    info = resumen["modelos"][nombre]
    X_cv, y_cv, X_te = d["X"][d["idx_cv"]], d["y_cv"], d["X"][d["idx_te"]]
    todos = np.arange(y_cv.size)

    def entrenar(n, hp, X=X_cv):
        param, fabrica = SUPERVISADOS[n]
        m = muestrear(todos, y_cv, cfg, d["semilla"])
        return fabrica(hp[param], d["semilla"]).fit_table(X[m], y_cv[m])

    t0 = time.perf_counter()
    if nombre in SUPERVISADOS:
        pred = entrenar(nombre, info["hiperparametro"]).score_table(X_te)
        mapa = mapa_de_tabla(pred, d["idx_te"], d["forma"])
    elif nombre == "stacking":
        base = info["hiperparametro"]["base"]
        Z_cv = np.column_stack([
            np.array(rasterio.open(resumen["modelos"][b]["archivo"]).read(1)).ravel()[d["idx_cv"]]
            for b in base])
        Z_te = np.column_stack([entrenar(b, resumen["modelos"][b]["hiperparametro"]).score_table(X_te)
                                for b in base])
        meta = LogisticDetector(C=1.0, seed=d["semilla"]).fit_table(Z_cv, y_cv)
        mapa = mapa_de_tabla(meta.score_table(Z_te), d["idx_te"], d["forma"])
    else:
        mapa = np.array(reglas(cfg, d)[nombre]["mapa"], dtype=np.float32)
        mapa[~d["prueba"]] = np.nan
    seg = time.perf_counter() - t0
    ruta = escribir(nombre, mapa, d, info["higher_is_better"], prefijo="final")
    print(f"PRUEBA FINAL {nombre}: {d['idx_te'].size:,} px ({int(d['y_te'].sum()):,} positivos) "
          f"| umbral fijado en la validacion cruzada: {info['umbral_top']} | {seg:.1f} s")
    print(f"Escrito {ruta}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=RUTA_CONFIG)
    parser.add_argument("--final", default=None, help="Modelo ganador a evaluar en la prueba final")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    d = preparar(cfg)
    if args.final:
        final(cfg, d, args.final)
    else:
        comparar(cfg, d)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
