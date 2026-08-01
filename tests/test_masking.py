"""Pruebas de la mascara de nubes/sombra/agua basada en SCL."""

import numpy as np
import pytest

from mineralmap.preprocessing.masking import (
    DEFAULT_INVALID_CLASSES,
    SCL_CLASSES,
    apply_mask,
    build_cloud_mask,
    mask_summary,
)

# SCL sintetico con las 12 clases, una por pixel, en orden 0..11.
SCL_TODAS_LAS_CLASES = np.arange(12, dtype=np.uint8).reshape(3, 4)

# Clases que sobreviven al criterio por defecto.
CLASES_VALIDAS = {4, 5, 7}


def test_mascara_por_defecto_conserva_solo_vegetacion_suelo_y_no_clasificado():
    """De las 12 clases SCL, solo 4, 5 y 7 quedan como pixel usable."""
    mascara = build_cloud_mask(SCL_TODAS_LAS_CLASES, DEFAULT_INVALID_CLASSES)

    validas = set(SCL_TODAS_LAS_CLASES[mascara].tolist())
    assert validas == CLASES_VALIDAS
    assert mascara.dtype == np.bool_
    assert mascara.shape == SCL_TODAS_LAS_CLASES.shape


def test_el_agua_queda_invalida():
    """El agua (6) se descarta: su firma no compite con la de un mineral.

    Test explicito porque es justo el criterio que unifica dos versiones que
    convivian en el repo (una incluia el agua y la otra no).
    """
    scl = np.array([[5, 6], [6, 5]], dtype=np.uint8)
    mascara = build_cloud_mask(scl, DEFAULT_INVALID_CLASSES)

    assert not mascara[0, 1]
    assert not mascara[1, 0]
    assert mascara[0, 0]
    assert mascara[1, 1]
    assert SCL_CLASSES[6] == "agua"


def test_sin_clases_a_enmascarar_todo_es_valido():
    """Una lista vacia deja el raster entero como valido."""
    mascara = build_cloud_mask(SCL_TODAS_LAS_CLASES, [])

    assert mascara.all()


def test_apply_mask_pone_nan_en_todas_las_bandas_y_no_muta_el_cubo():
    """Los pixeles invalidos quedan NaN en todas las bandas; el original queda igual."""
    cubo = np.ones((3, 2, 2), dtype=np.float32)
    mascara = np.array([[True, False], [True, True]])

    resultado = apply_mask(cubo, mascara)

    assert np.isnan(resultado[:, 0, 1]).all()
    assert np.array_equal(resultado[:, 0, 0], np.ones(3, dtype=np.float32))
    assert np.array_equal(resultado[:, 1, :], np.ones((3, 2), dtype=np.float32))
    # El cubo de entrada no se toca: apply_mask devuelve una copia.
    assert not np.isnan(cubo).any()
    assert resultado is not cubo


def test_apply_mask_rechaza_formas_incompatibles():
    """Una mascara que no calza con el cubo es un error, no un broadcast."""
    cubo = np.ones((3, 2, 2), dtype=np.float32)

    with pytest.raises(ValueError, match="no calza"):
        apply_mask(cubo, np.ones((4, 4), dtype=bool))

    with pytest.raises(ValueError, match="n_bandas"):
        apply_mask(np.ones((2, 2), dtype=np.float32), np.ones((2, 2), dtype=bool))


def test_mask_summary_suma_cien_y_coincide_con_la_mascara():
    """Los porcentajes por clase suman 100 y pct_validos calza con la mascara."""
    resumen = mask_summary(SCL_TODAS_LAS_CLASES, DEFAULT_INVALID_CLASSES)

    por_clase = {k: v for k, v in resumen.items() if k != "pct_validos"}
    assert len(por_clase) == 12
    assert sum(por_clase.values()) == pytest.approx(100.0)

    esperado = 100.0 * len(CLASES_VALIDAS) / SCL_TODAS_LAS_CLASES.size
    assert resumen["pct_validos"] == pytest.approx(esperado)
    assert resumen["6_agua"] == pytest.approx(100.0 / 12)
