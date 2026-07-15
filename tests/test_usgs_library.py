"""Pruebas del parser de la libreria espectral USGS splib07."""

import pytest

from mineralmap.spectral.usgs_library import load_usgs_signature


def test_load_usgs_signature_not_implemented():
    with pytest.raises(NotImplementedError):
        load_usgs_signature("KGa-1")
