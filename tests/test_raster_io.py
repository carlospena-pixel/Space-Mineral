"""Pruebas de la escritura de GeoTIFF georreferenciados.

Sin dependencia de la escena: el Scene se arma sintetico, como en
tests/test_maps.py. Los archivos se escriben en el tmp_path de pytest.
"""

import hashlib

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS

from mineralmap.io.raster_io import Scene, write_geotiff

# Transform de un AOI plausible: origen en UTM 19S y pixel de 20 m, que es la
# grilla objetivo del proyecto. La identidad serviria para los asserts, pero
# entonces el test no distinguiria "escribio la transform del Scene" de
# "escribio la transform por defecto de GDAL".
TRANSFORM_AOI = Affine(20.0, 0.0, 420000.0, 0.0, -20.0, 7780000.0)


def _scene_sintetico(alto: int = 4, ancho: int = 6) -> Scene:
    """Scene minimo de 2 bandas con georreferenciacion realista."""
    return Scene(
        cube=np.zeros((2, alto, ancho), dtype=np.float32),
        band_names=["B11", "B12"],
        transform=TRANSFORM_AOI,
        crs=CRS.from_epsg(32719),
        mask=np.ones((alto, ancho), dtype=bool),
    )


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_el_geotiff_conserva_crs_transform_dtype_y_valores(tmp_path):
    """Round-trip completo: lo que se lee es lo que se escribio.

    Es el contrato que hace utilizable el archivo fuera del proyecto: un .tif
    sin CRS o con la transform equivocada se abre igual en cualquier SIG y cae
    sobre el terreno equivocado.
    """
    scene = _scene_sintetico()
    mapa = np.linspace(0.1, 0.9, 24, dtype=np.float64).reshape(4, 6)
    ruta = tmp_path / "mapa.tif"

    write_geotiff(str(ruta), mapa, scene)

    with rasterio.open(ruta) as src:
        assert src.count == 1
        assert src.shape == (4, 6)
        assert src.crs == scene.crs
        assert src.transform == scene.transform
        assert src.dtypes == ("float32",)
        assert np.isnan(src.nodata)
        np.testing.assert_allclose(src.read(1), mapa.astype(np.float32))


def test_los_nan_del_mapa_sobreviven_a_la_escritura(tmp_path):
    """NaN es el nodata del archivo, no un valor que se aplaste a cero.

    Un angulo espectral de 0 rad es coincidencia perfecta con la firma: si el
    enmascarado se escribiera como 0, los pixeles invalidos apareceran como
    las detecciones mas fuertes del mapa.
    """
    scene = _scene_sintetico()
    mapa = np.full((4, 6), 0.3)
    mapa[0, 0] = np.nan
    ruta = tmp_path / "con_nan.tif"

    write_geotiff(str(ruta), mapa, scene)

    with rasterio.open(ruta) as src:
        leido = src.read(1)

    assert np.isnan(leido[0, 0])
    assert leido[1, 1] == pytest.approx(0.3)


def test_un_cubo_3d_se_escribe_como_multibanda_con_sus_descripciones(tmp_path):
    """Un raster de varias bandas que no dice que es cada una obliga a leer el
    codigo que lo produjo para interpretarlo."""
    scene = _scene_sintetico()
    cubo = np.stack([np.full((4, 6), 0.2), np.full((4, 6), 0.7)])
    ruta = tmp_path / "cubo.tif"

    write_geotiff(str(ruta), cubo, scene, band_descriptions=["angulo", "confianza"])

    with rasterio.open(ruta) as src:
        assert src.count == 2
        assert src.descriptions == ("angulo", "confianza")
        assert src.read(2)[0, 0] == pytest.approx(0.7)


def test_escribir_un_mapa_de_otra_forma_espacial_es_un_error(tmp_path):
    """Es el modo de fallo que no se nota: el archivo saldria perfecto y
    georreferenciado sobre una ventana que no es la suya.

    El mensaje nombra las dos formas porque el error tipico es haber calculado
    el mapa sobre un subconjunto del AOI, y saber cual de las dos es la del
    Scene es lo que dice donde esta la equivocacion.
    """
    scene = _scene_sintetico()

    with pytest.raises(ValueError, match=r"\(3, 3\).*\(4, 6\)"):
        write_geotiff(str(tmp_path / "no.tif"), np.zeros((3, 3)), scene)


def test_un_arreglo_que_no_es_2d_ni_3d_es_un_error(tmp_path):
    """Un vector 1D pasaria como "una fila" y produciria un raster degenerado."""
    scene = _scene_sintetico()

    with pytest.raises(ValueError, match="dimensiones"):
        write_geotiff(str(tmp_path / "no.tif"), np.zeros(24), scene)


def test_pedir_mas_descripciones_que_bandas_es_un_error(tmp_path):
    """Sin la comprobacion, la descripcion sobrante se pierde en silencio y el
    resto queda corrido una banda."""
    scene = _scene_sintetico()

    with pytest.raises(ValueError, match="descripciones"):
        write_geotiff(
            str(tmp_path / "no.tif"),
            np.zeros((4, 6)),
            scene,
            band_descriptions=["a", "b"],
        )


def test_el_directorio_padre_se_crea_si_no_existe(tmp_path):
    """El pipeline escribe en outputs/maps/ y no deberia fallar en un clon
    donde esa carpeta todavia no se creo."""
    scene = _scene_sintetico()
    ruta = tmp_path / "sin" / "crear" / "mapa.tif"

    write_geotiff(str(ruta), np.zeros((4, 6)), scene)

    assert ruta.exists()


def test_dos_escrituras_del_mismo_mapa_dan_archivos_identicos(tmp_path):
    """Es el test del criterio de reproducibilidad (E1).

    Si el GeoTIFF llevara fecha, usuario o ruta de origen en sus tags, dos
    corridas del mismo experimento producirian archivos distintos y comparar
    hashes dejaria de servir para decir si un resultado cambio.
    """
    scene = _scene_sintetico()
    mapa = np.linspace(0.0, 1.0, 24).reshape(4, 6)

    primera = tmp_path / "primera.tif"
    segunda = tmp_path / "segunda.tif"
    write_geotiff(str(primera), mapa, scene, band_descriptions=["angulo"])
    write_geotiff(str(segunda), mapa, scene, band_descriptions=["angulo"])

    assert _sha256(primera) == _sha256(segunda)
