"""Genera el RGB del AOI (la misma zona que el Scene) con realce por percentiles.

Carga data/interim/scene.npz; si no existe, construye el Scene desde data/raw/.
Toma B4/B3/B2 como Rojo/Verde/Azul, estira el contraste a los percentiles 2-98
y guarda la figura en outputs/figures/scene_rgb.png.

El realce y el armado del compuesto viven en `visualization/maps.py`: el
notebook 01 necesita exactamente el mismo RGB, y dos copias de la logica
pueden divergir sin que ninguna de las dos figuras se vea mal.
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt

from mineralmap.io.raster_io import Scene, load_scene
from mineralmap.preprocessing.scene_builder import build_scene_from_safe
from mineralmap.visualization.maps import rgb_composite

RUTA_SCENE = "data/interim/scene.npz"
RUTA_RAW = "data/raw/"
OUTPUT_PATH = "outputs/figures/scene_rgb.png"


def _cargar_scene() -> Scene:
    """Carga el Scene desde disco; si no existe, lo construye desde data/raw/."""
    if os.path.exists(RUTA_SCENE):
        return load_scene(RUTA_SCENE)

    print(f"No existe {RUTA_SCENE}; construyendo el Scene desde {RUTA_RAW}...")
    return build_scene_from_safe(root=RUTA_RAW)


def main() -> None:
    """Arma el RGB del AOI y lo guarda como PNG."""
    scene = _cargar_scene()
    rgb = rgb_composite(scene)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(rgb)
    ax.axis("off")
    fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Guardado: {OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"[ABORTADO] {e}")
        raise SystemExit(1)
