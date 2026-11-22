"""Pruebas de las familias de modelos con datos sinteticos diminutos.

Patron obvio: la entrada 0 separa las clases (positivos ~2, negativos ~0).
Las etiquetas 255 se ponen "al reves" a proposito: si un modelo las usara para
entrenar, aprenderia el patron contrario y la prueba lo detectaria.
"""

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from mineralmap.algorithms.matched_filter import MatchedFilter
from mineralmap.algorithms.random_forest import RandomForestDetector
from mineralmap.algorithms.sid import SID
from mineralmap.algorithms.supervised import (
    HistGradientBoostingDetector,
    KNNDetector,
    LogisticDetector,
    SVMDetector,
    XGBoostDetector,
)
from mineralmap.algorithms.unmixing import UnmixingDetector
from mineralmap.spectral.features import build_feature_stack

SUPERVISADOS = [
    lambda: LogisticDetector(C=1.0, seed=0),
    lambda: KNNDetector(k=5, seed=0),
    lambda: SVMDetector(C=1.0, seed=0),
    lambda: RandomForestDetector(n_estimators=30, seed=0),
    lambda: HistGradientBoostingDetector(learning_rate=0.1, seed=0),
    lambda: XGBoostDetector(max_depth=3, seed=0),
]
IDS = ["logistica", "knn", "svm", "random_forest", "hgb", "xgboost"]


def _datos(seed=0, alto=20, ancho=20):
    rng = np.random.default_rng(seed)
    y = (rng.random((alto, ancho)) < 0.3).astype(np.float64)
    X = rng.normal(0, 0.3, (3, alto, ancho))
    X[0] += 2.0 * y
    # Trampa: pixeles 255 con la entrada 0 al reves de su "clase" visual.
    trampa = rng.random((alto, ancho)) < 0.2
    X[0][trampa] = 2.0 - X[0][trampa]
    y[trampa] = 255
    # Pixeles NaN: una entrada sin dato y una etiqueta NaN.
    X[1, 0, 0] = np.nan
    y[0, 1] = np.nan
    return X, y


@pytest.mark.parametrize("hacer", SUPERVISADOS, ids=IDS)
def test_supervisado_aprende_patron_obvio_y_forma_correcta(hacer):
    X, y = _datos()
    puntaje = hacer().fit(X, y).predict(X)
    assert puntaje.shape == y.shape
    assert np.isnan(puntaje[0, 0])  # entrada NaN -> sin puntaje
    ok = np.isin(y, (0, 1)) & np.isfinite(puntaje)
    assert roc_auc_score(y[ok], puntaje[ok]) > 0.95


@pytest.mark.parametrize("hacer", SUPERVISADOS, ids=IDS)
def test_supervisado_ignora_255_y_nan(hacer):
    X, y = _datos()
    # Mismo modelo entrenado sin los 255 ni los NaN: tiene que dar lo mismo.
    y_limpio = np.where(np.isin(y, (0, 1)), y, -1.0)
    a = hacer().fit(X, y).predict(X)
    b = hacer().fit(X, y_limpio).predict(X)
    np.testing.assert_allclose(a, b, equal_nan=True)


@pytest.mark.parametrize("hacer", SUPERVISADOS, ids=IDS)
def test_supervisado_repite_con_la_misma_semilla(hacer):
    X, y = _datos()
    np.testing.assert_array_equal(
        hacer().fit(X, y).predict(X), hacer().fit(X, y).predict(X)
    )


def test_fit_table_rechaza_etiqueta_255():
    with pytest.raises(ValueError):
        LogisticDetector().fit_table(np.zeros((4, 2)), np.array([0, 1, 255, 0]))


def test_predict_sin_entrenar_es_error():
    with pytest.raises(RuntimeError):
        LogisticDetector().predict(np.zeros((2, 3, 3)))


def _cubo_con_firma():
    firma = np.array([0.6, 0.5, 0.2, 0.4])
    fondo = np.array([0.2, 0.3, 0.4, 0.5])
    rng = np.random.default_rng(0)
    cubo = fondo[:, None, None] + rng.normal(0, 0.01, (4, 10, 10))
    cubo[:, :3, :3] = firma[:, None, None] + rng.normal(0, 0.01, (4, 3, 3))
    cubo[:, 9, 9] = np.nan
    objetivo = np.zeros((10, 10), dtype=bool)
    objetivo[:3, :3] = True
    return cubo, firma, objetivo


def test_sid_marca_la_firma_con_valores_bajos():
    cubo, firma, objetivo = _cubo_con_firma()
    sid = SID().predict(cubo, firma)
    assert sid.shape == objetivo.shape and np.isnan(sid[9, 9])
    assert np.nanmax(sid[objetivo]) < np.nanmin(sid[~objetivo])


def test_matched_filter_marca_la_firma_con_valores_altos_y_repite():
    cubo, firma, objetivo = _cubo_con_firma()
    mf = MatchedFilter(seed=0).predict(cubo, firma)
    assert mf.shape == objetivo.shape and np.isnan(mf[9, 9])
    assert np.nanmin(mf[objetivo]) > np.nanmax(mf[~objetivo])
    np.testing.assert_array_equal(mf, MatchedFilter(seed=0).predict(cubo, firma))


def test_fcls_recupera_proporciones_conocidas_y_suman_uno():
    ref = np.array([0.6, 0.5, 0.2, 0.4])
    otro = np.array([0.2, 0.3, 0.4, 0.5])
    sombra = np.zeros(4)
    mezcla = 0.3 * ref + 0.5 * otro + 0.2 * sombra
    cubo = np.stack([mezcla, ref, np.full(4, np.nan)], axis=1)[:, None, :]
    det = UnmixingDetector(np.vstack([otro, sombra]))
    prop = det.proportions(cubo, ref)
    np.testing.assert_allclose(prop[:, 0, 0], [0.3, 0.5, 0.2], atol=1e-3)
    np.testing.assert_allclose(prop[:, 0, 0].sum(), 1.0, atol=1e-3)
    assert det.predict(cubo, ref)[0, 1] == pytest.approx(1.0, abs=1e-3)
    assert np.isnan(det.predict(cubo, ref)[0, 2])


def test_pila_de_entradas_agrega_indices_y_propaga_nan():
    bandas = ["B2", "B4", "B8A", "B11", "B12"]
    cubo = np.full((5, 2, 2), 0.2)
    cubo[1] = 0.4  # B4
    cubo[0, 1, 1] = np.nan
    pila, nombres = build_feature_stack(cubo, bandas)
    assert nombres[-3:] == [
        "clay_ratio_b11_b12",
        "ferric_iron_b4_b2",
        "ferric_oxide_b11_b8a",
    ]
    assert pila.shape == (8, 2, 2)
    assert pila[nombres.index("ferric_iron_b4_b2"), 0, 0] == pytest.approx(2.0)
    assert np.isnan(pila[:, 1, 1]).all()
