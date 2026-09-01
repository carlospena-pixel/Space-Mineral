"""Pruebas de las metricas de validacion.

Sin red y sin la escena de 196 MB: todos los casos son vectores de a lo mas unas
decenas de elementos, elegidos para que el valor esperado se pueda calcular a
mano y escribirse en el test como un literal.

Ese es el criterio del repo y la razon por la que los esperados **no** se
recalculan con una segunda implementacion de la misma formula: un test que
reimplementa lo que prueba pasa igual cuando ambas copias comparten el error. El
contraste contra `sklearn` existe al final del archivo, pero como oraculo
opcional y adicional, nunca como definicion de lo correcto.
"""

import numpy as np
import pytest

from mineralmap.validation.geology import (
    CLASE_AMBIGUO,
    CLASE_NEGATIVO,
    CLASE_POSITIVO,
)
from mineralmap.validation.metrics import (
    cohen_kappa,
    confusion_matrix,
    curva_roc,
    evaluar_deteccion,
    f1_score,
    iou_score,
    precision_score,
    preparar_pares,
    recall_score,
    roc_auc,
)

# Caso base, resuelto a mano y reutilizado por varios tests.
#
#   y_true  1 1 1 1 0 0 0 0 0 0   -> 4 positivos, 6 negativos
#   y_pred  1 1 0 0 1 0 0 0 0 0   -> 3 detecciones
#
#   vp = 2   (indices 0 y 1)
#   fn = 2   (indices 2 y 3)
#   fp = 1   (indice 4)
#   vn = 5   (indices 5..9)
Y_TRUE_BASE = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
Y_PRED_BASE = np.array([1, 1, 0, 0, 1, 0, 0, 0, 0, 0], dtype=np.uint8)


# --------------------------------------------------------------------------
# Matriz de confusion y metricas de conteo
# --------------------------------------------------------------------------


def test_la_matriz_de_confusion_cuenta_las_cuatro_celdas():
    m = confusion_matrix(Y_TRUE_BASE, Y_PRED_BASE)

    assert (m.vp, m.fp, m.fn, m.vn) == (2, 1, 2, 5)
    assert m.total == 10


def test_la_matriz_se_lee_por_nombre_y_no_por_posicion():
    """Un array 2x2 transpuesto intercambia fp y fn sin que nada falle.

    Con nombres el error es imposible, y este test fija el contrato: `fp` son
    detecciones sobre negativos reales, `fn` son positivos reales no detectados.
    """
    y_true = np.array([1, 0], dtype=np.uint8)
    y_pred = np.array([0, 1], dtype=np.uint8)

    m = confusion_matrix(y_true, y_pred)

    assert m.fn == 1  # el positivo real que no se detecto
    assert m.fp == 1  # el negativo real que se detecto
    assert m.vp == 0
    assert m.vn == 0


def test_precision_y_recall_del_caso_base():
    # precision = vp / (vp + fp) = 2 / 3
    # recall    = vp / (vp + fn) = 2 / 4
    assert precision_score(Y_TRUE_BASE, Y_PRED_BASE) == pytest.approx(2 / 3)
    assert recall_score(Y_TRUE_BASE, Y_PRED_BASE) == 0.5


def test_f1_del_caso_base():
    # f1 = 2*vp / (2*vp + fp + fn) = 4 / (4 + 1 + 2) = 4/7
    assert f1_score(Y_TRUE_BASE, Y_PRED_BASE) == pytest.approx(4 / 7)


def test_iou_del_caso_base():
    # iou = vp / (vp + fp + fn) = 2 / 5
    assert iou_score(Y_TRUE_BASE, Y_PRED_BASE) == 0.4


def test_kappa_del_caso_base():
    # po = (vp + vn) / n = 7 / 10 = 0,7
    # pe = ((vp+fp)(vp+fn) + (fn+vn)(fp+vn)) / n^2
    #    = (3*4 + 7*6) / 100 = 54 / 100 = 0,54
    # kappa = (0,7 - 0,54) / (1 - 0,54) = 0,16 / 0,46
    assert cohen_kappa(Y_TRUE_BASE, Y_PRED_BASE) == pytest.approx(0.16 / 0.46)


def test_una_prediccion_perfecta_da_todo_uno():
    y = np.array([1, 1, 0, 0], dtype=np.uint8)

    assert f1_score(y, y) == 1.0
    assert iou_score(y, y) == 1.0
    assert cohen_kappa(y, y) == 1.0


def test_kappa_es_cero_cuando_el_acuerdo_es_el_del_azar():
    """Prediccion independiente de la verdad con las mismas marginales."""
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_pred = np.array([1, 0, 1, 0], dtype=np.uint8)

    # vp=1, fp=1, fn=1, vn=1 -> po = 0,5 y pe = (2*2 + 2*2)/16 = 0,5
    assert cohen_kappa(y_true, y_pred) == 0.0


def test_una_prediccion_booleana_se_acepta():
    """`Detector.detects` devuelve booleanos; deben entrar sin castear a mano."""
    y_pred_bool = Y_PRED_BASE.astype(bool)

    assert f1_score(Y_TRUE_BASE, y_pred_bool) == pytest.approx(4 / 7)


# --------------------------------------------------------------------------
# El caso desbalanceado que ocurre de verdad con este dataset
# --------------------------------------------------------------------------


def test_un_detector_que_no_detecta_nada_da_f1_e_iou_cero():
    """98 negativos y 2 positivos: decir "no" en todo da 98 % de exactitud.

    Es el caso real del AOI con el umbral heredado de 0,1 rad. F1 e IoU tienen
    que dar 0 --- y no lanzar, ni devolver nan --- para que la corrida principal
    se pueda reportar tal cual.
    """
    y_true = np.zeros(100, dtype=np.uint8)
    y_true[:2] = 1
    y_pred = np.zeros(100, dtype=np.uint8)

    m = confusion_matrix(y_true, y_pred)
    assert (m.vp, m.fp, m.fn, m.vn) == (0, 0, 2, 98)

    # La exactitud, que este modulo no expone a proposito, valdria 0,98.
    assert (m.vp + m.vn) / m.total == 0.98

    assert f1_score(y_true, y_pred) == 0.0
    assert iou_score(y_true, y_pred) == 0.0
    assert precision_score(y_true, y_pred) == 0.0
    assert recall_score(y_true, y_pred) == 0.0
    assert cohen_kappa(y_true, y_pred) == 0.0


def test_sin_positivos_reales_ni_predichos_f1_e_iou_valen_cero():
    """El caso 0/0 documentado: se devuelve 0.0, nunca 1.0 ni nan."""
    y = np.zeros(5, dtype=np.uint8)

    assert f1_score(y, y) == 0.0
    assert iou_score(y, y) == 0.0


# --------------------------------------------------------------------------
# ROC / AUC: direccion del puntaje y empates
# --------------------------------------------------------------------------


def test_auc_sin_empates_calculado_a_mano():
    """4 pares (positivo, negativo); 3 quedan bien ordenados -> 3/4."""
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_score = np.array([0.9, 0.4, 0.6, 0.1])

    # (0,9 vs 0,6) bien, (0,9 vs 0,1) bien, (0,4 vs 0,6) mal, (0,4 vs 0,1) bien
    assert roc_auc(y_true, y_score, higher_is_better=True) == 0.75


def test_un_empate_entre_positivo_y_negativo_aporta_medio_par():
    """Convencion de rangos promedio, equivalente al trapecio de la ROC."""
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_score = np.array([0.9, 0.5, 0.5, 0.1])

    # (0,9 vs 0,5) = 1, (0,9 vs 0,1) = 1, (0,5 vs 0,5) = 0,5, (0,5 vs 0,1) = 1
    # -> 3,5 / 4 = 0,875. Resolver el empate "a favor" daria 1,0.
    assert roc_auc(y_true, y_score, higher_is_better=True) == 0.875


def test_todo_empatado_da_exactamente_azar():
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_score = np.full(4, 0.3)

    assert roc_auc(y_true, y_score, higher_is_better=True) == 0.5


def test_la_direccion_del_puntaje_da_aucs_complementarios():
    """auc + auc' = 1. Es el error de signo que invierte la conclusion entera.

    Un detector donde menor es mejor --- el SAM --- medido como si mayor fuera
    mejor da `1 - AUC`. Ninguno de los dos lanza nada, y los dos son defendibles
    en una presentacion; por eso `higher_is_better` no tiene default.
    """
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_score = np.array([0.9, 0.5, 0.5, 0.1])

    arriba = roc_auc(y_true, y_score, higher_is_better=True)
    abajo = roc_auc(y_true, y_score, higher_is_better=False)

    assert arriba == 0.875
    assert abajo == 0.125
    assert arriba + abajo == 1.0


def test_negar_el_puntaje_equivale_a_invertir_la_direccion():
    y_true = np.array([1, 1, 0, 0, 1], dtype=np.uint8)
    y_score = np.array([0.9, 0.5, 0.5, 0.1, 0.2])

    assert roc_auc(y_true, y_score, higher_is_better=False) == roc_auc(
        y_true, -y_score, higher_is_better=True
    )


def test_un_puntaje_donde_menor_es_mejor_se_mide_bien_al_declararlo():
    """Angulo espectral sintetico: los positivos tienen el angulo mas chico."""
    y_true = np.array([1, 1, 1, 0, 0, 0], dtype=np.uint8)
    angulos = np.array([0.10, 0.12, 0.15, 0.30, 0.40, 0.50])

    assert roc_auc(y_true, angulos, higher_is_better=False) == 1.0
    assert roc_auc(y_true, angulos, higher_is_better=True) == 0.0


def test_higher_is_better_no_se_puede_pasar_por_posicion():
    """Es keyword-only para que no lo ocupe otro booleano por accidente."""
    y_true = np.array([1, 0], dtype=np.uint8)
    y_score = np.array([0.9, 0.1])

    with pytest.raises(TypeError):
        roc_auc(y_true, y_score, False)  # type: ignore[misc]


# --------------------------------------------------------------------------
# Curva ROC y umbrales de calibracion
# --------------------------------------------------------------------------


def test_la_curva_roc_arranca_en_el_origen_y_termina_en_uno():
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_score = np.array([0.9, 0.4, 0.6, 0.1])

    curva = curva_roc(y_true, y_score, higher_is_better=True)

    assert curva.fpr[0] == 0.0 and curva.tpr[0] == 0.0
    assert curva.fpr[-1] == 1.0 and curva.tpr[-1] == 1.0
    assert np.all(np.diff(curva.fpr) >= 0)
    assert np.all(np.diff(curva.tpr) >= 0)


def test_los_umbrales_salen_en_las_unidades_originales_del_puntaje():
    """Con higher_is_better=False no se devuelve el puntaje negado.

    Si se devolvieran orientados, compararlos con `angle_threshold_rad` del
    config daria un umbral negativo que ningun angulo alcanza jamas.
    """
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    angulos = np.array([0.10, 0.20, 0.30, 0.40])

    curva = curva_roc(y_true, angulos, higher_is_better=False)

    finitos = curva.umbrales[np.isfinite(curva.umbrales)]
    assert np.all(finitos > 0)
    assert set(finitos.tolist()) == {0.10, 0.20, 0.30, 0.40}
    # El umbral que separa perfecto es 0,20: detecta `angulo <= 0,20`.
    assert curva.umbral_youden == 0.20
    assert curva.youden_j == 1.0


def test_youden_y_f1_no_tienen_por_que_coincidir():
    """F1 ignora los verdaderos negativos y Youden no; sobre clases
    desbalanceadas eligen umbrales distintos, y por eso se reportan los dos."""
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_score = np.array([0.9, 0.5, 0.5, 0.1])

    curva = curva_roc(y_true, y_score, higher_is_better=True)

    # Umbral 0,9: vp=1 fp=0 fn=1 -> tpr=0,5 fpr=0,0 -> J=0,50  F1=2/3
    # Umbral 0,5: vp=2 fp=1 fn=0 -> tpr=1,0 fpr=0,5 -> J=0,50  F1=0,8
    # Empatan en Youden (gana el primero) y no en F1.
    assert curva.umbral_youden == 0.9
    assert curva.youden_j == 0.5
    assert curva.umbral_f1 == 0.5
    assert curva.f1_maximo == pytest.approx(0.8)


def test_el_auc_de_la_curva_es_el_de_roc_auc():
    y_true = np.array([1, 1, 0, 0, 1, 0], dtype=np.uint8)
    y_score = np.array([0.9, 0.5, 0.5, 0.1, 0.7, 0.2])

    curva = curva_roc(y_true, y_score, higher_is_better=False)

    assert curva.auc == roc_auc(y_true, y_score, higher_is_better=False)


def test_el_umbral_de_f1_maximo_reproduce_el_f1_que_reporta():
    """La calibracion no sirve si el umbral que devuelve no da el F1 que dice."""
    y_true = np.array([1, 1, 1, 0, 0, 0, 1, 0], dtype=np.uint8)
    angulos = np.array([0.10, 0.12, 0.25, 0.15, 0.30, 0.40, 0.35, 0.20])

    curva = curva_roc(y_true, angulos, higher_is_better=False)
    y_pred = angulos <= curva.umbral_f1

    assert f1_score(y_true, y_pred) == pytest.approx(curva.f1_maximo)


# --------------------------------------------------------------------------
# preparar_pares: el unico filtro
# --------------------------------------------------------------------------


def _gt(valores):
    """Verdad de terreno en float32, como la escribe `write_geotiff`."""
    return np.asarray(valores, dtype=np.float32)


def test_los_ambiguos_no_cambian_ninguna_metrica():
    """Dos entradas identicas salvo por pixeles ambiguos dan lo mismo.

    Si algun dia una funcion dejara de filtrar, este test es el que lo dice:
    colapsar los 255 a negativo cambiaria la matriz de confusion y el kappa sin
    lanzar ninguna excepcion.
    """
    scores = np.array([0.10, 0.20, 0.30, 0.40])
    gt = _gt([CLASE_POSITIVO, CLASE_POSITIVO, CLASE_NEGATIVO, CLASE_NEGATIVO])

    scores_con_ambiguos = np.array([0.10, 0.20, 0.05, 0.30, 0.40, 0.01])
    gt_con_ambiguos = _gt(
        [
            CLASE_POSITIVO,
            CLASE_POSITIVO,
            CLASE_AMBIGUO,
            CLASE_NEGATIVO,
            CLASE_NEGATIVO,
            CLASE_AMBIGUO,
        ]
    )

    limpio = preparar_pares(scores, gt)
    sucio = preparar_pares(scores_con_ambiguos, gt_con_ambiguos)

    np.testing.assert_array_equal(limpio.y_true, sucio.y_true)
    np.testing.assert_array_equal(limpio.y_score, sucio.y_score)
    assert sucio.descartes["ambiguo"] == 2
    assert sucio.descartes["evaluados"] == 4

    # Los dos ambiguos tienen el angulo mas chico del conjunto: colapsarlos a
    # negativo los volveria falsos positivos y hundiria la precision.
    assert roc_auc(limpio.y_true, limpio.y_score, higher_is_better=False) == roc_auc(
        sucio.y_true, sucio.y_score, higher_is_better=False
    )


def test_los_nan_del_puntaje_se_excluyen():
    scores = np.array([0.10, np.nan, 0.30, 0.40])
    gt = _gt([CLASE_POSITIVO, CLASE_POSITIVO, CLASE_NEGATIVO, CLASE_NEGATIVO])

    pares = preparar_pares(scores, gt)

    assert pares.descartes["score_nan"] == 1
    assert pares.descartes["evaluados"] == 3
    assert not np.isnan(pares.y_score).any()
    np.testing.assert_array_equal(pares.y_true, np.array([1, 0, 0], dtype=np.uint8))


def test_la_mascara_del_scene_se_aplica():
    scores = np.array([0.10, 0.20, 0.30, 0.40])
    gt = _gt([CLASE_POSITIVO, CLASE_POSITIVO, CLASE_NEGATIVO, CLASE_NEGATIVO])
    mask = np.array([True, False, True, True])

    pares = preparar_pares(scores, gt, mask=mask)

    assert pares.descartes["mascara"] == 1
    assert pares.descartes["evaluados"] == 3


def test_las_causas_de_descarte_suman_el_total():
    """Un pixel ambiguo y ademas NaN se cuenta una sola vez, en `ambiguo`."""
    scores = np.array([0.10, np.nan, 0.30, np.nan, 0.50])
    gt = _gt(
        [
            CLASE_POSITIVO,
            CLASE_AMBIGUO,  # ambiguo Y NaN: gana `ambiguo` por precedencia
            CLASE_NEGATIVO,
            CLASE_NEGATIVO,  # solo NaN
            CLASE_NEGATIVO,
        ]
    )
    mask = np.array([True, True, True, True, False])

    d = preparar_pares(scores, gt, mask=mask).descartes

    assert d["ambiguo"] == 1
    assert d["score_nan"] == 1
    assert d["mascara"] == 1
    assert d["evaluados"] == 2
    assert (
        d["ambiguo"] + d["gt_nan"] + d["score_nan"] + d["mascara"] + d["evaluados"]
        == d["total"]
    )


def test_preparar_pares_cuenta_positivos_y_negativos():
    scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    gt = _gt([1, 1, 1, 0, 255])

    d = preparar_pares(scores, gt).descartes

    assert d["positivos"] == 3
    assert d["negativos"] == 1
    assert d["ambiguo"] == 1


def test_un_nan_en_la_verdad_de_terreno_se_descarta_aparte():
    """El nodata del GeoTIFF de verdad de terreno es NaN, no 255."""
    scores = np.array([0.1, 0.2, 0.3])
    gt = _gt([CLASE_POSITIVO, np.nan, CLASE_NEGATIVO])

    d = preparar_pares(scores, gt).descartes

    assert d["gt_nan"] == 1
    assert d["evaluados"] == 2


def test_la_verdad_de_terreno_entera_tambien_se_acepta():
    """`build_ground_truth` devuelve uint8; el GeoTIFF lo trae en float32."""
    scores = np.array([0.1, 0.2, 0.3])
    gt = np.array([1, 255, 0], dtype=np.uint8)

    pares = preparar_pares(scores, gt)

    np.testing.assert_array_equal(pares.y_true, np.array([1, 0], dtype=np.uint8))


# --------------------------------------------------------------------------
# Fallos ruidosos
# --------------------------------------------------------------------------


def test_formas_distintas_son_rechazadas():
    with pytest.raises(ValueError, match="misma forma"):
        preparar_pares(np.zeros((2, 2)), _gt(np.zeros((3, 3))))

    with pytest.raises(ValueError, match="misma forma"):
        f1_score(np.array([1, 0]), np.array([1, 0, 1]))


def test_arreglos_vacios_son_rechazados():
    with pytest.raises(ValueError, match="vac"):
        preparar_pares(np.array([]), np.array([]))

    with pytest.raises(ValueError, match="vac"):
        f1_score(np.array([], dtype=np.uint8), np.array([], dtype=np.uint8))


def test_y_true_fuera_de_cero_y_uno_es_rechazado():
    """Pasar la verdad de terreno cruda haria que los 255 contaran como positivos."""
    with pytest.raises(ValueError, match="solo admite 0 y 1"):
        f1_score(np.array([1, 255, 0]), np.array([1, 0, 0]))

    with pytest.raises(ValueError, match="solo admite 0 y 1"):
        roc_auc(np.array([1, 255, 0]), np.array([0.1, 0.2, 0.3]), higher_is_better=True)


def test_y_pred_no_binaria_es_rechazada():
    """Atrapa el mapa de puntaje pasado sin binarizar."""
    with pytest.raises(ValueError, match="y_pred solo admite"):
        f1_score(np.array([1, 0]), np.array([0.3, 0.7]))


def test_una_verdad_de_terreno_con_una_clase_desconocida_es_rechazada():
    with pytest.raises(ValueError, match="no son ninguna de las tres clases"):
        preparar_pares(np.array([0.1, 0.2]), _gt([CLASE_POSITIVO, 7]))


def test_el_auc_con_una_sola_clase_lanza_en_vez_de_devolver_nan():
    """Es el caso que, devuelto como nan, acaba impreso en la tabla."""
    with pytest.raises(ValueError, match="una sola clase"):
        roc_auc(np.ones(4, dtype=np.uint8), np.arange(4.0), higher_is_better=True)

    with pytest.raises(ValueError, match="una sola clase"):
        roc_auc(np.zeros(4, dtype=np.uint8), np.arange(4.0), higher_is_better=True)


def test_el_auc_con_nan_en_el_puntaje_lanza():
    y_true = np.array([1, 1, 0, 0], dtype=np.uint8)
    y_score = np.array([0.1, np.nan, 0.3, 0.4])

    with pytest.raises(ValueError, match="NaN"):
        roc_auc(y_true, y_score, higher_is_better=False)


def test_sin_pixeles_evaluables_se_aborta():
    scores = np.array([0.1, 0.2])
    gt = _gt([CLASE_AMBIGUO, CLASE_AMBIGUO])

    with pytest.raises(ValueError, match="no queda ningun"):
        preparar_pares(scores, gt)


# --------------------------------------------------------------------------
# evaluar_deteccion: el camino que consume el script
# --------------------------------------------------------------------------


def test_evaluar_deteccion_binariza_segun_la_direccion_declarada():
    """Con higher_is_better=False detecta `puntaje <= umbral`, como el SAM."""
    scores = np.array([0.10, 0.12, 0.30, 0.40])
    gt = _gt([CLASE_POSITIVO, CLASE_POSITIVO, CLASE_NEGATIVO, CLASE_NEGATIVO])

    r = evaluar_deteccion(scores, gt, 0.20, higher_is_better=False)

    assert r["matriz_confusion"] == {"vp": 2, "fp": 0, "fn": 0, "vn": 2}
    assert r["metricas"]["f1"] == 1.0
    assert r["metricas"]["roc_auc"] == 1.0

    # La direccion contraria detecta los dos negativos y ningun positivo.
    r_invertido = evaluar_deteccion(scores, gt, 0.20, higher_is_better=True)
    assert r_invertido["matriz_confusion"] == {"vp": 0, "fp": 2, "fn": 2, "vn": 0}
    assert r_invertido["metricas"]["roc_auc"] == 0.0


def test_evaluar_deteccion_traza_los_descartes():
    scores = np.array([0.10, np.nan, 0.30, 0.40])
    gt = _gt([CLASE_POSITIVO, CLASE_POSITIVO, CLASE_AMBIGUO, CLASE_NEGATIVO])

    r = evaluar_deteccion(scores, gt, 0.20, higher_is_better=False)

    assert r["descartes"]["ambiguo"] == 1
    assert r["descartes"]["score_nan"] == 1
    assert r["descartes"]["evaluados"] == 2
    assert r["umbral"] == 0.20
    assert r["higher_is_better"] is False


def test_evaluar_deteccion_sobre_una_grilla_2d():
    """El camino real recibe rasters 2D, no vectores."""
    scores = np.array([[0.10, 0.12], [0.30, 0.40]])
    gt = _gt([[CLASE_POSITIVO, CLASE_POSITIVO], [CLASE_NEGATIVO, CLASE_NEGATIVO]])

    r = evaluar_deteccion(scores, gt, 0.20, higher_is_better=False)

    assert r["descartes"]["evaluados"] == 4
    assert r["metricas"]["f1"] == 1.0


# --------------------------------------------------------------------------
# Oraculo de contraste opcional
# --------------------------------------------------------------------------


def test_contraste_contra_sklearn():
    """Contraste adicional, no definicion de lo correcto.

    Los valores esperados de este archivo son literales calculados a mano; esto
    solo comprueba que la convencion de empates y la direccion coinciden con la
    implementacion de referencia mas usada.
    """
    sk = pytest.importorskip("sklearn.metrics")

    rng = np.random.default_rng(20260901)
    y_true = rng.integers(0, 2, size=500).astype(np.uint8)
    # Redondeo a 2 decimales a proposito: fuerza empates masivos, que es donde
    # las convenciones se separan.
    y_score = np.round(rng.random(500), 2)

    assert roc_auc(y_true, y_score, higher_is_better=True) == pytest.approx(
        sk.roc_auc_score(y_true, y_score)
    )
    assert roc_auc(y_true, y_score, higher_is_better=False) == pytest.approx(
        sk.roc_auc_score(y_true, -y_score)
    )

    y_pred = (y_score >= 0.5).astype(np.uint8)
    assert f1_score(y_true, y_pred) == pytest.approx(sk.f1_score(y_true, y_pred))
    assert iou_score(y_true, y_pred) == pytest.approx(sk.jaccard_score(y_true, y_pred))
    assert cohen_kappa(y_true, y_pred) == pytest.approx(
        sk.cohen_kappa_score(y_true, y_pred)
    )

    m = confusion_matrix(y_true, y_pred)
    vn, fp, fn, vp = sk.confusion_matrix(y_true, y_pred).ravel()
    assert (m.vp, m.fp, m.fn, m.vn) == (vp, fp, fn, vn)
