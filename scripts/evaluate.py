"""CLI: evalua un mapa de puntaje contra la verdad de terreno y porfidos conocidos.

Tres partes, segun los insumos que se le pasen:

- **A, por pixel** (`--truth`): ROC AUC sobre el puntaje continuo y, con
  `--threshold`, matriz de confusion, precision, recall, F1, IoU, kappa y
  enriquecimiento espacial, junto a una linea base aleatoria de la misma tasa
  de positivos. Los pixeles ambiguos (255) de la verdad no se evaluan.
- **B, captura de porfidos** (`--porphyries`): fraccion de los puntos conocidos
  que cae en el `--top-fraction` mejor puntuado, contra el azar.
- **C, por bloques** (`--block-km`): AUC y captura en cada bloque de N x N km,
  con su media y desviacion.

No reproyecta nada: si el mapa y la verdad no estan en la misma grilla, aborta
diciendo que difiere. Toda la logica vive en `mineralmap.validation`; este
archivo solo parsea argumentos, llama al paquete e imprime.

Uso (desde la raiz del repo):
    python scripts/evaluate.py --score outputs/maps/kaolinite_sam_angle.tif \\
        --truth outputs/maps/ground_truth.tif --lower-is-better --threshold 0.1
"""

from __future__ import annotations

import argparse
import sys

import rasterio

from mineralmap.validation.evaluation import (
    format_report,
    run_evaluation,
    write_outputs,
)

DIR_SALIDA_POR_DEFECTO = "outputs/metrics/"


def _parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Argumentos de la CLI."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--score", required=True, help="GeoTIFF del mapa de puntaje")
    parser.add_argument(
        "--truth",
        default=None,
        help="GeoTIFF de verdad de terreno (1 positivo, 0 negativo, 255 ambiguo)",
    )

    # Sin default: si no se declara, se intenta deducir del config o de la
    # descripcion de banda, y si no se puede, se aborta. Un default silencioso
    # es justo lo que convierte un AUC de 0,82 en uno de 0,18.
    direccion = parser.add_mutually_exclusive_group()
    direccion.add_argument(
        "--higher-is-better",
        dest="higher_is_better",
        action="store_const",
        const=True,
        default=None,
        help="Puntaje mayor = mas evidencia (probabilidades, indices)",
    )
    direccion.add_argument(
        "--lower-is-better",
        dest="higher_is_better",
        action="store_const",
        const=False,
        help="Puntaje menor = mas evidencia (angulo de SAM)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="YAML del experimento; solo se usa para deducir la direccion",
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Umbral en unidades del puntaje para las metricas binarias",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla de la linea base aleatoria (default: %(default)s)",
    )
    parser.add_argument(
        "--porphyries",
        default=None,
        help="CSV (columnas lat/lon) o GeoJSON de puntos en EPSG:4326",
    )
    parser.add_argument(
        "--top-fraction",
        type=float,
        default=0.10,
        help="Fraccion top del mapa para la captura (default: %(default)s)",
    )
    parser.add_argument(
        "--block-km",
        type=float,
        default=5.0,
        help="Lado del bloque espacial en km; 0 lo desactiva (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=DIR_SALIDA_POR_DEFECTO,
        help="Carpeta de salida (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Corre la evaluacion, escribe las salidas e imprime la tabla."""
    args = _parsear_argumentos(argv)

    resultado, roc = run_evaluation(
        score_path=args.score,
        truth_path=args.truth,
        higher_is_better=args.higher_is_better,
        config_path=args.config,
        threshold=args.threshold,
        seed=args.seed,
        porphyries_path=args.porphyries,
        top_fraction=args.top_fraction,
        block_km=args.block_km if args.block_km > 0 else None,
    )

    print(format_report(resultado))
    for ruta in write_outputs(resultado, roc, args.out):
        print(f"Escrito: {ruta}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, rasterio.errors.RasterioIOError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
