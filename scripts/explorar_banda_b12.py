"""Comprobacion visual de la banda B12 (SWIR) completa, en reflectancia.

No recorta al AOI ni arma un Scene: lee la banda entera del tile y la grafica,
para verificar a ojo que la conversion DN -> reflectancia da valores sensatos.
"""

from __future__ import annotations

import os
import sys

import matplotlib.pyplot as plt
import rasterio

from mineralmap.io.raster_io import find_band_file, find_safe_dir
from mineralmap.preprocessing.reflectance import dn_to_reflectance, read_l2a_scaling

RUTA_DATOS = "data/raw/"
OUTPUT_PATH = "outputs/figures/banda_12_reflectancia.png"


def explorar_banda_cientifica(ruta_base: str) -> None:
    """Grafica la banda B12 en reflectancia y guarda la figura en outputs/."""
    safe_dir = find_safe_dir(ruta_base)
    ruta_b12, resolucion = find_band_file(safe_dir, "B12")
    print(f"Archivo encontrado: {os.path.basename(ruta_b12)} (R{resolucion}m)")

    baseline, offset, quantification = read_l2a_scaling(safe_dir)
    print(f"Escalado: baseline {baseline}, offset {offset}, /{quantification}")

    with rasterio.open(ruta_b12) as src:
        banda_cruda = src.read(1)

    # Misma conversion que usa el Scene: nada de repetir la formula a mano.
    banda_reflectancia = dn_to_reflectance(
        banda_cruda,
        baseline=baseline,
        offset=offset,
        quantification=quantification,
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 8))
    # cmap gris: una sola banda no tiene color, es intensidad de luz.
    imagen = ax.imshow(banda_reflectancia, cmap="gray")
    fig.colorbar(imagen, ax=ax, label="Reflectancia (0.0 a 1.0)")
    ax.set_title("Banda B12 (SWIR) - reflectancia superficial")
    ax.axis("off")
    fig.savefig(OUTPUT_PATH, dpi=100, bbox_inches="tight")
    plt.close(fig)
    print(f"Guardado: {OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        explorar_banda_cientifica(RUTA_DATOS)
    except FileNotFoundError as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
