
import rasterio
from rasterio.windows import Window
import glob
import numpy as np
import os

# Importamos la clase Scene que tu equipo definió en el Nivel 1
from src.mineralmap.io.raster_io import Scene

def construir_scene_final(ruta_base):
    print("--- Iniciando construcción del Objeto Scene ---")
    
    bandas_requeridas = ['B02', 'B03', 'B04', 'B8A', 'B11', 'B12']
    capas_procesadas = []
    ventana_aoi = Window(col_off=1000, row_off=1000, width=2000, height=2000)
    
    # Variables para almacenar la geografía de nuestro recorte
    mi_crs = None
    mi_transform = None
    
    print("1. Procesando bandas científicas y extrayendo metadatos...")
    for banda in bandas_requeridas:
        archivos = glob.glob(f"{ruta_base}/**/*.SAFE/**/IMG_DATA/R20m/*_{banda}_20m.jp2", recursive=True)
        
        with rasterio.open(archivos[0]) as src:
            # En la primera vuelta, guardamos las coordenadas geográficas del recorte
            if mi_crs is None:
                mi_crs = src.crs
                # src.window_transform recalcula las coordenadas GPS solo para tu zona AOI
                mi_transform = src.window_transform(ventana_aoi)
            
            matriz = src.read(1, window=ventana_aoi)
            reflectancia = (matriz.astype(float) - 1000) / 10000.0
            capas_procesadas.append(np.clip(reflectancia, 0, 1))

    # Al usar np.array en una lista de matrices 2D, Python apila en forma (Bandas, Alto, Ancho)
    # ¡Cumpliendo exactamente el contrato de tu clase Scene!
    cubo_final = np.array(capas_procesadas)
    
    print("2. Calculando la máscara de nubes (SCL)...")
    archivos_scl = glob.glob(f"{ruta_base}/**/*.SAFE/**/IMG_DATA/R20m/*_SCL_20m.jp2", recursive=True)
    
    with rasterio.open(archivos_scl[0]) as src:
        mascara_scl = src.read(1, window=ventana_aoi)
        # Generamos la matriz booleana: True para suelo, False para nubes/sombras
        pixeles_validos = ~np.isin(mascara_scl, [3, 8, 9, 10])

    # ORDEN 6: Armar el objeto Scene
    print("\n3. Empaquetando todo en el contrato Scene...")
    escena_lista = Scene(
        cube=cubo_final,
        band_names=bandas_requeridas,
        transform=mi_transform,
        crs=mi_crs,
        mask=pixeles_validos
    )
    
    print("==================================================")
    print("¡ÉXITO! Track A completado al 100%")
    print(f"Objeto creado: {type(escena_lista)}")
    print(f"Dimensiones del Cubo: {escena_lista.cube.shape}")
    print(f"Sistema Geográfico: {escena_lista.crs}")
    print("==================================================")
    
    return escena_lista

# --- EJECUCIÓN PRINCIPAL ---
RUTA_DATOS = "data/raw/" 
mi_scene_oficial = construir_scene_final(RUTA_DATOS)