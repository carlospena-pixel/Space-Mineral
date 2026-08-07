"""Registro de minerales objetivo y sus firmas espectrales de referencia."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mineralmap.config import BAND_ORDER, band_wavelengths
from mineralmap.spectral.usgs_library import load_usgs_rs_sentinel2

# Orden en que load_usgs_rs_sentinel2 devuelve las 13 bandas (incluye B10).
_RAW_BAND_ORDER = [
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B10", "B11", "B12",
]

# Raiz del repositorio: src/mineralmap/spectral/endmembers.py -> repo_root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

_DIR_EXTERNA = _REPO_ROOT / "data" / "external"

# Plataforma contra la que se valida el orden de _RAW_BAND_ORDER. Es S2A y no
# DEFAULT_PLATFORM (S2B) porque el remuestreo rsSentinel2 de splib07 esta hecho
# con las funciones de respuesta de Sentinel-2A. DECLARADO, sin verificar: la
# libreria no viene con el archivo de longitudes de onda en este repositorio,
# asi que no hay con que comprobarlo. El dia que el archivo este, este mismo
# valor es lo primero que hay que confirmar: si la firma estuviera remuestreada
# a S2B, B12 caeria en 2185.7 nm y no en 2202.4, y la diferencia de 16.7 nm
# supera la tolerancia por defecto, o sea que la validacion lo denunciaria.
USGS_RESAMPLING_PLATFORM = "S2A"

# Tolerancia por defecto al comparar las longitudes de onda del archivo USGS
# contra la tabla de ESA. DECLARADA, sin ajustar contra datos: el archivo de
# longitudes de onda todavia no esta en data/external/ (ver
# find_usgs_wavelengths_file). 15 nm es holgado frente a la diferencia entre
# plataformas en las bandas angostas y ajustado frente a la separacion entre
# bandas vecinas mas cercanas del sensor (B5 y B6, 36 nm), que es lo que de
# verdad tiene que distinguir: con esta tolerancia, confundir dos bandas
# contiguas es imposible.
DEFAULT_WAVELENGTH_TOLERANCE_NM = 15.0

ENDMEMBERS = {
    "kaolinite": {
        "usgs_sample_id": "KGa-1",
        "usgs_file": "S07SNTL2_Kaolinite_CM9_BECKb_AREF.txt",
    },
    # "alunite": {"usgs_sample_id": "..."},
    # "hematite": {"usgs_sample_id": "..."},
}


def find_usgs_wavelengths_file() -> Path | None:
    """Localiza el archivo de longitudes de onda de splib07 en data/external/.

    FALTA DESCARGAR. El repositorio versiona la firma de caolinita
    (S07SNTL2_Kaolinite_CM9_BECKb_AREF.txt) pero no el archivo de longitudes de
    onda que la acompana en el paquete `ASCIIdata_splib07*_rsSentinel2` de la
    USGS Spectral Library Version 7
    (https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d).
    Sin el, el orden de `_RAW_BAND_ORDER` esta anclado a evidencia fisica (la
    caida aislada de la posicion 10, que solo puede ser el sobretono OH de
    ~1400 nm que muestrea B10) pero no a la fuente.

    La busqueda es por patron y no por nombre exacto a proposito: el nombre del
    archivo dentro del paquete no esta confirmado y ponerlo a mano seria
    inventarlo. Cualquier .txt de data/external/ cuyo nombre mencione
    "wavelength" sirve.

    Returns
    -------
    Path | None
        Ruta del archivo si existe, None si todavia no se descargo.
    """
    if not _DIR_EXTERNA.is_dir():
        return None

    candidatos = sorted(
        ruta for ruta in _DIR_EXTERNA.glob("*.txt") if "wavelength" in ruta.name.lower()
    )
    return candidatos[0] if candidatos else None


def validate_raw_band_order(
    wavelengths_nm: np.ndarray | None = None,
    platform: str = USGS_RESAMPLING_PLATFORM,
    tolerance_nm: float = DEFAULT_WAVELENGTH_TOLERANCE_NM,
) -> np.ndarray | None:
    """Comprueba que `_RAW_BAND_ORDER` describe de verdad al archivo USGS.

    `_RAW_BAND_ORDER` es la unica pieza del proyecto que dice que la posicion
    `i` de un archivo de splib07 es tal banda de Sentinel-2. Si estuviera
    equivocada nada fallaria: `get_reference_spectrum` seguiria devolviendo 12
    numeros del tipo correcto, el SAM seguiria calculando un angulo y el mapa
    resultante seria basura plausible. Esta funcion convierte esa suposicion en
    algo que se puede romper ruidosamente.

    Hace dos comprobaciones, la segunda solo si se le pasan longitudes de onda:

    1. Que las 13 posiciones esten en orden creciente de longitud de onda
       segun la tabla del proyecto (`config.BAND_WAVELENGTHS_NM`). No necesita
       ningun archivo.
    2. Que cada longitud de onda medida en el archivo USGS caiga a menos de
       `tolerance_nm` de la que ESA declara para esa banda.

    Parameters
    ----------
    wavelengths_nm:
        Longitudes de onda del archivo de splib07 en nm, tal como las devuelve
        `load_usgs_wavelengths`. None para correr solo la comprobacion de orden.
    platform:
        Plataforma cuya tabla de longitudes de onda se usa como referencia.
        Por defecto USGS_RESAMPLING_PLATFORM, no DEFAULT_PLATFORM.
    tolerance_nm:
        Desvio maximo aceptado por banda, en nanometros.

    Returns
    -------
    np.ndarray | None
        Desvio por banda en nm (largo 13) si se pasaron longitudes de onda;
        None si solo corrio la comprobacion de orden.

    Raises
    ------
    ValueError
        Si `_RAW_BAND_ORDER` no esta en orden creciente de longitud de onda, si
        `wavelengths_nm` no trae 13 valores, si no es estrictamente creciente,
        o si alguna banda se desvia mas de `tolerance_nm`.
    """
    lambdas_esa = np.array(band_wavelengths(_RAW_BAND_ORDER, platform=platform))

    if not np.all(np.diff(lambdas_esa) > 0):
        raise ValueError(
            f"_RAW_BAND_ORDER no esta en orden creciente de longitud de onda "
            f"segun la tabla de {platform}: {list(zip(_RAW_BAND_ORDER, lambdas_esa))}"
        )

    if wavelengths_nm is None:
        return None

    medidas = np.asarray(wavelengths_nm, dtype=float)
    if medidas.shape != (len(_RAW_BAND_ORDER),):
        raise ValueError(
            f"Se esperaban {len(_RAW_BAND_ORDER)} longitudes de onda, "
            f"recibi un arreglo de forma {medidas.shape}."
        )

    if not np.all(np.diff(medidas) > 0):
        raise ValueError(
            f"Las longitudes de onda del archivo USGS no son estrictamente "
            f"crecientes: {medidas.tolist()}. El archivo no esta en el orden "
            f"que asume _RAW_BAND_ORDER."
        )

    desvios = np.abs(medidas - lambdas_esa)
    fuera = [
        f"{banda}: USGS {medida:.1f} nm vs ESA {esperada:.1f} nm "
        f"(desvio {desvio:.1f} nm)"
        for banda, medida, esperada, desvio in zip(
            _RAW_BAND_ORDER, medidas, lambdas_esa, desvios
        )
        if desvio > tolerance_nm
    ]
    if fuera:
        raise ValueError(
            f"Estas bandas se desvian mas de {tolerance_nm} nm de la tabla de "
            f"{platform}: " + "; ".join(fuera)
        )

    return desvios


def get_reference_spectrum(
    mineral: str, band_order: list[str] = BAND_ORDER
) -> np.ndarray:
    """Firma espectral de referencia de `mineral`, remuestreada a `band_order`.

    Busca el archivo USGS asociado a `mineral` en ENDMEMBERS (bajo
    data/external/), lo carga con load_usgs_rs_sentinel2, descarta la banda
    B10 (no existe en el producto L2A) y reordena los 12 valores restantes
    segun `band_order`.

    Parameters
    ----------
    mineral:
        Nombre del mineral objetivo (clave de ENDMEMBERS), p. ej. "kaolinite".
    band_order:
        Orden de bandas Sentinel-2 en el que debe devolverse la firma.
        Por defecto, BAND_ORDER (12 bandas, sin B10).

    Returns
    -------
    np.ndarray
        Vector 1D de reflectancia de largo len(band_order), alineado
        posicionalmente con band_order.
    """
    if mineral not in ENDMEMBERS:
        raise KeyError(f"No hay firma USGS registrada para el mineral '{mineral}'.")

    usgs_path = _REPO_ROOT / "data" / "external" / ENDMEMBERS[mineral]["usgs_file"]
    raw_values = load_usgs_rs_sentinel2(str(usgs_path))

    raw_by_band = dict(zip(_RAW_BAND_ORDER, raw_values))
    raw_by_band.pop("B10", None)  # B10 no viene en L2A.

    spectrum = np.array([raw_by_band[band] for band in band_order], dtype=float)

    if len(spectrum) != len(band_order):
        raise ValueError(
            f"La firma resultante tiene {len(spectrum)} valores, se esperaban "
            f"{len(band_order)} (largo de band_order)."
        )

    return spectrum
