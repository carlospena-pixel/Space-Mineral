"""Pruebas de la biblioteca de metricas de validacion.

Los valores esperados de la bateria principal no salen de correr el codigo y
guardar lo que dio: salen de una matriz de confusion escrita a mano cuyos
cuatro conteos se eligieron para que F1, IoU y kappa den fracciones exactas,
calculables en papel y verificables sin computador. Un test que compara contra
una corrida anterior solo demuestra que el codigo no cambio, incluso si estaba
mal desde el principio.

sklearn aparece aca y **no** en el codigo de produccion, a proposito. Es un
oraculo independiente: si mi implementacion de numpy y la de sklearn coinciden
sobre un caso aleatorio, es muy improbable que las dos se equivoquen igual. El
modulo `validation.metrics` no lo importa, para que las metricas se puedan leer
y defender en un code review sin abrir otra libreria.

Sobre las tolerancias. Casi todo cierra a precision de maquina y se verifica con
`abs=1e-12`: los conteos son enteros y las metricas son cocientes de enteros
pequenos. Las dos excepciones son el AUC de un puntaje aleatorio, que es un
estadistico y lleva su tolerancia declarada en el propio test, y el contraste
contra sklearn, donde las dos implementaciones acumulan en distinto orden.
"""

import numpy as np
import pytest
from sklearn import metrics as sk

from mineralmap.validation.metrics import (
    ConfusionMatrix,
    agreement,
    cohen_kappa,
    confusion_matrix,
    f1_score,
    iou_score,
    precision_recall,
    roc_auc,
    roc_curve,
    spatial_enrichment,
)

# Tolerancia de los casos exactos: cocientes de enteros en float64.
ATOL_EXACTO = 1e-12

# Tolerancia del contraste contra sklearn, que suma en otro orden.
ATOL_ORACULO = 1e-10


# --------------------------------------------------------------------------
# La matriz escrita a mano y las cuatro metricas calculadas en papel.
#
#   indice : 0  1  2  3  4  5  6  7  8  9
#   y_true : 1  1  1  1  0  0  0  0  0  0
#   y_pred : 1  1  1  0  1  1  0  0  0  0
#            \____TP___/ FN \_FP_/ \__TN__/
#
#   TP = 3, FP = 2, FN = 1, TN = 4, N = 10
#
#   precision = TP/(TP+FP) = 3/5  = 0,6
#   recall    = TP/(TP+FN) = 3/4  = 0,75
#   F1        = 2TP/(2TP+FP+FN) = 6/9 = 2/3
#   IoU       = TP/(TP+FP+FN)   = 3/6 = 0,5
#   po        = (TP+TN)/N = 7/10 = 0,7
#   pe        = [(TP+FP)(TP+FN) + (FN+TN)(FP+TN)]/N^2
#             = [5*4 + 5*6]/100 = 50/100 = 0,5
#   kappa     = (po-pe)/(1-pe) = 0,2/0,5 = 0,4
# --------------------------------------------------------------------------

VERDAD_A_MANO = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)
PREDICCION_A_MANO = np.array([1, 1, 1, 0, 1, 1, 0, 0, 0, 0], dtype=bool)


def test_matriz_de_confusion_escrita_a_mano():
    """Los cuatro conteos del caso de arriba, contados uno por uno."""
    matriz = confusion_matrix(VERDAD_A_MANO, PREDICCION_A_MANO)

    assert matriz == ConfusionMatrix(tp=3, fp=2, fn=1, tn=4)
    assert matriz.n == 10


def test_precision_y_recall_del_caso_a_mano():
    """precision = 3/5 y recall = 3/4, ambos exactos en binario."""
    resultado = precision_recall(VERDAD_A_MANO, PREDICCION_A_MANO)

    assert resultado.precision == pytest.approx(0.6, abs=ATOL_EXACTO)
    assert resultado.recall == pytest.approx(0.75, abs=ATOL_EXACTO)


def test_f1_iou_y_kappa_del_caso_a_mano():
    """F1 = 2/3, IoU = 1/2 y kappa = 2/5 para la misma matriz."""
    assert f1_score(VERDAD_A_MANO, PREDICCION_A_MANO) == pytest.approx(
        2 / 3, abs=ATOL_EXACTO
    )
    assert iou_score(VERDAD_A_MANO, PREDICCION_A_MANO) == pytest.approx(
        0.5, abs=ATOL_EXACTO
    )
    assert cohen_kappa(VERDAD_A_MANO, PREDICCION_A_MANO) == pytest.approx(
        0.4, abs=ATOL_EXACTO
    )


def test_kappa_es_simetrico():
    """Intercambiar los dos argumentos no cambia kappa.

    Es lo que autoriza a usarlo en `agreement`, donde ninguna de las dos
    mascaras es la verdad.
    """
    directo = cohen_kappa(VERDAD_A_MANO, PREDICCION_A_MANO)
    invertido = cohen_kappa(PREDICCION_A_MANO, VERDAD_A_MANO)

    assert directo == pytest.approx(invertido, abs=ATOL_EXACTO)


# --------------------------------------------------------------------------
# Clasificadores extremos.
# --------------------------------------------------------------------------


def test_clasificador_perfecto_da_uno_en_todo():
    """Prediccion identica a la verdad: F1, IoU, kappa y AUC valen 1."""
    verdad = np.array([0, 0, 1, 1], dtype=bool)
    puntaje = np.array([0.1, 0.2, 0.8, 0.9])

    assert f1_score(verdad, verdad) == pytest.approx(1.0, abs=ATOL_EXACTO)
    assert iou_score(verdad, verdad) == pytest.approx(1.0, abs=ATOL_EXACTO)
    assert cohen_kappa(verdad, verdad) == pytest.approx(1.0, abs=ATOL_EXACTO)
    assert roc_auc(verdad, puntaje) == pytest.approx(1.0, abs=ATOL_EXACTO)


def test_clasificador_que_invierte_todo_da_auc_cero():
    """El test que atrapa la direccion del puntaje.

    El puntaje es alto justo donde la verdad es negativa: es un ordenamiento
    perfectamente invertido, y su AUC es 0, no 1. Si esta prueba pasara a dar 1
    querria decir que `roc_auc` esta enderezando la direccion por su cuenta,
    que es exactamente lo que no debe hacer: con el angulo de SAM devolveria un
    numero plausible y al reves sin que nada lo denuncie.

    Declarar la direccion con `greater_is_better=False` es lo que lo endereza,
    y ahi si vale 1.
    """
    verdad = np.array([0, 0, 1, 1], dtype=bool)
    puntaje_al_reves = np.array([0.9, 0.8, 0.2, 0.1])

    assert roc_auc(verdad, puntaje_al_reves) == pytest.approx(0.0, abs=ATOL_EXACTO)
    assert roc_auc(verdad, puntaje_al_reves, greater_is_better=False) == pytest.approx(
        1.0, abs=ATOL_EXACTO
    )


def test_auc_invertido_es_uno_menos_el_directo():
    """Sobre un caso cualquiera, declarar la direccion refleja el AUC.

    Es la relacion `AUC(-s) = 1 - AUC(s)` que hace que el error de direccion sea
    tan dificil de ver: 0,18 y 0,82 son igual de plausibles mirando el numero
    solo. Fija por que 0,5 no es un valor neutro sino el punto fijo del reflejo.
    """
    rng = np.random.default_rng(20260830)
    verdad = rng.random(2000) > 0.6
    puntaje = rng.random(2000) + verdad * 0.4

    directo = roc_auc(verdad, puntaje)
    declarado = roc_auc(verdad, puntaje, greater_is_better=False)

    assert directo == pytest.approx(1.0 - declarado, abs=ATOL_EXACTO)
    # El caso construido separa de verdad: si no, el reflejo se cumpliria
    # trivialmente alrededor de 0,5 y el test no probaria nada.
    assert directo > 0.6


def test_puntaje_aleatorio_da_auc_cercano_a_un_medio():
    """Un puntaje sin relacion con la verdad no ordena mejor que el azar.

    La tolerancia es 0,02 y esta declarada, no ajustada hasta que pasara: con
    20.000 muestras el error estandar del AUC bajo la hipotesis nula ronda
    0,004, asi que 0,02 son unas cinco desviaciones y la semilla fija hace el
    resultado reproducible.
    """
    rng = np.random.default_rng(12345)
    verdad = rng.random(20_000) > 0.5
    puntaje = rng.random(20_000)

    assert roc_auc(verdad, puntaje) == pytest.approx(0.5, abs=0.02)


# --------------------------------------------------------------------------
# NaN y mascara de validez.
# --------------------------------------------------------------------------


def test_los_pixeles_invalidos_no_entran_en_ningun_conteo():
    """Agregar mil pixeles invalidos no mueve ninguna metrica.

    Es la propiedad que separa "excluir del denominador" de "imputar": si los
    NaN se convirtieran en ceros, los mil pixeles extra entrarian como TN y
    moverian kappa y la exactitud aunque F1 e IoU se salvaran.
    """
    rng = np.random.default_rng(0)
    verdad = rng.random(1000) > 0.5
    prediccion = rng.random(1000) > 0.5

    relleno = rng.random(1000) > 0.5
    verdad_extendida = np.concatenate([verdad, relleno])
    prediccion_extendida = np.concatenate([prediccion, ~relleno])
    validos = np.concatenate([np.ones(1000, bool), np.zeros(1000, bool)])

    assert confusion_matrix(
        verdad_extendida, prediccion_extendida, valid=validos
    ) == confusion_matrix(verdad, prediccion)

    for metrica in (f1_score, iou_score, cohen_kappa):
        assert metrica(
            verdad_extendida, prediccion_extendida, valid=validos
        ) == pytest.approx(metrica(verdad, prediccion), abs=ATOL_EXACTO)


def test_los_nan_del_puntaje_se_descartan_solos():
    """Un puntaje con NaN da el mismo AUC que el mismo puntaje sin esos pixeles.

    Aca no hace falta pasar `valid`: el NaN es la senal de invalidez y la
    funcion lo saca junto con su pixel de `y_true`. Es el caso real del mapa de
    angulos, que llega enmascarado con NaN y sin mascara aparte.
    """
    rng = np.random.default_rng(99)
    verdad = rng.random(5000) > 0.5
    puntaje = rng.random(5000) + verdad * 0.5

    verdad_extendida = np.concatenate([verdad, rng.random(1000) > 0.5])
    puntaje_extendido = np.concatenate([puntaje, np.full(1000, np.nan)])

    assert roc_auc(verdad_extendida, puntaje_extendido) == pytest.approx(
        roc_auc(verdad, puntaje), abs=ATOL_EXACTO
    )


def test_un_nan_no_se_cuenta_como_deteccion():
    """NaN castea a True en numpy; la conversion a booleano no puede verlo.

    `np.asarray([np.nan]).astype(bool)` devuelve True porque NaN no es cero. Si
    la conversion ocurriera antes del filtrado, cada pixel enmascarado entraria
    como deteccion positiva. Este test fija el orden correcto.
    """
    verdad = np.array([True, True, False, False])
    prediccion = np.array([1.0, np.nan, np.nan, 0.0])

    # Solo quedan los indices 0 (TP) y 3 (TN): los dos NaN salen.
    assert confusion_matrix(verdad, prediccion) == ConfusionMatrix(
        tp=1, fp=0, fn=0, tn=1
    )


def test_mascara_valid_de_otra_forma_lanza_value_error():
    """Una mascara de otra ventana silenciaria pixeles arbitrarios."""
    verdad = np.zeros((4, 4), dtype=bool)

    with pytest.raises(ValueError, match="valid"):
        f1_score(verdad, verdad, valid=np.ones((3, 3), dtype=bool))


def test_formas_distintas_lanzan_value_error():
    """Comparar dos rasters de distinta forma no significa nada."""
    with pytest.raises(ValueError, match="forma"):
        f1_score(np.zeros(10, dtype=bool), np.zeros(11, dtype=bool))


# --------------------------------------------------------------------------
# Casos degenerados. Son el regimen real de este proyecto, no rarezas.
# --------------------------------------------------------------------------


def test_cero_detecciones_no_lanza_y_deja_la_precision_sin_definir():
    """El regimen real: la verdad tiene positivos y el detector no marca nada.

    F1 e IoU valen 0 --el detector no encontro nada de lo que habia-- y la
    precision es NaN, porque no hay ninguna deteccion cuya calidad medir.
    Devolver 0,0 en la precision afirmaria que todas las detecciones fueron
    falsas alarmas, que es una medicion distinta y falsa.
    """
    verdad = np.array([1, 1, 0, 0, 0, 0], dtype=bool)
    sin_detecciones = np.zeros(6, dtype=bool)

    resultado = precision_recall(verdad, sin_detecciones)
    assert np.isnan(resultado.precision)
    assert resultado.recall == pytest.approx(0.0, abs=ATOL_EXACTO)

    assert f1_score(verdad, sin_detecciones) == pytest.approx(0.0, abs=ATOL_EXACTO)
    assert iou_score(verdad, sin_detecciones) == pytest.approx(0.0, abs=ATOL_EXACTO)
    # po = pe cuando una de las dos mascaras es constante: kappa es exactamente 0.
    assert cohen_kappa(verdad, sin_detecciones) == pytest.approx(0.0, abs=ATOL_EXACTO)


def test_verdad_sin_positivos_deja_el_auc_sin_definir():
    """Sin un solo positivo no hay TPR que calcular: el AUC es NaN, no 0,5.

    Devolver 0,5 afirmaria "el detector no distingue", que es una medicion. Lo
    que pasa aca es que no hay nada que medir.
    """
    verdad = np.zeros(100, dtype=bool)
    puntaje = np.random.default_rng(1).random(100)

    assert np.isnan(roc_auc(verdad, puntaje))

    fpr, tpr, umbrales = roc_curve(verdad, puntaje)
    assert np.isnan(fpr).all() and np.isnan(tpr).all() and np.isnan(umbrales).all()


def test_verdad_sin_negativos_tampoco_define_el_auc():
    """El caso espejo del anterior: sin negativos no hay FPR."""
    verdad = np.ones(100, dtype=bool)
    puntaje = np.random.default_rng(2).random(100)

    assert np.isnan(roc_auc(verdad, puntaje))


def test_todo_vacio_no_lanza():
    """Cero pixeles validos: todas las metricas devuelven NaN sin excepciones."""
    verdad = np.zeros(10, dtype=bool)
    nada_valido = np.zeros(10, dtype=bool)

    assert np.isnan(f1_score(verdad, verdad, valid=nada_valido))
    assert np.isnan(iou_score(verdad, verdad, valid=nada_valido))
    assert np.isnan(cohen_kappa(verdad, verdad, valid=nada_valido))


# --------------------------------------------------------------------------
# Curva ROC: forma, umbrales y empates.
# --------------------------------------------------------------------------


def test_la_curva_empieza_en_el_origen_y_la_fpr_es_creciente():
    """Contrato de forma de la curva, independiente de los datos."""
    rng = np.random.default_rng(3)
    verdad = rng.random(500) > 0.7
    puntaje = rng.random(500)

    fpr, tpr, umbrales = roc_curve(verdad, puntaje)

    assert fpr[0] == 0.0 and tpr[0] == 0.0
    assert umbrales[0] == np.inf
    assert fpr.shape == tpr.shape == umbrales.shape
    assert np.all(np.diff(fpr) >= 0)
    assert np.all(np.diff(tpr) >= 0)
    assert fpr[-1] == pytest.approx(1.0) and tpr[-1] == pytest.approx(1.0)


def test_los_umbrales_vuelven_en_la_escala_del_puntaje_y_reproducen_la_curva():
    """Con `greater_is_better=False` los umbrales salen como angulos, no negados,
    y aplicarlos con `<=` reconstruye exactamente la TPR y la FPR de la curva.

    Es el test que cierra el contrato de direccion de punta a punta: no basta
    con que el AUC salga bien, los umbrales tienen que ser usables tal cual por
    quien despues llame a `algorithms.sam.threshold`, que detecta con `<=`.
    """
    rng = np.random.default_rng(4)
    verdad = rng.random(300) > 0.7
    # Angulos: menores donde la verdad es positiva, como haria SAM.
    angulo = rng.random(300) * 0.5 + np.where(verdad, 0.0, 0.2)

    fpr, tpr, umbrales = roc_curve(verdad, angulo, greater_is_better=False)

    assert np.all(umbrales[1:] >= 0.0)
    assert umbrales[0] == -np.inf

    positivos = np.count_nonzero(verdad)
    negativos = np.count_nonzero(~verdad)

    for indice in range(1, len(umbrales)):
        detectado = angulo <= umbrales[indice]
        assert np.count_nonzero(detectado & verdad) / positivos == pytest.approx(
            tpr[indice], abs=ATOL_EXACTO
        )
        assert np.count_nonzero(detectado & ~verdad) / negativos == pytest.approx(
            fpr[indice], abs=ATOL_EXACTO
        )


def test_los_empates_no_inflan_el_auc():
    """Un puntaje constante no separa nada: su AUC es 0,5 exacto.

    Si la curva cortara en medio de un grupo de empates, afirmaria que un umbral
    puede separar dos pixeles con el mismo puntaje y el AUC saldria optimista.
    Con todos los valores iguales, ese error se ve de inmediato.
    """
    verdad = np.array([1, 0, 1, 0, 1, 0], dtype=bool)
    constante = np.full(6, 0.42)

    assert roc_auc(verdad, constante) == pytest.approx(0.5, abs=ATOL_EXACTO)


# --------------------------------------------------------------------------
# Enriquecimiento espacial (E3).
# --------------------------------------------------------------------------


def test_detecciones_repartidas_en_proporcion_al_area_dan_uno():
    """Misma densidad dentro y fuera: el enriquecimiento es exactamente 1.

    1.000 pixeles, zona de 100. Diez detecciones dentro (10/100 = 0,1) y noventa
    fuera (90/900 = 0,1): las dos tasas coinciden y la razon es 1.
    """
    zona = np.zeros(1000, dtype=bool)
    zona[:100] = True

    detecciones = np.zeros(1000, dtype=bool)
    detecciones[:10] = True  # dentro
    detecciones[100:190] = True  # fuera

    assert spatial_enrichment(detecciones, zona) == pytest.approx(1.0, abs=ATOL_EXACTO)


def test_una_zona_enorme_no_infla_el_enriquecimiento():
    """La razon vale 1 donde la fraccion cruda de detecciones daria 0,9.

    Es el argumento del docstring, escrito como test. La zona cubre el 90 % del
    AOI y recibe el 90 % de las detecciones, pero solo porque es grande: la
    densidad es la misma a los dos lados. Una metrica que reportara la fraccion
    cruda diria 0,9 y se leeria como un exito.
    """
    zona = np.zeros(1000, dtype=bool)
    zona[:900] = True

    detecciones = np.zeros(1000, dtype=bool)
    detecciones[:90] = True  # dentro, 90/900 = 0,1
    detecciones[900:910] = True  # fuera,  10/100 = 0,1

    fraccion_cruda = np.count_nonzero(detecciones & zona) / np.count_nonzero(
        detecciones
    )
    assert fraccion_cruda == pytest.approx(0.9, abs=ATOL_EXACTO)
    assert spatial_enrichment(detecciones, zona) == pytest.approx(1.0, abs=ATOL_EXACTO)


def test_detecciones_concentradas_en_la_zona_dan_una_razon_alta():
    """20 detecciones dentro (0,2) contra 1 fuera (1/900): razon 180."""
    zona = np.zeros(1000, dtype=bool)
    zona[:100] = True

    detecciones = np.zeros(1000, dtype=bool)
    detecciones[:20] = True
    detecciones[500] = True

    assert spatial_enrichment(detecciones, zona) == pytest.approx(
        0.2 / (1 / 900), abs=1e-9
    )


def test_todas_las_detecciones_dentro_de_la_zona_dan_infinito():
    """Cero detecciones fuera es concentracion total, no un error de calculo."""
    zona = np.zeros(1000, dtype=bool)
    zona[:100] = True

    detecciones = np.zeros(1000, dtype=bool)
    detecciones[:20] = True

    assert spatial_enrichment(detecciones, zona) == np.inf


def test_enriquecimiento_sin_pixeles_fuera_no_esta_definido():
    """Una zona que cubre todo el AOI evaluable no deja con que comparar."""
    zona = np.ones(100, dtype=bool)
    detecciones = np.zeros(100, dtype=bool)
    detecciones[:5] = True

    assert np.isnan(spatial_enrichment(detecciones, zona))


def test_enriquecimiento_sin_detecciones_no_esta_definido():
    """Sin ninguna deteccion a ningun lado no hay densidades que comparar."""
    zona = np.zeros(100, dtype=bool)
    zona[:10] = True

    assert np.isnan(spatial_enrichment(np.zeros(100, dtype=bool), zona))


def test_el_enriquecimiento_respeta_la_mascara_de_validez():
    """Enmascarar media zona encoge su denominador, no lo deja igual.

    Si el enmascarado no entrara en el denominador de dentro, la tasa dentro
    saldria a la mitad y el enriquecimiento se reportaria como 0,5 donde en
    realidad es 1.
    """
    zona = np.zeros(1000, dtype=bool)
    zona[:100] = True

    validos = np.ones(1000, dtype=bool)
    validos[50:100] = False  # media zona enmascarada, sin detecciones ahi

    detecciones = np.zeros(1000, dtype=bool)
    detecciones[:5] = True  # 5 de los 50 validos dentro = 0,1
    detecciones[100:190] = True  # 90 de 900 fuera = 0,1

    assert spatial_enrichment(detecciones, zona, valid=validos) == pytest.approx(
        1.0, abs=ATOL_EXACTO
    )


# --------------------------------------------------------------------------
# Acuerdo entre dos mascaras (E5).
# --------------------------------------------------------------------------


def test_el_acuerdo_es_simetrico():
    """`agreement(a, b)` y `agreement(b, a)` dan el mismo IoU y el mismo kappa.

    Es lo que autoriza a usarlo con SAM y el clay ratio, donde ninguna de las
    dos mascaras es la verdad de terreno.
    """
    rng = np.random.default_rng(5)
    a = rng.random(500) > 0.8
    b = rng.random(500) > 0.8

    ab = agreement(a, b)
    ba = agreement(b, a)

    assert ab.iou == pytest.approx(ba.iou, abs=ATOL_EXACTO)
    assert ab.kappa == pytest.approx(ba.kappa, abs=ATOL_EXACTO)
    assert (ab.n_a, ab.n_b) == (ba.n_b, ba.n_a)


def test_el_acuerdo_reporta_los_conteos_que_lo_originan():
    """Un IoU bajo tiene que poder diagnosticarse sin recalcular nada."""
    a = np.array([1, 1, 1, 0, 0, 0], dtype=bool)
    b = np.array([0, 1, 1, 1, 0, 0], dtype=bool)

    resultado = agreement(a, b)

    assert (resultado.n_a, resultado.n_b, resultado.n_ambas, resultado.n) == (
        3,
        3,
        2,
        6,
    )
    # IoU = 2 en comun / 4 en la union.
    assert resultado.iou == pytest.approx(0.5, abs=ATOL_EXACTO)


def test_dos_mascaras_disjuntas_no_acuerdan():
    """Sin ni un pixel en comun el IoU es 0 y kappa es negativo.

    Kappa por debajo de cero no es un error: dice que las dos mascaras coinciden
    menos de lo que coincidirian barajandolas.
    """
    a = np.array([1, 1, 0, 0, 0, 0], dtype=bool)
    b = np.array([0, 0, 1, 1, 0, 0], dtype=bool)

    resultado = agreement(a, b)

    assert resultado.iou == pytest.approx(0.0, abs=ATOL_EXACTO)
    assert resultado.kappa < 0.0


# --------------------------------------------------------------------------
# Oraculo independiente: sklearn.
# --------------------------------------------------------------------------


def test_oraculo_sklearn_sobre_un_caso_aleatorio():
    """F1, IoU, kappa y AUC coinciden con sklearn sobre el mismo caso.

    La semilla es fija para que un fallo sea reproducible. Las cuatro metricas
    se contrastan en la misma prueba porque comparten la matriz de confusion: si
    una discrepa, conviene ver de inmediato si las otras tambien.
    """
    rng = np.random.default_rng(2026)
    verdad = rng.random(5000) > 0.7
    prediccion = rng.random(5000) > 0.6
    puntaje = rng.random(5000) + verdad * 0.3

    assert f1_score(verdad, prediccion) == pytest.approx(
        sk.f1_score(verdad, prediccion), abs=ATOL_ORACULO
    )
    assert iou_score(verdad, prediccion) == pytest.approx(
        sk.jaccard_score(verdad, prediccion), abs=ATOL_ORACULO
    )
    assert cohen_kappa(verdad, prediccion) == pytest.approx(
        sk.cohen_kappa_score(verdad, prediccion), abs=ATOL_ORACULO
    )
    assert roc_auc(verdad, puntaje) == pytest.approx(
        sk.roc_auc_score(verdad, puntaje), abs=ATOL_ORACULO
    )


def test_oraculo_sklearn_de_la_direccion_declarada():
    """`greater_is_better=False` equivale a pasarle el puntaje negado a sklearn.

    Fija que "declarar la direccion" es exactamente negar antes de rankear, y no
    alguna otra operacion que casualmente de bien en los casos faciles.
    """
    rng = np.random.default_rng(777)
    verdad = rng.random(3000) > 0.75
    angulo = rng.random(3000) - verdad * 0.3

    assert roc_auc(verdad, angulo, greater_is_better=False) == pytest.approx(
        sk.roc_auc_score(verdad, -angulo), abs=ATOL_ORACULO
    )


def test_oraculo_sklearn_de_la_matriz_de_confusion():
    """Los cuatro conteos coinciden con sklearn, que los ordena distinto.

    sklearn devuelve (TN, FP, FN, TP) y este modulo (TP, FP, FN, TN). El test
    desempaca explicitamente en el orden de sklearn: es la razon por la que
    `ConfusionMatrix` es un NamedTuple y no una tupla pelada.
    """
    rng = np.random.default_rng(31)
    verdad = rng.random(1000) > 0.6
    prediccion = rng.random(1000) > 0.5

    tn, fp, fn, tp = sk.confusion_matrix(verdad, prediccion).ravel()
    mia = confusion_matrix(verdad, prediccion)

    assert (mia.tp, mia.fp, mia.fn, mia.tn) == (tp, fp, fn, tn)
