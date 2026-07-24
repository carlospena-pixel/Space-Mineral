"""Grafica la firma espectral de referencia de caolinita en las 12 bandas Sentinel-2."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt

from mineralmap.config import BAND_ORDER
from mineralmap.spectral.endmembers import get_reference_spectrum

OUTPUT_PATH = "outputs/figures/kaolinite_signature.png"


def main() -> None:
    """Genera y guarda el grafico de reflectancia vs. banda para caolinita."""
    spectrum = get_reference_spectrum("kaolinite", band_order=BAND_ORDER)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(BAND_ORDER, spectrum, marker="o", color="#8B5E3C")
    ax.set_xlabel("Banda Sentinel-2")
    ax.set_ylabel("Reflectancia")
    ax.set_title("Firma espectral de referencia: caolinita (USGS splib07)")
    ax.grid(alpha=0.3)

    # Rasgo diagnostico de la caolinita: fuerte absorcion Al-OH en ~2.2 um, que
    # se manifiesta como la caida de B11 a B12. La resaltamos y la etiquetamos.
    b11_idx = BAND_ORDER.index("B11")
    b12_idx = BAND_ORDER.index("B12")
    ax.plot(
        [b11_idx, b12_idx],
        [spectrum[b11_idx], spectrum[b12_idx]],
        color="#C0392B",
        linewidth=2.5,
        marker="o",
        zorder=3,
    )
    ax.annotate(
        "Absorción Al–OH (~2.2 µm)",
        xy=(b12_idx, spectrum[b12_idx]),
        xytext=(b12_idx - 4, spectrum[b12_idx] - 0.18),
        arrowprops=dict(arrowstyle="->", color="black"),
        fontsize=10,
        fontweight="bold",
    )

    fig.tight_layout()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=150)

    print(f"Guardado: {OUTPUT_PATH}")
    print(f"B11={spectrum[b11_idx]:.4f}  B12={spectrum[b12_idx]:.4f}")


if __name__ == "__main__":
    main()
