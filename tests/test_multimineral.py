"""Pruebas de remuestreo a bandas EMIT, SAM con muchas bandas, particion por
familia de roca y combinacion de pistas en zonas. Todo sintetico."""

import numpy as np
import pytest

from mineralmap.algorithms.sam import SAM
from mineralmap.spectral.pistas import combine_zone, percentile_rank
from mineralmap.spectral.resample import load_splib_signature, resample_to_bands
from mineralmap.validation.familias import block_ids, is_evaluable, leave_one_family_out

# --- remuestreo -------------------------------------------------------------


def test_remuestreo_de_una_recta_devuelve_la_recta_en_los_centros():
    wl = np.arange(350.0, 2501.0, 1.0)
    firma = 0.1 + 1e-4 * wl  # una recta: el promedio gaussiano simetrico es exacto
    centros = np.array([500.0, 1000.0, 2200.0])
    salida = resample_to_bands(wl, firma, centros, np.full(3, 8.5))
    np.testing.assert_allclose(salida, 0.1 + 1e-4 * centros, rtol=1e-9)


def test_remuestreo_ignora_el_nodata_usgs_y_deja_nan_sin_muestras():
    wl = np.arange(400.0, 501.0, 1.0)
    firma = np.full(wl.shape, 0.5)
    firma[30:71] = -1.23e34  # nodata de splib07 entre 430 y 470 nm: cubre los
    # +-3 sigma (~10,8 nm) de la gaussiana centrada en 450 nm
    salida = resample_to_bands(
        wl, firma, np.array([420.0, 450.0, 900.0]), np.full(3, 8.5)
    )
    assert salida[0] == pytest.approx(0.5)
    assert np.isnan(salida[1])  # todo lo que cubre la gaussiana es nodata
    assert np.isnan(salida[2])  # fuera del rango de la firma


def test_remuestreo_suaviza_un_rasgo_angosto_segun_el_fwhm():
    wl = np.arange(2100.0, 2301.0, 1.0)
    firma = np.ones(wl.shape)
    firma[wl == 2200.0] = 0.0  # absorcion de 1 nm
    angosta = resample_to_bands(wl, firma, np.array([2200.0]), np.array([2.0]))[0]
    ancha = resample_to_bands(wl, firma, np.array([2200.0]), np.array([20.0]))[0]
    assert angosta < ancha < 1.0


def test_lector_splib_convierte_micrometros_y_nodata(tmp_path):
    firma = tmp_path / "firma.txt"
    lambdas = tmp_path / "lambdas.txt"
    firma.write_text("splib07b Record=1: X\n-1.2300000e+034\n0.5\n0.6\n")
    lambdas.write_text("splib07b Record=2: W\n0.400\n0.401\n0.402\n")
    wl, v = load_splib_signature(str(firma), str(lambdas))
    np.testing.assert_allclose(wl, [400.0, 401.0, 402.0])
    assert np.isnan(v[0]) and v[1] == pytest.approx(0.5)
    (tmp_path / "corta.txt").write_text("h\n0.400\n0.401\n")
    with pytest.raises(ValueError):
        load_splib_signature(str(firma), str(tmp_path / "corta.txt"))


def test_remuestreo_rechaza_fwhm_no_positivo():
    with pytest.raises(ValueError):
        resample_to_bands(np.arange(5.0), np.ones(5), np.array([2.0]), np.array([0.0]))


# --- SAM con muchas bandas --------------------------------------------------


def test_sam_sobre_285_bandas_identifica_la_firma_y_propaga_nan():
    rng = np.random.default_rng(0)
    n = 285
    firma = 0.3 + 0.2 * np.sin(np.linspace(0, 6, n))
    cubo = rng.uniform(0.1, 0.6, (n, 4, 5))
    cubo[:, 0, 0] = 2.5 * firma  # mismo espectro, otro brillo -> angulo 0
    cubo[7, 3, 4] = np.nan
    angulo = SAM().predict(cubo, firma)
    assert angulo.shape == (4, 5)
    assert angulo[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert np.isnan(angulo[3, 4])
    assert np.nanmin(angulo[np.arange(4)[:, None] + np.zeros(5, int) != 0]) > 0.0


# --- particion por familia ----------------------------------------------------


def _escena_familias():
    forma = (8, 8)  # bloques de 2 px -> 16 bloques
    verdad = np.zeros(forma)
    familia = np.zeros(forma, dtype=int)
    for (r, c), f in {(0, 0): 1, (0, 1): 1, (4, 4): 1, (2, 6): 2, (6, 1): 3}.items():
        verdad[r, c] = 1
        familia[r, c] = f
    verdad[7, 7] = 255
    return verdad, familia, block_ids(forma, 2)


def test_ninguna_familia_aparece_en_entrenamiento_y_prueba_a_la_vez():
    verdad, familia, bloques = _escena_familias()
    nombres = {1: "A", 2: "B", 3: "C"}
    splits = leave_one_family_out(
        verdad, familia, nombres, bloques, np.ones(verdad.shape, bool)
    )
    assert [s.familia for s in splits] == ["A", "B", "C"]
    for s, codigo in zip(splits, nombres):
        de_f = (verdad == 1) & (familia == codigo)
        assert not (s.entrenamiento & de_f).any()  # la familia no entrena
        assert np.array_equal(s.prueba_pos, de_f)
        en_prueba = np.isin(bloques, s.bloques_prueba)
        assert not (s.entrenamiento & en_prueba).any()  # bloques de prueba no entrenan
        assert not (s.prueba_neg & ~en_prueba).any()  # negativos solo de esos bloques
        assert not (s.entrenamiento & (verdad == 255)).any()  # 255 nunca


def test_familia_a_ocupa_dos_bloques_y_b_uno():
    verdad, familia, bloques = _escena_familias()
    a, b, _ = leave_one_family_out(
        verdad, familia, {1: "A", 2: "B", 3: "C"}, bloques, np.ones(verdad.shape, bool)
    )
    assert a.bloques_prueba == [0, 10] and a.n_pos == 3
    assert is_evaluable(a, min_pixeles=3, min_bloques=2)
    assert not is_evaluable(b, min_pixeles=1, min_bloques=2)  # un solo bloque


def test_positivo_sin_familia_es_un_error():
    verdad, familia, bloques = _escena_familias()
    familia[0, 0] = 0
    with pytest.raises(ValueError):
        leave_one_family_out(
            verdad,
            familia,
            {1: "A", 2: "B", 3: "C"},
            bloques,
            np.ones(verdad.shape, bool),
        )


# --- zonas --------------------------------------------------------------------


def test_rango_percentil_respeta_la_direccion_y_combina_por_maximo():
    angulo = np.array([[0.1, 0.3], [0.2, np.nan]])  # menor es mejor
    profundidad = np.array([[0.0, 0.0], [0.9, 0.5]])  # mayor es mejor
    r_ang = percentile_rank(angulo, higher_is_better=False)
    r_bd = percentile_rank(profundidad, higher_is_better=True)
    assert r_ang[0, 0] > r_ang[1, 0] > r_ang[0, 1]
    assert r_bd[0, 0] == r_bd[0, 1]  # empates con el mismo rango
    zona = combine_zone([r_ang, r_bd])
    assert zona[1, 1] == r_bd[1, 1]  # SAM sin dato: queda la otra pista
    np.testing.assert_allclose(zona, np.fmax(r_ang, r_bd))
