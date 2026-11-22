"""Pruebas sinteticas del umbral comun, el AUC por grupo y el empate."""

import numpy as np
import pytest

from mineralmap.validation.comparacion import (
    block_bootstrap_ties,
    group_auc,
    top_threshold,
)


def test_umbral_respeta_la_direccion():
    v = np.arange(101.0)
    assert top_threshold(v, 0.1, True) == (pytest.approx(90.0), "top")
    assert top_threshold(v, 0.1, False) == (pytest.approx(10.0), "top")


def test_umbral_con_mayoria_de_ceros_usa_identificado():
    v = np.r_[np.zeros(95), [0.3, 0.2, 0.4, 0.5, 0.6]]
    assert top_threshold(v, 0.1, True) == (pytest.approx(0.2), "identificado")


def test_auc_por_grupo_solo_cuenta_los_positivos_del_grupo():
    y = np.array([1, 1, 0, 0, 255])
    s = np.array([0.9, 0.1, 0.5, 0.4, 1.0])
    validos = y != 255
    a = np.array([True, False, False, False, False])
    assert group_auc(s, y, validos, a) == 1.0
    assert group_auc(s, y, validos, ~a) == 0.0


def test_empate_detecta_igual_y_peor_y_repite():
    y = np.tile([0, 0, 1, 1], 10)
    bloques = np.repeat(np.arange(10), 4)
    bueno = y.astype(float)
    puntajes = {"bueno": bueno, "igual": bueno.copy(), "malo": -bueno}
    mejor, filas = block_bootstrap_ties(puntajes, y, bloques, n_sorteos=30)
    assert mejor == "bueno"
    assert filas["igual"]["empate"] and not filas["malo"]["empate"]
    assert block_bootstrap_ties(puntajes, y, bloques, n_sorteos=30)[1] == filas
