"""Carga de poligonos geologicos SERNAGEOMIN y rasterizacion de la verdad de terreno.

Este modulo convierte la cartografia vectorial en una capa raster alineada
pixel a pixel con el `Scene`, para que la deteccion espectral se pueda cotejar
contra algo que no salio del mismo dato que la produjo.

De donde salen los poligonos
----------------------------
De las dos hojas 1:100.000 de SERNAGEOMIN de la zona --- Pozo Almonte (M204)
y Mamina (M303) ---, descargadas con
`scripts/descargar_geologia.py` desde el FeatureServer `Chile_Geology`. Ese
servicio es una **digitalizacion de terceros** sin licencia declarada: se usa
como insumo tecnico y la cita que corresponde es siempre la carta original. Ver
`data/external/geologia/README.md`.

Por que la verdad de terreno no es un filtro
--------------------------------------------
SERNAGEOMIN publica un unico tema cartografico ("Geologia Basica") y **no**
publica poligonos de alteracion hidrotermal para el norte de Chile. Las cartas
traen litologia, no alteracion, asi que no hay ninguna columna "alteracion" que
filtrar. El positivo de la verdad de terreno es una **seleccion de unidades
litologicas** declarada a mano en `configs/verdad_terreno_cerro_colorado.yaml`.
un juicio geologico explicito, no un dato del mapa original, y por eso vive en
un YAML versionado y revisable en vez de estar escrito en este archivo.

Por que hay tres clases y no dos
--------------------------------
`1` positivo, `0` negativo y `255` ambiguo (unidad no clasificada o pixel fuera
de todo poligono). Los `255` se excluyen del calculo de metricas. Colapsarlos a
`0` convertiria "no lo se" en "no hay", que sobre una clase tan desbalanceada
como esta es justo la sustitucion que infla la precision sin que nada falle.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np
import yaml

# Valores por defecto de las tres clases. El YAML puede sobreescribirlos, pero
# tener el default aca permite construir y testear la capa sin un YAML delante.
CLASE_POSITIVO = 1
CLASE_NEGATIVO = 0
CLASE_AMBIGUO = 255

# Nombre de la columna que agrega `clasificar_unidades` y que consume
# `rasterize_ground_truth`. Se declara como constante porque es el contrato
# entre ambas funciones.
COLUMNA_CLASE = "clase"


def _normalizar_etiqueta(valor: Any) -> str:
    """Normaliza el nombre de una unidad para compararlo con el YAML.

    Solo recorta espacios de los extremos. Hace falta porque la fuente trae la
    misma unidad con dos etiquetas: en la hoja Mamina, "Granitos, monzonitas
    cuarciferas y sienogranitos del Cretacico Superior" aparece con y sin
    espacio final (32,73 km2 y 0,53 km2). Sin recortar, el YAML nombraria una
    de las dos y la otra caeria en `ambiguo` sin que nada lo advirtiera.

    No se toca nada mas --- ni mayusculas ni acentos ---: cualquier
    normalizacion mas agresiva empieza a fusionar unidades que la carta
    distingue a proposito.
    """
    return "" if valor is None else str(valor).strip()


def load_geology_polygons(path: str):
    """Lee un archivo vectorial de poligonos geologicos.

    Parameters
    ----------
    path:
        Ruta del archivo. `geopandas.read_file` cubre GeoJSON, shapefile y
        GeoPackage, asi que no se restringe la extension.

    Returns
    -------
    geopandas.GeoDataFrame
        Los poligonos tal como vienen, sin reproyectar. La reproyeccion es
        trabajo de `rasterize_ground_truth`, que es quien conoce el CRS destino.

    Raises
    ------
    FileNotFoundError
        Si el archivo no existe. El mensaje nombra la ruta buscada y el script
        que la genera.
    ValueError
        Si el archivo no trae ninguna geometria de poligono, o si viene sin CRS
        declarado. Un GeoDataFrame sin CRS no se puede reproyectar, y
        rasterizarlo igual produce un raster impecable sobre el terreno
        equivocado: no falla nunca y no hay forma de notarlo mirando la salida.
    """
    import geopandas as gpd

    ruta = Path(path)
    if not ruta.exists():
        raise FileNotFoundError(
            f"No encontre el archivo de poligonos {ruta}. "
            "¿Corriste `python scripts/descargar_geologia.py`?"
        )

    gdf = gpd.read_file(ruta)

    if gdf.crs is None:
        raise ValueError(
            f"{ruta} no declara CRS. Sin CRS no se puede reproyectar a la "
            "grilla del Scene, y rasterizarlo igual daria una verdad de "
            "terreno georreferenciada sobre otra parte del desierto."
        )

    tipos = set(gdf.geometry.geom_type.dropna().unique())
    if not tipos & {"Polygon", "MultiPolygon"}:
        raise ValueError(
            f"{ruta} no trae geometrias de poligono; encontre {sorted(tipos)}. "
            "La verdad de terreno se construye rasterizando areas, no puntos "
            "ni lineas."
        )

    return gdf


def cargar_config_verdad(config_path: str) -> dict:
    """Lee y valida el YAML que asigna una clase a cada unidad geologica.

    Parameters
    ----------
    config_path:
        Ruta del YAML, p. ej. `configs/verdad_terreno_cerro_colorado.yaml`.

    Returns
    -------
    dict
        El contenido del YAML, con `clases` y `unidades` completados con los
        defaults del modulo si el archivo los omite. Las listas de `unidades`
        pueden venir vacias: eso deja todo el AOI en `ambiguo`, que es un
        estado valido --- el del pipeline antes de que alguien clasifique ---
        y no un error.

    Raises
    ------
    FileNotFoundError
        Si el YAML no existe.
    ValueError
        Si no trae la seccion `fuente`, si `fuente` no nombra ningun archivo de
        poligonos, o si una misma unidad aparece en mas de una lista de clase.
    """
    ruta = Path(config_path)
    if not ruta.exists():
        raise FileNotFoundError(f"No encontre el config de verdad de terreno {ruta}.")

    config = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}

    fuente = config.get("fuente")
    if not isinstance(fuente, dict):
        raise ValueError(
            f"{ruta} no trae una seccion `fuente` con las rutas de los "
            "GeoJSON y el nombre del campo de unidad."
        )

    campo = fuente.get("campo_unidad")
    if not campo:
        raise ValueError(
            f"{ruta} no declara `fuente.campo_unidad`; sin el no se sabe que "
            "columna de la cartografia nombra la unidad geologica."
        )

    archivos = {k: v for k, v in fuente.items() if k != "campo_unidad"}
    if not archivos:
        raise ValueError(f"{ruta} no nombra ningun archivo de poligonos en `fuente`.")

    clases = {
        "positivo": CLASE_POSITIVO,
        "negativo": CLASE_NEGATIVO,
        "ambiguo": CLASE_AMBIGUO,
        **(config.get("clases") or {}),
    }
    unidades = config.get("unidades") or {}
    unidades = {
        nombre: list(unidades.get(nombre) or []) for nombre in ("positivo", "negativo")
    }

    # Una unidad en dos listas es una contradiccion del criterio, no un empate
    # que el codigo pueda resolver por su cuenta: cualquier desempate que
    # eligiera aca quedaria escondido y le cambiaria el significado al YAML.
    repetidas = {_normalizar_etiqueta(u) for u in unidades["positivo"]} & {
        _normalizar_etiqueta(u) for u in unidades["negativo"]
    }
    if repetidas:
        raise ValueError(
            f"{ruta} declara estas unidades como positivo y negativo a la vez: "
            f"{sorted(repetidas)}. Hay que decidir una."
        )

    config["fuente"] = fuente
    config["clases"] = clases
    config["unidades"] = unidades
    config["_archivos"] = archivos
    config["_campo_unidad"] = campo
    return config


def clasificar_unidades(gdf, mapping: dict):
    """Agrega la columna `clase` (uint8) segun el mapeo unidad -> clase del YAML.

    Todo lo que no este nombrado en `unidades.positivo` ni en
    `unidades.negativo` cae en `ambiguo`. Es el default deliberado: la carta
    trae decenas de unidades y solo unas pocas se pueden defender como
    compatibles con alteracion argilica, asi que el silencio del YAML tiene que
    significar "no lo se", nunca "no hay".

    Parameters
    ----------
    gdf:
        GeoDataFrame de poligonos, con la columna que nombra
        `mapping["fuente"]["campo_unidad"]`.
    mapping:
        Config ya validado por `cargar_config_verdad`, o un dict con las mismas
        claves (`fuente.campo_unidad`, `clases`, `unidades`).

    Returns
    -------
    geopandas.GeoDataFrame
        Copia del GeoDataFrame con la columna `clase` agregada.

    Warns
    -----
    UserWarning
        Si quedan unidades sin clasificar, informando cuantas son y que
        fraccion de la superficie total representan. Sin este aviso, un YAML
        cuyas listas no casan con las etiquetas reales de la carta produce una
        capa 100 % ambigua que se ve exactamente igual que una capa correcta
        hasta que alguien mira el histograma.

    Raises
    ------
    ValueError
        Si el GeoDataFrame no trae la columna de unidad declarada.
    """
    campo = mapping.get("_campo_unidad") or mapping["fuente"]["campo_unidad"]
    clases = mapping["clases"]
    unidades = mapping["unidades"]

    if campo not in gdf.columns:
        raise ValueError(
            f"Los poligonos no traen la columna '{campo}' declarada en "
            f"`fuente.campo_unidad`; columnas disponibles: {list(gdf.columns)}."
        )

    tabla = {}
    for nombre_clase in ("negativo", "positivo"):
        valor = int(clases[nombre_clase])
        for unidad in unidades.get(nombre_clase, []):
            tabla[_normalizar_etiqueta(unidad)] = valor

    ambiguo = int(clases["ambiguo"])
    etiquetas = gdf[campo].map(_normalizar_etiqueta)
    asignadas = etiquetas.map(lambda e: tabla.get(e, ambiguo)).astype("uint8")

    resultado = gdf.copy()
    resultado[COLUMNA_CLASE] = asignadas

    sin_clasificar = sorted(set(etiquetas[asignadas == ambiguo]))
    if sin_clasificar:
        # El area se calcula solo si el CRS es proyectado: en grados el
        # numero no significa nada y un "12,4 % de la superficie" en unidades
        # de latitud es peor que no decir nada.
        if gdf.crs is not None and gdf.crs.is_projected:
            areas = gdf.geometry.area
            fraccion = 100.0 * float(areas[asignadas == ambiguo].sum() / areas.sum())
            detalle = f", {fraccion:.2f} % de la superficie de la cartografia"
        else:
            detalle = ""
        warnings.warn(
            f"{len(sin_clasificar)} unidades geologicas quedaron sin clasificar "
            f"y caen en `ambiguo`{detalle}. Las primeras: "
            f"{sin_clasificar[:5]}. Se declaran en "
            "configs/verdad_terreno_cerro_colorado.yaml.",
            stacklevel=2,
        )

    return resultado


def rasterize_ground_truth(
    polygons, scene, fill: int = CLASE_AMBIGUO, all_touched: bool = False
) -> np.ndarray:
    """Rasteriza los poligonos clasificados a la grilla exacta del `Scene`.

    Parameters
    ----------
    polygons:
        GeoDataFrame con la columna `clase` que agrega `clasificar_unidades`.
    scene:
        Scene que define la grilla destino. Aporta `crs`, `transform` y la
        forma espacial de `cube`.
    fill:
        Valor de los pixeles que ningun poligono cubre. Por defecto `255`
        (ambiguo): fuera de la cartografia no se sabe nada, y eso no es lo
        mismo que saber que no hay alteracion.
    all_touched:
        Si es False (el default), un pixel pertenece al poligono que cubre su
        **centro**. Con True se marca todo pixel que el poligono roce, lo que
        engorda cada area positiva en un anillo de un pixel completo justo en
        los bordes, que es donde una carta 1:100.000 es menos confiable frente
        a pixeles de 20 m. La precision del contacto entre unidades en esa
        carta es de varios pixeles; ensancharlo a proposito solo agrega area
        positiva que no se puede defender.

    Returns
    -------
    np.ndarray
        Arreglo `(alto, ancho)` uint8 con los valores de clase. **No se aplica
        `scene.mask`**: que un pixel sea valido (nubes, sombra, agua) y que
        este cubierto por la cartografia son dos cosas distintas, y quien las
        combina es el consumidor. Es el mismo criterio con que `scene_builder`
        entrega la mascara SCL aparte en vez de aplicarla al cubo.

    Raises
    ------
    ValueError
        Si `polygons` no trae la columna `clase`, si viene sin CRS, o si la
        forma resultante no calza con la del `Scene`.
    """
    import geopandas as gpd  # noqa: F401  (geopandas define el tipo de entrada)
    from rasterio.features import rasterize

    if COLUMNA_CLASE not in polygons.columns:
        raise ValueError(
            f"Los poligonos no traen la columna '{COLUMNA_CLASE}'; hay que "
            "pasarlos por `clasificar_unidades` antes de rasterizar."
        )

    if polygons.crs is None:
        raise ValueError(
            "Los poligonos vienen sin CRS declarado; no se pueden reproyectar "
            "a la grilla del Scene."
        )

    # Reproyectar siempre, aunque ya venga en el CRS destino: `to_crs` es
    # idempotente en ese caso y es la red de seguridad contra el unico modo de
    # fallo que no se nota. Un GeoDataFrame en 4326 rasterizado con una
    # transform en metros no lanza nada: devuelve un raster entero en `fill`,
    # o peor, un puñado de pixeles marcados en una esquina.
    proyectados = polygons.to_crs(scene.crs)

    forma = tuple(scene.cube.shape[1:])

    # Se descartan los poligonos cuya clase es el propio `fill`: dejarlos como
    # figuras a pintar no agrega informacion (ya es el fondo) y en un solape
    # borraria una clase concreta con un "no se". El orden ascendente por clase
    # hace que, donde dos poligonos se pisan, gane el valor mas alto: entre
    # negativo (0) y positivo (1) prevalece el positivo, que es la clase rara y
    # la que se perderia sin dejar rastro. Las dos hojas se solapan en una
    # franja estrecha (E 447.510-447.677), asi que el caso ocurre de verdad.
    a_pintar = proyectados[proyectados[COLUMNA_CLASE] != fill]
    a_pintar = a_pintar.sort_values(COLUMNA_CLASE, kind="stable")

    figuras = [
        (geometria, int(clase))
        for geometria, clase in zip(a_pintar.geometry, a_pintar[COLUMNA_CLASE])
        if geometria is not None and not geometria.is_empty
    ]

    if figuras:
        salida = rasterize(
            figuras,
            out_shape=forma,
            transform=scene.transform,
            fill=fill,
            all_touched=all_touched,
            dtype="uint8",
        )
    else:
        # `rasterize` exige al menos una figura. Sin poligonos que pintar, la
        # respuesta correcta es el fondo entero, no una excepcion: es lo que
        # pasa con el YAML sin llenar y es un estado valido del pipeline.
        salida = np.full(forma, fill, dtype="uint8")

    if salida.shape != forma:
        raise ValueError(
            f"El raster de verdad de terreno {salida.shape} no calza con la "
            f"forma espacial del Scene {forma}; compararlo con el mapa de "
            "angulos pixel a pixel no significaria nada."
        )

    return salida


def build_ground_truth(config_path: str, scene) -> tuple[np.ndarray, dict]:
    """Orquesta el camino completo: YAML -> poligonos -> clases -> raster.

    Parameters
    ----------
    config_path:
        Ruta del YAML de verdad de terreno.
    scene:
        Scene que define la grilla destino.

    Returns
    -------
    tuple[np.ndarray, dict]
        El raster `(alto, ancho)` uint8 y un dict de trazabilidad con los
        archivos usados, los poligonos y pixeles por clase, la fraccion del AOI
        en cada clase y las unidades que quedaron sin clasificar con su area.
        Ese dict es lo que imprime `scripts/construir_verdad_terreno.py`: la
        capa sola no dice de que cartografia salio ni cuanto de ella se dejo en
        "no se".

    Raises
    ------
    FileNotFoundError
        Si el YAML o alguno de los GeoJSON que nombra no existen.
    ValueError
        Si las capas no se pueden combinar o si el config esta mal formado.
    """
    import geopandas as gpd
    import pandas as pd

    config = cargar_config_verdad(config_path)
    campo = config["_campo_unidad"]
    clases = config["clases"]

    capas = []
    archivos_usados = {}
    for nombre, ruta in config["_archivos"].items():
        gdf = load_geology_polygons(ruta)
        archivos_usados[nombre] = {"ruta": str(ruta), "poligonos": int(len(gdf))}
        # Se homogeneiza el CRS antes de concatenar: `pd.concat` no lo revisa,
        # asi que dos capas en CRS distintos se apilarian sin quejarse y la
        # mitad de las geometrias quedaria en el hemisferio equivocado.
        capas.append(gdf.to_crs(scene.crs))

    combinados = gpd.GeoDataFrame(
        pd.concat(capas, ignore_index=True), geometry="geometry", crs=scene.crs
    )

    clasificados = clasificar_unidades(combinados, config)
    raster = rasterize_ground_truth(clasificados, scene, fill=int(clases["ambiguo"]))

    total_px = int(raster.size)
    valores, cuentas = np.unique(raster, return_counts=True)
    por_valor = {int(v): int(c) for v, c in zip(valores, cuentas)}

    pixeles_por_clase = {
        nombre: por_valor.get(int(valor), 0) for nombre, valor in clases.items()
    }
    fraccion_por_clase = {
        nombre: 100.0 * n / total_px for nombre, n in pixeles_por_clase.items()
    }

    conteo_clases = clasificados[COLUMNA_CLASE].value_counts()
    poligonos_por_clase = {
        nombre: int(conteo_clases.get(int(valor), 0))
        for nombre, valor in clases.items()
    }

    etiquetas = clasificados[campo].map(_normalizar_etiqueta)
    es_ambiguo = clasificados[COLUMNA_CLASE] == int(clases["ambiguo"])
    areas_km2 = clasificados.geometry.area / 1e6
    sin_clasificar = (
        areas_km2[es_ambiguo]
        .groupby(etiquetas[es_ambiguo])
        .sum()
        .sort_values(ascending=False)
    )

    trazabilidad = {
        "config": str(config_path),
        "campo_unidad": campo,
        "crs": str(scene.crs),
        "forma": tuple(int(v) for v in raster.shape),
        "archivos": archivos_usados,
        "poligonos_totales": int(len(clasificados)),
        "poligonos_por_clase": poligonos_por_clase,
        "pixeles_por_clase": pixeles_por_clase,
        "fraccion_aoi_por_clase_pct": fraccion_por_clase,
        "unidades_sin_clasificar": {
            str(unidad): float(area) for unidad, area in sin_clasificar.items()
        },
        "all_touched": False,
    }

    return raster, trazabilidad
