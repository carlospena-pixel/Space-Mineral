"""Pruebas de la carga, clasificacion y rasterizacion de la verdad de terreno.

Sin red y sin la escena de 196 MB: el Scene es sintetico (2 bandas de 10x10 px)
y los poligonos se construyen con coordenadas elegidas a mano, de modo que los
pixeles que deben quedar marcados se pueden contar sin ejecutar nada.

La grilla de los tests es `Affine(20, 0, 400000, 0, -20, 7800000)` sobre
EPSG:32719: pixel de 20 m, origen en la esquina superior izquierda, fila 0
arriba. En coordenadas del terreno el AOI de prueba va de E 400.000 a 400.200 y
de N 7.799.800 a 7.800.000.
"""

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS
from shapely.geometry import box

from mineralmap.io.raster_io import Scene
from mineralmap.validation.geology import (
    CLASE_AMBIGUO,
    CLASE_NEGATIVO,
    CLASE_POSITIVO,
    build_ground_truth,
    clasificar_unidades,
    load_geology_polygons,
    rasterize_ground_truth,
)

gpd = pytest.importorskip("geopandas")

# Grilla de prueba: 20 m de pixel, origen UTM 19S. No es la identidad a
# proposito: con `Affine.identity()` las coordenadas del terreno coinciden con
# los indices de pixel y el test de reproyeccion no distinguiria un acierto de
# una casualidad.
TRANSFORM = Affine(20.0, 0.0, 400000.0, 0.0, -20.0, 7800000.0)
CRS_ESCENA = CRS.from_epsg(32719)
ALTO = ANCHO = 10

# Esquina superior izquierda del AOI de prueba, en coordenadas del terreno.
E0, N0 = 400000.0, 7800000.0
PIXEL = 20.0

CAMPO = "Unidad_geologica"


def _scene(alto: int = ALTO, ancho: int = ANCHO) -> Scene:
    """Scene minimo de 2 bandas con la grilla de prueba."""
    return Scene(
        cube=np.zeros((2, alto, ancho), dtype=np.float32),
        band_names=["B11", "B12"],
        transform=TRANSFORM,
        crs=CRS_ESCENA,
        mask=np.ones((alto, ancho), dtype=bool),
    )


def _caja_de_pixeles(col0: int, fila0: int, ncols: int, nfilas: int):
    """Poligono que cubre exactamente el bloque de pixeles indicado.

    Traduce indices de pixel a coordenadas del terreno con la misma transform
    del Scene, para que el test pueda declarar "las filas 2-4, columnas 1-3" y
    comparar contra un slice de numpy escrito con esos mismos indices.
    """
    izq = E0 + col0 * PIXEL
    der = izq + ncols * PIXEL
    arriba = N0 - fila0 * PIXEL
    abajo = arriba - nfilas * PIXEL
    return box(izq, abajo, der, arriba)


def _gdf(geometrias, unidades, crs=CRS_ESCENA):
    """GeoDataFrame de poligonos con su columna de unidad geologica."""
    return gpd.GeoDataFrame({CAMPO: list(unidades)}, geometry=list(geometrias), crs=crs)


def _mapping(positivo=(), negativo=()):
    """Config minimo equivalente al que devuelve `cargar_config_verdad`."""
    return {
        "fuente": {"campo_unidad": CAMPO},
        "_campo_unidad": CAMPO,
        "clases": {
            "positivo": CLASE_POSITIVO,
            "negativo": CLASE_NEGATIVO,
            "ambiguo": CLASE_AMBIGUO,
        },
        "unidades": {"positivo": list(positivo), "negativo": list(negativo)},
    }


# --------------------------------------------------------------------------
# 1. Alineacion con el Scene
# --------------------------------------------------------------------------


def test_el_raster_tiene_la_forma_espacial_del_scene():
    """La salida calza con `scene.cube.shape[1:]`, que es lo que la hace
    comparable pixel a pixel con el mapa de angulos."""
    scene = _scene()
    gdf = _gdf([_caja_de_pixeles(0, 0, 3, 3)], ["alterada"])
    clasificados = clasificar_unidades(gdf, _mapping(positivo=["alterada"]))

    raster = rasterize_ground_truth(clasificados, scene)

    assert raster.shape == scene.cube.shape[1:] == (ALTO, ANCHO)
    assert raster.dtype == np.uint8


def test_la_forma_sigue_al_scene_cuando_no_es_cuadrado():
    """Un Scene rectangular no se rasteriza como cuadrado: sin esto, un error
    de orden (alto, ancho) pasaria inadvertido en la grilla cuadrada."""
    scene = _scene(alto=7, ancho=13)
    gdf = _gdf([_caja_de_pixeles(0, 0, 2, 2)], ["alterada"])
    clasificados = clasificar_unidades(gdf, _mapping(positivo=["alterada"]))

    assert rasterize_ground_truth(clasificados, scene).shape == (7, 13)


# --------------------------------------------------------------------------
# 2. Correccion geometrica
# --------------------------------------------------------------------------


def test_un_poligono_marca_exactamente_los_pixeles_que_cubre():
    """Un rectangulo sobre filas 2-4 y columnas 1-3 marca esos 9 pixeles y
    ningun otro. Los indices se cuentan a mano desde la transform."""
    scene = _scene()
    gdf = _gdf([_caja_de_pixeles(col0=1, fila0=2, ncols=3, nfilas=3)], ["alterada"])
    clasificados = clasificar_unidades(gdf, _mapping(positivo=["alterada"]))

    raster = rasterize_ground_truth(clasificados, scene)

    esperado = np.full((ALTO, ANCHO), CLASE_AMBIGUO, dtype=np.uint8)
    esperado[2:5, 1:4] = CLASE_POSITIVO

    np.testing.assert_array_equal(raster, esperado)
    assert int((raster == CLASE_POSITIVO).sum()) == 9


def test_positivo_y_negativo_conviven_en_el_mismo_raster():
    """Dos unidades disjuntas producen sus dos clases, cada una en su sitio."""
    scene = _scene()
    gdf = _gdf(
        [
            _caja_de_pixeles(0, 0, 2, 2),
            _caja_de_pixeles(5, 5, 3, 2),
        ],
        ["alterada", "salar"],
    )
    clasificados = clasificar_unidades(
        gdf, _mapping(positivo=["alterada"], negativo=["salar"])
    )

    raster = rasterize_ground_truth(clasificados, scene)

    esperado = np.full((ALTO, ANCHO), CLASE_AMBIGUO, dtype=np.uint8)
    esperado[0:2, 0:2] = CLASE_POSITIVO
    esperado[5:7, 5:8] = CLASE_NEGATIVO

    np.testing.assert_array_equal(raster, esperado)


def test_en_un_solape_gana_el_positivo():
    """Donde un negativo y un positivo se pisan prevalece el positivo.

    Las dos hojas de la cartografia se solapan en una franja real (E
    447.510-447.677), asi que el caso ocurre. Se elige el positivo porque es la
    clase rara: borrarla con un negativo la haria desaparecer sin dejar rastro,
    mientras que lo contrario solo agrega un area positiva que se ve.
    """
    scene = _scene()
    gdf = _gdf(
        [
            _caja_de_pixeles(0, 0, 4, 4),  # negativo, grande
            _caja_de_pixeles(1, 1, 2, 2),  # positivo, encima
        ],
        ["salar", "alterada"],
    )
    clasificados = clasificar_unidades(
        gdf, _mapping(positivo=["alterada"], negativo=["salar"])
    )

    raster = rasterize_ground_truth(clasificados, scene)

    assert np.all(raster[1:3, 1:3] == CLASE_POSITIVO)
    assert raster[0, 0] == CLASE_NEGATIVO


# --------------------------------------------------------------------------
# 3. Reproyeccion: el fallo que no se nota
# --------------------------------------------------------------------------


def test_la_misma_geometria_en_4326_da_el_mismo_raster_que_en_32719():
    """Un GeoDataFrame en lon/lat se reproyecta antes de rasterizar.

    Es el test que atrapa el modo de fallo silencioso: sin `.to_crs()`, unas
    coordenadas en grados contra una transform en metros no lanzan nada,
    simplemente no marcan nada, y la capa sale entera en `ambiguo` --- que es
    justo el aspecto que tiene una capa correcta con el YAML sin llenar.
    """
    scene = _scene()
    geometria = _caja_de_pixeles(col0=2, fila0=3, ncols=4, nfilas=2)

    en_utm = _gdf([geometria], ["alterada"])
    en_wgs84 = en_utm.to_crs(4326)
    assert en_wgs84.crs.to_epsg() == 4326

    mapping = _mapping(positivo=["alterada"])
    raster_utm = rasterize_ground_truth(clasificar_unidades(en_utm, mapping), scene)
    raster_wgs = rasterize_ground_truth(clasificar_unidades(en_wgs84, mapping), scene)

    np.testing.assert_array_equal(raster_utm, raster_wgs)
    # Y no coinciden por estar ambos vacios, que los haria pasar sin decir nada.
    assert int((raster_wgs == CLASE_POSITIVO).sum()) == 8


# --------------------------------------------------------------------------
# 4. Fill: lo no cubierto es ambiguo, no negativo
# --------------------------------------------------------------------------


def test_los_pixeles_fuera_de_todo_poligono_valen_255():
    """Fuera de la cartografia no se sabe nada, y eso no es "no hay"."""
    scene = _scene()
    gdf = _gdf([_caja_de_pixeles(0, 0, 2, 2)], ["alterada"])
    clasificados = clasificar_unidades(gdf, _mapping(positivo=["alterada"]))

    raster = rasterize_ground_truth(clasificados, scene)

    assert raster[9, 9] == CLASE_AMBIGUO
    assert int((raster == CLASE_AMBIGUO).sum()) == ALTO * ANCHO - 4


def test_sin_poligonos_que_pintar_la_capa_queda_entera_en_fill():
    """El estado del pipeline con el YAML sin llenar es valido, no un error."""
    scene = _scene()
    gdf = _gdf([_caja_de_pixeles(0, 0, 3, 3)], ["unidad cualquiera"])

    with pytest.warns(UserWarning):
        clasificados = clasificar_unidades(gdf, _mapping())

    raster = rasterize_ground_truth(clasificados, scene)

    assert np.all(raster == CLASE_AMBIGUO)


# --------------------------------------------------------------------------
# 5. all_touched
# --------------------------------------------------------------------------


def test_all_touched_false_no_marca_un_pixel_que_el_poligono_solo_roza():
    """Un poligono que entra 5 m en un pixel de 20 m no lo marca con
    `all_touched=False`, y si lo marca con True.

    El poligono va de E 400.000 a E 400.025: cubre entero el pixel de la
    columna 0 (400.000-400.020) y solo los primeros 5 m del de la columna 1
    (400.020-400.040), cuyo centro esta en E 400.030. Como el centro queda
    fuera, la columna 1 no se marca. Verticalmente cubre las filas 0 y 1
    completas (N 7.800.000 a 7.799.960).
    """
    scene = _scene()
    poligono = box(400000.0, 7799960.0, 400025.0, 7800000.0)
    gdf = _gdf([poligono], ["alterada"])
    clasificados = clasificar_unidades(gdf, _mapping(positivo=["alterada"]))

    ajustado = rasterize_ground_truth(clasificados, scene, all_touched=False)
    generoso = rasterize_ground_truth(clasificados, scene, all_touched=True)

    # El centro del pixel (0,1) esta en E 400.030, fuera del poligono.
    assert ajustado[0, 1] == CLASE_AMBIGUO
    assert generoso[0, 1] == CLASE_POSITIVO

    # La columna 0 queda marcada en ambos casos: el poligono la cubre entera.
    assert ajustado[0, 0] == generoso[0, 0] == CLASE_POSITIVO

    # `all_touched=True` solo puede agregar area, nunca quitarla.
    assert int((generoso == CLASE_POSITIVO).sum()) > int(
        (ajustado == CLASE_POSITIVO).sum()
    )


# --------------------------------------------------------------------------
# 6. Unidades sin clasificar
# --------------------------------------------------------------------------


def test_una_unidad_no_declarada_cae_en_ambiguo_y_avisa():
    """El silencio del YAML significa "no lo se", y se avisa por warning."""
    scene = _scene()
    gdf = _gdf(
        [_caja_de_pixeles(0, 0, 3, 3), _caja_de_pixeles(5, 5, 2, 2)],
        ["alterada", "unidad que nadie clasifico"],
    )

    with pytest.warns(UserWarning, match="sin clasificar"):
        clasificados = clasificar_unidades(gdf, _mapping(positivo=["alterada"]))

    raster = rasterize_ground_truth(clasificados, scene)

    assert np.all(raster[0:3, 0:3] == CLASE_POSITIVO)
    assert np.all(raster[5:7, 5:7] == CLASE_AMBIGUO)


def test_no_avisa_cuando_todo_esta_clasificado():
    """Un warning que suena siempre deja de leerse."""
    import warnings

    gdf = _gdf([_caja_de_pixeles(0, 0, 2, 2)], ["alterada"])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        clasificar_unidades(gdf, _mapping(positivo=["alterada"]))


def test_la_comparacion_de_unidades_ignora_espacios_de_los_extremos():
    """La fuente trae la misma unidad con y sin espacio final.

    En la hoja Mamina, "Granitos, monzonitas cuarciferas y sienogranitos del
    Cretacico Superior" aparece como dos etiquetas distintas. Sin recortar, el
    YAML nombraria una y la otra caeria en `ambiguo` en silencio.
    """
    scene = _scene()
    gdf = _gdf(
        [_caja_de_pixeles(0, 0, 2, 2), _caja_de_pixeles(4, 4, 2, 2)],
        ["Granito X", "Granito X "],
    )
    clasificados = clasificar_unidades(gdf, _mapping(positivo=["Granito X"]))

    raster = rasterize_ground_truth(clasificados, scene)

    assert np.all(raster[0:2, 0:2] == CLASE_POSITIVO)
    assert np.all(raster[4:6, 4:6] == CLASE_POSITIVO)


# --------------------------------------------------------------------------
# 7. Errores con mensaje util
# --------------------------------------------------------------------------


def test_un_archivo_inexistente_dice_donde_busco(tmp_path):
    with pytest.raises(FileNotFoundError, match="descargar_geologia"):
        load_geology_polygons(str(tmp_path / "no_existe.geojson"))


def test_un_archivo_sin_poligonos_es_rechazado(tmp_path):
    """La verdad de terreno se construye rasterizando areas, no puntos."""
    from shapely.geometry import Point

    ruta = tmp_path / "puntos.geojson"
    gpd.GeoDataFrame(
        {CAMPO: ["a"]}, geometry=[Point(400000, 7800000)], crs=CRS_ESCENA
    ).to_file(ruta, driver="GeoJSON")

    with pytest.raises(ValueError, match="poligono"):
        load_geology_polygons(str(ruta))


def test_rasterizar_sin_crs_falla_en_vez_de_inventar_uno():
    """Un GeoDataFrame sin CRS no se puede reproyectar, y rasterizarlo igual
    daria un raster impecable sobre el terreno equivocado."""
    scene = _scene()
    gdf = _gdf([_caja_de_pixeles(0, 0, 2, 2)], ["alterada"], crs=None)
    clasificados = clasificar_unidades(gdf, _mapping(positivo=["alterada"]))

    with pytest.raises(ValueError, match="sin CRS"):
        rasterize_ground_truth(clasificados, scene)


def test_rasterizar_sin_la_columna_clase_falla():
    """Hay que pasar por `clasificar_unidades` antes de rasterizar."""
    scene = _scene()
    gdf = _gdf([_caja_de_pixeles(0, 0, 2, 2)], ["alterada"])

    with pytest.raises(ValueError, match="clase"):
        rasterize_ground_truth(gdf, scene)


def test_clasificar_sin_la_columna_de_unidad_falla():
    scene = _scene()  # noqa: F841  (fija la grilla del poligono de prueba)
    gdf = gpd.GeoDataFrame(
        {"otra_columna": ["a"]},
        geometry=[_caja_de_pixeles(0, 0, 2, 2)],
        crs=CRS_ESCENA,
    )

    with pytest.raises(ValueError, match="Unidad_geologica"):
        clasificar_unidades(gdf, _mapping(positivo=["alterada"]))


def test_una_unidad_declarada_en_dos_clases_es_una_contradiccion(tmp_path):
    """Un desempate elegido por el codigo quedaria escondido y le cambiaria el
    significado al YAML."""
    from mineralmap.validation.geology import cargar_config_verdad

    ruta = tmp_path / "conflicto.yaml"
    ruta.write_text(
        "fuente:\n"
        "  capa: capa.geojson\n"
        "  campo_unidad: Unidad_geologica\n"
        "unidades:\n"
        "  positivo: [Granito X]\n"
        "  negativo: [Granito X]\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="positivo y negativo"):
        cargar_config_verdad(str(ruta))


def test_un_config_sin_fuente_es_rechazado(tmp_path):
    from mineralmap.validation.geology import cargar_config_verdad

    ruta = tmp_path / "vacio.yaml"
    ruta.write_text("clases: {positivo: 1}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="fuente"):
        cargar_config_verdad(str(ruta))


def test_build_ground_truth_recorre_el_camino_completo(tmp_path):
    """Del YAML al raster, con dos capas que se concatenan, sin red."""
    capa_a = tmp_path / "a.geojson"
    capa_b = tmp_path / "b.geojson"
    _gdf([_caja_de_pixeles(0, 0, 3, 3)], ["alterada"]).to_file(capa_a, driver="GeoJSON")
    _gdf([_caja_de_pixeles(6, 6, 2, 2)], ["salar"]).to_file(capa_b, driver="GeoJSON")

    config = tmp_path / "verdad.yaml"
    config.write_text(
        f"fuente:\n"
        f"  a: {capa_a.as_posix()}\n"
        f"  b: {capa_b.as_posix()}\n"
        f"  campo_unidad: {CAMPO}\n"
        f"unidades:\n"
        f"  positivo: [alterada]\n"
        f"  negativo: [salar]\n",
        encoding="utf-8",
    )

    raster, traza = build_ground_truth(str(config), _scene())

    assert raster.shape == (ALTO, ANCHO)
    assert np.all(raster[0:3, 0:3] == CLASE_POSITIVO)
    assert np.all(raster[6:8, 6:8] == CLASE_NEGATIVO)
    assert traza["poligonos_totales"] == 2
    assert traza["pixeles_por_clase"]["positivo"] == 9
    assert traza["pixeles_por_clase"]["negativo"] == 4
    assert traza["unidades_sin_clasificar"] == {}
    assert set(traza["archivos"]) == {"a", "b"}


# --------------------------------------------------------------------------
# 8. Los GeoJSON reales, si estan en disco
# --------------------------------------------------------------------------

RUTAS_REALES = (
    "data/external/geologia/pozo_almonte.geojson",
    "data/external/geologia/mamina.geojson",
)

# Bbox del AOI del proyecto en EPSG:32719 (ventana col_off=2700, row_off=650,
# 2000x2000 px a 20 m sobre el tile T19KDT). Es el AOI del distrito Cerro
# Colorado, al que se movio la ventana en la Semana 5.
AOI_BBOX = (453960.0, 7747040.0, 493960.0, 7787040.0)

# Unidades por las que se movio el AOI: son la razon de ser de la ventana
# nueva. Se nombran por fragmento porque la etiqueta completa trae acentos y
# variantes de facies.
UNIDADES_DE_ALTERACION = ("Cerro Colorado", "Brechas hidrotermales")


def _faltan_los_geojson() -> bool:
    from pathlib import Path

    return not all(Path(ruta).exists() for ruta in RUTAS_REALES)


@pytest.mark.skipif(
    _faltan_los_geojson(),
    reason="los GeoJSON reales no estan en disco; corre scripts/descargar_geologia.py",
)
def test_la_union_de_las_dos_hojas_contiene_el_aoi():
    """Si la cartografia no cubre el AOI, rasterizarla no tiene sentido."""
    import pandas as pd

    capas = [load_geology_polygons(ruta) for ruta in RUTAS_REALES]
    assert all(capa.crs.to_epsg() == 32719 for capa in capas)

    union = gpd.GeoDataFrame(
        pd.concat(capas, ignore_index=True), geometry="geometry", crs=capas[0].crs
    )
    izq, abajo, der, arriba = union.total_bounds
    aoi_izq, aoi_abajo, aoi_der, aoi_arriba = AOI_BBOX

    assert izq <= aoi_izq, f"la cartografia empieza en E {izq}, al este del AOI"
    assert abajo <= aoi_abajo, f"la cartografia empieza en N {abajo}"
    assert der >= aoi_der, f"la cartografia termina en E {der}, al oeste del AOI"
    assert arriba >= aoi_arriba, f"la cartografia termina en N {arriba}"


@pytest.mark.skipif(
    _faltan_los_geojson(),
    reason="los GeoJSON reales no estan en disco; corre scripts/descargar_geologia.py",
)
def test_las_dos_hojas_se_solapan_y_no_dejan_hueco_en_la_costura():
    """Entre las dos hojas no puede haber un hueco.

    El AOI actual cae entero dentro de Mamina, asi que hoy la costura no lo
    toca. El test se conserva igual porque la ventana ya se movio dos veces:
    si vuelve a correrse al oeste y hubiera un hueco entre las hojas, quedaria
    una franja vertical de `ambiguo` con toda la pinta de ser un resultado.
    """
    oeste = load_geology_polygons(RUTAS_REALES[0])
    este = load_geology_polygons(RUTAS_REALES[1])

    borde_este_de_oeste = oeste.total_bounds[2]
    borde_oeste_de_este = este.total_bounds[0]

    assert borde_oeste_de_este <= borde_este_de_oeste, (
        f"hay un hueco entre las hojas: la oeste termina en E "
        f"{borde_este_de_oeste} y la este empieza en E {borde_oeste_de_este}"
    )


@pytest.mark.skipif(
    _faltan_los_geojson(),
    reason="los GeoJSON reales no estan en disco; corre scripts/descargar_geologia.py",
)
def test_las_unidades_de_alteracion_caen_dentro_del_aoi():
    """El AOI se movio a Cerro Colorado justamente para incluirlas.

    Es el test que ancla la razon de ser de la ventana: sin estas unidades
    adentro no hay positivo posible en la verdad de terreno, y el criterio E3
    del Plan Maestro --- "las detecciones se concentran preferentemente en
    zonas de alteracion documentadas" --- no se puede ni formular. Fue
    exactamente lo que pasaba con la ventana anterior.
    """
    import pandas as pd

    capas = [load_geology_polygons(ruta) for ruta in RUTAS_REALES]
    union = gpd.GeoDataFrame(
        pd.concat(capas, ignore_index=True), geometry="geometry", crs=capas[0].crs
    )
    aoi_izq, aoi_abajo, aoi_der, aoi_arriba = AOI_BBOX

    for fragmento in UNIDADES_DE_ALTERACION:
        seleccion = union[union["Unidad_geologica"].str.contains(fragmento, na=False)]
        assert not seleccion.empty, f"no hay ninguna unidad que contenga {fragmento!r}"

        izq, abajo, der, arriba = seleccion.total_bounds
        assert izq >= aoi_izq and der <= aoi_der, (
            f"{fragmento}: E {izq:.0f}-{der:.0f} se sale del AOI "
            f"E {aoi_izq:.0f}-{aoi_der:.0f}"
        )
        assert abajo >= aoi_abajo and arriba <= aoi_arriba, (
            f"{fragmento}: N {abajo:.0f}-{arriba:.0f} se sale del AOI "
            f"N {aoi_abajo:.0f}-{aoi_arriba:.0f}"
        )
