"""CLI: lleva EMIT L2B a la grilla del Scene y escribe mapas de puntaje.

Lee `configs/emit_cerro_colorado.yaml`, ortorrectifica con la GLT del producto,
arma un puntaje por cada mapa declarado (profundidad de banda donde el mineral
identificado esta en la lista; mayor es mejor), lo reproyecta a la grilla de
`data/interim/scene.npz` -la misma de outputs/maps/ground_truth.tif- y lo
escribe como GeoTIFF.

Toda la logica vive en `mineralmap.io.emit` y `mineralmap.spectral.emit_scores`.

Uso
---
    python scripts/emit_to_grid.py
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

import numpy as np
import yaml

from mineralmap.io.emit import apply_glt, read_emit_l2b_min, reproject_to_scene
from mineralmap.io.raster_io import load_scene, write_geotiff
from mineralmap.spectral.emit_scores import band_depth_score, resolve_library_ids

RUTA_CONFIG = "configs/emit_cerro_colorado.yaml"


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=RUTA_CONFIG, help="YAML de EMIT (default: %(default)s)"
    )
    return parser.parse_args()


def _nombres_del_mapa(mapas: dict, clave: str) -> list[str]:
    """Entradas de un mapa, sumando las del mapa que declare en `incluye`."""
    mapa = mapas[clave]
    nombres = list(mapa.get("entradas", []))
    if mapa.get("incluye"):
        nombres = _nombres_del_mapa(mapas, mapa["incluye"]) + nombres
    return nombres


def main() -> None:
    args = _parsear_argumentos()
    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    emit_cfg = config["emit"]
    grupo = int(emit_cfg["grupo"])
    emit = read_emit_l2b_min(emit_cfg["min_file"])
    scene = load_scene(config["scene"])

    ids_orto = apply_glt(emit.mineral_id[grupo], emit.glt)
    bd_orto = apply_glt(emit.band_depth[grupo], emit.glt)
    total = scene.mask.size
    etiqueta = dict(zip(emit.library["index"].tolist(), emit.library["sample_name"]))

    print("=" * 68)
    print(f"Escena EMIT      : {emit.attrs.get('flight_line')}  "
          f"{emit.attrs.get('time_coverage_start')}  {emit.attrs.get('product_version')}")
    print(f"Grupo usado      : {grupo}")
    print(f"Grilla destino   : {scene.crs}  {scene.mask.shape}  (desde {config['scene']})")

    for clave, mapa in config["mapas"].items():
        nombres = _nombres_del_mapa(config["mapas"], clave)
        ids = resolve_library_ids(emit.library, nombres, grupo)

        puntaje_orto = band_depth_score(ids_orto, bd_orto, ids)
        puntaje = reproject_to_scene(puntaje_orto, emit.transform, emit.crs, scene)

        con_dato = np.isfinite(puntaje)
        positivos = con_dato & (puntaje > 0)
        ids_en_aoi = reproject_to_scene(ids_orto, emit.transform, emit.crs, scene)
        conteo = Counter(ids_en_aoi[positivos].astype(int).tolist())

        write_geotiff(
            mapa["salida"], puntaje, scene,
            band_descriptions=[mapa["descripcion_banda"]],
        )

        print("-" * 68)
        print(f"Mapa             : {clave}  ({len(ids)} entradas de la biblioteca)")
        print(f"Con dato EMIT    : {int(con_dato.sum()):>10,} px  "
              f"{100 * con_dato.sum() / total:8.4f} % del AOI")
        print(f"Sin dato EMIT    : {int((~con_dato).sum()):>10,} px  "
              f"{100 * (~con_dato).sum() / total:8.4f} % del AOI")
        print(f"Puntaje > 0      : {int(positivos.sum()):>10,} px  "
              f"{100 * positivos.sum() / total:8.4f} % del AOI")
        if positivos.any():
            v = puntaje[positivos]
            print(f"band_depth > 0   : min {v.min():.4f} | mediana {np.median(v):.4f} "
                  f"| max {v.max():.4f}")
        for i, n in conteo.most_common():
            print(f"    id {i:3d} {n:>9,} px  {etiqueta.get(i, '?')}")
        print(f"GeoTIFF escrito  : {mapa['salida']}")
    print("=" * 68)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
