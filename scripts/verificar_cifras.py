"""CLI: cotejo de las cifras publicadas en los documentos contra el GeoTIFF real.

Por que existe. El README y las secciones 7 y 11 de decisiones tecnicas publican
la distribucion de angulos, el barrido de umbrales y --- desde la Semana 6 --- la
tabla de metricas de validacion del AOI. Esas cifras se
escribieron a mano copiandolas de una corrida, y una copia a mano se desactualiza
sin avisar: ya paso una vez, cuando el repositorio afirmaba "ni un solo pixel
bajo el umbral" con una medicion tomada sobre una ventana de 256x256 px mientras
el AOI completo dejaba 62. El documento no se rompe cuando miente, se lee igual
de bien.

Este script convierte esa comprobacion manual en una que se puede correr. NO
escribe nada: abre el .tif, recalcula cada cifra, la busca en los documentos
--parseandola de los propios archivos, no de una copia guardada aca-- y sale con
codigo 1 si alguna no calza.

Necesita los dos .tif --- el mapa de puntaje y la verdad de terreno ---, o sea la
escena, asi que no va en CI: el runner de GitHub no tiene el producto .SAFE. Se
corre en local antes de publicar cambios de docs.

Uso (desde la raiz del repo):
    python scripts/verificar_cifras.py
    python scripts/verificar_cifras.py --tif outputs/maps/otro_mapa.tif
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

TIF_POR_DEFECTO = "outputs/maps/kaolinite_sam_angle.tif"
GROUND_TRUTH_POR_DEFECTO = "outputs/maps/ground_truth.tif"
CONFIG_POR_DEFECTO = "configs/cerro_colorado_kaolinite.yaml"

# Umbrales del barrido, los mismos de `pipeline.THRESHOLD_SWEEP`. Se repiten
# aca en vez de importarlos porque este script verifica lo que dicen los
# documentos, y tiene que fallar tambien si el pipeline cambia el barrido y los
# documentos se quedan con el viejo.
UMBRALES = (0.05, 0.08, 0.10, 0.15, 0.20)

# Tolerancia al comparar. Los documentos publican 4 decimales, asi que media
# unidad del ultimo decimal publicado es lo maximo que puede separar a una cifra
# correcta de su medicion.
TOLERANCIA = 5e-5

# Cifras que son conteos de pixeles y se comparan exacto, no con TOLERANCIA.
# Se listan por nombre en vez de deducirse de un prefijo: `youden_umbral` es un
# angulo y `umbral_0.10` es un conteo, y un prefijo compartido los confundiria.
CONTEOS = frozenset(
    {"validos", "px_evaluables", "px_positivos", "px_negativos", "vp", "fp", "fn", "vn"}
)


@dataclass(frozen=True)
class Documento:
    """Un archivo a verificar y la convencion numerica con que esta escrito.

    El separador decimal se declara por documento en vez de deducirse: "4.513"
    es cuatro mil quinientos trece en el README en espanol y cuatro coma
    quinientos trece en el ingles, y ninguna heuristica puede distinguirlos
    mirando solo el numero.
    """

    ruta: str
    decimal: str  # "," en los documentos ES, "." en los EN
    etiquetas: dict[str, str]  # nombre de la cifra -> rotulo de la fila


# Que se busca en cada documento. Las claves de `etiquetas` son las cifras que
# calcula `medir()`; los valores son el rotulo de la primera celda de la fila de
# la tabla markdown que la publica.
# Los rotulos de los dos bloques del README (ES y EN) tienen que ser
# TEXTUALMENTE DISTINTOS. El archivo es uno solo y cada Documento lo recorre
# entero, asi que un rotulo compartido haria que la pasada ES leyera la fila EN
# con la convencion decimal equivocada: "0.2403" interpretado como ES da 2403.
# Por eso el README lleva una tabla corta con rotulos disjuntos y la tabla
# completa de metricas vive en los dos archivos de decisiones tecnicas, que si
# son archivos separados y pueden usar rotulos simetricos.
DOCUMENTOS: tuple[Documento, ...] = (
    Documento(
        ruta="README.md",
        decimal=",",
        etiquetas={
            "min": "mínimo",
            "p1": "percentil 1",
            "mediana": "mediana",
            "max": "máximo",
            "px_evaluables": "píxeles evaluables",
            "f1": "F1 (umbral 0,10)",
            "iou": "IoU (umbral 0,10)",
            "kappa": "kappa de Cohen",
            "roc_auc": "AUC de la curva ROC",
        },
    ),
    Documento(
        ruta="README.md",
        decimal=".",
        etiquetas={
            "min": "minimum",
            "p1": "1st percentile",
            "mediana": "median",
            "max": "maximum",
            "px_evaluables": "evaluable pixels",
            "f1": "F1 (threshold 0.10)",
            "iou": "IoU (threshold 0.10)",
            "kappa": "Cohen's kappa",
            "roc_auc": "ROC curve AUC",
        },
    ),
    Documento(
        ruta="docs/es/decisiones_tecnicas.md",
        decimal=",",
        etiquetas={
            "fila_sam": "`SAM_BANDS` (9)",
            "px_evaluables": "píxeles evaluables",
            "px_positivos": "positivos evaluables",
            "px_negativos": "negativos evaluables",
            "vp": "verdaderos positivos (VP)",
            "fp": "falsos positivos (FP)",
            "fn": "falsos negativos (FN)",
            "vn": "verdaderos negativos (VN)",
            "precision": "precisión",
            "recall": "recall",
            "f1": "F1",
            "iou": "IoU",
            "kappa": "kappa de Cohen",
            "roc_auc": "ROC AUC",
            "fila_youden": "índice de Youden",
            "fila_f1max": "F1 máximo",
        },
    ),
    Documento(
        ruta="docs/en/technical_decisions.md",
        decimal=".",
        etiquetas={
            "fila_sam": "`SAM_BANDS` (9)",
            "px_evaluables": "evaluable pixels",
            "px_positivos": "evaluable positives",
            "px_negativos": "evaluable negatives",
            "vp": "true positives (TP)",
            "fp": "false positives (FP)",
            "fn": "false negatives (FN)",
            "vn": "true negatives (TN)",
            "precision": "precision",
            "recall": "recall",
            "f1": "F1",
            "iou": "IoU",
            "kappa": "Cohen's kappa",
            "roc_auc": "ROC AUC",
            "fila_youden": "Youden index",
            "fila_f1max": "maximum F1",
        },
    ),
)

# Filas de tabla que publican mas de una cifra: rotulo -> nombre de la cifra de
# cada columna despues de la primera.
#
#   | `SAM_BANDS` (9)   | min    | p1     | mediana | max |
#   | indice de Youden  | umbral | J      |
#   | F1 maximo         | umbral | F1     |
COLUMNAS_MULTIPLES: dict[str, tuple[str, ...]] = {
    "fila_sam": ("min", "p1", "mediana", "max"),
    "fila_youden": ("youden_umbral", "youden_j"),
    "fila_f1max": ("f1max_umbral", "f1max_f1"),
}


def _a_numero(texto: str, decimal: str) -> float | None:
    """Convierte una celda de tabla markdown a float, o None si no es un numero.

    Tolera el resaltado (`**62**`), el signo de porcentaje, los espacios y los
    separadores de miles de las dos convenciones. El separador de miles es
    siempre el que no es el decimal.
    """
    limpio = texto.strip().strip("*").replace("%", "").replace("`", "").strip()
    limpio = limpio.replace(" ", "").replace(" ", "").replace(" ", "")
    if not limpio:
        return None

    miles = "." if decimal == "," else ","
    limpio = limpio.replace(miles, "").replace(decimal, ".")

    try:
        return float(limpio)
    except ValueError:
        return None


def _celdas(linea: str) -> list[str]:
    """Celdas de una fila de tabla markdown, sin los pipes de los extremos."""
    return [celda.strip() for celda in linea.strip().strip("|").split("|")]


def _filas_de_tabla(texto: str) -> list[list[str]]:
    """Todas las filas de tabla markdown del documento, ya troceadas en celdas.

    Se descartan las lineas separadoras (`|---|---|`), que no traen datos.
    """
    filas = []
    for linea in texto.splitlines():
        if not linea.strip().startswith("|"):
            continue
        celdas = _celdas(linea)
        if all(re.fullmatch(r":?-{2,}:?", celda) for celda in celdas if celda):
            continue
        filas.append(celdas)
    return filas


def medir(ruta_tif: str) -> dict[str, float]:
    """Recalcula desde el .tif las cifras de distribucion y del barrido."""
    with rasterio.open(ruta_tif) as src:
        mapa = src.read(1).astype(np.float64)

    validos = mapa[np.isfinite(mapa)]
    if validos.size == 0:
        raise ValueError(f"{ruta_tif} no tiene ni un pixel valido.")

    cifras = {
        "min": float(validos.min()),
        "p1": float(np.percentile(validos, 1)),
        "mediana": float(np.median(validos)),
        "max": float(validos.max()),
        "validos": float(validos.size),
    }
    for umbral in UMBRALES:
        cifras[f"umbral_{umbral:.2f}"] = float((validos <= umbral).sum())

    return cifras


def medir_metricas(ruta_tif: str, ruta_gt: str, ruta_config: str) -> dict[str, float]:
    """Recalcula las metricas de validacion que los documentos publican.

    El umbral y la direccion del puntaje salen del config, no de constantes
    escritas aca. Es deliberado y es lo contrario del criterio que se usa con
    `UMBRALES`: el barrido se repite a mano porque el documento tiene que fallar
    si el pipeline lo cambia, mientras que las metricas se publican **respecto
    del umbral vigente**, asi que cambiar el config tiene que invalidar la tabla
    publicada. Las dos reglas apuntan a lo mismo: que ninguna cifra del
    documento sobreviva al cambio que la deja obsoleta.

    Parameters
    ----------
    ruta_tif:
        Mapa de puntaje.
    ruta_gt:
        Verdad de terreno.
    ruta_config:
        YAML del experimento.

    Returns
    -------
    dict[str, float]
        Las metricas con los mismos nombres que usan las etiquetas de
        `DOCUMENTOS`.

    Raises
    ------
    FileNotFoundError
        Si falta la verdad de terreno o el config.
    """
    from mineralmap.config import load_config
    from mineralmap.pipeline import DETECTORS
    from mineralmap.validation.metrics import evaluar_desde_rasters

    config = load_config(ruta_config)
    umbral = float(config.algorithm["params"]["angle_threshold_rad"])
    higher_is_better = DETECTORS[config.algorithm["name"]].higher_is_better

    r = evaluar_desde_rasters(
        ruta_tif, ruta_gt, umbral, higher_is_better=higher_is_better
    )
    d, m, met, cal = (
        r["descartes"],
        r["matriz_confusion"],
        r["metricas"],
        r["calibracion"],
    )

    return {
        "px_evaluables": float(d["evaluados"]),
        "px_positivos": float(d["positivos"]),
        "px_negativos": float(d["negativos"]),
        "vp": float(m["vp"]),
        "fp": float(m["fp"]),
        "fn": float(m["fn"]),
        "vn": float(m["vn"]),
        "precision": met["precision"],
        "recall": met["recall"],
        "f1": met["f1"],
        "iou": met["iou"],
        "kappa": met["kappa"],
        "roc_auc": met["roc_auc"],
        "youden_umbral": cal["umbral_youden"],
        "youden_j": cal["youden_j"],
        "f1max_umbral": cal["umbral_f1_maximo"],
        "f1max_f1": cal["f1_maximo"],
    }


def _declaradas(doc: Documento, texto: str) -> dict[str, float]:
    """Extrae del documento las cifras que declara, por rotulo de fila."""
    encontradas: dict[str, float] = {}

    for celdas in _filas_de_tabla(texto):
        if not celdas:
            continue
        rotulo = celdas[0].strip().strip("*").strip()

        for nombre, etiqueta in doc.etiquetas.items():
            if rotulo.lower() != etiqueta.lower():
                continue
            if nombre in COLUMNAS_MULTIPLES:
                for columna, celda in zip(COLUMNAS_MULTIPLES[nombre], celdas[1:]):
                    valor = _a_numero(celda, doc.decimal)
                    if valor is not None:
                        encontradas[columna] = valor
            else:
                valor = _a_numero(celdas[1], doc.decimal)
                if valor is not None:
                    encontradas[nombre] = valor

        # Filas del barrido de umbrales: | 0,10 | 62 | 0,002 % |
        umbral = _a_numero(rotulo, doc.decimal)
        if umbral is not None and len(celdas) >= 2:
            for esperado in UMBRALES:
                if abs(umbral - esperado) < 1e-9:
                    pixeles = _a_numero(celdas[1], doc.decimal)
                    if pixeles is not None:
                        encontradas[f"umbral_{esperado:.2f}"] = pixeles

    return encontradas


def verificar(
    ruta_tif: str, ruta_gt: str, ruta_config: str, raiz: Path
) -> tuple[list[tuple], bool]:
    """Coteja cada cifra declarada contra la medida. Devuelve (filas, todo_ok)."""
    medidas = medir(ruta_tif)
    medidas.update(medir_metricas(ruta_tif, ruta_gt, ruta_config))
    filas: list[tuple] = []
    todo_ok = True

    for doc in DOCUMENTOS:
        ruta = raiz / doc.ruta
        if not ruta.is_file():
            filas.append(("(archivo)", doc.ruta, "no existe", "FALTA"))
            todo_ok = False
            continue

        declaradas = _declaradas(doc, ruta.read_text(encoding="utf-8"))
        if not declaradas:
            # Un documento del que no se extrae ninguna cifra es un fallo, no un
            # exito vacio: significa que se renombro un rotulo de tabla y el
            # cotejo dejo de mirar lo que decia mirar.
            origen = f"{doc.ruta} [{doc.decimal}]"
            filas.append(("(ninguna)", origen, "-", "SIN CIFRAS"))
            todo_ok = False
            continue

        for nombre, declarada in sorted(declaradas.items()):
            medida = medidas.get(nombre)
            if medida is None:
                filas.append((nombre, doc.ruta, "no se mide", "DESCONOCIDA"))
                todo_ok = False
                continue

            # Las cifras de conteo son enteras y se comparan exacto; las de
            # angulo se publican redondeadas a 4 decimales.
            if nombre.startswith("umbral_") or nombre in CONTEOS:
                ok = abs(declarada - medida) < 0.5
            else:
                ok = abs(declarada - medida) <= TOLERANCIA

            todo_ok = todo_ok and ok
            filas.append(
                (
                    f"{nombre} = {declarada:g}",
                    f"{doc.ruta} [{doc.decimal}]",
                    f"{medida:g}",
                    "OK" if ok else "NO CALZA",
                )
            )

    return filas, todo_ok


def _imprimir(filas: list[tuple]) -> None:
    """Imprime la tabla cifra | documento | medido | veredicto."""
    cabecera = ("cifra", "documento", "medido", "veredicto")
    anchos = [max(len(str(fila[i])) for fila in [cabecera, *filas]) for i in range(4)]
    linea = "  ".join("-" * ancho for ancho in anchos)

    print("  ".join(str(c).ljust(a) for c, a in zip(cabecera, anchos)))
    print(linea)
    for fila in filas:
        print("  ".join(str(c).ljust(a) for c, a in zip(fila, anchos)))


def main() -> None:
    """Coteja los documentos contra el .tif e imprime el resultado."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tif",
        default=TIF_POR_DEFECTO,
        help="GeoTIFF del mapa de puntaje (default: %(default)s)",
    )
    parser.add_argument(
        "--ground-truth",
        default=GROUND_TRUTH_POR_DEFECTO,
        help="GeoTIFF de la verdad de terreno (default: %(default)s)",
    )
    parser.add_argument(
        "--config",
        default=CONFIG_POR_DEFECTO,
        help="YAML del experimento, de donde sale el umbral (default: %(default)s)",
    )
    args = parser.parse_args()

    raiz = Path(__file__).resolve().parents[1]
    filas, todo_ok = verificar(args.tif, args.ground_truth, args.config, raiz)

    _imprimir(filas)
    print()
    if todo_ok:
        print(f"OK: las {len(filas)} cifras publicadas coinciden con {args.tif}.")
    else:
        fallidas = sum(1 for fila in filas if fila[3] != "OK")
        print(f"FALLA: {fallidas} de {len(filas)} cifras no coinciden con {args.tif}.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, rasterio.errors.RasterioIOError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
