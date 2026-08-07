"""Carga y valida los YAML de configuracion -> objeto Config tipado."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Orden estandar de bandas Sentinel-2 usado en todo el pipeline (io, spectral,
# algorithms). B10 (cirrus, ~1375 nm) se excluye porque no viene en el
# producto L2A: Sen2Cor la descarta durante la correccion atmosferica, ya
# que solo sirve para deteccion de cirrus en L1C.
BAND_ORDER: list[str] = [
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12",
]

# Subconjunto de bandas disponibles a 20 m que se usa para construir el Scene
# de Nivel 1. En nombres canonicos SIN cero (mismo estilo que BAND_ORDER); el
# mapeo a los tokens de archivo CON cero (B02, B03, B04) vive en el script que
# arma el Scene, no aqui.
COMMON_BANDS: list[str] = ["B2", "B3", "B4", "B8A", "B11", "B12"]

# Subconjunto que consumira el detector espectral (SAM). El Scene sigue
# naciendo con las 12 bandas de BAND_ORDER: subconjuntar despues siempre se
# puede, recuperar una banda que nunca se leyo no. Se excluyen tres respecto
# de BAND_ORDER, y por motivos distintos:
#   - B1 (443 nm, aerosol costero): existe para la correccion atmosferica. Su
#     varianza informa sobre el estado de la atmosfera, no sobre la superficie.
#   - B9 (945 nm, vapor de agua): mismo argumento, y ademas es la unica banda
#     con resolucion nativa de 60 m, o sea la de menor informacion real por
#     pixel de todo el cubo.
#   - B8 (833 nm, ancha): se solapa con B8A (865 nm, angosta), que cubre la
#     misma region con mejor definicion espectral. Conservar ambas le daria
#     peso doble al infrarrojo cercano al calcular el angulo espectral.
SAM_BANDS: list[str] = ["B2", "B3", "B4", "B5", "B6", "B7", "B8A", "B11", "B12"]

# Plataforma que senso la escena del proyecto. Se declara explicita en vez de
# deducirse del nombre del .SAFE porque es un dato del que dependen los
# graficos y la validacion de alineamiento: si algun dia entra una escena S2A,
# el default equivocado no falla, solo desplaza el eje.
DEFAULT_PLATFORM: str = "S2B"

# Respuesta espectral nominal del instrumento MSI: banda -> (longitud de onda
# central en nm, ancho de banda FWHM en nm), por plataforma.
#
# Por que hay dos tablas. S2A y S2B son dos satelites con dos copias fisicas
# del MSI, y sus filtros no salieron identicos de fabrica. La divergencia mas
# grande es justo la banda que le importa a este proyecto: B12 esta centrada
# en 2202.4 nm en S2A y en 2185.7 nm en S2B, 16.7 nm de diferencia. B12 es la
# banda que muestrea el doblete Al-OH de la caolinita (2160/2200 nm), donde la
# reflectancia cambia rapido con la longitud de onda. Usar la tabla de S2A
# sobre una escena S2B no lanza ningun error: corre el centro de la banda
# dentro del rasgo de absorcion y devuelve un grafico y una validacion de
# alineamiento que se ven bien y estan mal.
#
# Fuente: SentiWiki (Copernicus), "S2 Mission", Tabla 3, derivada de las
# funciones de respuesta espectral de ESA (COPE-GSEG-EOPG-TN-15-0007).
# https://sentiwiki.copernicus.eu/web/s2-mission
#
# B10 (cirrus) esta en la tabla aunque no este en BAND_ORDER: el producto L2A
# no la trae, pero el archivo de la libreria USGS si, y la validacion del
# alineamiento de la firma de referencia necesita saber donde cae.
#
# Los FWHM difieren de los que circulan en algunas planillas derivadas del
# mismo documento (p. ej. B8 S2A 106 nm y B12 S2A 175 nm); aca manda la tabla
# citada arriba. La discrepancia no afecta a nada implementado hoy: el FWHM no
# se consume, solo se documenta a la espera de `spectral/srf.py`.
_BAND_SRF_NM: dict[str, dict[str, tuple[float, float]]] = {
    "S2A": {
        "B1": (442.7, 20.0),
        "B2": (492.7, 64.0),
        "B3": (559.8, 35.0),
        "B4": (664.6, 30.0),
        "B5": (704.1, 14.0),
        "B6": (740.5, 14.0),
        "B7": (782.8, 20.0),
        "B8": (832.8, 118.0),
        "B8A": (864.7, 20.0),
        "B9": (945.1, 20.0),
        "B10": (1373.5, 30.0),
        "B11": (1613.7, 88.0),
        "B12": (2202.4, 179.0),
    },
    "S2B": {
        "B1": (442.2, 20.0),
        "B2": (492.3, 65.0),
        "B3": (558.9, 35.0),
        "B4": (664.9, 31.0),
        "B5": (703.8, 15.0),
        "B6": (739.1, 14.0),
        "B7": (779.7, 20.0),
        "B8": (832.9, 115.0),
        "B8A": (864.0, 20.0),
        "B9": (943.2, 20.0),
        "B10": (1376.9, 30.0),
        "B11": (1610.4, 93.0),
        "B12": (2185.7, 181.0),
    },
}

# Las dos vistas publicas se derivan de la tabla anterior en vez de escribirse
# a mano, por el mismo motivo que BAND_TOKEN se genera desde BAND_ORDER: dos
# diccionarios paralelos mantenidos a mano pueden desincronizarse (una banda
# con longitud de onda y sin FWHM) sin que nada falle.
BAND_WAVELENGTHS_NM: dict[str, dict[str, float]] = {
    plataforma: {banda: srf[0] for banda, srf in tabla.items()}
    for plataforma, tabla in _BAND_SRF_NM.items()
}

BAND_FWHM_NM: dict[str, dict[str, float]] = {
    plataforma: {banda: srf[1] for banda, srf in tabla.items()}
    for plataforma, tabla in _BAND_SRF_NM.items()
}


def band_wavelengths(
    band_order: list[str] = BAND_ORDER, platform: str = DEFAULT_PLATFORM
) -> list[float]:
    """Longitudes de onda centrales (nm) alineadas posicionalmente con `band_order`.

    Es el mismo contrato posicional que `get_reference_spectrum`: el llamador
    fija el orden y recibe un vector alineado con el, para que graficar o
    validar una firma no dependa de que el consumidor recuerde el orden de la
    tabla.

    Parameters
    ----------
    band_order:
        Bandas pedidas, en el orden en que deben devolverse las longitudes de
        onda. Por defecto BAND_ORDER.
    platform:
        "S2A" o "S2B". Por defecto DEFAULT_PLATFORM.

    Returns
    -------
    list[float]
        Longitudes de onda centrales en nanometros, largo len(band_order).

    Raises
    ------
    KeyError
        Si la plataforma no existe o si alguna banda no esta en la tabla.
    """
    if platform not in BAND_WAVELENGTHS_NM:
        raise KeyError(
            f"Plataforma '{platform}' desconocida; hay tabla para "
            f"{sorted(BAND_WAVELENGTHS_NM)}."
        )

    tabla = BAND_WAVELENGTHS_NM[platform]
    faltantes = [banda for banda in band_order if banda not in tabla]
    if faltantes:
        raise KeyError(
            f"No hay longitud de onda registrada para {faltantes} en {platform}."
        )

    return [tabla[banda] for banda in band_order]


@dataclass
class Config:
    scene: dict[str, Any] = field(default_factory=dict)
    aoi: dict[str, Any] = field(default_factory=dict)
    preprocessing: dict[str, Any] = field(default_factory=dict)
    mineral: dict[str, Any] = field(default_factory=dict)
    algorithm: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path) -> Config:
    """Lee un YAML de configuracion (con soporte de `defaults:`) y devuelve un Config."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    defaults_name = raw.pop("defaults", None)
    if defaults_name:
        base = load_config(path.parent / defaults_name)
        merged = dict(base.__dict__)
        for key, value in raw.items():
            if isinstance(value, dict):
                merged[key] = {**merged.get(key, {}), **value}
            else:
                merged[key] = value
        raw = merged

    known_fields = Config.__dataclass_fields__
    return Config(**{k: v for k, v in raw.items() if k in known_fields})
