"""CLI: calcula las metricas de un mapa de salida contra la verdad de terreno.

Lee los dos GeoTIFF --- el mapa de puntaje del detector y la capa de verdad de
terreno ---, comprueba que estan alineados, descarta los pixeles sobre los que
no se puede medir e imprime la tabla de metricas junto con la trazabilidad de
donde salio cada numero.

Toda la logica vive en `mineralmap.validation.metrics`; este archivo solo parsea
argumentos, llama al paquete e imprime.

Uso
---
    python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif \\
        outputs/maps/ground_truth.tif

El umbral y la direccion del puntaje salen del config del experimento, no de
constantes escritas aca: el umbral es `algorithm.params.angle_threshold_rad` y
la direccion es `Detector.higher_is_better` del detector que el config nombra.
Duplicar cualquiera de los dos en este archivo crearia una segunda fuente de
verdad que envejeceria en silencio, y con la direccion equivocada el AUC sale
como `1 - AUC` sin que nada falle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mineralmap.config import load_config
from mineralmap.pipeline import DETECTORS
from mineralmap.validation.metrics import evaluar_desde_rasters

RUTA_CONFIG = "configs/cerro_colorado_kaolinite.yaml"
RUTA_SCENE = "data/interim/scene.npz"
RUTA_FIGURA = "outputs/figures/roc_kaolinite_sam.png"

# Resolucion de la figura. La misma que usan las demas figuras del entregable:
# a 100 dpi el rotulo del AUC no se lee en una impresion.
FIGURA_DPI = 150


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("predicted", help="Ruta al mapa de puntaje (GeoTIFF)")
    parser.add_argument("ground_truth", help="Ruta a la verdad de terreno (GeoTIFF)")
    parser.add_argument(
        "--config",
        default=RUTA_CONFIG,
        help="YAML del experimento, de donde salen el umbral y el detector "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Umbral de deteccion en las unidades del puntaje. Por defecto, el "
        "que declara el config.",
    )
    parser.add_argument(
        "--scene",
        default=None,
        help=f"Scene serializado del que tomar la mascara de validez "
        f"(p. ej. {RUTA_SCENE}). Por defecto no se aplica.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Ruta donde volcar el resultado completo como JSON.",
    )
    parser.add_argument(
        "--figura",
        nargs="?",
        const=RUTA_FIGURA,
        default=None,
        help=f"Escribe la figura de validacion (curva ROC + histograma del "
        f"angulo por clase). Sin valor usa {RUTA_FIGURA}.",
    )
    return parser.parse_args()


def _umbral_y_direccion(config_path: str, umbral_cli: float | None):
    """Resuelve el umbral y la direccion del puntaje desde el config.

    Returns
    -------
    tuple[float, bool, str, str]
        Umbral, `higher_is_better`, nombre del algoritmo y de donde salio el
        umbral ("config" o "--threshold"), para poder imprimirlo.

    Raises
    ------
    ValueError
        Si el config no nombra un detector registrado o no declara umbral y
        tampoco se paso `--threshold`. Inventar un default aca correria la
        evaluacion con un umbral que nadie eligio.
    """
    config = load_config(config_path)

    nombre = config.algorithm.get("name")
    if nombre not in DETECTORS:
        raise ValueError(
            f"El config nombra el algoritmo {nombre!r}, que no esta en el "
            f"registro DETECTORS ({sorted(DETECTORS)}). Sin detector no se "
            "puede saber en que direccion apunta su puntaje."
        )
    higher_is_better = DETECTORS[nombre].higher_is_better

    if umbral_cli is not None:
        return float(umbral_cli), higher_is_better, nombre, "--threshold"

    params = config.algorithm.get("params") or {}
    umbral = params.get("angle_threshold_rad")
    if umbral is None:
        raise ValueError(
            f"{config_path} no declara `algorithm.params.angle_threshold_rad` "
            "y tampoco se paso --threshold."
        )
    return float(umbral), higher_is_better, nombre, "config"


def _imprimir_resultado(r: dict, algoritmo: str, origen_umbral: str) -> None:
    """Imprime la tabla de metricas con su trazabilidad."""
    ancho = 68
    fuentes = r["fuentes"]
    d = r["descartes"]
    m = r["matriz_confusion"]
    met = r["metricas"]
    cal = r["calibracion"]

    print("=" * ancho)
    print(f"Mapa de puntaje  : {fuentes['puntaje']['ruta']}")
    print(f"Verdad de terreno: {fuentes['verdad_terreno']['ruta']}")
    print(
        f"CRS / forma      : {fuentes['puntaje']['crs']}  "
        f"{fuentes['puntaje']['forma']}  (alineacion verificada)"
    )
    if fuentes["scene"] is not None:
        print(
            f"Mascara del Scene: {fuentes['scene']['ruta']}  "
            f"{fuentes['scene']['pixeles_validos']:,} pixeles validos"
        )
    else:
        print("Mascara del Scene: no aplicada")
    print(f"Algoritmo        : {algoritmo}")
    print(
        f"Umbral           : {r['umbral']:.4f}  (de {origen_umbral})   "
        f"higher_is_better = {r['higher_is_better']}"
    )

    print("-" * ancho)
    print("Pixeles que entran al calculo:")
    print(f"  {'evaluados':<24} {d['evaluados']:>12,}")
    print(f"    {'positivos':<22} {d['positivos']:>12,}")
    print(f"    {'negativos':<22} {d['negativos']:>12,}")
    print("Descartados, por causa:")
    print(f"  {'ambiguo (clase 255)':<24} {d['ambiguo']:>12,}")
    print(f"  {'NaN en verdad terreno':<24} {d['gt_nan']:>12,}")
    print(f"  {'NaN en el puntaje':<24} {d['score_nan']:>12,}")
    print(f"  {'invalido por mascara':<24} {d['mascara']:>12,}")
    print(f"  {'TOTAL del AOI':<24} {d['total']:>12,}")

    print("-" * ancho)
    print("Matriz de confusion:")
    print(f"  {'verdaderos positivos (vp)':<28} {m['vp']:>12,}")
    print(f"  {'falsos positivos     (fp)':<28} {m['fp']:>12,}")
    print(f"  {'falsos negativos     (fn)':<28} {m['fn']:>12,}")
    print(f"  {'verdaderos negativos (vn)':<28} {m['vn']:>12,}")

    print("-" * ancho)
    print("Metricas:")
    for etiqueta, clave in (
        ("precision", "precision"),
        ("recall", "recall"),
        ("F1", "f1"),
        ("IoU", "iou"),
        ("kappa de Cohen", "kappa"),
        ("ROC AUC", "roc_auc"),
    ):
        print(f"  {etiqueta:<28} {met[clave]:>12.4f}")

    print("-" * ancho)
    print(f"Calibracion (curva ROC de {cal['puntos_curva']:,} puntos):")
    print(
        f"  {'umbral de Youden':<28} {cal['umbral_youden']:>12.4f}"
        f"   J = {cal['youden_j']:.4f}"
    )
    print(
        f"  {'umbral de F1 maximo':<28} {cal['umbral_f1_maximo']:>12.4f}"
        f"   F1 = {cal['f1_maximo']:.4f}"
    )
    print("=" * ancho)


def _volcar_json(r: dict, ruta: str) -> None:
    """Escribe el resultado como JSON, sin la curva completa.

    La curva son dos arreglos de decenas de miles de puntos: en el JSON solo
    pesarian. Quien la necesite la recalcula con `curva_roc`, que es
    determinista sobre los mismos insumos.
    """
    serializable = {k: v for k, v in r.items() if not k.startswith("_")}
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"JSON escrito     : {destino}")


def _escribir_figura(r: dict, ruta: str) -> None:
    """Dibuja la ROC y el histograma por clase en una figura de dos paneles.

    Los dos paneles van juntos porque el AUC solo no distingue "las dos
    distribuciones se superponen" de "estan separadas, pero al reves". El
    segundo panel es el que lo dice, y separarlos en dos archivos hace que uno
    se cite sin el otro.
    """
    import matplotlib

    # Backend sin ventana: el script corre en terminal y en CI, donde abrir un
    # display no falla de inmediato sino que cuelga.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from mineralmap.visualization.validacion import (
        plot_curva_roc,
        plot_histograma_por_clase,
    )

    pares = r["_pares"]
    fig, (ax_roc, ax_hist) = plt.subplots(1, 2, figsize=(15, 6.5))

    plot_curva_roc(
        r["_curva"],
        title=f"Curva ROC --- SAM caolinita\n{pares.descartes['evaluados']:,} "
        f"pixeles evaluables",
        ax=ax_roc,
    )
    plot_histograma_por_clase(
        pares.y_true, pares.y_score, umbral=r["umbral"], ax=ax_hist
    )

    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(destino, dpi=FIGURA_DPI)
    plt.close(fig)
    print(f"Figura escrita   : {destino}")


def main() -> None:
    """Evalua el mapa contra la verdad de terreno e imprime la tabla."""
    args = _parsear_argumentos()

    umbral, higher_is_better, algoritmo, origen = _umbral_y_direccion(
        args.config, args.threshold
    )

    resultado = evaluar_desde_rasters(
        args.predicted,
        args.ground_truth,
        umbral,
        higher_is_better=higher_is_better,
        ruta_scene=args.scene,
    )

    _imprimir_resultado(resultado, algoritmo, origen)

    if args.out:
        _volcar_json(resultado, args.out)

    if args.figura:
        _escribir_figura(resultado, args.figura)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
