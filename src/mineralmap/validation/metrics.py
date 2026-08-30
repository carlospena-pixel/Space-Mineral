"""Metricas de validacion: matriz de confusion, F1, IoU, ROC/AUC, kappa.

Este modulo no conoce el proyecto. Sus funciones reciben arreglos de numpy y
devuelven numeros o arreglos: nada de `Scene`, nada de rasterio, nada de rutas
ni de nombres de banda. Es lo que permite testearlas sin la escena y reusarlas
tal cual con el Random Forest del Nivel 2, que producira puntajes con otra
escala y otra direccion.

Dos convenciones atraviesan todo el modulo:

1. **Los NaN son pixeles invalidos, no ceros.** El mapa de angulos llega con
   NaN en lo enmascarado (nubes, agua, norma cero). Toda metrica los excluye
   del denominador en vez de imputarlos. Un `np.nan_to_num` los convertiria en
   angulo 0, o sea en las detecciones mas fuertes del mapa: es el mismo error
   que `algorithms.sam.threshold` documenta y evita.
2. **Un denominador vacio devuelve NaN, no 0.** Una metrica que nadie puede
   calcular tiene que decirlo. Devolver 0,0 la haria indistinguible de una
   metrica calculada que dio 0, que es un resultado completamente distinto:
   "no hubo detecciones que evaluar" no es lo mismo que "todas las detecciones
   estuvieron mal". La excepcion son F1 e IoU, que se calculan por conteos y
   por eso estan definidos en casos donde precision y recall no lo estan (ver
   el docstring de `f1_score`).

Sobre scikit-learn. Esta en las dependencias del proyecto y no se usa aca a
proposito: cada metrica son diez lineas de numpy y tienen que poder explicarse
en un code review sin abrir otra libreria. sklearn si se usa en
`tests/test_metrics.py`, como oraculo independiente contra el cual contrastar
esta implementacion.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np


class ConfusionMatrix(NamedTuple):
    """Los cuatro conteos de la matriz de confusion binaria.

    Es un NamedTuple y no una tupla pelada de cuatro enteros porque el orden de
    esos cuatro numeros no tiene una convencion universal: sklearn los devuelve
    como (TN, FP, FN, TP) y la literatura suele escribirlos como
    (TP, FP, FN, TN). Desempacar una tupla con el orden de la otra convencion
    intercambia TP con TN y no lanza nada: las metricas siguen saliendo, con
    los aciertos y los rechazos correctos cambiados de lugar.
    """

    tp: int  # detectado y presente
    fp: int  # detectado y ausente (falsa alarma)
    fn: int  # no detectado y presente (omision)
    tn: int  # no detectado y ausente

    @property
    def n(self) -> int:
        """Total de pixeles que entraron en la matriz."""
        return self.tp + self.fp + self.fn + self.tn


class PrecisionRecall(NamedTuple):
    """Precision y recall, cada uno NaN cuando su denominador es cero."""

    precision: float
    recall: float


class Agreement(NamedTuple):
    """Acuerdo entre dos mascaras binarias, sin jerarquia entre ellas."""

    iou: float
    kappa: float
    n_a: int  # pixeles marcados en la mascara A
    n_b: int  # pixeles marcados en la mascara B
    n_ambas: int  # pixeles marcados en las dos
    n: int  # pixeles validos comparados


def _a_booleano(array: np.ndarray, nombre: str) -> np.ndarray:
    """Convierte un arreglo ya restringido a pixeles validos en booleano.

    Solo se llama despues de `_seleccion_valida`, que ya saco los no finitos.
    El orden importa: `np.asarray([np.nan]).astype(bool)` devuelve True, porque
    NaN no es cero. Castear antes de filtrar convertiria cada pixel enmascarado
    en una deteccion positiva, en silencio.
    """
    if array.dtype == bool:
        return array
    if not np.isfinite(array).all():
        raise ValueError(
            f"'{nombre}' todavia tiene valores no finitos al convertirlo a "
            f"booleano; hay que filtrarlos antes (NaN castea a True, no a False)."
        )
    return array != 0


def _seleccion_valida(
    forma: tuple[int, ...],
    valid: np.ndarray | None,
    *arrays: np.ndarray,
) -> np.ndarray:
    """Mascara plana de los pixeles que entran en el calculo.

    Combina dos fuentes de invalidez que el llamador no deberia tener que
    fusionar a mano: la mascara `valid` explicita (tipicamente `Scene.mask`) y
    los valores no finitos de cualquiera de los arreglos de punto flotante.

    Parameters
    ----------
    forma:
        Forma que deben compartir todos los arreglos.
    valid:
        Mascara booleana opcional. Donde es False, el pixel no entra en ningun
        conteo. None equivale a "todos entran".
    *arrays:
        Arreglos a inspeccionar. Los de punto flotante aportan su `isfinite`.

    Returns
    -------
    np.ndarray
        Mascara booleana 1D de largo `prod(forma)`.

    Raises
    ------
    ValueError
        Si `valid` no tiene la forma de los datos.
    """
    if valid is None:
        base = np.ones(forma, dtype=bool)
    else:
        base = np.asarray(valid)
        if base.shape != forma:
            raise ValueError(
                f"La mascara `valid` tiene forma {base.shape} y los datos "
                f"{forma}: una mascara de otra ventana silenciaria pixeles "
                f"arbitrarios sin que ningun conteo lo denuncie."
            )
        if np.issubdtype(base.dtype, np.floating):
            base = np.isfinite(base) & (base != 0)
        else:
            base = base.astype(bool)

    for array in arrays:
        if np.issubdtype(array.dtype, np.floating):
            base = base & np.isfinite(array)

    return base.ravel()


def _alinear(
    y_true: np.ndarray, y_pred: np.ndarray, valid: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    """Valida formas y devuelve las dos mascaras restringidas a lo valido."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    if y_true.shape != y_pred.shape:
        raise ValueError(
            f"`y_true` tiene forma {y_true.shape} y `y_pred` {y_pred.shape}; "
            f"tienen que ser el mismo raster para que los conteos signifiquen algo."
        )

    seleccion = _seleccion_valida(y_true.shape, valid, y_true, y_pred)
    verdad = _a_booleano(y_true.ravel()[seleccion], "y_true")
    prediccion = _a_booleano(y_pred.ravel()[seleccion], "y_pred")
    return verdad, prediccion


def confusion_matrix(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    valid: np.ndarray | None = None,
) -> ConfusionMatrix:
    """Cuenta TP, FP, FN y TN entre dos mascaras binarias.

    Parameters
    ----------
    y_true:
        Verdad de terreno, forma (alto, ancho) o cualquier forma compartida.
        True = el mineral esta presente. Un arreglo de punto flotante se
        interpreta como "distinto de cero es positivo", y sus NaN se descartan.
    y_pred:
        Mascara de deteccion, misma forma que `y_true`.
    valid:
        Mascara booleana opcional de pixeles evaluables. Donde es False, el
        pixel no entra en ningun conteo. None cuenta todos los pixeles.

    Returns
    -------
    ConfusionMatrix
        Los cuatro conteos como enteros de Python, mas la propiedad `n`.

    Raises
    ------
    ValueError
        Si `y_true` y `y_pred` no tienen la misma forma, o si `valid` no calza
        con ellos.
    """
    verdad, prediccion = _alinear(y_true, y_pred, valid)

    return ConfusionMatrix(
        tp=int(np.count_nonzero(verdad & prediccion)),
        fp=int(np.count_nonzero(~verdad & prediccion)),
        fn=int(np.count_nonzero(verdad & ~prediccion)),
        tn=int(np.count_nonzero(~verdad & ~prediccion)),
    )


def precision_recall(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    valid: np.ndarray | None = None,
) -> PrecisionRecall:
    """Precision y recall de la deteccion, con NaN donde no estan definidos.

    Que devuelve cuando el denominador es cero, y por que. La precision es
    TP/(TP+FP): el denominador es el numero de detecciones. Con cero
    detecciones --el regimen real de este proyecto, 62 pixeles de 4 millones y
    cero bajo umbrales mas estrictos-- no hay ninguna deteccion cuya calidad
    medir, y la respuesta correcta es **NaN**, no 0,0. Devolver 0,0 afirmaria
    que todas las detecciones fueron falsas alarmas, que es una medicion
    concreta y distinta; ademas promedia y se grafica como si fuera un dato,
    con lo cual un barrido de umbrales que no detecta nada dibujaria una curva
    de precision cayendo a cero en vez de un tramo sin definir. El recall es
    TP/(TP+FN): su denominador es la cantidad de positivos que hay en la verdad
    de terreno, y solo es cero si la verdad de terreno no tiene ni un positivo,
    caso en que tambien devuelve NaN.

    Parameters
    ----------
    y_true:
        Verdad de terreno, True = presente.
    y_pred:
        Mascara de deteccion, misma forma.
    valid:
        Mascara booleana opcional de pixeles evaluables.

    Returns
    -------
    PrecisionRecall
        `precision` = TP/(TP+FP) o NaN si no hubo detecciones.
        `recall` = TP/(TP+FN) o NaN si la verdad no tiene positivos.
    """
    matriz = confusion_matrix(y_true, y_pred, valid=valid)

    detecciones = matriz.tp + matriz.fp
    positivos = matriz.tp + matriz.fn

    return PrecisionRecall(
        precision=matriz.tp / detecciones if detecciones else float("nan"),
        recall=matriz.tp / positivos if positivos else float("nan"),
    )


def f1_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    valid: np.ndarray | None = None,
) -> float:
    """Media armonica de precision y recall, calculada por conteos.

    Se calcula como ``2*TP / (2*TP + FP + FN)`` y no como ``2*P*R / (P + R)``,
    y no es lo mismo aunque algebraicamente coincidan donde las dos estan
    definidas. Con cero detecciones sobre una verdad de terreno que si tiene
    positivos, la precision es NaN (ver `precision_recall`) y la formula con P
    y R propagaria ese NaN; la formula por conteos da ``0 / (0 + 0 + FN) = 0``,
    que es la respuesta correcta y util: el detector no encontro nada de lo que
    habia que encontrar. El unico caso realmente indefinido es que el
    denominador entero sea cero, o sea que no haya ni positivos en la verdad ni
    detecciones, y ahi devuelve NaN.

    Parameters
    ----------
    y_true:
        Verdad de terreno, True = presente.
    y_pred:
        Mascara de deteccion, misma forma.
    valid:
        Mascara booleana opcional de pixeles evaluables.

    Returns
    -------
    float
        F1 en [0, 1], o NaN si no hay positivos ni detecciones.
    """
    matriz = confusion_matrix(y_true, y_pred, valid=valid)

    denominador = 2 * matriz.tp + matriz.fp + matriz.fn
    if denominador == 0:
        return float("nan")
    return 2 * matriz.tp / denominador


def iou_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    valid: np.ndarray | None = None,
) -> float:
    """Indice de Jaccard: interseccion sobre union de las dos mascaras.

    Se calcula como ``TP / (TP + FP + FN)``. Los TN no aparecen, y es la
    diferencia que lo hace util aca: en un problema con 0,002 % de positivos la
    exactitud (accuracy) es 99,998 % para un detector que no detecta nada,
    porque los TN dominan el conteo. El IoU ignora ese fondo y solo mira la
    union de lo detectado con lo presente.

    Parameters
    ----------
    y_true:
        Verdad de terreno, True = presente.
    y_pred:
        Mascara de deteccion, misma forma.
    valid:
        Mascara booleana opcional de pixeles evaluables.

    Returns
    -------
    float
        IoU en [0, 1], o NaN si la union es vacia (ni positivos ni
        detecciones), que es el unico caso en que no esta definido.
    """
    matriz = confusion_matrix(y_true, y_pred, valid=valid)

    union = matriz.tp + matriz.fp + matriz.fn
    if union == 0:
        return float("nan")
    return matriz.tp / union


def cohen_kappa(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    valid: np.ndarray | None = None,
) -> float:
    """Kappa de Cohen: acuerdo observado corregido por el acuerdo esperado al azar.

    La formula es ``kappa = (po - pe) / (1 - pe)``, donde:

    - ``po = (TP + TN) / N`` es el **acuerdo observado**, la fraccion de
      pixeles en que las dos mascaras dicen lo mismo.
    - ``pe = [(TP+FP)(TP+FN) + (FN+TN)(FP+TN)] / N^2`` es el **acuerdo esperado
      por azar**. Sale de suponer que las dos mascaras son independientes y que
      cada una conserva su proporcion de positivos: la probabilidad de que
      ambas digan "positivo" en el mismo pixel es el producto de sus tasas
      marginales de positivos, y analogamente para "negativo". Sumadas, dan el
      acuerdo que se obtendria barajando las dos mascaras.

    Kappa vale 1 con acuerdo perfecto, 0 cuando el acuerdo observado es
    exactamente el que daria el azar, y es negativo cuando es peor que el azar.

    **En un problema con 0,002 % de positivos kappa se comporta de forma poco
    intuitiva, y hay que decirlo antes de reportarlo.** Con esa prevalencia, pe
    es practicamente 1: casi todo el acuerdo entre dos mascaras cualesquiera es
    acuerdo sobre pixeles negativos, y el azar ya lo consigue solo. El
    denominador ``1 - pe`` se vuelve minusculo, asi que kappa amplifica
    muchisimo unos pocos pixeles: un solo TP puede mover el valor varias
    decimas, y kappa se desploma apenas aparecen unos pocos FP aunque el
    detector haya acertado la mayoria de los positivos. Es una metrica de
    acuerdo, no de deteccion, y a esta prevalencia su valor absoluto no es
    comparable con el de otro problema con otra tasa de positivos.

    Parameters
    ----------
    y_true:
        Primera mascara. En el uso clasico, la verdad de terreno.
    y_pred:
        Segunda mascara, misma forma. La formula es simetrica: intercambiar los
        dos argumentos da el mismo kappa.
    valid:
        Mascara booleana opcional de pixeles evaluables.

    Returns
    -------
    float
        Kappa en [-1, 1], o NaN si `pe` es exactamente 1 (las dos mascaras
        constantes y del mismo valor: no hay variabilidad que corregir) o si no
        queda ningun pixel valido.
    """
    matriz = confusion_matrix(y_true, y_pred, valid=valid)
    n = matriz.n

    if n == 0:
        return float("nan")

    po = (matriz.tp + matriz.tn) / n
    pe = (
        (matriz.tp + matriz.fp) * (matriz.tp + matriz.fn)
        + (matriz.fn + matriz.tn) * (matriz.fp + matriz.tn)
    ) / (n * n)

    if pe == 1.0:
        return float("nan")
    return (po - pe) / (1.0 - pe)


def roc_curve(
    y_true: np.ndarray,
    y_score: np.ndarray,
    valid: np.ndarray | None = None,
    higher_is_better: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Curva ROC completa: FPR, TPR y los umbrales donde la curva cambia.

    Barre **todos** los umbrales relevantes --un punto por cada valor distinto
    del puntaje-- y no una grilla arbitraria de cinco valores. Una grilla fija
    no es una curva ROC: es un muestreo de cinco puntos de ella, y el area bajo
    esos cinco puntos depende de donde se pusieron.

    Sobre `higher_is_better`, que es la razon de ser de este parametro. Ver
    `docs/es/decisiones_tecnicas.md`, seccion 8.

    El default `True` es la convencion estandar de la literatura y de sklearn:
    puntaje mas alto = mas evidencia de positivo. **SAM no cumple esa
    convencion**: devuelve un angulo espectral, donde MENOR es mas parecido.
    Pasarle el angulo crudo a esta funcion sin declarar la direccion no lanza
    ningun error y no produce ninguna advertencia: devuelve la curva reflejada
    y un AUC invertido, ``1 - AUC``. Un detector que en realidad separa con AUC
    0,82 se reporta como 0,18, que es un numero perfectamente plausible, en el
    rango correcto, y exactamente al reves. Con `higher_is_better=False` la
    funcion niega internamente el puntaje antes de rankear, que es la operacion
    que endereza la direccion sin tocar el detector.

    El parametro **no** tiene un default que "haga lo correcto" segun el
    contenido: no hay forma de mirar un arreglo de flotantes y saber si son
    angulos o probabilidades. Quien pase un angulo tiene que escribirlo.

    Los umbrales se devuelven **en la escala original del puntaje**, tambien
    cuando `higher_is_better=False`: con angulos salen angulos, no sus
    negativos. La regla de deteccion asociada cambia con la direccion, y es la
    misma que ya usa `algorithms.sam.threshold`:

    - con `higher_is_better=True`, el punto `i` corresponde a detectar donde
      ``y_score >= umbrales[i]``;
    - con `higher_is_better=False`, a detectar donde ``y_score <= umbrales[i]``.

    El primer punto de la curva es siempre (0, 0), el umbral que no detecta
    nada, y su umbral asociado es +inf o -inf segun la direccion.

    Parameters
    ----------
    y_true:
        Verdad de terreno, True = presente. Misma forma que `y_score`.
    y_score:
        Puntaje continuo del detector. Sus NaN se descartan junto con los
        pixeles correspondientes de `y_true`.
    valid:
        Mascara booleana opcional de pixeles evaluables.
    higher_is_better:
        True si un puntaje mayor significa mas evidencia (default, convencion
        estandar). False para puntajes donde menor es mejor, como el angulo
        espectral de SAM.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray]
        `(fpr, tpr, umbrales)`, los tres del mismo largo y ordenados de menor a
        mayor FPR. Si la verdad de terreno no tiene positivos o no tiene
        negativos, la curva no esta definida: se devuelven tres arreglos de un
        solo NaN, en vez de lanzar, porque es un caso que el barrido de umbral
        de este proyecto atraviesa de forma rutinaria.

    Raises
    ------
    ValueError
        Si las formas no calzan.
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=np.float64)

    if y_true.shape != y_score.shape:
        raise ValueError(
            f"`y_true` tiene forma {y_true.shape} y `y_score` {y_score.shape}; "
            f"tienen que ser el mismo raster."
        )

    seleccion = _seleccion_valida(y_true.shape, valid, y_true, y_score)
    verdad = _a_booleano(y_true.ravel()[seleccion], "y_true")
    puntaje = y_score.ravel()[seleccion]

    positivos = int(np.count_nonzero(verdad))
    negativos = int(verdad.size - positivos)

    if positivos == 0 or negativos == 0:
        nan = np.array([np.nan])
        return nan, nan.copy(), nan.copy()

    # Rankear siempre "mayor primero" y enderezar la direccion negando. Negar
    # es exacto en punto flotante (solo cambia el bit de signo), asi que no
    # introduce ningun empate ni desempate que no estuviera ya en el puntaje.
    orientado = puntaje if higher_is_better else -puntaje

    # `mergesort` es estable: dos pixeles con el mismo puntaje conservan su
    # orden relativo, y por lo tanto la curva sale igual en dos corridas.
    orden = np.argsort(-orientado, kind="mergesort")
    orientado = orientado[orden]
    verdad = verdad[orden]

    tps = np.cumsum(verdad)
    fps = np.cumsum(~verdad)

    # Un punto por cada valor distinto de puntaje, quedandose con el ULTIMO
    # indice de cada grupo de empates. Cortar en medio de un grupo de empates
    # afirmaria que un umbral puede separar dos pixeles con el mismo puntaje,
    # que es justamente lo que un umbral no puede hacer: infla el AUC de forma
    # optimista en cualquier puntaje con valores repetidos.
    ultimos = np.r_[np.flatnonzero(np.diff(orientado)), orientado.size - 1]

    tpr = np.r_[0.0, tps[ultimos] / positivos]
    fpr = np.r_[0.0, fps[ultimos] / negativos]
    umbrales = np.r_[np.inf, orientado[ultimos]]

    # Devolver los umbrales en la escala del puntaje que entro, no en la
    # interna: un barrido que imprima "-0,15" donde el usuario piensa en
    # angulos es inutilizable. El +inf del primer punto pasa a -inf, que con la
    # regla `<=` es igualmente el umbral que no detecta nada.
    if not higher_is_better:
        umbrales = -umbrales

    return fpr, tpr, umbrales


def roc_auc(
    y_true: np.ndarray,
    y_score: np.ndarray,
    valid: np.ndarray | None = None,
    higher_is_better: bool = True,
) -> float:
    """Area bajo la curva ROC, por regla del trapecio.

    Interpretacion: es la probabilidad de que un pixel positivo tomado al azar
    reciba mejor puntaje que un pixel negativo tomado al azar. 0,5 es azar y 1
    es separacion perfecta. Un AUC **menor** que 0,5 casi nunca significa "el
    detector es peor que el azar": significa que el puntaje entro con la
    direccion invertida.

    Es la metrica que mas se presta a ese error silencioso, porque un AUC
    invertido sigue siendo un numero en [0, 1] con aspecto de resultado. Con el
    angulo espectral de SAM hay que pasar ``higher_is_better=False``.

    Que dice el AUC que el F1 no: el F1 evalua **una** mascara binaria, o sea
    un umbral ya elegido, y cambia si se cambia el umbral. El AUC resume el
    ordenamiento completo que produce el puntaje, sobre todos los umbrales a la
    vez, y por eso separa "el detector no ordena bien los pixeles" de "el
    detector ordena bien pero el umbral esta mal puesto". Son la pregunta del
    algoritmo y la pregunta de la calibracion, y conviene no mezclarlas.

    Parameters
    ----------
    y_true:
        Verdad de terreno, True = presente.
    y_score:
        Puntaje continuo del detector. Sus NaN se descartan.
    valid:
        Mascara booleana opcional de pixeles evaluables.
    higher_is_better:
        True si un puntaje mayor significa mas evidencia (default). False para
        el angulo espectral de SAM.

    Returns
    -------
    float
        AUC en [0, 1], o NaN si la verdad de terreno no tiene positivos o no
        tiene negativos, caso en que la curva ROC no esta definida.
    """
    fpr, tpr, _ = roc_curve(
        y_true, y_score, valid=valid, higher_is_better=higher_is_better
    )

    if fpr.size == 1 and not np.isfinite(fpr[0]):
        return float("nan")

    return float(np.trapezoid(tpr, fpr))


def spatial_enrichment(
    detection: np.ndarray,
    zones: np.ndarray,
    valid: np.ndarray | None = None,
) -> float:
    """Enriquecimiento espacial (E3): cuanto mas densamente detecta dentro de
    `zones` que fuera.

    Es la razon entre dos tasas::

        tasa_dentro = detecciones dentro de zones / pixeles validos dentro
        tasa_fuera  = detecciones fuera de zones  / pixeles validos fuera
        enriquecimiento = tasa_dentro / tasa_fuera

    **Por que la razon y no la fraccion cruda de detecciones que caen dentro.**
    La fraccion cruda depende del tamano de la zona y no del detector: una zona
    que cubra el 90 % del AOI recibiria el 90 % de las detecciones aunque estas
    se hubieran repartido tirando dados, y ese 0,9 se leeria como un exito
    rotundo. La razon normaliza por el area de cada lado, asi que un detector
    indiferente a la geologia da 1 con cualquier tamano de zona.

    Como se lee el valor:

    - **1** = ninguna preferencia espacial. Las detecciones se reparten dentro
      y fuera en proporcion al area de cada region, que es lo que haria el azar.
    - **> 1** = las detecciones se concentran en la zona. Un valor de 3 dice que
      dentro de la zona la densidad de detecciones es el triple que fuera.
    - **< 1** = se concentran fuera, que para una zona de alteracion documentada
      es evidencia en contra del detector.

    El valor **no** es una probabilidad y no tiene cota superior, y no dice nada
    sobre si las detecciones son correctas: dice donde caen. Con una zona mal
    delimitada el numero sale igual.

    Parameters
    ----------
    detection:
        Mascara booleana de detecciones, forma (alto, ancho).
    zones:
        Mascara booleana de las zonas de interes (p. ej. alteracion hidrotermal
        documentada), misma forma.
    valid:
        Mascara booleana opcional de pixeles evaluables. Importa mas que en las
        otras metricas: si el enmascarado de nubes se come justo la mitad de la
        zona, el denominador de dentro tiene que encogerse con ella.

    Returns
    -------
    float
        La razon de tasas. Casos sin definir, todos NaN: no queda ningun pixel
        valido dentro de la zona, no queda ninguno fuera (la zona cubre todo el
        AOI evaluable, y entonces no hay con que comparar), o no hay ninguna
        deteccion en ninguno de los dos lados. Devuelve **inf** cuando hay
        detecciones dentro y exactamente cero fuera: es el caso limite de
        concentracion total, y es un resultado real y no un error de calculo.

    Raises
    ------
    ValueError
        Si las formas no calzan.
    """
    detection = np.asarray(detection)
    zones = np.asarray(zones)

    if detection.shape != zones.shape:
        raise ValueError(
            f"`detection` tiene forma {detection.shape} y `zones` "
            f"{zones.shape}; tienen que ser el mismo raster."
        )

    seleccion = _seleccion_valida(detection.shape, valid, detection, zones)
    detecciones = _a_booleano(detection.ravel()[seleccion], "detection")
    zona = _a_booleano(zones.ravel()[seleccion], "zones")

    n_dentro = int(np.count_nonzero(zona))
    n_fuera = int(zona.size - n_dentro)

    if n_dentro == 0 or n_fuera == 0:
        return float("nan")

    tasa_dentro = np.count_nonzero(detecciones & zona) / n_dentro
    tasa_fuera = np.count_nonzero(detecciones & ~zona) / n_fuera

    if tasa_fuera == 0.0:
        # Sin detecciones a ningun lado no hay nada que comparar; con
        # detecciones solo dentro, la concentracion es total.
        return float("nan") if tasa_dentro == 0.0 else float("inf")

    return tasa_dentro / tasa_fuera


def agreement(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    valid: np.ndarray | None = None,
) -> Agreement:
    """Acuerdo entre dos mascaras binarias (E5), sin suponer cual es la verdad.

    Es deliberadamente simetrica. El caso de uso es cruzar la deteccion de SAM
    con la mascara del clay ratio, y el clay ratio **no es verdad de terreno**:
    es una segunda opinion derivada de las mismas dos bandas de la misma imagen.
    Llamar a una "prediccion" y a la otra "verdad" en ese cruce invitaria a leer
    la precision resultante como si midiera aciertos, cuando lo unico que se
    esta midiendo es cuanto se parecen dos criterios que pueden equivocarse
    juntos.

    Por eso devuelve IoU y kappa, que son las dos metricas simetricas del
    modulo, y no precision ni recall, que no lo son.

    Como leer el resultado. Un IoU cerca de 0 dice que las dos mascaras marcan
    pixeles casi disjuntos. Con tasas de positivos muy bajas eso es esperable
    incluso entre dos criterios razonables, asi que el numero solo significa
    algo comparado contra el que da una mascara aleatoria de la misma tasa de
    positivos: es lo que hace `scripts/sweep_threshold.py`.

    Parameters
    ----------
    mask_a:
        Primera mascara booleana.
    mask_b:
        Segunda mascara booleana, misma forma.
    valid:
        Mascara booleana opcional de pixeles evaluables.

    Returns
    -------
    Agreement
        `iou` y `kappa` del cruce, mas los conteos que los originan (`n_a`,
        `n_b`, `n_ambas`, `n`) para que un IoU bajo se pueda diagnosticar sin
        recalcular nada: dos mascaras de tamanos muy distintos dan IoU bajo por
        construccion, y eso se ve comparando `n_a` con `n_b`.

    Raises
    ------
    ValueError
        Si las formas no calzan.
    """
    primera, segunda = _alinear(mask_a, mask_b, valid)

    return Agreement(
        iou=iou_score(primera, segunda),
        kappa=cohen_kappa(primera, segunda),
        n_a=int(np.count_nonzero(primera)),
        n_b=int(np.count_nonzero(segunda)),
        n_ambas=int(np.count_nonzero(primera & segunda)),
        n=int(primera.size),
    )
