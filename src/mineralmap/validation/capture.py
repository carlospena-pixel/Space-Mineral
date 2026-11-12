"""Tasa de captura de porfidos: cuantos depositos conocidos caen en lo mejor del mapa.

Es la metrica que pide el plan de "puntaje de parecido a porfido": dado un mapa
de puntaje y una lista de porfidos conocidos, ¿que fraccion de ellos cae dentro
del `top_fraction` de pixeles mejor puntuados? Es la pregunta operativa de un
geologo de exploracion --"si mando la campana a revisar el 10 % mejor del mapa,
¿cuantos de los depositos que ya conozco habria encontrado?"-- y no necesita una
verdad de terreno pixel a pixel, que en el norte de Chile no existe.

Por que es un modulo propio y no una funcion mas de `metrics.py`
------------------------------------------------------------------
1. **El contrato de entrada es otro.** Todo `metrics.py` compara dos rasteres
   alineados pixel a pixel (`y_true` contra `y_pred` o `y_score`). Aca uno de
   los dos lados es una lista de puntos, ya convertidos a fila/columna, con
   casos que alla no existen: puntos fuera de la grilla, varios puntos sobre el
   mismo pixel, puntos sobre pixeles invalidos. Mezclarlo rompe la regla que
   hace leible a `metrics.py` ("todo recibe dos mascaras de la misma forma").
2. **La linea base es analitica.** En `metrics.py` el azar se construye
   (mascara aleatoria de la misma tasa); aca el azar tiene valor esperado
   cerrado: un punto que cae uniforme sobre los pixeles validos esta en el top
   con probabilidad igual a la fraccion marcada. No hace falta simular nada.
3. **`metrics.py` esta congelado y testeado.** Agregar aca deja intacto ese
   archivo y su bateria de tests, que es lo que el plan pide.

Las dos convenciones de `metrics.py` se mantienen: los NaN son pixeles
invalidos (nunca se imputan) y un denominador vacio devuelve NaN, no 0.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from mineralmap.spectral.indices import mask_by_positive_rate


class CaptureResult(NamedTuple):
    """Resultado de `capture_rate`, con los conteos que lo explican.

    Los puntos se reparten en tres grupos disjuntos que suman `n_points`:
    `n_evaluated` (sobre un pixel valido), `n_invalid` (dentro de la grilla
    pero sobre un pixel invalido) y `n_outside` (fuera de la grilla).
    """

    capture: float  # n_captured / n_evaluated, NaN si n_evaluated == 0
    chance: float  # captura esperada al azar = n_top_pixels / n_valid_pixels
    lift: float  # capture / chance; 1 = igual que el azar
    n_captured: int  # puntos evaluados que caen en el top
    n_evaluated: int  # puntos sobre pixel valido: el denominador de `capture`
    n_invalid: int  # puntos dentro de la grilla pero sobre pixel invalido
    n_outside: int  # puntos fuera de la grilla
    n_points: int  # total de puntos recibidos
    top_fraction: float  # fraccion pedida
    n_top_pixels: int  # pixeles marcados como top
    n_valid_pixels: int  # area evaluada, en pixeles


def _validar_puntos(points_rc: np.ndarray) -> np.ndarray:
    """Comprueba que `points_rc` sea una lista (n, 2) de indices enteros.

    Se exige dtype entero en vez de redondear: la conversion de coordenadas a
    fila/columna es un `floor` (el pixel que contiene al punto), y un `round`
    hecho aca por comodidad moveria medio pixel los puntos que caen en la mitad
    inferior derecha de su celda sin que nada lo denuncie.
    """
    puntos = np.asarray(points_rc)

    if puntos.size == 0:
        return np.empty((0, 2), dtype=np.int64)

    if puntos.ndim != 2 or puntos.shape[1] != 2:
        raise ValueError(
            f"`points_rc` debe tener forma (n, 2) con (fila, columna); recibi "
            f"forma {puntos.shape}."
        )
    if not np.issubdtype(puntos.dtype, np.integer):
        raise ValueError(
            f"`points_rc` debe ser de enteros y llego como {puntos.dtype}. "
            f"Convierte coordenadas a indices con floor (el pixel que contiene "
            f"al punto), no con round."
        )
    return puntos.astype(np.int64)


def capture_rate(
    score: np.ndarray,
    points_rc: np.ndarray,
    top_fraction: float = 0.10,
    valid: np.ndarray | None = None,
    higher_is_better: bool = True,
) -> CaptureResult:
    """Fraccion de puntos conocidos que caen en el `top_fraction` mejor del mapa.

    El top se construye con `spectral.indices.mask_by_positive_rate`, la misma
    funcion que arma las mascaras de tasa fija del contraste E5: marca
    **exactamente** ``round(top_fraction * n_validos)`` pixeles, rompiendo
    empates por orden de pixel. Cortar por el valor del percentil haria que un
    grupo de empates en el corte entrara entero o no entrara, y el area marcada
    --y con ella la linea base-- dejaria de ser la pedida.

    Como se trata cada punto:

    - **Fuera de la grilla** (fila o columna negativa o mas alla del borde):
      `n_outside`. No es un fallo del mapa: el mapa no tiene nada que decir ahi.
    - **Sobre un pixel invalido** (NaN en el puntaje o False en `valid`):
      `n_invalid`. Tampoco es un fallo. Contarlo como "no capturado" castigaria
      al detector por las nubes de la escena, y contarlo como capturado lo
      premiaria por ellas.
    - **Sobre un pixel valido**: entra al denominador (`n_evaluated`) y suma a
      `n_captured` si ese pixel esta en el top. Dos porfidos sobre el mismo
      pixel cuentan dos veces: son dos depositos.

    Linea base de azar. Un punto que cae uniforme sobre los pixeles validos
    esta en el top con probabilidad ``n_top / n_validos``, que es
    `top_fraction` salvo el redondeo a un pixel entero. Eso es `chance`, y
    `lift = capture / chance` dice cuantas veces mejor que el azar captura el
    mapa: 1 es azar, 3 es el triple. Ojo que el azar supone puntos uniformes,
    y los porfidos no lo son --se agrupan en franjas--, asi que con pocos
    puntos el `lift` es ruidoso y conviene leerlo junto a `n_evaluated`.

    Parameters
    ----------
    score:
        Mapa de puntaje 2D (alto, ancho). Sus NaN son pixeles invalidos.
    points_rc:
        Arreglo entero (n, 2) de (fila, columna) de los puntos conocidos, ya
        convertidos a la grilla del mapa. Puede traer indices fuera de rango.
    top_fraction:
        Fraccion de los pixeles validos que se considera "top", en (0, 1].
    valid:
        Mascara booleana opcional de pixeles evaluables, misma forma que
        `score`. Se combina con los NaN del puntaje.
    higher_is_better:
        True si un puntaje mayor es mas evidencia; False para el angulo de SAM.
        Sin default "inteligente", por la misma razon que en
        `metrics.roc_curve`: mirando flotantes no se sabe la direccion.

    Returns
    -------
    CaptureResult
        `capture`, `chance`, `lift` y los conteos. `capture` es NaN si ningun
        punto cae sobre un pixel valido; `chance` es NaN si no hay pixeles
        validos; `lift` es NaN si cualquiera de los dos lo es o si `chance` es 0.

    Raises
    ------
    ValueError
        Si `score` no es 2D, si `valid` no calza con su forma, si `points_rc`
        no es (n, 2) entero, o si `top_fraction` no esta en (0, 1].
    """
    score = np.asarray(score, dtype=np.float64)
    if score.ndim != 2:
        raise ValueError(
            f"`score` debe ser un mapa 2D (alto, ancho); recibi forma {score.shape}."
        )
    if not 0.0 < top_fraction <= 1.0:
        raise ValueError(
            f"`top_fraction` es una fraccion en (0, 1]; recibi {top_fraction}. "
            f"Para el 10 % se escribe 0.10."
        )

    validos = np.isfinite(score)
    if valid is not None:
        valid = np.asarray(valid)
        if valid.shape != score.shape:
            raise ValueError(
                f"La mascara `valid` tiene forma {valid.shape} y el mapa "
                f"{score.shape}: una mascara de otra ventana descartaria puntos "
                f"arbitrarios sin que ningun conteo lo denuncie."
            )
        validos &= valid.astype(bool)

    puntos = _validar_puntos(points_rc)
    alto, ancho = score.shape

    top = mask_by_positive_rate(
        score, top_fraction, valid=validos, higher_is_better=higher_is_better
    )
    n_validos = int(np.count_nonzero(validos))
    n_top = int(np.count_nonzero(top))

    filas, columnas = puntos[:, 0], puntos[:, 1]
    dentro = (filas >= 0) & (filas < alto) & (columnas >= 0) & (columnas < ancho)

    # Indexar solo con los puntos de adentro: un indice negativo en numpy no
    # falla, cuenta desde el otro borde, y un porfido al sur del AOI apareceria
    # evaluado sobre un pixel del extremo norte.
    filas_in, columnas_in = filas[dentro], columnas[dentro]
    sobre_valido = validos[filas_in, columnas_in]
    capturados = top[filas_in, columnas_in] & sobre_valido

    n_evaluados = int(np.count_nonzero(sobre_valido))
    n_capturados = int(np.count_nonzero(capturados))

    captura = n_capturados / n_evaluados if n_evaluados else float("nan")
    azar = n_top / n_validos if n_validos else float("nan")
    if np.isfinite(captura) and np.isfinite(azar) and azar > 0:
        lift = captura / azar
    else:
        lift = float("nan")

    return CaptureResult(
        capture=captura,
        chance=azar,
        lift=lift,
        n_captured=n_capturados,
        n_evaluated=n_evaluados,
        n_invalid=int(dentro.sum()) - n_evaluados,
        n_outside=int(np.count_nonzero(~dentro)),
        n_points=int(puntos.shape[0]),
        top_fraction=float(top_fraction),
        n_top_pixels=n_top,
        n_valid_pixels=n_validos,
    )
