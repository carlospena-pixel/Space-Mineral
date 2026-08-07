"""Pruebas de los contratos de bandas declarados en config.py."""

import pytest

from mineralmap.config import (
    BAND_FWHM_NM,
    BAND_ORDER,
    BAND_WAVELENGTHS_NM,
    COMMON_BANDS,
    DEFAULT_PLATFORM,
    SAM_BANDS,
    band_wavelengths,
)


def test_sam_bands_tiene_nueve_bandas():
    """SAM_BANDS son las 12 de BAND_ORDER menos B1, B8 y B9."""
    assert len(SAM_BANDS) == 9


def test_sam_bands_es_subconjunto_de_band_order():
    """No puede pedir una banda que el Scene no trae."""
    assert set(SAM_BANDS).issubset(set(BAND_ORDER))


def test_sam_bands_conserva_el_orden_relativo_de_band_order():
    """El orden posicional importa: el cubo y la firma se alinean por indice.

    Si SAM_BANDS reordenara las bandas respecto de BAND_ORDER, subconjuntar
    el cubo por indice daria un vector espectral desordenado sin que nada
    fallara de forma visible.
    """
    esperado = [banda for banda in BAND_ORDER if banda in set(SAM_BANDS)]
    assert SAM_BANDS == esperado


def test_sam_bands_excluye_las_bandas_atmosfericas_y_la_redundante():
    """B1 y B9 miden atmosfera; B8 se solapa con B8A."""
    for banda in ("B1", "B8", "B9"):
        assert banda not in SAM_BANDS


def test_common_bands_sigue_siendo_subconjunto_de_band_order():
    """COMMON_BANDS se conserva como subconjunto documentado, no como default."""
    assert set(COMMON_BANDS).issubset(set(BAND_ORDER))
    assert len(COMMON_BANDS) == 6


def test_band_order_esta_en_orden_creciente_de_longitud_de_onda():
    """El contrato de bandas debe estar ordenado por longitud de onda.

    Es la verificacion de alineamiento de Track B convertida en codigo. Todo el
    proyecto asume que `cube[i]` y `firma[i]` corresponden a la misma banda y
    que el indice avanza hacia el infrarrojo: los graficos de firma, la lectura
    de la absorcion Al-OH (B11 -> B12) y cualquier interpolacion futura entre
    bandas dependen de eso. Un BAND_ORDER desordenado no rompe nada de forma
    visible, solo produce firmas que parecen ruido.
    """
    for plataforma in BAND_WAVELENGTHS_NM:
        lambdas = band_wavelengths(BAND_ORDER, platform=plataforma)
        mensaje = f"BAND_ORDER no esta ordenado por longitud de onda en {plataforma}"
        assert lambdas == sorted(lambdas), mensaje


def test_toda_banda_del_contrato_tiene_longitud_de_onda_y_viceversa():
    """La tabla de longitudes de onda es BAND_ORDER mas B10, ni una banda mas.

    En las dos direcciones. Que falte una banda del contrato rompe cualquier
    grafico con un KeyError; que sobre una banda desconocida significa que la
    tabla y el contrato se desincronizaron y alguien va a leer una longitud de
    onda que el cubo nunca muestrea. B10 es la unica excepcion permitida: no
    esta en el producto L2A pero si en el archivo de la libreria USGS, y la
    validacion de la firma de referencia la necesita.
    """
    esperadas = set(BAND_ORDER) | {"B10"}

    for plataforma, tabla in BAND_WAVELENGTHS_NM.items():
        assert set(tabla) == esperadas, f"la tabla de {plataforma} no calza"
        # Las dos vistas se derivan de la misma tabla base; el test lo fija
        # para que separarlas en el futuro no pase inadvertido.
        assert set(BAND_FWHM_NM[plataforma]) == esperadas


def test_las_dos_plataformas_difieren_justo_en_la_banda_que_importa():
    """S2A y S2B no comparten centro de banda en B12, y por eso hay dos tablas.

    B12 muestrea el doblete Al-OH de la caolinita, donde la reflectancia cambia
    rapido con la longitud de onda. Si algun refactor colapsara las dos tablas
    en una, este test es el que avisa.
    """
    assert BAND_WAVELENGTHS_NM["S2A"]["B12"] != BAND_WAVELENGTHS_NM["S2B"]["B12"]

    separacion = abs(
        BAND_WAVELENGTHS_NM["S2A"]["B12"] - BAND_WAVELENGTHS_NM["S2B"]["B12"]
    )
    assert separacion > 10.0


def test_band_wavelengths_respeta_el_orden_pedido():
    """El llamador fija el orden, igual que en get_reference_spectrum."""
    lambdas = band_wavelengths(SAM_BANDS)

    assert len(lambdas) == len(SAM_BANDS)
    tabla = BAND_WAVELENGTHS_NM[DEFAULT_PLATFORM]
    assert lambdas == [tabla[banda] for banda in SAM_BANDS]


def test_band_wavelengths_rechaza_plataforma_y_banda_desconocidas():
    """Pedir una banda o plataforma que no existe es un error, no un default."""
    with pytest.raises(KeyError, match="Plataforma"):
        band_wavelengths(BAND_ORDER, platform="S2Z")

    with pytest.raises(KeyError, match="B99"):
        band_wavelengths(["B2", "B99"])
