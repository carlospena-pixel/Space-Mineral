"""Figura: SAM vs EMIT caolinita vs verdad de terreno, en la grilla del AOI.

Los tres GeoTIFF tienen que compartir la grilla (los escribe el proyecto sobre
data/interim/scene.npz); si no, aborta en vez de dibujar paneles desalineados.

Uso
---
    python scripts/figura_emit_vs_sam.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402


def _leer(ruta: str):
    with rasterio.open(ruta) as src:
        return src.read(1).astype(np.float64), src.transform, src.crs, src.shape


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sam", default="outputs/maps/kaolinite_sam_angle.tif")
    parser.add_argument("--emit", default="outputs/maps/emit_kaolinite_band_depth.tif")
    parser.add_argument("--truth", default="outputs/maps/ground_truth.tif")
    parser.add_argument(
        "--out", default="outputs/figures/emit_vs_sam_cerro_colorado.png"
    )
    args = parser.parse_args()

    sam, t_sam, crs_sam, f_sam = _leer(args.sam)
    emit, t_emit, crs_emit, f_emit = _leer(args.emit)
    verdad, t_ver, crs_ver, f_ver = _leer(args.truth)
    if not (
        t_sam == t_emit == t_ver
        and crs_sam == crs_emit == crs_ver
        and f_sam == f_emit == f_ver
    ):
        raise ValueError(
            "Los tres GeoTIFF no comparten grilla (transform, CRS o forma)."
        )

    alto, ancho = f_ver
    extent = [
        t_ver.c / 1000,
        (t_ver.c + ancho * t_ver.a) / 1000,
        (t_ver.f + alto * t_ver.e) / 1000,
        t_ver.f / 1000,
    ]

    fig, ejes = plt.subplots(1, 3, figsize=(16, 5.6), constrained_layout=True)

    # SAM: menor angulo = mas parecido a caolinita -> colormap invertido.
    vmin, vmax = np.nanpercentile(sam, [1, 99])
    im = ejes[0].imshow(sam, cmap="viridis_r", vmin=vmin, vmax=vmax, extent=extent)
    fig.colorbar(im, ax=ejes[0], shrink=0.8, label="angulo SAM (rad, menor = mejor)")
    ejes[0].set_title("Sentinel-2 SAM caolinita (2025-12-31)")

    # EMIT: 0 = pixel con dato sin caolinita identificada; se pinta gris.
    fondo = np.where(np.isfinite(emit), 0.0, np.nan)
    ejes[1].imshow(fondo, cmap=ListedColormap(["#d9d9d9"]), extent=extent)
    emit_pos = np.where(emit > 0, emit, np.nan)
    im = ejes[1].imshow(
        emit_pos,
        cmap="magma_r",
        vmin=0,
        vmax=np.nanpercentile(emit_pos, 99),
        extent=extent,
    )
    fig.colorbar(im, ax=ejes[1], shrink=0.8, label="band depth (mayor = mejor)")
    ejes[1].set_title("EMIT L2B V002 grupo caolinita (2024-07-16)")

    # Verdad: 1 positivo, 0 negativo, 255 ambiguo.
    clases = np.full(verdad.shape, np.nan)
    clases[verdad == 255] = 0
    clases[verdad == 0] = 1
    clases[verdad == 1] = 2
    cmap = ListedColormap(["#eeeeee", "#4c72b0", "#d62728"])
    ejes[2].imshow(
        clases, cmap=cmap, vmin=0, vmax=2, interpolation="nearest", extent=extent
    )
    ejes[2].legend(
        handles=[
            Patch(color="#d62728", label="positivo"),
            Patch(color="#4c72b0", label="negativo"),
            Patch(color="#eeeeee", label="ambiguo (no se evalua)"),
        ],
        loc="lower left",
        fontsize=8,
        framealpha=0.9,
    )
    ejes[2].set_title("Verdad de terreno SERNAGEOMIN")

    for eje in ejes:
        eje.set_xlabel("Este (km, EPSG:32719)")
    ejes[0].set_ylabel("Norte (km)")
    fig.suptitle("Cerro Colorado (Tarapaca): SAM vs EMIT vs verdad de terreno")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150)
    plt.close(fig)
    print(f"Figura escrita: {args.out}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, rasterio.errors.RasterioIOError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
