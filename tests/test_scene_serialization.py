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


def _scene_minimo(meta=None) -> Scene:
    """Scene 1x2x2 con lo justo para ejercitar la serializacion."""
    return Scene(
        cube=np.zeros((1, 2, 2), dtype=np.float32),
        band_names=["B2"],
        transform=Affine(20.0, 0.0, 300000.0, 0.0, -20.0, 6000000.0),
        crs=CRS.from_epsg(32719),
        mask=np.ones((2, 2), dtype=bool),
        meta=meta if meta is not None else {},
    )


def test_meta_sobrevive_el_round_trip_con_sus_tipos(tmp_path):
    """meta viaja como JSON: strings, ints, floats, listas y dicts anidados."""
    meta = {
        "safe_name": "S2B_MSIL2A_20251231T144729_T19KDT.SAFE",
        "processing_baseline": "05.11",
        "boa_offset": -1000.0,
        "aoi_window": [1000, 1000, 2000, 2000],
        "bands_source": {"B8": 10, "B9": 60, "B11": 20},
    }

    ruta = tmp_path / "con_meta.npz"
    save_scene(_scene_minimo(meta), str(ruta))
    recargado = load_scene(str(ruta))

    assert recargado.meta == meta
    assert isinstance(recargado.meta["boa_offset"], float)
    assert isinstance(recargado.meta["bands_source"]["B8"], int)
    assert isinstance(recargado.meta["processing_baseline"], str)


def test_npz_antiguo_sin_meta_se_carga_con_meta_vacio(tmp_path):
    """Un .npz escrito antes de que Scene tuviera meta debe seguir cargandose."""
    scene = _scene_minimo()
    ruta = tmp_path / "sin_meta.npz"

    # Se escribe a mano sin la clave `meta`, replicando el formato anterior.
    np.savez(
        ruta,
        cube=scene.cube,
        band_names=np.asarray(scene.band_names),
        transform=np.asarray(tuple(scene.transform)[:6], dtype=np.float64),
        crs=scene.crs.to_wkt(),
        mask=scene.mask,
    )

    recargado = load_scene(str(ruta))

    assert recargado.meta == {}
    assert recargado.band_names == ["B2"]
