"""Pruebas del detector Spectral Angle Mapper (SAM)."""

import pytest

from mineralmap.algorithms.sam import SAM


def test_sam_predict_not_implemented():
    sam = SAM(angle_threshold_rad=0.1)
    with pytest.raises(NotImplementedError):
        sam.predict(cube=None)
