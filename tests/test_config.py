"""Pruebas de los contratos de bandas declarados en config.py."""

from mineralmap.config import BAND_ORDER, COMMON_BANDS, SAM_BANDS


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
