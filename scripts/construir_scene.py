"""Arma el Scene de Nivel 1 recortado al AOI y lo serializa a data/interim/.

`construir_scene_final(ruta_base) -> Scene` puede importarse sin efectos
secundarios: solo hace trabajo (y requiere la escena .SAFE) cuando se la llama.
La ejecucion como script vive bajo `if __name__ == "__main__":`.
"""

import glob
import os
import sys

import numpy as np
import rasterio
from rasterio.windows import Window

from mineralmap.config import COMMON_BANDS
from mineralmap.io.raster_io import Scene, save_scene

# --- Parametros del recorte AOI (columna/fila de inicio y tamano en pixeles a
# 20 m). Cambiar aqui para mover o redimensionar la zona de estudio. ---
AOI_COL_OFF = 1000
AOI_ROW_OFF = 1000
AOI_WIDTH = 2000
AOI_HEIGHT = 2000

# Escala DN -> reflectancia. El baseline de procesamiento >= 04.00 agrega un
# offset de +1000 a los enteros del producto L2A: hay que restarlo antes de
# dividir por 10000, y recortar a [0, 1].
DN_OFFSET = 1000
DN_SCALE = 10000.0

# Clases SCL que marcamos como NO validas: 3=sombra de nube, 8=nube (prob.
# media), 9=nube (prob. alta), 10=cirrus.
SCL_INVALID = [3, 8, 9, 10]

# Mapeo token de archivo (.jp2, CON cero) -> nombre canonico (SIN cero). Los
# .jp2 se llaman B02/B03/B04 pero el Scene usa B2/B3/B4; B8A/B11/B12 no cambian.
TOKEN_A_BANDA = {
    "B02": "B2",
    "B03": "B3",
    "B04": "B4",
    "B8A": "B8A",
    "B11": "B11",
    "B12": "B12",
}
# Reverso para iterar en el orden exacto de COMMON_BANDS (el cubo queda alineado
# posicionalmente con COMMON_BANDS).
BANDA_A_TOKEN = {banda: token for token, banda in TOKEN_A_BANDA.items()}

RUTA_DATOS = "data/raw/"
RUTA_SCENE = "data/interim/scene.npz"


def _primer_archivo(patron: str, mensaje_faltante: str) -> str:
    """Devuelve el primer archivo que casa `patron`; aborta si no hay ninguno."""
    encontrados = glob.glob(patron, recursive=True)
    if not encontrados:
        raise FileNotFoundError(mensaje_faltante)
    return encontrados[0]


def construir_scene_final(ruta_base: str) -> Scene:
    """Construye el Scene de Nivel 1 (AOI recortada) desde la escena .SAFE.

    Lee las bandas de COMMON_BANDS a 20 m, las recorta al AOI, las pasa a
    reflectancia y arma la mascara de validez desde SCL. Aborta con un mensaje
    claro si falta la escena o alguna banda/SCL, en vez de reventar con
    IndexError.
    """
    print("--- Construyendo el objeto Scene ---")
    base = ruta_base.rstrip("/\\")

    # Abortar temprano si no hay ninguna carpeta .SAFE bajo la ruta base.
    if not glob.glob(f"{base}/**/*.SAFE", recursive=True):
        raise FileNotFoundError(
            f"No encontre ninguna carpeta .SAFE en {ruta_base}; "
            "¿esta descargada la escena?"
        )

    ventana_aoi = Window(
        col_off=AOI_COL_OFF,
        row_off=AOI_ROW_OFF,
        width=AOI_WIDTH,
        height=AOI_HEIGHT,
    )

    capas = []
    mi_crs = None
    mi_transform = None

    print("1. Leyendo bandas y extrayendo la georreferenciacion del recorte...")
    for banda in COMMON_BANDS:
        token = BANDA_A_TOKEN[banda]
        patron = f"{base}/**/*.SAFE/**/IMG_DATA/R20m/*_{token}_20m.jp2"
        ruta = _primer_archivo(
            patron,
            f"No encontre la banda {token} en {ruta_base}; "
            "¿esta descargada la escena?",
        )
        with rasterio.open(ruta) as src:
            if mi_crs is None:
                mi_crs = src.crs
                # Recalcula las coordenadas geograficas solo para el AOI.
                mi_transform = src.window_transform(ventana_aoi)
            dn = src.read(1, window=ventana_aoi)
            reflectancia = (dn.astype(np.float32) - DN_OFFSET) / DN_SCALE
            capas.append(np.clip(reflectancia, 0, 1))

    # np.array sobre una lista de matrices 2D apila en forma (bandas, alto, ancho).
    cubo = np.array(capas, dtype=np.float32)

    print("2. Calculando la mascara de validez desde SCL...")
    patron_scl = f"{base}/**/*.SAFE/**/IMG_DATA/R20m/*_SCL_20m.jp2"
    ruta_scl = _primer_archivo(
        patron_scl,
        f"No encontre la banda SCL en {ruta_base}; ¿esta descargada la escena?",
    )
    with rasterio.open(ruta_scl) as src:
        scl = src.read(1, window=ventana_aoi)
        # True = pixel valido (suelo), False = nube/sombra/cirrus.
        mascara = ~np.isin(scl, SCL_INVALID)

    print("3. Empaquetando en el contrato Scene...")
    return Scene(
        cube=cubo,
        band_names=list(COMMON_BANDS),
        transform=mi_transform,
        crs=mi_crs,
        mask=mascara,
    )


def main() -> None:
    """Construye el Scene, lo guarda en disco e imprime un resumen."""
    scene = construir_scene_final(RUTA_DATOS)

    os.makedirs(os.path.dirname(RUTA_SCENE), exist_ok=True)
    save_scene(scene, RUTA_SCENE)

    n_validos = int(scene.mask.sum())
    print("==================================================")
    print(f"Forma del cubo  : {scene.cube.shape}")
    print(f"band_names      : {scene.band_names}")
    print(f"Pixeles validos : {n_validos:,} / {scene.mask.size:,}")
    print(f"Scene guardado  : {RUTA_SCENE}")
    print("==================================================")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
