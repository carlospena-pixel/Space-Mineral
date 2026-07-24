"""Genera el RGB del AOI (la misma zona que el Scene) con realce por percentiles.

Carga data/interim/scene.npz; si no existe, construye el Scene desde data/raw/.
Toma B4/B3/B2 como Rojo/Verde/Azul, estira el contraste a los percentiles 2-98
y guarda la figura en outputs/figures/scene_rgb.png.
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np

from mineralmap.io.raster_io import Scene, load_scene

RUTA_SCENE = "data/interim/scene.npz"
RUTA_RAW = "data/raw/"
OUTPUT_PATH = "outputs/figures/scene_rgb.png"

# Percentiles para el realce de contraste: se recorta a [P_LOW, P_HIGH] y se
# reescala a [0, 1] para que la imagen no salga oscura.
P_LOW = 2
P_HIGH = 98


def _cargar_scene() -> Scene:
    """Carga el Scene desde disco; si no existe, lo construye desde data/raw/."""
    if os.path.exists(RUTA_SCENE):
        return load_scene(RUTA_SCENE)

    print(f"No existe {RUTA_SCENE}; construyendo el Scene desde {RUTA_RAW}...")
    # Import diferido: construir_scene es un script vecino, no un modulo del paquete.
    from construir_scene import construir_scene_final

    return construir_scene_final(RUTA_RAW)


def _banda(scene: Scene, nombre: str) -> np.ndarray:
    """Devuelve la capa del cubo cuyo nombre canonico es `nombre`."""
    if nombre not in scene.band_names:
        raise ValueError(
            f"La banda {nombre} no esta en el Scene (band_names={scene.band_names})."
        )
    return scene.cube[scene.band_names.index(nombre)]


def _realce_percentil(banda: np.ndarray) -> np.ndarray:
    """Recorta a los percentiles [P_LOW, P_HIGH] y reescala a [0, 1]."""
    lo, hi = np.percentile(banda, (P_LOW, P_HIGH))
    if hi <= lo:
        return np.zeros_like(banda)
    return np.clip((banda - lo) / (hi - lo), 0, 1)


def main() -> None:
    """Arma el RGB del AOI y lo guarda como PNG."""
    scene = _cargar_scene()

    rgb = np.dstack(
        [
            _realce_percentil(_banda(scene, "B4")),  # Rojo
            _realce_percentil(_banda(scene, "B3")),  # Verde
            _realce_percentil(_banda(scene, "B2")),  # Azul
        ]
    )

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
