"""Validacion por bloques espaciales: AUC y captura zona por zona.

Por que existe. Un AUC calculado sobre todos los pixeles de una escena mezcla
dos cosas: si el puntaje ordena bien los pixeles, y cuantos pixeles vecinos casi
identicos hay. Los pixeles de 20 m no son muestras independientes --un afloramiento
de 1 km2 son 2.500 pixeles con la misma firma--, asi que un solo cuerpo bien
detectado puede sostener un AUC global alto aunque el mapa falle en todo el
resto del AOI. Partir la grilla en bloques de varios km y calcular la metrica
en cada uno muestra esa variacion: un AUC global de 0,80 con bloques entre 0,45
y 0,95 dice algo muy distinto que el mismo 0,80 con bloques entre 0,75 y 0,85.

Que **no** es. No es validacion cruzada espacial en el sentido de entrenar en
unos bloques y evaluar en otros: aca no se entrena nada. Es la misma metrica,
repetida por zona, para ver cuanto depende de donde se mide.

El modulo es numpy puro, como `metrics.py` y `capture.py`: recibe el tamano del
bloque en pixeles. La conversion de km a pixeles necesita el transform del
raster y vive en `validation.evaluation`.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from mineralmap.validation.capture import CaptureResult, capture_rate
from mineralmap.validation.metrics import roc_auc


class BlockResult(NamedTuple):
    """Metricas de un bloque, con su ubicacion y los conteos que las sostienen."""

    row0: int  # primera fila del bloque en la grilla completa
    col0: int  # primera columna
    n_rows: int  # alto del bloque (los del borde pueden ser menores)
    n_cols: int  # ancho del bloque
    n_valid: int  # pixeles con puntaje valido
    n_pos: int  # positivos evaluables de la verdad (0 si no hay verdad)
    n_neg: int  # negativos evaluables de la verdad
    auc: float  # NaN si no hay verdad o el bloque no tiene las dos clases
    capture: CaptureResult | None  # None si no se pasaron puntos


class BlockSummary(NamedTuple):
    """Media y dispersion de una metrica entre bloques donde esta definida."""

    mean: float
    std: float  # desviacion muestral (ddof=1); NaN con menos de 2 bloques
    min: float
    max: float
    n_defined: int  # bloques donde la metrica no es NaN
    n_blocks: int  # bloques totales


def block_bounds(
    shape: tuple[int, int], block_px: tuple[int, int]
) -> list[tuple[int, int, int, int]]:
    """Limites (fila0, fila1, col0, col1) de cada bloque, fila por fila.

    Los bloques se anclan en el pixel (0, 0) de la grilla. Si el tamano no
    divide exacto, los bloques del borde derecho e inferior quedan mas chicos y
    se incluyen igual: descartarlos dejaria sin evaluar una franja del AOI, y
    su tamano real queda registrado en `BlockResult` para quien quiera
    filtrarlos.

    Parameters
    ----------
    shape:
        Forma (alto, ancho) de la grilla.
    block_px:
        Tamano (alto, ancho) del bloque en pixeles, ambos >= 1.

    Returns
    -------
    list[tuple[int, int, int, int]]
        Un rango semiabierto por bloque.

    Raises
    ------
    ValueError
        Si algun lado del bloque es menor que 1.
    """
    alto, ancho = shape
    paso_f, paso_c = (int(v) for v in block_px)
    if paso_f < 1 or paso_c < 1:
        raise ValueError(f"El bloque debe medir al menos 1x1 pixel; recibi {block_px}.")

    return [
        (f0, min(f0 + paso_f, alto), c0, min(c0 + paso_c, ancho))
        for f0 in range(0, alto, paso_f)
        for c0 in range(0, ancho, paso_c)
    ]


def block_metrics(
    score: np.ndarray,
    block_px: tuple[int, int],
    higher_is_better: bool,
    y_true: np.ndarray | None = None,
    truth_valid: np.ndarray | None = None,
    points_rc: np.ndarray | None = None,
    top_fraction: float = 0.10,
) -> list[BlockResult]:
    """AUC y tasa de captura calculados por separado en cada bloque.

    Las dos metricas usan mascaras de validez distintas, y es a proposito. El
    AUC compara contra la verdad de terreno, asi que solo entran los pixeles
    donde la verdad dice algo (`truth_valid`: no ambiguos y con puntaje). La
    captura no usa la verdad: un porfido sobre una unidad que la carta deja
    ambigua sigue siendo un porfido, y su pixel sigue teniendo puntaje.

    La captura de cada bloque rankea **dentro del bloque**: el top 10 % es el
    10 % mejor de ese bloque, no el 10 % mejor de la escena que cae en el.
    Es lo que hace comparables los bloques entre si --cada uno tiene la misma
    linea base de azar--. Con uno o dos porfidos por bloque el valor solo
    puede ser 0, 0,5 o 1; leerlo junto a `capture.n_evaluated`.

    Parameters
    ----------
    score:
        Mapa de puntaje 2D con NaN en lo invalido.
    block_px:
        Tamano (alto, ancho) del bloque en pixeles.
    higher_is_better:
        Direccion del puntaje. Obligatoria, sin default (ver `metrics.roc_curve`).
    y_true:
        Mascara booleana de positivos de la verdad de terreno, misma forma.
        None omite el AUC.
    truth_valid:
        Pixeles donde la verdad es evaluable (no ambiguos). Solo se usa con
        `y_true`; None equivale a todos.
    points_rc:
        Arreglo entero (n, 2) de (fila, columna) de puntos conocidos en la
        grilla completa. None omite la captura.
    top_fraction:
        Fraccion top de cada bloque para la captura.

    Returns
    -------
    list[BlockResult]
        Un resultado por bloque, en el orden de `block_bounds`.

    Raises
    ------
    ValueError
        Si las formas no calzan.
    """
    score = np.asarray(score, dtype=np.float64)
    forma = score.shape

    for nombre, arreglo in (("y_true", y_true), ("truth_valid", truth_valid)):
        if arreglo is not None and np.asarray(arreglo).shape != forma:
            raise ValueError(
                f"`{nombre}` tiene forma {np.asarray(arreglo).shape} y `score` "
                f"{forma}; tienen que ser el mismo raster."
            )

    validos_verdad = None
    if y_true is not None:
        y_true = np.asarray(y_true, dtype=bool)
        validos_verdad = np.isfinite(score)
        if truth_valid is not None:
            validos_verdad &= np.asarray(truth_valid, dtype=bool)

    puntos = None if points_rc is None else np.asarray(points_rc)

    resultados: list[BlockResult] = []
    for f0, f1, c0, c1 in block_bounds(forma, block_px):
        bloque = score[f0:f1, c0:c1]
        n_validos = int(np.count_nonzero(np.isfinite(bloque)))

        auc = float("nan")
        n_pos = n_neg = 0
        if y_true is not None:
            verdad_b = y_true[f0:f1, c0:c1]
            validos_b = validos_verdad[f0:f1, c0:c1]
            n_pos = int(np.count_nonzero(verdad_b & validos_b))
            n_neg = int(np.count_nonzero(~verdad_b & validos_b))
            auc = roc_auc(
                verdad_b, bloque, valid=validos_b, higher_is_better=higher_is_better
            )

        captura = None
        if puntos is not None and n_validos:
            # Solo los puntos que caen en este bloque, trasladados a su origen.
            # Pasarle todos dejaria al resto como "fuera de la grilla" y el
            # conteo `n_outside` de cada bloque no significaria nada.
            if puntos.size:
                en_bloque = (
                    (puntos[:, 0] >= f0)
                    & (puntos[:, 0] < f1)
                    & (puntos[:, 1] >= c0)
                    & (puntos[:, 1] < c1)
                )
                locales = puntos[en_bloque] - np.array([f0, c0], dtype=puntos.dtype)
            else:
                locales = np.empty((0, 2), dtype=np.int64)
            captura = capture_rate(
                bloque,
                locales,
                top_fraction=top_fraction,
                higher_is_better=higher_is_better,
            )

        resultados.append(
            BlockResult(
                row0=f0,
                col0=c0,
                n_rows=f1 - f0,
                n_cols=c1 - c0,
                n_valid=n_validos,
                n_pos=n_pos,
                n_neg=n_neg,
                auc=auc,
                capture=captura,
            )
        )

    return resultados


def summarize(values: list[float]) -> BlockSummary:
    """Media, desviacion, minimo y maximo sobre los valores definidos.

    Los NaN (bloques donde la metrica no se pudo calcular) se excluyen y se
    cuentan aparte en `n_defined`: promediarlos como 0 inventaria bloques
    malos, y descartarlos sin contarlos esconderia que la media sale de tres
    bloques de sesenta y cuatro.

    Parameters
    ----------
    values:
        Un valor por bloque, NaN donde no esta definido.

    Returns
    -------
    BlockSummary
        Todo NaN si ningun bloque tiene la metrica definida. `std` es la
        desviacion muestral (ddof=1), NaN con un solo bloque definido.
    """
    arreglo = np.asarray(values, dtype=np.float64)
    definidos = arreglo[np.isfinite(arreglo)]
    n = int(definidos.size)

    if n == 0:
        nan = float("nan")
        return BlockSummary(nan, nan, nan, nan, 0, int(arreglo.size))

    return BlockSummary(
        mean=float(definidos.mean()),
        std=float(definidos.std(ddof=1)) if n >= 2 else float("nan"),
        min=float(definidos.min()),
        max=float(definidos.max()),
        n_defined=n,
        n_blocks=int(arreglo.size),
    )
