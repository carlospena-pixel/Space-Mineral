"""CLI: figura de la mascara de validez del AOI (SCL y Scene.mask lado a lado).

`preprocessing/masking.py` concentra las decisiones menos evidentes del
preprocesamiento --que clases SCL se descartan, que la mascara sea True donde
el pixel es valido-- y hasta ahora no producia ninguna salida que se pudiera
mirar. Esta figura es esa salida: el panel izquierdo es la entrada de la
decision y el derecho, su resultado.

Carga data/interim/scene.npz; si no existe, construye el Scene desde data/raw/,
igual que scripts/visualizar_rgb.py. La banda SCL se relee del .SAFE porque el
Scene guarda la mascara ya resuelta, no la clasificacion de la que salio.

Toda la logica de graficar vive en `visualization/maps.py`; este archivo solo
parsea argumentos, llama al paquete y guarda el PNG.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from rasterio.transform import array_bounds

from mineralmap.io.raster_io import Scene, find_band_file, find_safe_dir, load_scene
from mineralmap.preprocessing.resampling import read_band_on_grid, resampling_for
from mineralmap.preprocessing.scene_builder import (
    TARGET_RESOLUTION_M,
    build_scene_from_safe,
)
from mineralmap.visualization.maps import plot_scl_classes

RUTA_SCENE = "data/interim/scene.npz"
RUTA_RAW = "data/raw/"
OUTPUT_PATH = "outputs/figures/mascara_scl.png"


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scene",
        default=RUTA_SCENE,
        help="Ruta del .npz del Scene (default: %(default)s)",
    )
    parser.add_argument(
        "--root",
        default=RUTA_RAW,
        help="Directorio donde buscar la carpeta .SAFE (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=OUTPUT_PATH,
        help="Ruta del PNG de salida (default: %(default)s)",
    )
    return parser.parse_args()


def _cargar_scene(ruta_scene: str, root: str) -> Scene:
    """Carga el Scene desde disco; si no existe, lo construye desde `root`."""
    if os.path.exists(ruta_scene):
        return load_scene(ruta_scene)

    print(f"No existe {ruta_scene}; construyendo el Scene desde {root}...")
    return build_scene_from_safe(root=root)


def _releer_scl(scene: Scene, root: str) -> np.ndarray:
    """Relee la banda SCL del .SAFE sobre la misma ventana que el Scene.

    La ventana se deriva del `transform` y de la forma del propio Scene, no de
    `meta["aoi_window"]`: `meta` es documentacion, no configuracion (ver
    docs/es/decisiones_tecnicas.md, seccion 1.1). Asi la figura sigue siendo la
    del AOI correcto aunque el Scene se haya construido con una ventana
    distinta de la de por defecto.
    """
    alto, ancho = scene.cube.shape[1:]
    bounds = array_bounds(alto, ancho, scene.transform)

    safe_dir = find_safe_dir(root)
    ruta_scl, resolucion = find_band_file(safe_dir, "SCL")
    # categorical=True fuerza `nearest`: SCL es una etiqueta y promediarla
    # produce clases que el producto no trae. Es el mismo metodo con que
    # build_scene_from_safe la leyo para armar la mascara que se dibuja al lado.
    metodo = resampling_for(resolucion, TARGET_RESOLUTION_M, categorical=True)
    print(f"SCL desde R{resolucion}m con {metodo.name} -> ({alto}, {ancho})")

    return read_band_on_grid(
        ruta_scl,
        bounds,
        (alto, ancho),
        resampling=metodo,
        expected_crs=scene.crs,
    )


def main() -> None:
    """Arma la figura de dos paneles (SCL + mascara) y la guarda como PNG."""
    args = _parsear_argumentos()

    scene = _cargar_scene(args.scene, args.root)
    scl = _releer_scl(scene, args.root)

    tile = scene.meta.get("tile_id", "")
    fecha = scene.meta.get("sensing_date", "")[:10]
    ejes = plot_scl_classes(
        scl,
        scene.mask,
        title=f"AOI {tile} {fecha}".strip(),
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    figura = ejes[0].figure
    figura.savefig(args.out, dpi=150, bbox_inches="tight")

    print(f"Guardado: {args.out}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
