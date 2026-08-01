"""Escalado de digital numbers (DN) a reflectancia superficial.

El offset radiometrico aparece con el baseline de procesamiento >= 04.00.
"""

from __future__ import annotations

import os
import warnings
import xml.etree.ElementTree as ET

import numpy as np

# Metadatos a nivel de producto dentro del .SAFE.
MTD_FILENAME = "MTD_MSIL2A.xml"

# Baseline de procesamiento a partir del cual Sen2Cor introdujo el
# desplazamiento radiometrico (BOA_ADD_OFFSET).
BASELINE_CON_OFFSET = 4.0

# Fallbacks si el XML no esta disponible: se asume un producto moderno
# (baseline >= 04.00), que es el caso de todo lo que ESA distribuye hoy.
FALLBACK_BASELINE = "04.00"
FALLBACK_OFFSET = -1000.0
FALLBACK_QUANTIFICATION = 10000.0


def offset_for_baseline(baseline: str) -> float:
    """Devuelve el offset radiometrico que corresponde a un baseline dado.

    Parameters
    ----------
    baseline:
        Baseline de procesamiento tal como aparece en el XML, p. ej. "05.11".

    Returns
    -------
    float
        -1000.0 si el baseline es >= 04.00, 0.0 si es anterior.

    Raises
    ------
    ValueError
        Si `baseline` no se puede interpretar como numero.
    """
    try:
        numero = float(baseline)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"No pude interpretar el baseline de procesamiento {baseline!r} como "
            "numero (se esperaba algo como '05.11' o '03.01')."
        ) from exc

    return -1000.0 if numero >= BASELINE_CON_OFFSET else 0.0


def dn_to_reflectance(
    dn_array,
    baseline: str,
    *,
    offset: float | None = None,
    quantification: float = 10000.0,
    clip: bool = True,
    nodata_dn: int = 0,
) -> np.ndarray:
    """Convierte los enteros (DN) de una banda L2A a reflectancia superficial.

    La formula es ``(dn + offset) / quantification``. El sumando existe porque
    desde el baseline de procesamiento 04.00 Sen2Cor codifica la reflectancia
    con un desplazamiento: los productos anteriores guardaban directamente
    ``reflectancia * 10000``, mientras que los nuevos guardan
    ``reflectancia * 10000 + 1000``. El desplazamiento permite representar
    reflectancias ligeramente negativas (un resultado normal de la correccion
    atmosferica sobre superficies muy oscuras) sin recurrir a enteros con
    signo. En el XML del producto el valor aparece como
    ``BOA_ADD_OFFSET = -1000``: es un **sumando negativo**, es decir,
    equivalente a restar 1000.

    Parameters
    ----------
    dn_array:
        Banda cruda leida del .jp2 (enteros). Cualquier forma.
    baseline:
        Baseline de procesamiento del producto, p. ej. "05.11". Solo se usa
        para derivar `offset` cuando este no se pasa explicitamente.
    offset:
        Sumando radiometrico. Si es None se deriva de `baseline` con
        `offset_for_baseline`. Un valor explicito tiene prioridad sobre el
        derivado (asi el llamador puede usar el valor real del XML).
    quantification:
        Factor de cuantificacion (BOA_QUANTIFICATION_VALUE), normalmente 10000.
    clip:
        Si True, recorta el resultado a [0, 1]. Los NaN se preservan.
    nodata_dn:
        Valor DN que representa "sin dato" (0 en Sentinel-2 L2A). Esos pixeles
        pasan a NaN *antes* de escalar: si se escalaran, el nodata se
        convertiria en un valor perfectamente valido (con offset -1000 daria
        -0.1, que el clip dejaria en 0.0) y contaminaria toda estadistica
        posterior.

    Returns
    -------
    np.ndarray
        Reflectancia en float32, misma forma que `dn_array`, con NaN donde no
        habia dato.
    """
    dn = np.asarray(dn_array)

    if offset is None:
        offset = offset_for_baseline(baseline)

    # El nodata se identifica sobre los DN crudos, antes de aplicar la escala.
    sin_dato = dn == nodata_dn

    reflectancia = (dn.astype(np.float32) + np.float32(offset)) / np.float32(
        quantification
    )
    reflectancia[sin_dato] = np.nan

    if clip:
        # np.clip propaga los NaN (usa minimum/maximum): no los convierte en
        # 0 ni en 1. Hay un test que lo verifica explicitamente.
        reflectancia = np.clip(reflectancia, 0.0, 1.0)

    return reflectancia.astype(np.float32)


def read_l2a_scaling(safe_dir: str) -> tuple[str, float, float]:
    """Lee (baseline, offset, quantification) desde MTD_MSIL2A.xml del .SAFE.

    Se prefiere leer estos valores del producto antes que fijarlos en el
    codigo: el offset depende del baseline con que ESA proceso la escena, y
    una escena reprocesada puede cambiarlo sin que cambie nada mas.

    Parameters
    ----------
    safe_dir:
        Ruta a la carpeta .SAFE (el XML se busca dentro, como MTD_MSIL2A.xml).

    Returns
    -------
    tuple[str, float, float]
        (baseline, offset, quantification). Si el XML no existe o le falta
        algun campo, se devuelve el fallback correspondiente y se emite un
        `warnings.warn` diciendo que falto y donde se busco.

    Notes
    -----
    El parseo ignora los namespaces XML comparando solo la ultima parte del
    tag (``tag.split('}')[-1]``), porque el namespace del PSD cambia entre
    versiones del producto y anclarse a el rompe la lectura sin aviso.
    """
    ruta_xml = os.path.join(safe_dir, MTD_FILENAME)

    if not os.path.isfile(ruta_xml):
        warnings.warn(
            f"No encontre {MTD_FILENAME} en {safe_dir}; uso los valores por "
            f"defecto (baseline={FALLBACK_BASELINE}, offset={FALLBACK_OFFSET}, "
            f"quantification={FALLBACK_QUANTIFICATION}).",
            stacklevel=2,
        )
        return FALLBACK_BASELINE, FALLBACK_OFFSET, FALLBACK_QUANTIFICATION

    raiz = ET.parse(ruta_xml).getroot()

    baseline: str | None = None
    offsets: dict[str, float] = {}
    boa_quantification: float | None = None
    quantification_generica: float | None = None

    for elemento in raiz.iter():
        tag = elemento.tag.split("}")[-1]
        texto = (elemento.text or "").strip()

        if tag == "PROCESSING_BASELINE" and texto:
            baseline = texto
        elif tag == "BOA_ADD_OFFSET" and texto:
            offsets[elemento.get("band_id", "")] = float(texto)
        elif tag == "BOA_QUANTIFICATION_VALUE" and texto:
            boa_quantification = float(texto)
        elif tag == "QUANTIFICATION_VALUE" and texto:
            quantification_generica = float(texto)

    faltantes = []

    if baseline is None:
        faltantes.append("PROCESSING_BASELINE")
        baseline = FALLBACK_BASELINE

    if offsets:
        # El producto declara un offset por banda; en la practica todas
        # comparten el mismo valor. Se toma el de band_id="0" o, si no esta,
        # el primero que aparezca.
        offset = offsets.get("0", next(iter(offsets.values())))
    else:
        faltantes.append("BOA_ADD_OFFSET")
        offset = offset_for_baseline(baseline)

    quantification = boa_quantification or quantification_generica
    if quantification is None:
        faltantes.append("BOA_QUANTIFICATION_VALUE")
        quantification = FALLBACK_QUANTIFICATION

    if faltantes:
        warnings.warn(
            f"A {ruta_xml} le faltan los campos {faltantes}; uso los valores "
            f"por defecto para esos (baseline={baseline}, offset={offset}, "
            f"quantification={quantification}).",
            stacklevel=2,
        )

    return baseline, float(offset), float(quantification)
