"""Pruebas del detector Spectral Angle Mapper (SAM)."""

import numpy as np

from mineralmap.algorithms.sam import SAM, threshold


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


def test_threshold_devuelve_mascara_booleana():
    """threshold() debe marcar como True los pixeles con angulo <= max_angle."""
    mapa_angulos = np.array([[0.0, 0.5], [1.0, np.nan]])

    mascara = threshold(mapa_angulos, max_angle=0.6)

    assert mascara.dtype == bool
    np.testing.assert_array_equal(mascara, [[True, True], [False, False]])
