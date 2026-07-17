
import rasterio
import matplotlib.pyplot as plt
import glob
import numpy as np
import os

def explorar_banda_cientifica(ruta_base):
    print("Buscando la banda científica B12 (SWIR) a 20m...")
    
    # ORDEN 1: Buscar específicamente la banda 12
    archivos_b12 = glob.glob(f"{ruta_base}/**/*.SAFE/**/IMG_DATA/R20m/*_B12_20m.jp2", recursive=True)

    if not archivos_b12:
        print("Error: No se encontró la banda B12. Revisa tu carpeta data/raw.")
        return

    archivo_b12 = archivos_b12[0]
    print(f"Archivo encontrado: {os.path.basename(archivo_b12)}")

    # Leer la banda sola usando rasterio
    with rasterio.open(archivo_b12) as src:
        # Leemos toda la matriz de la banda 1 (la única capa que tiene este archivo)
        banda_12_cruda = src.read(1)

    print("ORDEN 3: Convertir valores a reflectancia pura...")
    # Convertimos a float para no perder los decimales cruciales en la división
    # Fórmula: (valor - 1000) / 10000
    banda_12_reflectancia = (banda_12_cruda.astype(float) - 1000) / 10000.0

    # Limpiamos anomalías (la reflectancia real se mide entre 0 y 1)
    banda_12_reflectancia = np.clip(banda_12_reflectancia, 0, 1)

    # Generar el gráfico de comprobación
    plt.figure(figsize=(8, 8))
    # Usamos cmap='gray' porque una sola banda no tiene color, es intensidad de luz
    plt.imshow(banda_12_reflectancia, cmap='gray')
    plt.colorbar(label="Reflectancia (0.0 a 1.0)")
    plt.title("Banda Científica B12 - Reflectancia Corregida")
    plt.axis("off")

    # Guardar el resultado
    plt.savefig("banda_12_reflectancia.png", dpi=100, bbox_inches="tight")
    print("¡Éxito! Se guardó la comprobación visual como banda_12_reflectancia.png")

# --- EJECUCIÓN PRINCIPAL ---
RUTA_DATOS = "data/raw/" 
explorar_banda_cientifica(RUTA_DATOS)