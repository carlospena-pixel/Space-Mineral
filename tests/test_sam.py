"""Pruebas del detector Spectral Angle Mapper (SAM).

Los angulos esperados de la bateria analitica no salen de comparar contra otra
implementacion de SAM: salen de construir el par (pixel, referencia) para que el
angulo entre ambos sea un valor conocido por geometria. Comparar contra otra
libreria solo demuestra que las dos coinciden, incluso si las dos se equivocan
igual.

Sobre las tolerancias. Los casos de angulo intermedio cierran a precision de
maquina (~1e-16) y se verifican con `atol=1e-12`, no con un 1e-6 por defecto:
una tolerancia holgada de mas deja pasar justo los errores que estos tests
existen para atrapar. Los dos casos de los extremos (angulo ~ 0 y angulo ~ pi)
son la excepcion, y no por como esta implementado el detector sino por como es
`arccos`: su derivada diverge en +-1, asi que un error de redondeo de ~2e-16 en
el coseno se convierte en ~2e-8 radianes en el angulo. Ese piso es irreducible
mientras el puntaje sea el angulo y no su coseno.
"""

import numpy as np
import pytest

from mineralmap.algorithms.sam import SAM, threshold
from mineralmap.config import BAND_ORDER, SAM_BANDS

# Tolerancia de los casos exactos en float64 (ver docstring del modulo).
ATOL_EXACTO = 1e-12

# Tolerancia de los casos que caen en los extremos de arccos, donde el error
# esta dominado por el condicionamiento de la funcion y no por el detector.
ATOL_EXTREMO = 1e-7


def _angulo_de(pixel, referencia) -> float:
    """Angulo que devuelve SAM para un unico pixel, como escalar."""
    pixel = np.asarray(pixel, dtype=np.float64)
    cubo = pixel.reshape(-1, 1, 1)
    return float(SAM().predict(cubo, np.asarray(referencia, dtype=np.float64))[0, 0])


# --------------------------------------------------------------------------
# Bateria analitica: angulos exactos por construccion geometrica.
# --------------------------------------------------------------------------


def test_vectores_ortogonales_dan_noventa_grados():
    """Referencia [1, 0] y pixel [0, 1] son perpendiculares: el producto punto
    es exactamente 0, el coseno es exactamente 0 y el angulo es pi/2.

    Es el unico caso de la bateria que sale con error exactamente nulo, porque
    ningun paso introduce redondeo: 1*0 + 0*1 es 0 en cualquier aritmetica.
    """
    assert _angulo_de([0.0, 1.0], [1.0, 0.0]) == pytest.approx(
        np.pi / 2, abs=ATOL_EXACTO
    )


def test_pixel_a_cuarenta_y_cinco_grados():
    """Referencia [1, 0] y pixel [1, 1]: dot = 1, ||x|| = sqrt(2), ||r|| = 1,
    luego cos = 1/sqrt(2) y el angulo es pi/4.
    """
    assert _angulo_de([1.0, 1.0], [1.0, 0.0]) == pytest.approx(
        np.pi / 4, abs=ATOL_EXACTO
    )


def test_pixel_a_sesenta_grados_en_tres_bandas():
    """Referencia [1, 0, 0] y pixel [1, 1, sqrt(2)]: dot = 1 y ||x|| = 2
    (porque 1 + 1 + 2 = 4), luego cos = 1/2 y el angulo es pi/3.

    Usa tres bandas a proposito: los casos de dos bandas no distinguirian un
    error que solo aparece al sumar sobre mas de dos terminos.
    """
    assert _angulo_de([1.0, 1.0, np.sqrt(2)], [1.0, 0.0, 0.0]) == pytest.approx(
        np.pi / 3, abs=ATOL_EXACTO
    )


def test_pixel_a_treinta_grados():
    """Referencia [1, 0] y pixel [sqrt(3), 1]: dot = sqrt(3), ||x|| = 2,
    luego cos = sqrt(3)/2 y el angulo es pi/6.
    """
    assert _angulo_de([np.sqrt(3), 1.0], [1.0, 0.0]) == pytest.approx(
        np.pi / 6, abs=ATOL_EXACTO
    )


def test_pixel_antiparalelo_da_pi_y_fija_el_clip_inferior():
    """Referencia [1, 1] y pixel [-1, -1] apuntan en direcciones opuestas:
    cos = -1 y el angulo es pi, el maximo que SAM puede devolver.

    Es el test que fija el clip inferior en -1. Sin el clip, ||r||*||x|| se
    calcula como sqrt(2)*sqrt(2) = 2.0000000000000004 y el cociente da
    -0.9999999999999998, que arccos todavia acepta; pero cualquier reordenamiento
    del calculo que lo empuje un ulp mas abajo de -1 produce NaN en vez de pi.

    La tolerancia es 1e-7 y no 1e-12 porque este caso cae en el extremo de
    arccos: el redondeo de ~2e-16 en el coseno se amplifica a ~2e-8 radianes.
    No es un defecto del detector, es la sensibilidad de arccos cerca de -1.
    """
    assert _angulo_de([-1.0, -1.0], [1.0, 1.0]) == pytest.approx(
        np.pi, abs=ATOL_EXTREMO
    )


def test_pixel_identico_da_angulo_cero():
    """Un pixel identico a la referencia debe dar angulo ~ 0."""
    referencia = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    cubo = referencia.reshape(4, 1, 1)

    mapa_angulos = SAM().predict(cubo, referencia)

    assert mapa_angulos.shape == (1, 1)
    # atol relajado: cerca de coseno = 1, arccos amplifica el error de
    # redondeo de float64 (su derivada diverge en x = 1).
    np.testing.assert_allclose(mapa_angulos, 0.0, atol=1e-6)


def test_pixel_proporcional_es_invariante_a_iluminacion():
    """Un pixel proporcional a la referencia (misma direccion, distinta
    magnitud) tambien debe dar angulo ~ 0, ya que SAM es invariante a la
    iluminacion/albedo.
    """
    referencia = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    pixel_escalado = referencia * 5.0
    cubo = pixel_escalado.reshape(4, 1, 1)

    mapa_angulos = SAM().predict(cubo, referencia)

    np.testing.assert_allclose(mapa_angulos, 0.0, atol=1e-6)


# --------------------------------------------------------------------------
# Propiedades del mapa completo.
# --------------------------------------------------------------------------


def test_cubo_sintetico_corre_sin_error_y_forma_correcta():
    """Un cubo sintetico de 12 bandas x 4 x 4 corre sin error y devuelve
    un mapa de forma (4, 4).
    """
    rng = np.random.default_rng(seed=0)
    n_bandas, alto, ancho = 12, 4, 4
    cubo = rng.uniform(low=0.01, high=1.0, size=(n_bandas, alto, ancho))
    referencia = rng.uniform(low=0.01, high=1.0, size=n_bandas)

    mapa_angulos = SAM().predict(cubo, referencia)

    assert mapa_angulos.shape == (alto, ancho)
    assert np.all(np.isfinite(mapa_angulos))
    assert np.all(mapa_angulos >= 0.0)


def test_version_vectorizada_coincide_con_el_bucle_ingenuo():
    """Oraculo: el mismo calculo pixel a pixel con un bucle for explicito.

    Es el test que atrapa un error de ejes en el einsum. Un `"bhw,b->hw"` mal
    escrito no lanza ninguna excepcion: devuelve un mapa transpuesto, o uno que
    sumo sobre el eje espacial en vez del espectral, y en los dos casos el
    resultado se ve como un mapa de angulos perfectamente razonable.

    El cubo es de 3 x 5 y no cuadrado justamente para que una transposicion
    falle por forma antes que por valor.
    """
    rng = np.random.default_rng(0)
    n_bandas, alto, ancho = 9, 3, 5
    cubo = rng.uniform(0.01, 1.0, size=(n_bandas, alto, ancho))
    referencia = rng.uniform(0.01, 1.0, size=n_bandas)

    esperado = np.empty((alto, ancho), dtype=np.float64)
    for fila in range(alto):
        for columna in range(ancho):
            pixel = cubo[:, fila, columna]
            coseno = np.dot(pixel, referencia) / (
                np.linalg.norm(pixel) * np.linalg.norm(referencia)
            )
            esperado[fila, columna] = np.arccos(np.clip(coseno, -1.0, 1.0))

    obtenido = SAM().predict(cubo, referencia)

    assert obtenido.shape == esperado.shape
    np.testing.assert_allclose(obtenido, esperado, atol=ATOL_EXACTO)


def test_el_rango_de_salida_esta_entre_cero_y_pi():
    """Todo valor finito del mapa cae en [0, pi], que es el recorrido de arccos.

    El cubo incluye reflectancias negativas a proposito: la correccion
    atmosferica puede producirlas sobre superficies oscuras (ver
    decisiones_tecnicas.md seccion 6), y son las unicas que pueden empujar el
    coseno por debajo de 0 y el angulo por encima de pi/2.
    """
    rng = np.random.default_rng(7)
    cubo = rng.uniform(-1.0, 1.0, size=(9, 12, 10))
    referencia = rng.uniform(-1.0, 1.0, size=9)

    mapa = SAM().predict(cubo, referencia)

    finitos = mapa[np.isfinite(mapa)]
    assert finitos.size > 0
    assert np.all(finitos >= 0.0)
    assert np.all(finitos <= np.pi)


def test_un_pixel_nan_no_contamina_a_sus_vecinos():
    """Un NaN en una sola banda de un pixel devuelve NaN en ESE pixel y deja
    finitos a todos los demas.

    Este test existe por el contrato con el Track A: el pipeline no le pasa al
    detector el cubo crudo, sino el cubo ya enmascarado con
    `preprocessing.masking.apply_mask`, que pone NaN en todas las bandas de cada
    pixel invalido. O sea que un cubo con NaN no es un caso patologico: es el
    caso de uso normal. Cualquier validacion que rechace un cubo con NaN, o
    cualquier implementacion que propague el NaN al resto del mapa (por ejemplo
    normalizando con un factor global calculado sobre todo el cubo), rompe el
    pipeline entero.
    """
    cubo = np.ones((9, 3, 3), dtype=np.float64)
    cubo[4, 1, 1] = np.nan  # una sola banda de un solo pixel

    mapa = SAM().predict(cubo, np.ones(9))

    assert np.isnan(mapa[1, 1])
    assert np.isnan(mapa).sum() == 1
    vecinos = np.delete(mapa.ravel(), 4)
    assert np.all(np.isfinite(vecinos))


def test_pixel_de_norma_cero_devuelve_nan():
    """Un pixel con todas las bandas en 0 no tiene direccion, asi que el angulo
    contra el no esta definido y el detector devuelve NaN.

    La alternativa seria devolver 0, que significaria "coincidencia perfecta" y
    pintaria un pixel sin senal como la deteccion mas fuerte del mapa. El NaN lo
    saca del mapa por el mismo camino que un pixel enmascarado.
    """
    cubo = np.ones((3, 1, 2), dtype=np.float64)
    cubo[:, 0, 0] = 0.0

    mapa = SAM().predict(cubo, np.array([1.0, 1.0, 1.0]))

    assert np.isnan(mapa[0, 0])
    assert np.isfinite(mapa[0, 1])


def test_escalar_cada_pixel_por_un_factor_distinto_no_cambia_el_mapa():
    """Invariancia al albedo, version fuerte: multiplicar CADA pixel por un
    factor positivo distinto deja el mapa de angulos identico.

    Es la propiedad que justifica usar SAM sobre una escena con iluminacion
    variable, y los casos de un solo pixel proporcional no la demuestran: ahi un
    factor global podria cancelarse por casualidad. Aca cada pixel se mueve por
    su cuenta, que es lo que pasa de verdad con la topografia y el sombreado.
    """
    rng = np.random.default_rng(3)
    cubo = rng.uniform(0.01, 1.0, size=(9, 6, 7))
    referencia = rng.uniform(0.01, 1.0, size=9)
    factores = rng.uniform(0.1, 10.0, size=(1, 6, 7))

    mapa_original = SAM().predict(cubo, referencia)
    mapa_escalado = SAM().predict(cubo * factores, referencia)

    np.testing.assert_allclose(mapa_escalado, mapa_original, atol=ATOL_EXACTO)


def test_el_angulo_es_simetrico_entre_pixel_y_referencia():
    """theta(x, r) == theta(r, x): el angulo entre dos vectores no depende de
    cual de los dos se llame "referencia".
    """
    rng = np.random.default_rng(11)
    pixel = rng.uniform(0.01, 1.0, size=9)
    referencia = rng.uniform(0.01, 1.0, size=9)

    directo = _angulo_de(pixel, referencia)
    invertido = _angulo_de(referencia, pixel)

    assert directo == pytest.approx(invertido, abs=ATOL_EXACTO)


def test_el_dtype_del_cubo_no_cambia_el_resultado():
    """El mismo cubo en float32 y en float64 da el mismo mapa.

    La tolerancia sale de la medicion que motivo acumular en float64 dentro de
    `predict` (ver el comentario de precision en sam.py): con el acumulador en
    float64, la diferencia entre alimentar el cubo en float32 y en float64 quedo
    en ~4e-8 radianes en el peor caso medido. Antes de ese cambio, el mismo par
    de cubos diferia en ~4,5e-4 radianes y este test no habria pasado.
    """
    rng = np.random.default_rng(5)
    cubo64 = rng.uniform(0.01, 1.0, size=(9, 4, 4))
    referencia = rng.uniform(0.01, 1.0, size=9)

    mapa64 = SAM().predict(cubo64, referencia)
    mapa32 = SAM().predict(cubo64.astype(np.float32), referencia)

    assert mapa64.dtype == np.float64
    assert mapa32.dtype == np.float64
    np.testing.assert_allclose(mapa32, mapa64, atol=1e-6)


# --------------------------------------------------------------------------
# Validaciones de entrada: cada una nombra el problema real.
# --------------------------------------------------------------------------


def test_cubo_y_firma_con_distinto_numero_de_bandas_lanza_valueerror():
    """El fallo mas probable del Track A: cruzar los dos contratos de bandas.

    El mensaje tiene que nombrar los dos largos. Antes de esta validacion el
    error venia de adentro de np.einsum y hablaba de dimensiones de operandos,
    que no le dice a nadie que el problema es haber mezclado BAND_ORDER con
    SAM_BANDS.
    """
    cubo = np.ones((12, 2, 2))
    referencia = np.ones(9)

    with pytest.raises(ValueError, match=r"12 bandas.*9"):
        SAM().predict(cubo, referencia)


def test_cubo_que_no_es_3d_lanza_valueerror():
    """Un cubo 2D es una firma, no una escena; el mensaje nombra la forma."""
    with pytest.raises(ValueError, match=r"n_bandas, alto, ancho"):
        SAM().predict(np.ones((9, 4)), np.ones(9))


def test_referencia_que_no_es_1d_lanza_valueerror():
    """Una firma de forma (n, 1) hace broadcast silencioso y devuelve un mapa de
    la forma equivocada con valores plausibles, que es peor que fallar.
    """
    with pytest.raises(ValueError, match=r"vector 1D"):
        SAM().predict(np.ones((9, 2, 2)), np.ones((9, 1)))


def test_referencia_con_nan_lanza_valueerror():
    """Una firma con NaN vuelve NaN el mapa completo, y un mapa todo NaN es
    indistinguible de una escena enteramente enmascarada. A diferencia del cubo,
    una firma con NaN nunca es un caso legitimo.
    """
    referencia = np.ones(9)
    referencia[3] = np.nan

    with pytest.raises(ValueError, match=r"no finitos"):
        SAM().predict(np.ones((9, 2, 2)), referencia)


def test_referencia_de_norma_cero_lanza_valueerror():
    """Un vector nulo no tiene direccion contra la cual medir un angulo. Es el
    mismo criterio que aplica `visualization.spectra.normalize_signature`.
    """
    with pytest.raises(ValueError, match=r"norma 0"):
        SAM().predict(np.ones((9, 2, 2)), np.zeros(9))


# --------------------------------------------------------------------------
# Contrato con el pipeline (Track A).
# --------------------------------------------------------------------------


def test_cubo_y_firma_de_sam_bands_pasan_sin_error():
    """Nueve bandas contra nueve bandas es la combinacion que arma el pipeline:
    subconjunta el cubo a SAM_BANDS y pide la firma con band_order=SAM_BANDS.
    """
    n_bandas = len(SAM_BANDS)
    rng = np.random.default_rng(0)
    cubo = rng.uniform(0.01, 1.0, size=(n_bandas, 5, 5))
    referencia = rng.uniform(0.01, 1.0, size=n_bandas)

    mapa = SAM().predict(cubo, referencia)

    assert mapa.shape == (5, 5)
    assert np.all(np.isfinite(mapa))


def test_cubo_de_band_order_contra_firma_de_sam_bands_lanza_valueerror():
    """El escenario concreto que el Track A vuelve cotidiano: olvidarse de
    subconjuntar el cubo y pedir la firma ya subconjuntada. Sin esta validacion
    el resultado depende de que numpy encuentre o no una forma de hacer
    broadcast, no de que las bandas signifiquen lo mismo.
    """
    cubo = np.ones((len(BAND_ORDER), 3, 3))
    referencia = np.ones(len(SAM_BANDS))

    with pytest.raises(ValueError, match=r"12 bandas.*9"):
        SAM().predict(cubo, referencia)


# --------------------------------------------------------------------------
# threshold
# --------------------------------------------------------------------------


def test_threshold_devuelve_mascara_booleana():
    """threshold() debe marcar como True los pixeles con angulo <= max_angle."""
    mapa_angulos = np.array([[0.0, 0.5], [1.0, np.nan]])

    mascara = threshold(mapa_angulos, max_angle=0.6)

    assert mascara.dtype == bool
    np.testing.assert_array_equal(mascara, [[True, True], [False, False]])


def test_threshold_descarta_los_nan_a_proposito():
    """Un pixel sin dato no es una deteccion, y threshold lo descarta.

    El comportamiento correcto sale de la semantica de IEEE-754 (toda
    comparacion contra NaN es falsa) y no de codigo escrito para eso. Este test
    lo fija como contrato: una reimplementacion que "limpiara" los NaN antes de
    comparar, por ejemplo con np.nan_to_num, los convertiria en 0.0 y por lo
    tanto en las detecciones mas fuertes del mapa.
    """
    mapa = np.full((2, 2), np.nan)

    assert not threshold(mapa, max_angle=np.pi).any()
