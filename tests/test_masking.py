"""Pruebas de la mascara de nubes/sombra/agua basada en SCL."""

import pytest

from mineralmap.preprocessing.masking import build_cloud_mask


def test_build_cloud_mask_not_implemented():
    with pytest.raises(NotImplementedError):
        build_cloud_mask(scl_band=None, classes_to_mask=[3, 8, 9, 10])
