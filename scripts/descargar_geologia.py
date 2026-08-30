"""CLI: descarga la cartografia geologica que cubre el AOI del proyecto.

Baja las dos hojas 1:100.000 de SERNAGEOMIN de la zona --- Pozo Almonte (M204) y
Mamina (M303) --- desde el FeatureServer `Chile_Geology`, y las deja como
GeoJSON en EPSG:32719 bajo `data/external/geologia/`.

Por que dos hojas y no la "Carta Calama" del plan original: Calama esta en la
Region de Antofagasta, a unos 250 km al sur. La zona de estudio cambio a Pampa
del Tamarugal en la Semana 2 y al distrito Cerro Colorado en la Semana 5, y el
plan escrito nunca se actualizo.

Se bajan las dos aunque el AOI actual (lon -69,4412 a -69,0577) caiga entero
dentro de Mamina: el AOI anterior cruzaba el limite entre ambas cartas
(Pozo Almonte cubre 70,00-69,50 W; Mamina cubre 69,50-69,00 W), la ventana ya
se movio dos veces y unirlas no cuesta nada.

ADVERTENCIA SOBRE LA FUENTE. `Chile_Geology` es una digitalizacion de terceros
(publicada por Stanford en ArcGIS Online) de las cartas de SERNAGEOMIN, sin
licencia declarada. Se usa como insumo tecnico y la cita que corresponde es
siempre la carta original, no el servicio. Ver el README que este script
escribe junto a los GeoJSON.

Uso
---
    python scripts/descargar_geologia.py
    python scripts/descargar_geologia.py --force
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE_URL = (
    "https://services.arcgis.com/7CRlmWNEbeCqEJ6a/arcgis/rest/services"
    "/Chile_Geology/FeatureServer"
)

# EPSG del AOI (UTM 19S). Se pide al servicio con `outSR` para que los GeoJSON
# ya lleguen en la proyeccion de la escena: reproyectar despues tambien
# funciona, pero pedirlo aca deja el archivo en disco listo para cotejar a ojo
# contra los bounds del .tif sin ningun paso intermedio.
EPSG_SALIDA = 32719

# maxRecordCount declarado por ambos layers. Se pide exactamente eso por
# pagina y se itera con resultOffset: pedir mas no sirve (el servicio recorta
# igual) y pedir menos multiplica las peticiones sin ganar nada.
TAMANO_PAGINA = 2000

# Capas a descargar: nombre de archivo -> (id de layer, nombre humano).
CAPAS: dict[str, tuple[int, str]] = {
    "pozo_almonte": (439, "Pozo Almonte (M204)"),
    "mamina": (437, "Mamina (M303)"),
}

DIRECTORIO_SALIDA = "data/external/geologia"

# Campo con el nombre de la unidad litologica. Es el mismo en ambos layers, y
# es la clave con que `configs/verdad_terreno_cerro_colorado.yaml` asigna clases.
CAMPO_UNIDAD = "Unidad_geologica"


def url_de_consulta(layer_id: int, offset: int) -> str:
    """Arma la URL de una pagina de la consulta a un layer del FeatureServer.

    Parameters
    ----------
    layer_id:
        Identificador del layer dentro del FeatureServer (439 o 437).
    offset:
        Indice del primer feature de la pagina (`resultOffset` de ArcGIS).

    Returns
    -------
    str
        URL completa, lista para `urllib.request.urlopen`.
    """
    parametros = urllib.parse.urlencode(
        {
            "where": "1=1",
            "outFields": "*",
            "outSR": EPSG_SALIDA,
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": TAMANO_PAGINA,
        }
    )
    return f"{BASE_URL}/{layer_id}/query?{parametros}"


def _pedir_json(url: str) -> dict:
    """Descarga y parsea un JSON, culpando a la URL exacta si algo falla.

    Raises
    ------
    RuntimeError
        Si la peticion falla o si la respuesta no es JSON valido. El mensaje
        incluye la URL pedida: sin ella, un fallo del servicio es
        indistinguible de un fallo del parametro que uno mismo armo mal.
    """
    try:
        with urllib.request.urlopen(url, timeout=120) as respuesta:
            crudo = respuesta.read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Fallo la peticion a {url}\n  causa: {e!r}") from e

    try:
        return json.loads(crudo)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"La respuesta de {url} no es JSON valido.\n"
            f"  primeros 500 bytes: {crudo[:500]!r}"
        ) from e


def descargar_capa(layer_id: int) -> dict:
    """Descarga un layer completo paginando con `resultOffset`.

    ArcGIS corta cualquier consulta en `maxRecordCount` features (2000 aca) sin
    avisar de forma que rompa: devuelve un GeoJSON perfectamente valido, solo
    que truncado. Por eso se pagina siempre, aunque hoy la capa 439 quepa en
    una sola pagina: el dia que la capa crezca, no paginar produciria una
    verdad de terreno recortada en silencio.

    Parameters
    ----------
    layer_id:
        Identificador del layer dentro del FeatureServer.

    Returns
    -------
    dict
        FeatureCollection GeoJSON con todos los features concatenados.

    Raises
    ------
    RuntimeError
        Si el servicio responde un error de ArcGIS, si la respuesta no trae la
        clave `features`, o si el layer devuelve cero features. Un GeoJSON
        vacio escrito en disco es peor que un fallo: el pipeline sigue y
        produce una verdad de terreno 100 % ambigua sin ninguna senal.
    """
    features: list[dict] = []
    offset = 0
    crs_declarado = None

    while True:
        url = url_de_consulta(layer_id, offset)
        datos = _pedir_json(url)

        if "error" in datos:
            raise RuntimeError(
                f"El servicio respondio un error para {url}\n"
                f"  error: {datos['error']}"
            )

        if "features" not in datos:
            raise RuntimeError(
                f"La respuesta de {url} no trae la clave 'features'.\n"
                f"  claves recibidas: {sorted(datos)}"
            )

        pagina = datos["features"]
        features.extend(pagina)
        crs_declarado = datos.get("crs", crs_declarado)

        print(f"    offset {offset:>5}: {len(pagina)} features")

        if not pagina:
            break

        # Dos condiciones de corte y no una: `exceededTransferLimit` es la
        # senal explicita del servicio, pero no todas las versiones la
        # devuelven. Una pagina mas corta que el maximo tambien cierra.
        if not datos.get("exceededTransferLimit", False) and (
            len(pagina) < TAMANO_PAGINA
        ):
            break

        offset += len(pagina)

    if not features:
        raise RuntimeError(
            f"El layer {layer_id} devolvio cero features.\n"
            f"  URL pedida: {url_de_consulta(layer_id, 0)}\n"
            "  Sin poligonos no hay verdad de terreno; no escribo un GeoJSON vacio."
        )

    return {
        "type": "FeatureCollection",
        "crs": crs_declarado
        or {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{EPSG_SALIDA}"},
        },
        "features": features,
    }


def resumir_capa(ruta: Path) -> None:
    """Imprime features, CRS, bbox y la tabla de unidades de un GeoJSON.

    La tabla de unidades (conteo y area total, de mayor a menor) es el insumo
    con que se llena `configs/verdad_terreno_cerro_colorado.yaml`: es la lista
    exacta de valores que el YAML puede nombrar.
    """
    import geopandas as gpd

    gdf = gpd.read_file(ruta)

    print(f"  archivo    : {ruta}")
    print(f"  features   : {len(gdf)}")
    print(f"  CRS        : {gdf.crs}")
    print(f"  bounds     : {gdf.total_bounds}")

    if CAMPO_UNIDAD not in gdf.columns:
        print(
            f"  [AVISO] no hay columna '{CAMPO_UNIDAD}'; "
            f"columnas disponibles: {list(gdf.columns)}"
        )
        return

    tabla = (
        gdf.assign(_area_km2=gdf.geometry.area / 1e6)
        .groupby(CAMPO_UNIDAD, dropna=False)
        .agg(poligonos=("_area_km2", "size"), area_km2=("_area_km2", "sum"))
        .sort_values("area_km2", ascending=False)
    )

    print(f"  unidades   : {len(tabla)} distintas")
    print(f"  {'unidad':<58} {'polig.':>7} {'km2':>12}")
    for unidad, fila in tabla.iterrows():
        etiqueta = "(sin valor)" if unidad is None else str(unidad)
        print(f"  {etiqueta:<58} {int(fila.poligonos):>7} {fila.area_km2:>12.2f}")


def escribir_readme(directorio: Path) -> None:
    """Escribe el README que acompana a los GeoJSON en `data/external/geologia/`.

    Va junto a los datos y no solo en la docstring del modulo: quien se
    encuentre con los GeoJSON en el repo tiene que poder saber de donde salen y
    que citar sin leer codigo.
    """
    contenido = f"""# Cartografia geologica del AOI del distrito Cerro Colorado

Poligonos litologicos que cubren el AOI del proyecto (tile T19KDT, EPSG:32719,
E 453.960-493.960 / N 7.747.040-7.787.040), usados para construir la capa de
verdad de terreno.

- `mamina.geojson` --- hoja Mamina. Con el AOI actual cubre el AOI **entero**.
- `pozo_almonte.geojson` --- hoja Pozo Almonte. Queda al oeste del AOI actual
  y hoy no aporta ningun poligono, pero se conserva: cubria el AOI anterior y
  la ventana ya se movio dos veces.

Descargados el {date.today().isoformat()} con `scripts/descargar_geologia.py`.

## Por que dos hojas

El AOI **anterior** (lon -69,7673 a -69,383) cruzaba el limite entre ambas
cartas (Pozo Almonte cubre 70,00-69,50 W; Mamina cubre 69,50-69,00 W) y
necesitaba las dos. El AOI **actual** (lon -69,4412 a -69,0577) cae entero
dentro de Mamina. Se conservan las dos capas de todas formas: el codigo las
une sin costo y la ventana ya cambio dos veces.

La "Carta Calama" del plan original **no aplica**: Calama esta en la Region de
Antofagasta, a unos 250 km al sur. La zona de estudio cambio a Pampa del
Tamarugal en la Semana 2 y al distrito Cerro Colorado en la Semana 5.

## Fuente tecnica de los vectores

FeatureServer `Chile_Geology` de ArcGIS Online, una **digitalizacion de
terceros** (publicada por Stanford) de las cartas de SERNAGEOMIN:

- Base: <{BASE_URL}>
- Layer 439 = `Chile-geo-pozoalmonte`
- Layer 437 = `Chile-geo-Mamina`

**Este servicio no declara licencia.** Se usa como insumo tecnico y no
sustituye a la fuente cartografica: la cita que corresponde es siempre la carta
original de SERNAGEOMIN, no el servicio. Si el trabajo se publica, hay que
resolver la procedencia de estos vectores antes.

## Cartas originales que hay que citar

- **Pozo Almonte (M204)** --- Vasquez, P. y Sepulveda, F.A. (2013). *Carta Pozo
  Almonte, Region de Tarapaca*. Servicio Nacional de Geologia y Mineria, Carta
  Geologica de Chile, Serie Geologia Basica 162-163 (junto con la Carta
  Iquique), escala 1:100.000.
- **Mamina (M303)** --- Tomlinson, A.J., Blanco, N. y Ladino, M. (2015). *Carta
  Mamina, Region de Tarapaca*. Servicio Nacional de Geologia y Mineria, Carta
  Geologica de Chile, Serie Geologia Basica 174, escala 1:100.000.

## Lo que estos datos NO son

SERNAGEOMIN publica un unico tema cartografico ("Geologia Basica") y **no**
publica poligonos de alteracion hidrotermal para el norte de Chile (verificado:
no hay WFS ni un servicio de alteracion en su organizacion ArcGIS). Estas
capas traen **litologia**, no alteracion. Por eso la verdad de terreno del
proyecto no se obtiene filtrando una columna: es una **seleccion de unidades**
declarada a mano en `configs/verdad_terreno_cerro_colorado.yaml`, y ese archivo
es
donde hay que discutir el criterio.
"""
    (directorio / "README.md").write_text(contenido, encoding="utf-8")
    print(f"README escrito: {directorio / 'README.md'}")


def _parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=DIRECTORIO_SALIDA,
        help="Directorio de salida (default: %(default)s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-descarga aunque el GeoJSON ya exista",
    )
    return parser.parse_args()


def main() -> None:
    """Descarga ambas capas, escribe el README e imprime el resumen por capa."""
    args = _parsear_argumentos()
    directorio = Path(args.out)
    directorio.mkdir(parents=True, exist_ok=True)

    for nombre, (layer_id, humano) in CAPAS.items():
        ruta = directorio / f"{nombre}.geojson"
        print("=" * 72)
        print(f"{humano}  ->  layer {layer_id}")

        if ruta.exists() and not args.force:
            print(f"  ya existe {ruta}; no re-descargo (usa --force para forzar)")
        else:
            coleccion = descargar_capa(layer_id)
            ruta.write_text(json.dumps(coleccion), encoding="utf-8")
            print(f"  descargados {len(coleccion['features'])} features -> {ruta}")

        resumir_capa(ruta)

    print("=" * 72)
    escribir_readme(directorio)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
