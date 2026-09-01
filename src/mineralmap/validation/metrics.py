"""Metricas de validacion: matriz de confusion, F1, IoU, ROC/AUC, kappa.

Este modulo convierte dos rasters alineados --- el mapa de puntaje del detector
y la verdad de terreno --- en los numeros que dicen si el detector sirve.

Por que no se usa scikit-learn
------------------------------
`scikit-learn` es una dependencia declarada del proyecto, pero no aparece en el
camino de produccion de este modulo. El repo ya verifica el SAM contra casos
cuyo valor exacto se conoce por geometria, no contra otra implementacion, y las
metricas siguen el mismo criterio: los tests las contrastan contra literales
calculados a mano. Un test que compara dos librerias solo demuestra que ambas
coinciden, no que alguna acierta. `sklearn` si se usa **dentro de los tests**
como oraculo de contraste opcional, bajo `pytest.importorskip`.

Por que hay un solo lugar que decide que pixeles entran
-------------------------------------------------------
`preparar_pares` es el unico sitio donde se filtra. Si cada metrica aplicara su
propio filtro, bastaria con que una olvidara excluir los ambiguos para que la
tabla mezclara numeros calculados sobre poblaciones distintas: la matriz de
confusion sobre 242.967 pixeles y el AUC sobre 3.993.936, presentados en la
misma columna, sin que nada falle. Todas las demas funciones de este modulo
reciben arreglos ya filtrados y no vuelven a filtrar.

La direccion del puntaje no se adivina
--------------------------------------
El puntaje del SAM es el angulo espectral: **menor es mas evidencia**. Un AUC
de 0,23 y uno de 0,77 son el mismo calculo con el signo cambiado y ninguno de
los dos lanza una excepcion. Por eso `roc_auc` y `curva_roc` exigen
`higher_is_better` como argumento **obligatorio y por palabra clave**. Ver la
nota de diseno en el docstring de `roc_auc`.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import numpy as np

# Las tres clases las define la capa que construye la verdad de terreno. Se
# importan en vez de redeclararse: dos definiciones del valor "ambiguo" que
# empiecen iguales y se separen despues es justo el fallo que este modulo no
# puede permitirse, porque el sintoma seria una metrica plausible.
from mineralmap.validation.geology import (
    CLASE_AMBIGUO,
    CLASE_NEGATIVO,
    CLASE_POSITIVO,
)


class MatrizConfusion(NamedTuple):
    """Los cuatro conteos de la matriz de confusion, nombrados.

    Se devuelve un NamedTuple y no un array 2x2 a proposito: en un array hay
    que acordarse de si las filas son la verdad o la prediccion, y las dos
    convenciones existen en la literatura. Transponerlo por error intercambia
    `fp` y `fn`, lo que deja la exactitud y el kappa intactos e invierte
    precision y recall. Con nombres, ese error no se puede cometer en silencio.
    """

    vp: int
    fp: int
    fn: int
    vn: int

    @property
    def total(self) -> int:
        """Pixeles sobre los que se calculo la matriz."""
        return self.vp + self.fp + self.fn + self.vn


class ParesEvaluables(NamedTuple):
    """Salida de `preparar_pares`: los dos vectores y por que se descarto el resto."""

    y_true: np.ndarray
    y_score: np.ndarray
    descartes: dict


def preparar_pares(
    scores: np.ndarray,
    ground_truth: np.ndarray,
    mask: np.ndarray | None = None,
) -> ParesEvaluables:
    """Filtra los dos rasters a los pixeles sobre los que se puede medir.

    Es el **unico** lugar del modulo que decide que pixel entra al calculo. Un
    pixel entra solo si cumple las tres condiciones a la vez: su verdad de
    terreno es positivo o negativo, su puntaje no es NaN, y la mascara del
    Scene --- si se pasa --- lo declara valido.

    Por que se excluyen los ambiguos en vez de colapsarlos a negativo
    ----------------------------------------------------------------
    El `255` significa "la cartografia no dice"; el `0` significa "la
    cartografia dice que no hay". Colapsarlos convierte una ausencia de
    informacion en evidencia negativa. Sobre este AOI, donde el 93,9 % del area
    es ambigua y los positivos son el 1,27 %, esa sustitucion regala millones de
    verdaderos negativos gratis: la exactitud sube por encima del 98 % sin que
    el detector haya acertado nada, y ninguna funcion lanza una excepcion.

    Parameters
    ----------
    scores:
        Mapa de puntaje del detector, forma `(alto, ancho)`. Puede traer NaN en
        los pixeles que la mascara SCL invalido. No se le aplica ningun umbral
        aca: sale tal cual, en las unidades del detector.
    ground_truth:
        Raster de verdad de terreno de la misma forma, con los valores de
        `CLASE_POSITIVO`, `CLASE_NEGATIVO` y `CLASE_AMBIGUO`. Se acepta float
        porque `write_geotiff` escribe todo como float32: los tres valores de
        clase son enteros pequenos, exactamente representables en float32, asi
        que la comparacion por igualdad es segura. Un NaN aca se trata como
        ambiguo --- es el nodata que declara el GeoTIFF --- y se cuenta aparte.
    mask:
        Mascara booleana de validez del Scene, `True` = pixel valido. Opcional.
        Hoy es redundante con los NaN del puntaje (el pipeline propaga la misma
        mascara), pero eso es una coincidencia del pipeline actual, no una
        garantia del contrato: un detector que devolviera 0 en vez de NaN sobre
        pixeles invalidos los colaria como detecciones perfectas.

    Returns
    -------
    ParesEvaluables
        `y_true` en `uint8` con valores en {0, 1}, `y_score` en `float64`, ambos
        1-D, del mismo largo y alineados posicionalmente; mas un dict
        `descartes` con cuantos pixeles se fueron por cada causa.

        Las causas se cuentan con **precedencia**, en este orden: `ambiguo`,
        `gt_nan`, `score_nan`, `mascara`. Un pixel que sea ambiguo y ademas
        tenga el puntaje en NaN se cuenta una sola vez, en `ambiguo`. Se hace
        asi para que las cuatro causas mas `evaluados` sumen exactamente el
        total de pixeles: un desglose donde las causas se solapan no cuadra con
        el total y obliga a quien lee la tabla a adivinar si falta algo.

    Raises
    ------
    ValueError
        Si las formas no calzan, si algun arreglo esta vacio, si la verdad de
        terreno trae un valor que no es ninguna de las tres clases declaradas, o
        si tras el filtro no queda ningun pixel.

        El valor desconocido en la verdad de terreno se rechaza en vez de
        ignorarse: significa que el raster no salio de `build_ground_truth` o
        que las clases cambiaron, y en ambos casos seguir calculando produce una
        tabla de metricas sobre una poblacion que nadie definio.
    """
    puntaje = np.asarray(scores)
    verdad = np.asarray(ground_truth)

    if puntaje.shape != verdad.shape:
        raise ValueError(
            f"El mapa de puntaje {puntaje.shape} y la verdad de terreno "
            f"{verdad.shape} no tienen la misma forma. Compararlos pixel a "
            "pixel produciria numeros impecables sobre pares de pixeles que no "
            "corresponden al mismo punto del terreno."
        )
    if puntaje.size == 0:
        raise ValueError("Los rasters estan vacios; no hay nada que medir.")

    if mask is not None:
        mascara = np.asarray(mask)
        if mascara.shape != puntaje.shape:
            raise ValueError(
                f"La mascara {mascara.shape} no tiene la forma de los rasters "
                f"{puntaje.shape}."
            )
        valida = mascara.astype(bool)
    else:
        valida = np.ones(puntaje.shape, dtype=bool)

    puntaje = puntaje.ravel().astype(np.float64)
    verdad = verdad.ravel()
    valida = valida.ravel()

    gt_nan = np.isnan(verdad) if np.issubdtype(verdad.dtype, np.floating) else None
    if gt_nan is None:
        gt_nan = np.zeros(verdad.shape, dtype=bool)

    es_positivo = (verdad == CLASE_POSITIVO) & ~gt_nan
    es_negativo = (verdad == CLASE_NEGATIVO) & ~gt_nan
    es_ambiguo = (verdad == CLASE_AMBIGUO) & ~gt_nan

    desconocidos = ~(es_positivo | es_negativo | es_ambiguo | gt_nan)
    if desconocidos.any():
        valores = np.unique(verdad[desconocidos])
        raise ValueError(
            f"La verdad de terreno trae {int(desconocidos.sum())} pixeles con "
            f"valores que no son ninguna de las tres clases declaradas "
            f"({CLASE_POSITIVO} positivo, {CLASE_NEGATIVO} negativo, "
            f"{CLASE_AMBIGUO} ambiguo): {valores[:10].tolist()}. El raster no "
            "salio de `build_ground_truth` o las clases cambiaron."
        )

    score_nan = np.isnan(puntaje)

    # Precedencia. Cada mascara excluye a las anteriores para que los conteos
    # sumen el total y no haya que explicar solapamientos en la tabla.
    d_ambiguo = es_ambiguo
    d_gt_nan = gt_nan & ~d_ambiguo
    d_score_nan = score_nan & ~d_ambiguo & ~d_gt_nan
    d_mascara = ~valida & ~d_ambiguo & ~d_gt_nan & ~d_score_nan

    evaluables = (es_positivo | es_negativo) & ~score_nan & valida

    descartes = {
        "ambiguo": int(d_ambiguo.sum()),
        "gt_nan": int(d_gt_nan.sum()),
        "score_nan": int(d_score_nan.sum()),
        "mascara": int(d_mascara.sum()),
    }

    if not evaluables.any():
        raise ValueError(
            "Tras excluir ambiguos, NaN y pixeles enmascarados no queda ningun "
            f"pixel evaluable (descartes: {descartes}). Sin pixeles no hay "
            "metrica que calcular."
        )

    y_true = es_positivo[evaluables].astype(np.uint8)
    y_score = puntaje[evaluables]

    descartes["evaluados"] = int(evaluables.sum())
    descartes["total"] = int(verdad.size)
    descartes["positivos"] = int(y_true.sum())
    descartes["negativos"] = int(y_true.size - y_true.sum())

    return ParesEvaluables(y_true=y_true, y_score=y_score, descartes=descartes)


def _validar_etiquetas(y_true: np.ndarray, otro: np.ndarray, nombre: str):
    """Comprueba forma, no-vacuidad y dominio de dos vectores alineados.

    Centraliza las cuatro validaciones que toda metrica necesita para que el
    mensaje de error sea el mismo se llame a la funcion que se llame.

    Raises
    ------
    ValueError
        Si las formas difieren, si estan vacios, o si `y_true` trae algo que no
        sea 0 o 1. Lo ultimo atrapa el error de pasar la verdad de terreno cruda
        --- con sus 255 --- en vez de la salida de `preparar_pares`, que si no
        se detecta hace que los ambiguos cuenten como positivos.
    """
    verdad = np.asarray(y_true)
    comparado = np.asarray(otro)

    if verdad.shape != comparado.shape:
        raise ValueError(
            f"y_true {verdad.shape} y {nombre} {comparado.shape} no tienen la "
            "misma forma."
        )
    if verdad.size == 0:
        raise ValueError(f"y_true y {nombre} estan vacios; no hay nada que medir.")

    verdad = verdad.ravel()
    comparado = comparado.ravel()

    fuera = np.unique(verdad[(verdad != 0) & (verdad != 1)])
    if fuera.size:
        raise ValueError(
            f"y_true solo admite 0 y 1; encontre {fuera[:10].tolist()}. Si "
            f"estas pasando la verdad de terreno cruda, los {CLASE_AMBIGUO} "
            "hay que excluirlos primero con `preparar_pares`."
        )

    return verdad, comparado


def _validar_prediccion(y_true: np.ndarray, y_pred: np.ndarray):
    """Igual que `_validar_etiquetas`, exigiendo ademas que `y_pred` sea 0/1."""
    verdad, prediccion = _validar_etiquetas(y_true, y_pred, "y_pred")

    if prediccion.dtype == bool:
        prediccion = prediccion.astype(np.uint8)

    fuera = np.unique(prediccion[(prediccion != 0) & (prediccion != 1)])
    if fuera.size:
        raise ValueError(
            f"y_pred solo admite 0, 1 o booleanos; encontre {fuera[:10].tolist()}. "
            "Para binarizar un mapa de puntaje usa `detector.detects(scores, "
            "umbral)`, que respeta la direccion declarada por el detector, en "
            "vez de comparar a mano."
        )

    return verdad.astype(np.uint8), prediccion.astype(np.uint8)


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray) -> MatrizConfusion:
    """Cuenta verdaderos y falsos positivos y negativos.

    Parameters
    ----------
    y_true:
        Etiquetas verdaderas, valores en {0, 1}. Tal como las devuelve
        `preparar_pares`.
    y_pred:
        Prediccion binaria de la misma forma, en {0, 1} o booleana. Se obtiene
        de `detector.detects(scores, umbral)`, no de un `<=` escrito a mano: el
        SAM detecta con menor-o-igual y cualquier otro detector puede ir al
        reves.

    Returns
    -------
    MatrizConfusion
        Los cuatro conteos con nombre: `vp`, `fp`, `fn`, `vn`.

    Raises
    ------
    ValueError
        Si las formas no calzan, si los arreglos estan vacios o si alguno trae
        valores fuera de {0, 1}.
    """
    verdad, prediccion = _validar_prediccion(y_true, y_pred)

    positivo_real = verdad == 1
    positivo_pred = prediccion == 1

    return MatrizConfusion(
        vp=int(np.count_nonzero(positivo_real & positivo_pred)),
        fp=int(np.count_nonzero(~positivo_real & positivo_pred)),
        fn=int(np.count_nonzero(positivo_real & ~positivo_pred)),
        vn=int(np.count_nonzero(~positivo_real & ~positivo_pred)),
    )


def precision_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Fraccion de las detecciones que eran positivos reales: vp / (vp + fp).

    Returns
    -------
    float
        `0.0` cuando no hay ninguna deteccion (vp + fp = 0). Ver la
        justificacion en `f1_score`, que es el mismo caso y el mismo criterio.
    """
    m = confusion_matrix(y_true, y_pred)
    detecciones = m.vp + m.fp
    return float(m.vp / detecciones) if detecciones else 0.0


def recall_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Fraccion de los positivos reales que se detectaron: vp / (vp + fn).

    Returns
    -------
    float
        `0.0` cuando no hay ningun positivo real (vp + fn = 0). Ese caso no
        deberia llegar aca: `preparar_pares` no lo impide, pero `roc_auc` si lo
        rechaza, y una tabla de metricas sobre una sola clase no se sostiene.
    """
    m = confusion_matrix(y_true, y_pred)
    reales = m.vp + m.fn
    return float(m.vp / reales) if reales else 0.0


def f1_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Media armonica de precision y recall: 2*vp / (2*vp + fp + fn).

    Que pasa cuando no hay ninguna deteccion
    ----------------------------------------
    Devuelve **`0.0`**, no `ValueError` ni `nan`. Con `vp = fp = 0` la precision
    es 0/0, pero el recall es 0 y el F1 completo tambien vale 0 por la formula
    directa. Es un caso que ocurre de verdad con este dataset: con el umbral
    heredado de 0,1 rad no hay ni una deteccion dentro de las clases evaluables,
    y ese es precisamente el resultado que hay que poder reportar.

    Se eligio `0.0` sobre `ValueError` porque lanzar obligaria a envolver la
    corrida principal en un `try/except` cuyo unico trabajo seria imprimir un
    cero, y porque un detector que no detecta nada tiene rendimiento nulo, no
    rendimiento indefinido. Se eligio `0.0` sobre `nan` porque un `nan` se
    propaga en silencio a cualquier promedio o comparacion posterior.

    El unico caso genuinamente indefinido es que no haya positivos ni reales ni
    predichos (`2*vp + fp + fn = 0`). Tambien devuelve `0.0`: un conjunto sin un
    solo positivo real no es evidencia de acierto perfecto. Ese conjunto ya lo
    rechaza `roc_auc`, que es donde el problema se vuelve fatal.

    Raises
    ------
    ValueError
        Si las formas no calzan, si estan vacios o si hay valores fuera de
        {0, 1}.
    """
    m = confusion_matrix(y_true, y_pred)
    denominador = 2 * m.vp + m.fp + m.fn
    return float(2 * m.vp / denominador) if denominador else 0.0


def iou_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Interseccion sobre union de la clase positiva: vp / (vp + fp + fn).

    Es el indice de Jaccard sobre los pixeles positivos, la metrica habitual
    para comparar dos mapas de una clase. Ignora los verdaderos negativos a
    proposito, que es lo que la hace util sobre un AOI donde el 98,7 % de los
    pixeles evaluables son negativos: la exactitud premiaria a un detector que
    dijera "no" en todos lados y el IoU le da cero.

    Que pasa cuando no hay ninguna deteccion
    ----------------------------------------
    Devuelve **`0.0`**, por el mismo criterio que `f1_score`: la union es vacia
    solo si tampoco hay positivos reales, y en cualquiera de los dos casos el
    solapamiento medido es nulo.

    Raises
    ------
    ValueError
        Si las formas no calzan, si estan vacios o si hay valores fuera de
        {0, 1}.
    """
    m = confusion_matrix(y_true, y_pred)
    union = m.vp + m.fp + m.fn
    return float(m.vp / union) if union else 0.0


def cohen_kappa(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Acuerdo entre prediccion y verdad, descontando el esperado por azar.

    `kappa = (po - pe) / (1 - pe)`, con `po` el acuerdo observado y `pe` el
    acuerdo que se obtendria si ambas etiquetas fueran independientes con las
    mismas marginales. Se incluye porque la exactitud cruda sobre una clase con
    20 % de positivos ya parte del 80 % sin haber medido nada.

    Returns
    -------
    float
        En `[-1, 1]`. Vale `0.0` cuando `pe = 1`, es decir cuando prediccion y
        verdad son constantes y coinciden: ahi el azar ya explica el acuerdo
        entero y no queda margen que medir. Se devuelve `0.0` --- "ningun
        acuerdo por encima del azar" --- en vez de `nan`, que se propagaria a
        cualquier promedio posterior sin avisar.

    Raises
    ------
    ValueError
        Si las formas no calzan, si estan vacios o si hay valores fuera de
        {0, 1}.
    """
    m = confusion_matrix(y_true, y_pred)
    n = m.total

    po = (m.vp + m.vn) / n
    pe = ((m.vp + m.fp) * (m.vp + m.fn) + (m.fn + m.vn) * (m.fp + m.vn)) / (n * n)

    return float((po - pe) / (1.0 - pe)) if pe != 1.0 else 0.0


def _rangos_promedio(valores: np.ndarray) -> np.ndarray:
    """Rangos 1-based de `valores`, promediados dentro de cada grupo de empates.

    Es la pieza que hace que el AUC trate los empates de forma explicita. Sin
    promediar, el resultado dependeria del orden en que `argsort` deja los
    valores iguales, y sobre 4 millones de pixeles en float32 los empates son
    reales, no una rareza teorica.
    """
    n = valores.size
    orden = np.argsort(valores, kind="mergesort")
    ordenados = valores[orden]

    # Bordes de cada grupo de valores iguales, en indices 0-based del arreglo
    # ordenado. El primer y el ultimo borde se anaden a mano.
    cambia = np.empty(n + 1, dtype=bool)
    cambia[0] = True
    cambia[n] = True
    cambia[1:n] = ordenados[1:] != ordenados[:-1]
    bordes = np.flatnonzero(cambia)

    # Un grupo que ocupa las posiciones 0-based [a, b) tiene rangos 1-based
    # a+1 .. b, cuyo promedio es (a + b + 1) / 2.
    promedios = (bordes[:-1] + bordes[1:] + 1) / 2.0
    indice_de_grupo = np.repeat(np.arange(bordes.size - 1), np.diff(bordes))

    rangos = np.empty(n, dtype=np.float64)
    rangos[orden] = promedios[indice_de_grupo]
    return rangos


def roc_auc(
    y_true: np.ndarray, y_score: np.ndarray, *, higher_is_better: bool
) -> float:
    """Area bajo la curva ROC, con empates promediados.

    Por que `higher_is_better` es obligatorio y por palabra clave
    ------------------------------------------------------------
    El puntaje del SAM es el angulo espectral, donde **menor es mas evidencia**.
    Un AUC calculado con la direccion invertida da `1 - AUC`: 0,23 en vez de
    0,77. Ambos son numeros validos, ninguno lanza una excepcion y los dos se
    pueden defender en una presentacion. Es el error mas caro que puede cometer
    este modulo.

    De las dos salidas posibles --- un parametro explicito, o exigir que el
    llamador pase el puntaje ya orientado --- se eligio **el parametro
    explicito, sin valor por defecto y solo por palabra clave**. Razones:

    1. Un default silencioso reintroduce exactamente el fallo que se quiere
       evitar; sin default, el llamador no puede omitir la decision.
    2. `Detector.higher_is_better` ya existe como atributo del contrato, asi que
       el llamador correcto es `roc_auc(..., higher_is_better=det.higher_is_better)`
       y la direccion viaja desde su unica fuente de verdad.
    3. Exigir el puntaje pre-orientado mueve la inversion de signo al llamador,
       o sea la duplica en cada sitio que mida, y deja el mapa de angulos
       negados dando vueltas por el codigo.
    4. Por palabra clave para que no se pueda pasar por posicion a un tercer
       argumento y quedar cambiado por otro booleano cualquiera.

    Convencion de empates
    ---------------------
    Se calcula por el estadistico de Mann-Whitney U con **rangos promedio**: los
    pixeles con el mismo puntaje reciben todos el rango medio del grupo. Es
    identico a integrar la curva ROC con la **regla del trapecio** --- cada
    grupo de empates aporta el rectangulo medio y no un escalon --- y es la
    misma convencion de `sklearn.metrics.roc_auc_score`. Un par (positivo,
    negativo) empatado aporta 0,5 en vez de 0 o 1. Importa: el angulo es
    continuo, pero en float32 sobre millones de pixeles los empates exactos
    existen, y resolverlos "a favor" inflaria el AUC sin que nada falle.

    Parameters
    ----------
    y_true:
        Etiquetas verdaderas, valores en {0, 1}, ya filtradas por
        `preparar_pares`.
    y_score:
        Puntaje continuo del detector, en sus unidades originales. No se
        binariza y no se le aplica ningun umbral.
    higher_is_better:
        Direccion del puntaje. `True` = mayor valor es mas evidencia.
        Para el SAM es `False`. Tomalo de `Detector.higher_is_better`.

    Returns
    -------
    float
        AUC en `[0, 1]`. 0,5 es azar. Por debajo de 0,5 el detector ordena al
        reves de lo que declara, y eso es un resultado medido, no un error de
        signo, siempre que `higher_is_better` sea el correcto.

    Raises
    ------
    ValueError
        Si las formas no calzan, si estan vacios, si `y_true` trae valores fuera
        de {0, 1}, si `y_score` trae NaN, o si **solo hay una clase presente**.

        Lo ultimo se lanza en vez de devolver `nan`: el AUC mide la capacidad de
        ordenar positivos por delante de negativos, y con una sola clase no hay
        ningun par que ordenar. Un `nan` devuelto aca acaba impreso en una tabla
        como si fuera una medicion.
    """
    verdad, puntaje = _validar_etiquetas(y_true, y_score, "y_score")
    verdad = verdad.astype(np.uint8)
    puntaje = puntaje.astype(np.float64)

    if np.isnan(puntaje).any():
        raise ValueError(
            f"y_score trae {int(np.isnan(puntaje).sum())} NaN. Los pixeles sin "
            "dato hay que excluirlos con `preparar_pares` antes de medir; "
            "dejarlos ordena NaN al final del ranking y sesga el AUC."
        )

    n_pos = int(np.count_nonzero(verdad == 1))
    n_neg = int(verdad.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        presente = "positiva" if n_neg == 0 else "negativa"
        raise ValueError(
            f"El AUC no esta definido con una sola clase presente: los "
            f"{verdad.size} pixeles evaluables son todos de la clase "
            f"{presente}. No hay ningun par (positivo, negativo) que ordenar."
        )

    # La direccion se aplica una sola vez, aca, negando el puntaje. Todo lo que
    # sigue asume "mayor es mejor" y no vuelve a preguntar.
    orientado = puntaje if higher_is_better else -puntaje

    rangos = _rangos_promedio(orientado)
    suma_rangos_positivos = float(rangos[verdad == 1].sum())

    # Mann-Whitney U normalizado. El termino n_pos*(n_pos+1)/2 descuenta los
    # rangos que los positivos se ganan entre ellos.
    u = suma_rangos_positivos - n_pos * (n_pos + 1) / 2.0
    return float(u / (n_pos * n_neg))


class CurvaROC(NamedTuple):
    """Curva ROC completa mas los dos umbrales operativos que se derivan de ella."""

    fpr: np.ndarray
    tpr: np.ndarray
    umbrales: np.ndarray
    auc: float
    umbral_youden: float
    youden_j: float
    umbral_f1: float
    f1_maximo: float


def curva_roc(
    y_true: np.ndarray, y_score: np.ndarray, *, higher_is_better: bool
) -> CurvaROC:
    """Curva ROC completa y los umbrales que maximizan Youden y F1.

    Recorre todos los umbrales distintos que existen en `y_score` --- no una
    grilla arbitraria --- porque cualquier umbral intermedio produce exactamente
    la misma particion que el valor observado inmediatamente anterior, y una
    grilla se salta los codos de la curva o los duplica.

    Parameters
    ----------
    y_true:
        Etiquetas verdaderas en {0, 1}, ya filtradas por `preparar_pares`.
    y_score:
        Puntaje continuo, en las unidades originales del detector.
    higher_is_better:
        Direccion del puntaje, igual que en `roc_auc` y por las mismas razones.

    Returns
    -------
    CurvaROC
        `fpr` y `tpr` monotonos crecientes, y `umbrales` **en las unidades
        originales del puntaje**, no en las del puntaje orientado. Se devuelven
        sin des-orientar porque el uso inmediato es compararlos con
        `angle_threshold_rad` del config, que esta en radianes de angulo
        espectral; devolverlos negados obligaria a que quien lee la figura
        recordara invertirlos.

        Cada umbral es operativo con la semantica del detector: para el SAM
        (`higher_is_better=False`) detecta `scores <= umbral`, que es lo que
        hace `Detector.detects`.

        `umbral_youden` maximiza `TPR - FPR` y `umbral_f1` maximiza el F1. Se
        devuelven los dos porque optimizan cosas distintas: Youden pesa igual
        los dos tipos de error y F1 ignora los verdaderos negativos, asi que
        sobre una clase con 20 % de positivos no tienen por que coincidir.

    Raises
    ------
    ValueError
        Las mismas condiciones que `roc_auc`, incluida la de una sola clase.
    """
    auc = roc_auc(y_true, y_score, higher_is_better=higher_is_better)

    verdad = np.asarray(y_true).ravel().astype(np.uint8)
    puntaje = np.asarray(y_score).ravel().astype(np.float64)
    orientado = puntaje if higher_is_better else -puntaje

    n_pos = int(np.count_nonzero(verdad == 1))
    n_neg = int(verdad.size - n_pos)

    # Orden descendente del puntaje orientado: se va bajando el umbral y
    # acumulando aciertos. `mergesort` es estable, lo que hace el resultado
    # reproducible ante empates.
    orden = np.argsort(-orientado, kind="mergesort")
    s_ord = orientado[orden]
    y_ord = verdad[orden]

    vp_acum = np.cumsum(y_ord == 1)
    fp_acum = np.cumsum(y_ord == 0)

    # Un umbral solo es distinguible en el ultimo indice de cada grupo de
    # empates. Cortar dentro de un grupo daria un punto de la curva que ningun
    # umbral real puede alcanzar.
    ultimo_de_grupo = np.flatnonzero(np.r_[s_ord[1:] != s_ord[:-1], True])

    vp = vp_acum[ultimo_de_grupo]
    fp = fp_acum[ultimo_de_grupo]
    fn = n_pos - vp

    tpr = vp / n_pos
    fpr = fp / n_neg

    # (0, 0) al inicio: el umbral que no detecta nada. Sin ese punto la curva
    # no arranca en el origen y el trapecio del primer tramo queda mal.
    tpr = np.r_[0.0, tpr]
    fpr = np.r_[0.0, fpr]
    umbrales_orientados = np.r_[np.inf, s_ord[ultimo_de_grupo]]

    youden = tpr - fpr
    i_youden = int(np.argmax(youden))

    denominador_f1 = 2 * vp + fp + fn
    f1 = np.divide(
        2 * vp,
        denominador_f1,
        out=np.zeros(vp.shape, dtype=np.float64),
        where=denominador_f1 != 0,
    )
    i_f1 = int(np.argmax(f1))

    def _desorientar(valor: float) -> float:
        return float(valor) if higher_is_better else float(-valor)

    return CurvaROC(
        fpr=fpr,
        tpr=tpr,
        umbrales=np.array([_desorientar(v) for v in umbrales_orientados]),
        auc=auc,
        umbral_youden=_desorientar(umbrales_orientados[i_youden]),
        youden_j=float(youden[i_youden]),
        umbral_f1=_desorientar(s_ord[ultimo_de_grupo][i_f1]),
        f1_maximo=float(f1[i_f1]),
    )


def evaluar_deteccion(
    scores: np.ndarray,
    ground_truth: np.ndarray,
    threshold: float,
    *,
    higher_is_better: bool,
    mask: np.ndarray | None = None,
) -> dict:
    """Camino completo: filtra, binariza, calcula las seis metricas y traza todo.

    Es la funcion que consume `scripts/evaluate.py`. Existe para que el script
    no tenga que orquestar nada: pide argumentos, llama aca e imprime.

    Parameters
    ----------
    scores:
        Mapa de puntaje del detector, forma `(alto, ancho)`.
    ground_truth:
        Verdad de terreno de la misma forma, con las tres clases.
    threshold:
        Umbral con el que binarizar, en las unidades del puntaje.
    higher_is_better:
        Direccion del puntaje. Determina tanto el sentido de la comparacion con
        `threshold` como la orientacion del AUC, y por eso se pide una sola vez:
        binarizar en un sentido y medir el AUC en el otro daria una tabla donde
        el F1 y el AUC se contradicen sin que nada falle.
    mask:
        Mascara de validez del Scene, opcional.

    Returns
    -------
    dict
        Un dict de trazabilidad con la misma filosofia que el de
        `build_ground_truth`: ademas de las metricas, de donde salio cada cosa.
        Trae `umbral`, `higher_is_better`, `descartes` (los conteos por causa),
        `matriz_confusion`, `metricas` y `calibracion` (AUC, umbral de Youden y
        umbral de F1 maximo). Una tabla de metricas que no dice sobre cuantos
        pixeles se calculo no se puede defender.

    Raises
    ------
    ValueError
        Lo que propaguen `preparar_pares` y `roc_auc`.
    """
    pares = preparar_pares(scores, ground_truth, mask=mask)

    # Misma regla que `Detector.detects`, aplicada al vector ya filtrado. No se
    # llama al detector porque aca no hay uno instanciado: lo que viaja es su
    # direccion declarada, que es la unica parte del contrato que hace falta.
    if higher_is_better:
        y_pred = pares.y_score >= threshold
    else:
        y_pred = pares.y_score <= threshold

    matriz = confusion_matrix(pares.y_true, y_pred)
    curva = curva_roc(pares.y_true, pares.y_score, higher_is_better=higher_is_better)

    return {
        "umbral": float(threshold),
        "higher_is_better": bool(higher_is_better),
        "descartes": pares.descartes,
        "matriz_confusion": matriz._asdict(),
        "metricas": {
            "precision": precision_score(pares.y_true, y_pred),
            "recall": recall_score(pares.y_true, y_pred),
            "f1": f1_score(pares.y_true, y_pred),
            "iou": iou_score(pares.y_true, y_pred),
            "kappa": cohen_kappa(pares.y_true, y_pred),
            "roc_auc": curva.auc,
        },
        "calibracion": {
            "umbral_youden": curva.umbral_youden,
            "youden_j": curva.youden_j,
            "umbral_f1_maximo": curva.umbral_f1,
            "f1_maximo": curva.f1_maximo,
            "puntos_curva": int(curva.fpr.size),
        },
        # Prefijo `_`: son objetos vivos para quien dibuje la figura, no
        # parte de la trazabilidad serializable. `_volcar_json` los excluye por
        # ese prefijo en vez de por una lista de claves que habria que
        # mantener al dia.
        "_curva": curva,
        "_pares": pares,
    }


def _leer_raster(ruta: str, que_es: str):
    """Abre un GeoTIFF de una banda y devuelve el arreglo mas su georreferencia.

    Parameters
    ----------
    ruta:
        Ruta del .tif.
    que_es:
        Como nombrarlo en los mensajes de error ("mapa de puntaje", "verdad de
        terreno"). Sin esto, dos FileNotFoundError identicos obligan a mirar el
        traceback para saber cual de los dos archivos falta.

    Returns
    -------
    tuple[np.ndarray, dict]
        La banda 1 como `float64` y un dict con `crs`, `transform` y `forma`.

    Raises
    ------
    FileNotFoundError
        Si el archivo no existe. El mensaje nombra el script que lo genera.
    """
    import rasterio

    origen = Path(ruta)
    if not origen.exists():
        raise FileNotFoundError(
            f"No encontre el {que_es} en {origen}. "
            "El mapa de puntaje lo genera `python scripts/run_pipeline.py "
            "--config configs/cerro_colorado_kaolinite.yaml` y la verdad de "
            "terreno `python scripts/construir_verdad_terreno.py`."
        )

    with rasterio.open(origen) as src:
        datos = src.read(1).astype(np.float64)
        georreferencia = {
            "crs": str(src.crs),
            "transform": tuple(float(v) for v in src.transform[:6]),
            "forma": (int(src.height), int(src.width)),
        }

    return datos, georreferencia


def evaluar_desde_rasters(
    ruta_puntaje: str,
    ruta_verdad: str,
    threshold: float,
    *,
    higher_is_better: bool,
    ruta_scene: str | None = None,
) -> dict:
    """Lee los dos GeoTIFF, comprueba que estan alineados y evalua.

    Es la funcion que consume `scripts/evaluate.py`. Hace una cosa que
    `evaluar_deteccion` no puede hacer con arreglos sueltos: **comparar la
    georreferenciacion de los dos rasters antes de compararlos pixel a pixel**.

    Por que la alineacion se comprueba y no se asume
    -----------------------------------------------
    Dos rasters de la misma forma pero distinta `transform` cubren trozos
    distintos del desierto. Emparejarlos por indice produce una matriz de
    confusion, un F1 y un AUC perfectamente formados, calculados sobre pares de
    pixeles que no corresponden al mismo punto del terreno. No hay ninguna
    inspeccion de la salida que delate ese error: los numeros salen dentro de
    rango y la tabla se ve bien. Es el fallo silencioso mas caro de esta etapa,
    y por eso se aborta en vez de advertir.

    Parameters
    ----------
    ruta_puntaje:
        GeoTIFF del mapa de puntaje del detector.
    ruta_verdad:
        GeoTIFF de la verdad de terreno con las tres clases.
    threshold:
        Umbral con el que binarizar, en las unidades del puntaje.
    higher_is_better:
        Direccion del puntaje. Tomala de `Detector.higher_is_better`, no de una
        constante escrita aparte.
    ruta_scene:
        Ruta del Scene serializado del que sacar la mascara de validez.
        Opcional; `None` la omite.

    Returns
    -------
    dict
        Lo mismo que `evaluar_deteccion` mas una clave `fuentes` con las rutas,
        el CRS, la transform y la forma de cada insumo. Una tabla de metricas
        que no dice de que archivos salio no se puede auditar seis meses
        despues.

    Raises
    ------
    FileNotFoundError
        Si falta alguno de los archivos.
    ValueError
        Si los rasters no comparten CRS, transform y forma, o lo que propaguen
        `preparar_pares` y `roc_auc`.
    """
    puntaje, geo_puntaje = _leer_raster(ruta_puntaje, "mapa de puntaje")
    verdad, geo_verdad = _leer_raster(ruta_verdad, "verdad de terreno")

    desacuerdos = [
        (campo, geo_puntaje[campo], geo_verdad[campo])
        for campo in ("crs", "transform", "forma")
        if geo_puntaje[campo] != geo_verdad[campo]
    ]
    if desacuerdos:
        detalle = "; ".join(
            f"{campo}: puntaje {a} vs verdad {b}" for campo, a, b in desacuerdos
        )
        raise ValueError(
            f"Los dos rasters no estan alineados ({detalle}). Compararlos pixel "
            "a pixel daria una matriz de confusion y un AUC impecables sobre "
            "pares de pixeles que no son el mismo punto del terreno."
        )

    mask = None
    fuente_mascara = None
    if ruta_scene is not None:
        from mineralmap.io.raster_io import load_scene

        scene = load_scene(ruta_scene)
        mask = scene.mask
        fuente_mascara = {
            "ruta": str(ruta_scene),
            "pixeles_validos": int(np.count_nonzero(mask)),
        }

    resultado = evaluar_deteccion(
        puntaje,
        verdad,
        threshold,
        higher_is_better=higher_is_better,
        mask=mask,
    )
    resultado["fuentes"] = {
        "puntaje": {"ruta": str(ruta_puntaje), **geo_puntaje},
        "verdad_terreno": {"ruta": str(ruta_verdad), **geo_verdad},
        "scene": fuente_mascara,
    }
    return resultado
