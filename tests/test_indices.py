"""Pruebas del clay ratio y del umbral por tasa de positivos.

Los cubos son sinteticos y sus B11 y B12 se eligen para que el cociente sea un
numero exacto conocido de antemano (2, 0,5, 4), no para que "se vea razonable".
Un cubo de reflectancia real no serviria: no se sabria cual es la respuesta
correcta y el test solo podria comprobar que el codigo no cambio.

El test que importa mas es `test_nueve_bandas_y_doce_bandas_dan_el_mismo_mapa`.
El cubo del proyecto circula con las 12 bandas de `BAND_ORDER` y con las 9 de
`SAM_BANDS`, y B11 esta en la posicion 10 del primero y en la 7 del segundo: un
indice fijo devuelve un mapa impecable calculado sobre otras dos bandas.
"""

import numpy as np
import pytest

from mineralmap.config import BAND_ORDER, SAM_BANDS
from mineralmap.spectral.indices import clay_ratio, mask_by_positive_rate

ATOL_EXACTO = 1e-12


def _cubo_con(band_names: list[str], valores: dict[str, np.ndarray]) -> np.ndarray:
    """Arma un cubo donde cada banda nombrada en `valores` toma su mapa.

    Las bandas no mencionadas se llenan con -1, un valor que no puede aparecer
    en reflectancia: si el indice las leyera por error, el cociente saldria
    negativo y el test fallaria de forma visible en vez de dar un numero
    plausible.
    """
    alto, ancho = next(iter(valores.values())).shape
    cubo = np.full((len(band_names), alto, ancho), -1.0)
    for banda, mapa in valores.items():
        cubo[band_names.index(banda)] = mapa
    return cubo


# --------------------------------------------------------------------------
# clay_ratio: el cociente y su direccion.
# --------------------------------------------------------------------------


def test_el_cociente_es_exactamente_b11_sobre_b12():
    """B11 = 0,4 y B12 = 0,2 en todo el mapa: el ratio es exactamente 2."""
    b11 = np.full((3, 4), 0.4)
    b12 = np.full((3, 4), 0.2)

    ratio = clay_ratio(_cubo_con(BAND_ORDER, {"B11": b11, "B12": b12}), BAND_ORDER)

    assert ratio.shape == (3, 4)
    assert np.allclose(ratio, 2.0, atol=ATOL_EXACTO)


def test_el_ratio_sube_donde_b12_cae():
    """La direccion del indice, fijada como test y no solo escrita.

    Dos pixeles con el mismo hombro B11 y distinta absorcion B12. El que tiene
    B12 mas bajo --el que absorbe mas en el rasgo Al-OH, o sea el que tendria
    arcilla-- es el que recibe el ratio mas alto. Si algun dia alguien
    "arreglara" el indice invirtiendo el cociente, este test lo atrapa: el mapa
    seguiria calculandose y el barrido por percentil seleccionaria justo los
    pixeles opuestos.
    """
    b11 = np.array([[0.4, 0.4]])
    b12 = np.array([[0.4, 0.1]])  # el segundo pixel absorbe mas

    ratio = clay_ratio(_cubo_con(SAM_BANDS, {"B11": b11, "B12": b12}), SAM_BANDS)

    assert ratio[0, 0] == pytest.approx(1.0, abs=ATOL_EXACTO)
    assert ratio[0, 1] == pytest.approx(4.0, abs=ATOL_EXACTO)
    assert ratio[0, 1] > ratio[0, 0]


def test_nueve_bandas_y_doce_bandas_dan_el_mismo_mapa():
    """El test que blinda la busqueda por nombre.

    Las mismas B11 y B12 en un cubo de `SAM_BANDS` (9 bandas, B11 en la
    posicion 7) y en uno de `BAND_ORDER` (12 bandas, B11 en la posicion 10)
    tienen que producir el mapa identico. Con un indice fijo, uno de los dos
    leeria otras bandas y devolveria un mapa distinto sin lanzar nada.
    """
    rng = np.random.default_rng(11)
    b11 = rng.random((5, 6)) * 0.3 + 0.1
    b12 = rng.random((5, 6)) * 0.3 + 0.1

    de_nueve = clay_ratio(_cubo_con(SAM_BANDS, {"B11": b11, "B12": b12}), SAM_BANDS)
    de_doce = clay_ratio(_cubo_con(BAND_ORDER, {"B11": b11, "B12": b12}), BAND_ORDER)

    assert np.array_equal(de_nueve, de_doce)


def test_b12_en_cero_da_nan_y_no_infinito():
    """Un cociente infinito seria el maximo del mapa, o sea la arcilla mas
    fuerte, y sobreviviria a cualquier umbral por percentil.
    """
    b11 = np.array([[0.4, 0.4]])
    b12 = np.array([[0.2, 0.0]])

    ratio = clay_ratio(_cubo_con(SAM_BANDS, {"B11": b11, "B12": b12}), SAM_BANDS)

    assert ratio[0, 0] == pytest.approx(2.0, abs=ATOL_EXACTO)
    assert np.isnan(ratio[0, 1])
    assert not np.isinf(ratio).any()


def test_las_dos_bandas_en_cero_tambien_dan_nan():
    """0/0 es NaN en numpy y tiene que quedarse en NaN, no volverse 0."""
    b11 = np.array([[0.0]])
    b12 = np.array([[0.0]])

    ratio = clay_ratio(_cubo_con(SAM_BANDS, {"B11": b11, "B12": b12}), SAM_BANDS)

    assert np.isnan(ratio[0, 0])


def test_los_nan_del_cubo_se_propagan():
    """Un pixel enmascarado en el cubo sale enmascarado en el indice."""
    b11 = np.array([[0.4, np.nan]])
    b12 = np.array([[0.2, 0.2]])

    ratio = clay_ratio(_cubo_con(SAM_BANDS, {"B11": b11, "B12": b12}), SAM_BANDS)

    assert ratio[0, 0] == pytest.approx(2.0, abs=ATOL_EXACTO)
    assert np.isnan(ratio[0, 1])


# --------------------------------------------------------------------------
# clay_ratio: validaciones que fallan ruidosamente.
# --------------------------------------------------------------------------


def test_falta_b11_lanza_value_error_nombrandola():
    """El mensaje tiene que decir cual falta, no solo que falta algo."""
    sin_b11 = [banda for banda in SAM_BANDS if banda != "B11"]
    cubo = np.ones((len(sin_b11), 2, 2))

    with pytest.raises(ValueError, match="B11"):
        clay_ratio(cubo, sin_b11)


def test_falta_b12_lanza_value_error_nombrandola():
    """Caso espejo del anterior."""
    sin_b12 = [banda for banda in SAM_BANDS if banda != "B12"]
    cubo = np.ones((len(sin_b12), 2, 2))

    with pytest.raises(ValueError, match="B12"):
        clay_ratio(cubo, sin_b12)


def test_cubo_no_tridimensional_lanza_value_error():
    """Un mapa 2D pasado como cubo daria un resultado con la forma equivocada."""
    with pytest.raises(ValueError, match="dimensiones"):
        clay_ratio(np.ones((10, 10)), SAM_BANDS)


def test_band_names_de_largo_distinto_lanza_value_error():
    """Sin un nombre por banda, la busqueda por nombre no significa nada."""
    with pytest.raises(ValueError, match="band_names"):
        clay_ratio(np.ones((9, 2, 2)), BAND_ORDER)


# --------------------------------------------------------------------------
# mask_by_positive_rate: la tasa de positivos es la propiedad que se garantiza.
# --------------------------------------------------------------------------


def test_marca_exactamente_la_fraccion_pedida():
    """1.000 pixeles al 5 % son exactamente 50, no "aproximadamente 50"."""
    mapa = np.arange(1000, dtype=np.float64).reshape(20, 50)

    mascara = mask_by_positive_rate(mapa, 0.05)

    assert np.count_nonzero(mascara) == 50


def test_marca_los_valores_mas_altos_cuando_mayor_es_mejor():
    """Con el clay ratio se marcan los valores altos: los 10 ultimos de 100."""
    mapa = np.arange(100, dtype=np.float64).reshape(10, 10)

    mascara = mask_by_positive_rate(mapa, 0.10)

    assert np.array_equal(np.flatnonzero(mascara.ravel()), np.arange(90, 100))


def test_marca_los_valores_mas_bajos_cuando_menor_es_mejor():
    """Con un mapa de angulos se marcan los bajos: los 10 primeros de 100.

    Es la direccion contraria a la del clay ratio, y es explicita por la misma
    razon que en `validation.metrics.roc_curve`: mirando flotantes no se puede
    deducir en que sentido va la escala.
    """
    mapa = np.arange(100, dtype=np.float64).reshape(10, 10)

    mascara = mask_by_positive_rate(mapa, 0.10, higher_is_better=False)

    assert np.array_equal(np.flatnonzero(mascara.ravel()), np.arange(0, 10))


def test_los_nan_nunca_se_marcan_ni_cuentan_para_el_total():
    """Los NaN salen del numerador y del denominador.

    Si contaran para el total, la tasa se calcularia sobre 100 y marcaria 10
    pixeles de los 50 validos: el doble de la tasa pedida sobre lo evaluable.
    """
    mapa = np.arange(100, dtype=np.float64).reshape(10, 10)
    mapa[:5] = np.nan  # la mitad del mapa sin dato

    mascara = mask_by_positive_rate(mapa, 0.10)

    assert np.count_nonzero(mascara) == 5
    assert not np.any(mascara[:5])


def test_la_mascara_de_validez_encoge_el_denominador():
    """Enmascarar la mitad valida reduce a la mitad los pixeles marcados."""
    mapa = np.arange(100, dtype=np.float64).reshape(10, 10)
    validos = np.ones((10, 10), dtype=bool)
    validos[:5] = False

    mascara = mask_by_positive_rate(mapa, 0.10, valid=validos)

    assert np.count_nonzero(mascara) == 5
    assert not np.any(mascara[:5])


def test_una_tasa_que_redondea_a_cero_no_marca_nada():
    """Con 100 pixeles y una tasa de 2e-5 no se marca ningun pixel.

    Es el regimen real del proyecto en miniatura: la tasa de SAM bajo 0,10 rad
    es 2e-5, y sobre un AOI chico eso puede ser menos de un pixel. No marcar
    ninguno es la respuesta correcta; marcar uno seria inventar la tasa.
    """
    mapa = np.arange(100, dtype=np.float64).reshape(10, 10)

    assert np.count_nonzero(mask_by_positive_rate(mapa, 2e-5)) == 0


def test_tasa_fuera_de_rango_lanza_value_error():
    """El 0,002 % se escribe 2e-5; pasar 0 o mas de 1 es un error de unidad."""
    mapa = np.ones((4, 4))

    with pytest.raises(ValueError, match="positive_rate"):
        mask_by_positive_rate(mapa, 0.0)
    with pytest.raises(ValueError, match="positive_rate"):
        mask_by_positive_rate(mapa, 1.5)


def test_mascara_de_validez_de_otra_forma_lanza_value_error():
    """Una mascara de otra ventana marcaria pixeles arbitrarios."""
    with pytest.raises(ValueError, match="valid"):
        mask_by_positive_rate(np.ones((4, 4)), 0.5, valid=np.ones((3, 3), dtype=bool))


def test_dos_mascaras_a_la_misma_tasa_son_comparables():
    """La propiedad por la que existe esta funcion, escrita como test.

    Dos mapas distintos umbralizados a la misma tasa producen dos mascaras del
    mismo tamano. Es lo que hace que el IoU entre ellas hable de donde caen los
    pixeles y no de cuantos hay: con tamanos distintos, el IoU esta acotado por
    el cociente de los tamanos y mide sobre todo esa diferencia.
    """
    rng = np.random.default_rng(42)
    uno = rng.random((100, 100))
    otro = rng.random((100, 100))

    a = mask_by_positive_rate(uno, 0.01)
    b = mask_by_positive_rate(otro, 0.01)

    assert np.count_nonzero(a) == np.count_nonzero(b) == 100
