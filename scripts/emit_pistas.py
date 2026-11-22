"""CLI: pistas minerales de EMIT en la grilla del AOI.

Pasos (se pueden pedir por separado con --pasos):
  l2b    un mapa por mineral central de EMIT L2B (profundidad de banda donde el
         mineral identificado esta en la lista; mayor es mejor).
  sam    SAM sobre la reflectancia EMIT L2A para cada firma de `emit_sam` del
         config (angulo; menor es mejor). SAM se calcula por pixel en la
         geometria del sensor y despues se ortorrectifica el mapa con la GLT:
         la GLT solo elige que pixel del sensor va en cada celda, asi que el
         orden no cambia el resultado y no hace falta cargar el cubo de 1,8 GB.
  zonas  un mapa por zona de alteracion: maximo de los rangos percentiles de
         sus minerales disponibles.

Todo se escribe en outputs/maps/pistas/. Config: configs/pistas_cerro_colorado.yaml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
import yaml

from mineralmap.algorithms.sam import SAM
from mineralmap.io.emit import (
    apply_glt,
    iter_reflectance,
    read_emit_l2a_meta,
    read_emit_l2b_min,
    reproject_to_scene,
)
from mineralmap.io.raster_io import load_scene, write_geotiff
from mineralmap.spectral.emit_scores import band_depth_score, resolve_library_ids
from mineralmap.spectral.pistas import combine_zone, percentile_rank
from mineralmap.spectral.resample import load_splib_signature, resample_to_bands

RUTA_CONFIG = "configs/pistas_cerro_colorado.yaml"


def _cobertura(mapa: np.ndarray) -> str:
    return f"{100 * np.isfinite(mapa).mean():.2f} % con dato"


def paso_l2b(cfg: dict, scene, salida: Path) -> None:
    emit = read_emit_l2b_min(cfg["emit_l2b"]["min_file"])
    cache = {}
    for mineral, m in cfg["emit_l2b"]["minerales"].items():
        g = int(m["grupo"])
        if g not in cache:
            cache[g] = (
                apply_glt(emit.mineral_id[g], emit.glt),
                apply_glt(emit.band_depth[g], emit.glt),
            )
        ids = resolve_library_ids(emit.library, m["entradas"], g)
        puntaje = band_depth_score(*cache[g], ids)
        mapa = reproject_to_scene(puntaje, emit.transform, emit.crs, scene)
        ruta = salida / f"emit_l2b_{mineral}.tif"
        write_geotiff(
            str(ruta),
            mapa,
            scene,
            band_descriptions=[f"emit_l2b_band_depth_{mineral}_higher_is_better"],
        )
        print(
            f"L2B {mineral:16s} grupo {g} | {len(ids):2d} entradas | "
            f"puntaje > 0 en {100 * np.nanmean(mapa > 0):.2f} % del AOI con dato | "
            f"{_cobertura(mapa)} -> {ruta}"
        )


def firma_en_emit(ruta_firma: str, ruta_lambdas: str, meta) -> np.ndarray:
    """Firma splib07b remuestreada a las bandas EMIT (gaussiana con su FWHM)."""
    lambdas, valores = load_splib_signature(ruta_firma, ruta_lambdas)  # nm
    return resample_to_bands(lambdas, valores, meta.wavelengths, meta.fwhm)


def paso_sam(cfg: dict, scene, salida: Path) -> None:
    sam_cfg = cfg["emit_sam"]
    if not sam_cfg.get("minerales"):
        print(
            "SAM sobre EMIT omitido: faltan las firmas splib07b en emit_sam.minerales."
        )
        return
    meta = read_emit_l2a_meta(sam_cfg["rfl_file"])
    firmas = {}
    for mineral, m in sam_cfg["minerales"].items():
        firma = firma_en_emit(m["firma"], sam_cfg["longitudes_de_onda"], meta)
        usar = meta.good & np.isfinite(firma)
        firmas[mineral] = (firma, usar)
        print(
            f"SAM {mineral:16s} {m['firma']} | "
            f"bandas usadas {int(usar.sum())} de {usar.size}"
        )
    # Una sola mascara de bandas para leer el archivo una vez: la union de las
    # buenas; cada firma usa su propio subconjunto dentro del trozo.
    leer = np.any([u for _, u in firmas.values()], axis=0)
    idx_leer = np.flatnonzero(leer)
    mapas = {m: np.full(meta.shape[:2], np.nan, dtype=np.float32) for m in firmas}
    det = SAM()
    for r0, r1, cubo in iter_reflectance(meta.path, leer):
        for mineral, (firma, usar) in firmas.items():
            sel = np.isin(idx_leer, np.flatnonzero(usar))
            mapas[mineral][r0:r1] = det.predict(cubo[sel], firma[usar])
    for mineral, mapa_sensor in mapas.items():
        orto = apply_glt(mapa_sensor, meta.glt)
        mapa = reproject_to_scene(orto, meta.transform, meta.crs, scene)
        destino = sam_cfg["minerales"][mineral].get("salida") or str(
            salida / f"emit_sam_{mineral}.tif"
        )
        write_geotiff(
            destino, mapa, scene, band_descriptions=[f"sam_angle_rad_{mineral}_emit"]
        )
        print(f"SAM {mineral:16s} {_cobertura(mapa)} -> {destino}")


def paso_zonas(cfg: dict, scene, salida: Path) -> None:
    for zona, minerales in cfg["zonas"].items():
        rangos, usados = [], []
        for mineral in minerales:
            for ruta, mayor in (
                (salida / f"emit_l2b_{mineral}.tif", True),
                (salida / f"emit_sam_{mineral}.tif", False),
            ):
                if ruta.exists():
                    with rasterio.open(ruta) as src:
                        rangos.append(
                            percentile_rank(src.read(1).astype(np.float64), mayor)
                        )
                    usados.append(ruta.stem)
        faltan = [m for m in minerales if not any(m in u for u in usados)]
        if not rangos:
            print(f"Zona {zona}: sin mapas disponibles ({faltan}).")
            continue
        mapa = combine_zone(rangos)
        ruta = salida / f"zona_{zona}.tif"
        write_geotiff(
            str(ruta),
            mapa,
            scene,
            band_descriptions=[f"zona_{zona}_rank_higher_is_better"],
        )
        print(f"Zona {zona:18s} usa {usados} | faltan {faltan or 'ninguno'} -> {ruta}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", default=RUTA_CONFIG)
    parser.add_argument(
        "--pasos",
        nargs="+",
        default=["l2b", "sam", "zonas"],
        choices=["l2b", "sam", "zonas"],
    )
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    scene = load_scene(cfg["scene"])
    salida = Path(cfg["salida"])
    salida.mkdir(parents=True, exist_ok=True)
    for paso in args.pasos:
        {"l2b": paso_l2b, "sam": paso_sam, "zonas": paso_zonas}[paso](
            cfg, scene, salida
        )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
