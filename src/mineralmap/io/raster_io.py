"""Lectura/escritura de rasters GeoTIFF y la clase Scene (cubo de bandas +
metadatos geograficos).
"""

from __future__ import annotations

import glob
import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS

from mineralmap.config import BAND_ORDER


def _token_de_banda(banda: str) -> str:
    """Traduce un nombre canonico de banda al token que usan los archivos.

    Los .jp2 del .SAFE nombran las bandas con cero a la izquierda (B01, B08)
    mientras que el proyecto las nombra sin cero (B1, B8). B8A es la excepcion:
    no es un numero, asi que viaja invariante.
    """
    cuerpo = banda[1:]
    if cuerpo.isdigit():
        return "B" + cuerpo.zfill(2)
    return banda


# Nombre canonico -> token de archivo. Se genera desde BAND_ORDER para que
# agregar una banda al contrato no exija tocar tambien un diccionario a mano.
BAND_TOKEN: dict[str, str] = {banda: _token_de_banda(banda) for banda in BAND_ORDER}
BAND_TOKEN["SCL"] = "SCL"

# Resoluciones donde buscar cada banda, en orden de preferencia: 20 m es la
# grilla objetivo del proyecto, asi que se prefiere el archivo nativo a 20 m
# cuando existe y solo se cae a 10 m (B8) o 60 m (B9) cuando no queda otra.
RESOLUTION_DIRS: tuple[int, ...] = (20, 10, 60)


@dataclass
class Scene:
    """Escena Sentinel-2 preprocesada: cubo de bandas en reflectancia junto a
    su georreferenciacion y una mascara de pixeles validos.

    Es el objeto que produce `preprocessing/` y que consumen `spectral/` y
    `algorithms/`; no conoce formatos de archivo, solo datos en memoria.
    """

    cube: np.ndarray  # (n_bandas, alto, ancho), reflectancia [0,1]
    band_names: list[str]  # == BAND_ORDER
    transform: Affine
    crs: CRS
    mask: np.ndarray  # (alto, ancho) bool, True = pixel valido
    # Trazabilidad del origen del cubo (producto, AOI, escalado aplicado).
    # Va al final para no romper la construccion posicional ya existente.
    meta: dict[str, Any] = field(default_factory=dict)


def find_safe_dir(root: str) -> str:
    """Devuelve la ruta de la primera carpeta .SAFE encontrada bajo `root`.

    Parameters
    ----------
    root:
        Directorio donde buscar (recursivamente), p. ej. "data/raw/".

    Returns
    -------
    str
        Ruta de la carpeta .SAFE.

    Raises
    ------
    FileNotFoundError
        Si no hay ninguna carpeta .SAFE bajo `root`.
    """
    base = str(root).rstrip("/\\")
    # Solo directorios: en Windows el glob es insensible a mayusculas y
    # ".SAFE" tambien casa con el archivo "manifest.safe" que vive dentro del
    # propio producto, lo que haria creer que hay dos escenas.
    encontradas = sorted(
        ruta
        for ruta in glob.glob(f"{base}/**/*.SAFE", recursive=True)
        if os.path.isdir(ruta)
    )

    if not encontradas:
        raise FileNotFoundError(
            f"No encontre ninguna carpeta .SAFE en {root}; ¿esta descargada la escena?"
        )

    if len(encontradas) > 1:
        warnings.warn(
            f"Encontre {len(encontradas)} carpetas .SAFE en {root}; uso "
            f"{encontradas[0]}. Si querias otra escena, pasa su ruta explicitamente.",
            stacklevel=2,
        )

    return encontradas[0]


def find_band_file(
    safe_dir: str, band: str, prefer: tuple[int, ...] = RESOLUTION_DIRS
) -> tuple[str, int]:
    """Localiza el archivo de una banda dentro del .SAFE y dice a que resolucion.

    Parameters
    ----------
    safe_dir:
        Ruta de la carpeta .SAFE.
    band:
        Nombre canonico de la banda ("B1", "B8A", ...) o "SCL".
    prefer:
        Resoluciones a probar, en orden. La primera que exista gana.

    Returns
    -------
    tuple[str, int]
        (ruta del archivo, resolucion nativa en metros).

    Raises
    ------
    FileNotFoundError
        Si la banda no existe en ninguna de las resoluciones probadas. El
        mensaje nombra la banda y donde se busco.
    """
    token = BAND_TOKEN.get(band, _token_de_banda(band))
    base = str(safe_dir).rstrip("/\\")

    patrones = []
    for resolucion in prefer:
        patron = f"{base}/GRANULE/*/IMG_DATA/R{resolucion}m/*_{token}_{resolucion}m.jp2"
        patrones.append(patron)
        encontrados = sorted(glob.glob(patron))
        if encontrados:
            return encontrados[0], resolucion

    raise FileNotFoundError(
        f"No encontre la banda {band} (token {token}) en {safe_dir}. "
        f"Probe las resoluciones {list(prefer)} con los patrones: {patrones}"
    )


def read_scene(path: str) -> Scene:
    """Lee un Scene desde un GeoTIFF multibanda ya escrito por el proyecto.

    Es la contraparte de `write_geotiff`, no un lector de productos .SAFE:
    construir un Scene desde el producto crudo (localizar bandas, remuestrear,
    recortar, escalar, enmascarar) es trabajo de `preprocessing`, y vive en
    `preprocessing/scene_builder.py`. Ponerlo aqui invertiria el orden de
    capas del proyecto (io -> preprocessing -> spectral/algorithms).
    """
    raise NotImplementedError


def write_geotiff(
    path: str,
    array: np.ndarray,
    scene: Scene,
    band_descriptions: list[str] | None = None,
) -> None:
    """Escribe un arreglo como GeoTIFF con la georreferenciacion de `scene`.

    Parameters
    ----------
    path:
        Ruta del .tif de salida. El directorio padre se crea si no existe.
    array:
        Mapa 2D `(alto, ancho)` o cubo 3D `(n_bandas, alto, ancho)`. Se escribe
        siempre como float32: la reflectancia y los puntajes del proyecto viven
        en ese dtype y float64 duplicaria el peso sin agregar precision real.
    scene:
        Scene del que salieron los datos. Aporta `crs` y `transform`, y su
        forma espacial es la referencia contra la que se valida `array`.
    band_descriptions:
        Un nombre por banda escrita, en el mismo orden. None deja las bandas
        sin descripcion. Un raster de una banda que no dice que es obliga a
        leer el codigo que lo produjo para saberlo.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        Si `array` no es 2D ni 3D, si su forma espacial no calza con la de
        `scene.cube`, o si `band_descriptions` no trae un nombre por banda.
    """
    datos = np.asarray(array)

    if datos.ndim == 2:
        datos = datos[np.newaxis, ...]
    elif datos.ndim != 3:
        raise ValueError(
            f"write_geotiff acepta un mapa 2D (alto, ancho) o un cubo 3D "
            f"(n_bandas, alto, ancho); recibi {datos.ndim} dimensiones con "
            f"forma {np.asarray(array).shape}."
        )

    # Sin esta comprobacion, escribir un mapa calculado sobre otra ventana
    # produce un GeoTIFF impecable con la georreferenciacion equivocada: se
    # abre bien en cualquier SIG, cae sobre el terreno equivocado y no falla
    # nunca. Es el unico modo de fallo de esta funcion que no se nota.
    forma_escena = tuple(scene.cube.shape[1:])
    if tuple(datos.shape[1:]) != forma_escena:
        raise ValueError(
            f"La forma espacial del arreglo {tuple(datos.shape[1:])} no calza "
            f"con la del Scene {forma_escena}; escribirlo igual daria un "
            f"GeoTIFF georreferenciado sobre otra ventana."
        )

    if band_descriptions is not None and len(band_descriptions) != datos.shape[0]:
        raise ValueError(
            f"Recibi {len(band_descriptions)} descripciones para "
            f"{datos.shape[0]} bandas; se necesita una por banda."
        )

    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # No se escribe ningun tag propio (fecha, usuario, ruta de origen): el
    # archivo tiene que salir byte a byte identico en dos corridas seguidas
    # para que la reproducibilidad se pueda comprobar comparando hashes. La
    # trazabilidad del producto ya viaja en `Scene.meta` y en el .npz.
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=datos.shape[1],
        width=datos.shape[2],
        count=datos.shape[0],
        dtype="float32",
        crs=scene.crs,
        transform=scene.transform,
        # NaN como nodata y no 0: un angulo espectral de 0 rad es un valor
        # legitimo (coincidencia perfecta con la firma), asi que usarlo como
        # centinela borraria justo las detecciones mas fuertes.
        nodata=np.nan,
        compress="deflate",
        tiled=True,
    ) as dst:
        dst.write(datos.astype(np.float32))

        if band_descriptions is not None:
            for indice, nombre in enumerate(band_descriptions, start=1):
                dst.set_band_description(indice, nombre)


def save_scene(scene: Scene, path: str) -> None:
    """Serializa un Scene completo a un unico archivo .npz.

    El cubo se guarda como float32 (la reflectancia [0,1] no necesita float64),
    la transform como sus 6 coeficientes afines, el CRS como WKT, la mascara
    como bool y `meta` como una cadena JSON. Se puede recuperar un Scene
    equivalente con `load_scene`.
    """
    np.savez(
        path,
        cube=scene.cube.astype(np.float32),
        band_names=np.asarray(scene.band_names),
        # tuple(Affine) devuelve 9 valores (incluye la fila 0,0,1 implicita);
        # basta con los 6 coeficientes para reconstruirla.
        transform=np.asarray(tuple(scene.transform)[:6], dtype=np.float64),
        crs=scene.crs.to_wkt(),
        mask=np.asarray(scene.mask, dtype=bool),
        # JSON y no pickle: el .npz se carga con allow_pickle=False, asi que
        # abrirlo nunca puede ejecutar codigo.
        meta=np.asarray(json.dumps(scene.meta)),
    )


def load_scene(path: str) -> Scene:
    """Reconstruye un Scene equivalente al serializado con `save_scene`."""
    with np.load(path, allow_pickle=False) as data:
        cube = data["cube"].astype(np.float32)
        band_names = [str(b) for b in data["band_names"].tolist()]
        transform = Affine(*(float(v) for v in data["transform"].tolist()))
        crs = CRS.from_wkt(str(data["crs"].item()))
        mask = np.asarray(data["mask"], dtype=bool)
        # Los .npz escritos antes de que Scene tuviera `meta` siguen siendo
        # validos: se cargan con meta vacio en vez de fallar.
        meta = json.loads(str(data["meta"].item())) if "meta" in data.files else {}

    return Scene(
        cube=cube,
        band_names=band_names,
        transform=transform,
        crs=crs,
        mask=mask,
        meta=meta,
    )
