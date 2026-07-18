"""Pruebas de get_reference_spectrum: firma de referencia alineada a BAND_ORDER."""

import numpy as np

from mineralmap.config import BAND_ORDER
from mineralmap.spectral.endmembers import get_reference_spectrum


def test_kaolinite_devuelve_12_bandas_sin_b10():
    """La firma debe tener 12 valores (se descarta B10, que no existe en L2A)."""
    firma = get_reference_spectrum("kaolinite")

    assert firma.shape == (len(BAND_ORDER),)
    assert "B10" not in BAND_ORDER
    assert np.all(np.isfinite(firma))


def test_kaolinite_absorcion_al_oh_en_b12():
    """La caolinita cae fuerte en B12 (~2.2 um) por la absorcion Al-OH:
    B12 debe ser bastante menor que B11."""
    firma = get_reference_spectrum("kaolinite")
    b11 = firma[BAND_ORDER.index("B11")]
    b12 = firma[BAND_ORDER.index("B12")]

    assert b12 < b11
