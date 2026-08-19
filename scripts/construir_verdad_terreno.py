"""CLI: rasteriza la cartografia geologica a la grilla del Scene.

Carga el Scene desde `data/interim/scene.npz`, construye la capa de verdad de
terreno segun `configs/verdad_terreno_tamarugal.yaml` y la escribe como
GeoTIFF en `outputs/maps/ground_truth.tif`, alineada pixel a pixel con el mapa
de angulos.

Toda la logica vive en `mineralmap.validation.geology`; este archivo solo
parsea argumentos, llama al paquete e imprime la trazabilidad.

Uso
---
    python scripts/construir_verdad_terreno.py
"""

from __future__ import annotations

import argparse
import sys

from mineralmap.io.raster_io import load_scene, write_geotiff
from mineralmap.validation.geology import build_ground_truth

RUTA_SCENE = "data/interim/scene.npz"
RUTA_CONFIG = "configs/verdad_terreno_tamarugal.yaml"
RUTA_SALIDA = "outputs/maps/ground_truth.tif"

# Descripcion de la unica banda del GeoTIFF. Un raster de una banda que no dice
# que es obliga a leer el codigo que lo produjo para saberlo.
DESCRIPCION_BANDA = "ground_truth_alteracion"


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scene",
        default=RUTA_SCENE,
        help="Ruta del Scene serializado (default: %(default)s)",
    )
    parser.add_argument(
        "--config",
        default=RUTA_CONFIG,
        help="YAML de verdad de terreno (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=RUTA_SALIDA,
        help="Ruta del GeoTIFF de salida (default: %(default)s)",
    )
    return parser.parse_args()


def _imprimir_trazabilidad(traza: dict, ruta: str) -> None:
    """Imprime el dict de trazabilidad que devuelve `build_ground_truth`."""
    print("=" * 68)
    print(f"Config           : {traza['config']}")
    print(f"Campo de unidad  : {traza['campo_unidad']}")
    print(f"CRS / forma      : {traza['crs']}  {traza['forma']}")
    print(f"all_touched      : {traza['all_touched']}")

    print("Capas usadas:")
    for nombre, info in traza["archivos"].items():
        print(f"  {nombre:<14} {info['poligonos']:>6} poligonos  <- {info['ruta']}")
    print(f"  {'TOTAL':<14} {traza['poligonos_totales']:>6} poligonos")

    print("Poligonos por clase:")
    for clase, n in traza["poligonos_por_clase"].items():
        print(f"  {clase:<14} {n:>10,}")

    print("Pixeles por clase:")
    for clase, n in traza["pixeles_por_clase"].items():
        pct = traza["fraccion_aoi_por_clase_pct"][clase]
        print(f"  {clase:<14} {n:>12,}  {pct:8.4f} % del AOI")

    sin_clasificar = traza["unidades_sin_clasificar"]
    print(f"Unidades sin clasificar: {len(sin_clasificar)}")
    for unidad, area in sin_clasificar.items():
        print(f"  {area:>10.2f} km2  {unidad}")

    print(f"GeoTIFF escrito  : {ruta}")
    print("=" * 68)


def main() -> None:
    """Construye la capa de verdad de terreno, la escribe e imprime el resumen."""
    args = _parsear_argumentos()

    scene = load_scene(args.scene)
    raster, traza = build_ground_truth(args.config, scene)

    # Se apoya en la validacion de forma de `write_geotiff`: ya comprueba que
    # la forma espacial calce con la del Scene, que es exactamente el chequeo
    # que hace falta aca. Reimplementarlo daria dos mensajes de error para el
    # mismo fallo y uno de los dos envejeceria.
    write_geotiff(args.out, raster, scene, band_descriptions=[DESCRIPCION_BANDA])

    _imprimir_trazabilidad(traza, args.out)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
