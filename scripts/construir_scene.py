"""CLI: arma el Scene recortado al AOI y lo serializa a data/interim/.

Toda la logica vive en `mineralmap.preprocessing.scene_builder`; este archivo
solo parsea argumentos, llama al paquete e imprime el resumen.
"""

from __future__ import annotations

import argparse
import os
import sys

from mineralmap.config import BAND_ORDER, COMMON_BANDS
from mineralmap.io.raster_io import Scene, save_scene
from mineralmap.preprocessing.scene_builder import build_scene_from_safe

RUTA_DATOS = "data/raw/"
RUTA_SCENE = "data/interim/scene.npz"

# Conjuntos de bandas ofrecidos por la CLI. "all" es el contrato del proyecto.
CONJUNTOS_DE_BANDAS = {"all": BAND_ORDER, "common": COMMON_BANDS}


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=RUTA_DATOS,
        help="Directorio donde buscar la carpeta .SAFE (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=RUTA_SCENE,
        help="Ruta del .npz de salida (default: %(default)s)",
    )
    parser.add_argument(
        "--bands",
        choices=sorted(CONJUNTOS_DE_BANDAS),
        default="all",
        help="Conjunto de bandas: all = BAND_ORDER (12), common = COMMON_BANDS (6)",
    )
    parser.add_argument(
        "--aoi-bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=None,
        help="AOI como bbox en WGS84; si se omite, se usa la ventana por defecto",
    )
    return parser.parse_args()


def _imprimir_resumen(scene: Scene, ruta: str) -> None:
    """Imprime forma, bandas, escalado, resolucion nativa y composicion SCL."""
    meta = scene.meta
    print("=" * 60)
    print(f"Forma del cubo   : {scene.cube.shape}  ({scene.cube.dtype})")
    print(f"band_names       : {scene.band_names}")
    print(
        f"Escalado         : baseline {meta.get('processing_baseline')}, "
        f"offset {meta.get('boa_offset')}, "
        f"quantification {meta.get('quantification')}"
    )
    print(f"AOI (col,row,w,h): {meta.get('aoi_window')}")

    print("Resolucion nativa por banda:")
    for banda, resolucion in meta.get("bands_source", {}).items():
        print(f"  {banda:<4} -> {resolucion} m")

    resumen_scl = dict(meta.get("scl_summary", {}))
    pct_validos = resumen_scl.pop("pct_validos", 100.0 * float(scene.mask.mean()))
    print(f"Pixeles validos  : {pct_validos:.4f} %  ({int(scene.mask.sum()):,} px)")
    print("Composicion SCL del AOI:")
    for clase, porcentaje in sorted(
        resumen_scl.items(), key=lambda par: par[1], reverse=True
    ):
        print(f"  {clase:<22} {porcentaje:8.4f} %")

    print(f"Scene guardado   : {ruta}")
    print("=" * 60)


def main() -> None:
    """Construye el Scene, lo guarda en disco e imprime un resumen."""
    args = _parsear_argumentos()

    scene = build_scene_from_safe(
        root=args.root,
        band_names=CONJUNTOS_DE_BANDAS[args.bands],
        aoi=tuple(args.aoi_bbox) if args.aoi_bbox else None,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    save_scene(scene, args.out)

    _imprimir_resumen(scene, args.out)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
