"""CLI: evalua en lote los mapas de cada comparacion con la misma evaluacion.

    modelos   mapas de comparar_modelos.py (validacion cruzada)
    sensor    SAM en Sentinel-2, SAM en EMIT y EMIT L2B, sobre los mismos pixeles
    pistas    mapas por mineral y por zona de alteracion

No evalua la prueba final: ya se uso y no sirve para elegir.

Uso
---
    python scripts/evaluar_lote.py modelos sensor pistas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import yaml
from validar_familias import mapa_de_familias

from mineralmap.io.raster_io import load_scene, write_geotiff
from mineralmap.validation.comparacion import group_auc, top_threshold
from mineralmap.validation.evaluation import run_evaluation, write_outputs

CONFIG_FAMILIAS = "configs/familias_cerro_colorado.yaml"
VERDAD = "outputs/maps/ground_truth.tif"
PISTAS = Path("outputs/maps/pistas")
FRACCION_TOP = 0.10
SENSOR = {
    "sam_s2": ("outputs/maps/kaolinite_sam_angle.tif", False),
    "sam_emit": (str(PISTAS / "emit_sam_caolinita.tif"), False),
    "emit_l2b_caolinita": (str(PISTAS / "emit_l2b_caolinita.tif"), True),
}


def leer(ruta: str | Path) -> tuple[np.ndarray, str | None]:
    with rasterio.open(ruta) as src:
        return src.read(1).astype(np.float64), src.descriptions[0]


def evaluar(ruta: str | Path, mayor: bool, umbral: float, salida: Path) -> dict:
    resultado, roc = run_evaluation(
        score_path=str(ruta),
        truth_path=VERDAD,
        higher_is_better=mayor,
        threshold=umbral,
        block_km=5.0,
    )
    write_outputs(resultado, roc, str(salida))
    return resultado


def imprimir(nombre: str, resultado: dict, extra: str = "") -> None:
    pixel, bloques = resultado["pixel"], resultado["blocks"]["auc"]
    enriq = pixel["at_threshold"]["spatial_enrichment"]
    enriq = "NaN" if enriq is None else f"{enriq:.4f}"
    print(
        f"{nombre:28s} AUC {pixel['auc']:.4f} | bloques {bloques['mean']:.4f} "
        f"+- {bloques['std']:.4f} | enriq {enriq}{extra}"
    )


def modelos(salida: Path) -> None:
    resumen = json.loads(
        Path("outputs/metrics/modelos/resumen_cv.json").read_text(encoding="utf-8")
    )
    for nombre, m in resumen["modelos"].items():
        mayor = m["higher_is_better"]
        destino = salida / "modelos" / nombre
        imprimir(nombre, evaluar(m["archivo"], mayor, m["umbral_top"], destino))


def por_grupo(
    mapas: dict, salida: Path, recortes: Path | None, mismos_pixeles: bool
) -> None:
    cfg = yaml.safe_load(Path(CONFIG_FAMILIAS).read_text(encoding="utf-8"))
    scene = load_scene(cfg["scene"])
    verdad, _ = leer(VERDAD)
    familia, nombres = mapa_de_familias(cfg, scene, verdad.shape)
    yab = familia == next(k for k, v in nombres.items() if v == "yabricoya")

    evaluables = np.isin(verdad, (0, 1))
    comunes = evaluables.copy()
    if mismos_pixeles:
        for ruta, _ in mapas.values():
            comunes &= np.isfinite(leer(ruta)[0])

    for nombre, (ruta, mayor) in mapas.items():
        valores, descripcion = leer(ruta)
        validos = comunes & np.isfinite(valores)
        umbral, regla = top_threshold(valores[validos], FRACCION_TOP, mayor)
        a_evaluar = ruta
        if mismos_pixeles:
            a_evaluar = recortes / f"{nombre}.tif"
            recorte = np.where(validos, valores, np.nan)
            write_geotiff(str(a_evaluar), recorte, scene, [descripcion])
        resultado = evaluar(a_evaluar, mayor, umbral, salida / nombre)
        s = valores if mayor else -valores
        extra = (
            f" | Yabricoya {group_auc(s, verdad, validos, yab):.4f}"
            f" | otros {group_auc(s, verdad, validos, ~yab):.4f} | umbral {regla}"
        )
        imprimir(nombre, resultado, extra)


def mapas_de_pistas() -> dict:
    mapas = {}
    for patron in ("emit_l2b_*.tif", "emit_sam_*.tif", "zona_*.tif"):
        for ruta in sorted(PISTAS.glob(patron)):
            mapas[ruta.stem] = (ruta, not ruta.stem.startswith("emit_sam_"))
    if not mapas:
        raise FileNotFoundError(f"No hay mapas en {PISTAS}; corre emit_pistas.py.")
    return mapas


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("lotes", nargs="+", choices=["modelos", "sensor", "pistas"])
    parser.add_argument("--out", default="outputs/metrics", type=Path)
    args = parser.parse_args()

    for lote in args.lotes:
        print(f"== {lote}")
        if lote == "modelos":
            modelos(args.out)
        elif lote == "sensor":
            recortes = Path("outputs/maps/parte1")
            por_grupo(SENSOR, args.out / "parte1", recortes, mismos_pixeles=True)
        else:
            mapas = mapas_de_pistas()
            por_grupo(mapas, args.out / "parte2", None, mismos_pixeles=False)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, rasterio.errors.RasterioIOError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
