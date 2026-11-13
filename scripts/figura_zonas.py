"""Figura: un panel por zona de alteracion (EMIT) y la verdad de terreno.

Cada zona es el maximo de los rangos percentiles de sus minerales (0 = menos
evidencia, 1 = mas); ver scripts/emit_pistas.py. Los paneles comparten grilla
con outputs/maps/ground_truth.tif; si no, aborta.

Uso
---
    python scripts/figura_zonas.py
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

ZONAS = [
    ("argilica", "Argilica (caolinita, montmorillonita)"),
    ("filica", "Filica (sericita)"),
    ("argilica_avanzada", "Argilica avanzada (alunita, pirofilita)"),
    ("propilitica", "Propilitica (clorita, epidota, calcita)"),
    ("oxidos", "Oxidos (goethita, hematita, jarosita)"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="outputs/maps/pistas")
    parser.add_argument("--truth", default="outputs/maps/ground_truth.tif")
    parser.add_argument("--out", default="outputs/figures/zonas_alteracion_cerro_colorado.png")
    args = parser.parse_args()

    with rasterio.open(args.truth) as src:
        verdad, t, crs, forma = src.read(1), src.transform, src.crs, src.shape
    alto, ancho = forma
    extent = [t.c / 1000, (t.c + ancho * t.a) / 1000, (t.f + alto * t.e) / 1000, t.f / 1000]

    fig, ejes = plt.subplots(2, 3, figsize=(17, 11), constrained_layout=True)
    for eje, (zona, titulo) in zip(ejes.ravel(), ZONAS):
        with rasterio.open(Path(args.dir) / f"zona_{zona}.tif") as src:
            if src.transform != t or src.crs != crs or src.shape != forma:
                raise ValueError(f"zona_{zona}.tif no comparte la grilla de la verdad de terreno.")
            mapa = src.read(1)
        im = eje.imshow(mapa, cmap="magma", vmin=0, vmax=1, extent=extent, interpolation="nearest")
        eje.set_title(titulo, fontsize=11)
        fig.colorbar(im, ax=eje, shrink=0.75, label="rango percentil (mayor = mas evidencia)")

    clases = np.full(verdad.shape, np.nan)
    clases[verdad == 255] = 0
    clases[verdad == 0] = 1
    clases[verdad == 1] = 2
    eje = ejes.ravel()[-1]
    eje.imshow(clases, cmap=ListedColormap(["#eeeeee", "#4c72b0", "#d62728"]), vmin=0, vmax=2,
               extent=extent, interpolation="nearest")
    eje.legend(handles=[Patch(color="#d62728", label="positivo"), Patch(color="#4c72b0", label="negativo"),
                        Patch(color="#eeeeee", label="ambiguo (no se evalua)")],
               loc="lower left", fontsize=8, framealpha=0.9)
    eje.set_title("Verdad de terreno SERNAGEOMIN", fontsize=11)

    for eje in ejes.ravel():
        eje.set_xlabel("Este (km, EPSG:32719)")
        eje.set_ylabel("Norte (km)")
    fig.suptitle("Cerro Colorado: zonas de alteracion de un porfido con EMIT (2024-07-16)", fontsize=14)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130)
    plt.close(fig)
    print(f"Figura escrita: {args.out}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, rasterio.errors.RasterioIOError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
