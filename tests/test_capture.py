"""Pruebas de la tasa de captura de porfidos y de la validacion por bloques.

Como en `test_metrics.py`, los valores esperados salen de casos escritos a mano
y no de una corrida anterior. El mapa base es ``arange(100)`` en 10x10: el top
10 % con `higher_is_better=True` es exactamente la fila 9 (valores 90-99) y con
`higher_is_better=False` es exactamente la fila 0 (valores 0-9), asi que cada
caso se puede verificar mirando la grilla.
"""

import numpy as np
import pytest

from mineralmap.validation.blocks import block_bounds, block_metrics, summarize
from mineralmap.validation.capture import capture_rate

ATOL_EXACTO = 1e-12


@pytest.fixture
def mapa() -> np.ndarray:
    """Mapa 10x10 con valores 0..99 por filas."""
    return np.arange(100, dtype=np.float64).reshape(10, 10)


def _puntos(*pares: tuple[int, int]) -> np.ndarray:
    return np.array(pares, dtype=np.int64).reshape(-1, 2)


# --------------------------------------------------------------------------
# capture_rate: casos analiticos
# --------------------------------------------------------------------------


def test_todos_los_puntos_en_el_top_dan_captura_1(mapa):
    r = capture_rate(mapa, _puntos((9, 0), (9, 5), (9, 9)), top_fraction=0.10)

    assert r.capture == 1.0
    assert r.n_captured == 3
    assert r.n_evaluated == 3
    assert r.n_top_pixels == 10
    assert r.n_valid_pixels == 100
    assert r.chance == pytest.approx(0.10, abs=ATOL_EXACTO)
    assert r.lift == pytest.approx(10.0, abs=ATOL_EXACTO)


def test_ningun_punto_en_el_top_da_captura_0(mapa):
    r = capture_rate(mapa, _puntos((0, 0), (5, 5), (8, 9)), top_fraction=0.10)

    assert r.capture == 0.0
    assert r.n_captured == 0
    assert r.n_evaluated == 3
    assert r.lift == 0.0


def test_un_punto_sobre_nan_se_cuenta_aparte_y_no_como_fallo(mapa):
    mapa[9, 0] = np.nan  # pixel del top que pasa a invalido

    r = capture_rate(mapa, _puntos((9, 0), (9, 5)), top_fraction=0.10)

    assert r.n_invalid == 1
    assert r.n_evaluated == 1
    assert r.n_captured == 1
    # Si el invalido contara como fallo, la captura seria 0,5.
    assert r.capture == 1.0
    assert r.n_valid_pixels == 99


def test_un_punto_sobre_pixel_excluido_por_valid_se_cuenta_aparte(mapa):
    valid = np.ones_like(mapa, dtype=bool)
    valid[9, 5] = False

    r = capture_rate(mapa, _puntos((9, 5), (9, 6)), valid=valid)

    assert r.n_invalid == 1
    assert r.n_evaluated == 1
    assert r.capture == 1.0


def test_puntos_fuera_de_la_grilla_se_cuentan_aparte(mapa):
    # (-1, 9) es el caso traicionero: con indexado negativo de numpy caeria en
    # (9, 9), que es top, y contaria como capturado.
    fuera = _puntos((-1, 9), (10, 0), (0, 10), (3, -1))
    r = capture_rate(mapa, np.vstack([fuera, _puntos((9, 9))]))

    assert r.n_outside == 4
    assert r.n_points == 5
    assert r.n_evaluated == 1
    assert r.n_captured == 1
    assert r.capture == 1.0


def test_solo_puntos_fuera_da_captura_nan_y_no_cero(mapa):
    r = capture_rate(mapa, _puntos((-5, -5), (50, 50)))

    assert np.isnan(r.capture)
    assert np.isnan(r.lift)
    assert r.n_outside == 2


def test_higher_is_better_false_invierte_el_ranking(mapa):
    puntos = _puntos((0, 0), (0, 9))

    mayor = capture_rate(mapa, puntos, higher_is_better=True)
    menor = capture_rate(mapa, puntos, higher_is_better=False)

    assert mayor.capture == 0.0
    assert menor.capture == 1.0


def test_dos_porfidos_en_el_mismo_pixel_cuentan_dos_veces(mapa):
    r = capture_rate(mapa, _puntos((9, 9), (9, 9), (0, 0)))

    assert r.n_evaluated == 3
    assert r.n_captured == 2
    assert r.capture == pytest.approx(2 / 3, abs=ATOL_EXACTO)


def test_puntaje_aleatorio_captura_cerca_de_top_fraction():
    rng = np.random.default_rng(7)
    mapa = rng.random((200, 200))
    puntos = rng.integers(0, 200, size=(4000, 2))

    r = capture_rate(mapa, puntos, top_fraction=0.10)

    # Binomial con n=4000, p=0,1: desviacion ~0,0047. 0,02 son mas de 4 sigma.
    assert r.capture == pytest.approx(0.10, abs=0.02)
    assert r.lift == pytest.approx(1.0, abs=0.2)


def test_sin_puntos_la_captura_no_esta_definida(mapa):
    r = capture_rate(mapa, np.empty((0, 2), dtype=np.int64))

    assert np.isnan(r.capture)
    assert r.n_points == 0
    assert r.chance == pytest.approx(0.10, abs=ATOL_EXACTO)


def test_mapa_sin_pixeles_validos_no_inventa_azar():
    r = capture_rate(np.full((4, 4), np.nan), _puntos((1, 1)))

    assert np.isnan(r.chance)
    assert np.isnan(r.capture)
    assert r.n_invalid == 1


def test_puntos_con_decimales_son_rechazados(mapa):
    with pytest.raises(ValueError, match="floor"):
        capture_rate(mapa, np.array([[9.6, 0.2]]))


@pytest.mark.parametrize("fraccion", [0.0, -0.1, 1.5])
def test_top_fraction_fuera_de_rango_es_rechazada(mapa, fraccion):
    with pytest.raises(ValueError, match="top_fraction"):
        capture_rate(mapa, _puntos((0, 0)), top_fraction=fraccion)


def test_valid_de_otra_forma_es_rechazada(mapa):
    with pytest.raises(ValueError, match="forma"):
        capture_rate(mapa, _puntos((0, 0)), valid=np.ones((5, 5), dtype=bool))


# --------------------------------------------------------------------------
# Bloques espaciales
# --------------------------------------------------------------------------


def test_block_bounds_incluye_los_bloques_parciales_del_borde():
    limites = block_bounds((10, 7), (4, 4))

    assert limites == [
        (0, 4, 0, 4),
        (0, 4, 4, 7),
        (4, 8, 0, 4),
        (4, 8, 4, 7),
        (8, 10, 0, 4),
        (8, 10, 4, 7),
    ]


def test_block_metrics_calcula_auc_por_bloque():
    # Bloque izquierdo: el puntaje separa perfecto (AUC 1). Bloque derecho:
    # separa al reves (AUC 0). El AUC global ocultaria esa diferencia.
    puntaje = np.zeros((4, 8))
    verdad = np.zeros((4, 8), dtype=bool)
    verdad[:2, :] = True
    puntaje[:2, :4] = 1.0
    puntaje[2:, 4:] = 1.0

    bloques = block_metrics(puntaje, (4, 4), higher_is_better=True, y_true=verdad)

    assert [b.auc for b in bloques] == [1.0, 0.0]
    assert [(b.n_pos, b.n_neg) for b in bloques] == [(8, 8), (8, 8)]
    assert all(b.capture is None for b in bloques)


def test_block_metrics_rankea_la_captura_dentro_de_cada_bloque(mapa):
    # Con el top por bloque, el pixel (4, 4) es el mejor del bloque superior
    # izquierdo aunque en la escena completa este lejos del top 10 %.
    bloques = block_metrics(
        mapa,
        (5, 5),
        higher_is_better=True,
        points_rc=_puntos((4, 4), (0, 0), (9, 9)),
        top_fraction=0.04,
    )

    capturas = [b.capture.capture for b in bloques]
    evaluados = [b.capture.n_evaluated for b in bloques]
    assert capturas[0] == 0.5  # (4,4) dentro, (0,0) fuera del top del bloque
    assert evaluados == [2, 0, 0, 1]
    assert capturas[3] == 1.0
    assert np.isnan(capturas[1]) and np.isnan(capturas[2])


def test_summarize_excluye_nan_y_los_cuenta():
    s = summarize([0.6, np.nan, 0.8, np.nan])

    assert s.mean == pytest.approx(0.7, abs=ATOL_EXACTO)
    assert s.std == pytest.approx(np.std([0.6, 0.8], ddof=1), abs=ATOL_EXACTO)
    assert (s.n_defined, s.n_blocks) == (2, 4)


def test_summarize_sin_valores_definidos_es_todo_nan():
    s = summarize([np.nan, np.nan])

    assert np.isnan(s.mean) and np.isnan(s.std)
    assert s.n_defined == 0
