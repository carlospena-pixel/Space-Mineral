"""Grafica la firma espectral de referencia de caolinita en las 12 bandas Sentinel-2."""

from __future__ import annotations

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

    b12_idx = BAND_ORDER.index("B12")
    ax.annotate(
        f"Caida en B12 ({spectrum[b12_idx]:.2f})",
        xy=(b12_idx, spectrum[b12_idx]),
        xytext=(b12_idx - 3, spectrum[b12_idx] - 0.15),
        arrowprops=dict(arrowstyle="->", color="black"),
    )

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=150)

    b11_idx = BAND_ORDER.index("B11")
    print(f"Guardado: {OUTPUT_PATH}")
    print(f"B11={spectrum[b11_idx]:.4f}  B12={spectrum[b12_idx]:.4f}")


if __name__ == "__main__":
    main()
