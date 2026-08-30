"""CLI: genera la figura F5, la deteccion SAM sobre la cartografia geologica.

Lee el mapa de angulos que ya escribio el pipeline en `outputs/maps/` --- no lo
recalcula --- y le superpone los poligonos geologicos clasificados segun
`configs/verdad_terreno_cerro_colorado.yaml`. Guarda
`outputs/figures/overlay_deteccion_geologia.png`.

El dibujo vive en `visualization/maps.py::plot_overlay_geologia`; este archivo
solo carga los insumos y guarda el PNG.

Uso
---
    python scripts/figura_overlay_geologia.py
    python scripts/figura_overlay_geologia.py --threshold 0.1
"""

from __future__ import annotations

import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import rasterio  # noqa: E402

from mineralmap.io.raster_io import load_scene  # noqa: E402
from mineralmap.validation.geology import (  # noqa: E402
    cargar_config_verdad,
    clasificar_unidades,
    load_geology_polygons,
)
from mineralmap.visualization.maps import plot_overlay_geologia  # noqa: E402

RUTA_SCENE = "data/interim/scene.npz"
RUTA_CONFIG = "configs/verdad_terreno_cerro_colorado.yaml"
RUTA_ANGULOS = "outputs/maps/kaolinite_sam_angle.tif"
RUTA_SALIDA = "outputs/figures/overlay_deteccion_geologia.png"


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", default=RUTA_SCENE)
    parser.add_argument("--config", default=RUTA_CONFIG)
    parser.add_argument("--angles", default=RUTA_ANGULOS)
    parser.add_argument("--out", default=RUTA_SALIDA)
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=(
            "Umbral en radianes: dibuja la mascara binaria de deteccion en vez "
            "del mapa continuo. Sin el se dibuja el mapa continuo, que es lo "
            "honesto mientras el umbral siga sin calibrar."
        ),
    )
    return parser.parse_args()


def _cargar_poligonos(config_path: str, crs):
    """Carga las capas del YAML, las concatena y les asigna clase."""
    import geopandas as gpd
    import pandas as pd

    config = cargar_config_verdad(config_path)
    capas = [
        load_geology_polygons(ruta).to_crs(crs) for ruta in config["_archivos"].values()
    ]
    combinados = gpd.GeoDataFrame(
        pd.concat(capas, ignore_index=True), geometry="geometry", crs=crs
    )
    return clasificar_unidades(combinados, config)


def main() -> None:
    """Arma la figura F5 y la guarda como PNG."""
    args = _parsear_argumentos()

    scene = load_scene(args.scene)

    # Se lee el .tif ya escrito en vez de recalcular el SAM: la figura tiene
    # que mostrar exactamente el mapa que se publico, no uno equivalente.
    with rasterio.open(args.angles) as src:
        angulos = src.read(1)

    poligonos = _cargar_poligonos(args.config, scene.crs)

    ax = plot_overlay_geologia(angulos, scene, poligonos, threshold=args.threshold)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    ax.figure.savefig(args.out, dpi=150, bbox_inches="tight")
    plt.close(ax.figure)

    print(f"Guardado: {args.out}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
