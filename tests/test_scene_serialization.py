"""Round-trip de serializacion del Scene: save_scene/load_scene preservan todo."""

import numpy as np
from affine import Affine
from rasterio.crs import CRS

from mineralmap.config import COMMON_BANDS
from mineralmap.io.raster_io import Scene, load_scene, save_scene


def test_scene_round_trip(tmp_path):
    """Un Scene sintetico sobrevive un ciclo save/load sin perdida relevante."""
    rng = np.random.default_rng(0)
    cube = rng.random((6, 4, 4)).astype(np.float32)
    mask = np.array(
        [
            [True, True, False, True],
            [False, True, True, True],
            [True, False, True, False],
            [True, True, True, True],
        ]
    )
    transform = Affine(20.0, 0.0, 300000.0, 0.0, -20.0, 6000000.0)
    crs = CRS.from_epsg(32719)

    scene = Scene(
        cube=cube,
        band_names=list(COMMON_BANDS),
        transform=transform,
        crs=crs,
        mask=mask,
    )

    ruta = tmp_path / "scene.npz"
    save_scene(scene, str(ruta))
    recargado = load_scene(str(ruta))

    assert np.allclose(recargado.cube, cube)
    assert recargado.cube.dtype == np.float32
    assert recargado.band_names == list(COMMON_BANDS)
    assert np.array_equal(recargado.mask, mask)
    assert recargado.mask.dtype == np.bool_
    # transform equivalente (mismos 6 coeficientes afines).
    assert np.allclose(np.array(recargado.transform), np.array(transform))
    # crs equivalente (misma proyeccion UTM 19S).
    assert recargado.crs == crs
    assert recargado.crs.to_epsg() == 32719
