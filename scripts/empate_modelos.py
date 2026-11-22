"""CLI: que modelos empatan con el mejor en la validacion cruzada.

Bootstrap por bloques sobre los mapas de comparar_modelos.py. No lee la prueba
final.

Uso
---
    python scripts/empate_modelos.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import yaml

from mineralmap.validation.comparacion import block_bootstrap_ties
from mineralmap.validation.familias import block_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/modelos_cerro_colorado.yaml")
    parser.add_argument("--sorteos", type=int, default=500)
    parser.add_argument("--out", default="outputs/metrics/modelos/empate.json")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    resumen = json.loads(
        Path("outputs/metrics/modelos/resumen_cv.json").read_text(encoding="utf-8")
    )
    with rasterio.open(cfg["verdad"]) as src:
        verdad = src.read(1)
    etiquetados = np.isin(verdad, (0, 1))

    # Solo los pixeles etiquetados: 14 mapas completos no caben comodos en RAM.
    valores = {}
    for nombre, m in resumen["modelos"].items():
        with rasterio.open(m["archivo"]) as src:
            v = src.read(1)[etiquetados]
        valores[nombre] = v if m["higher_is_better"] else -v
    comunes = np.all([np.isfinite(v) for v in valores.values()], axis=0)

    bloques = block_ids(verdad.shape, int(cfg["bloques"]["tamano_px"]))
    mejor, filas = block_bootstrap_ties(
        {n: v[comunes] for n, v in valores.items()},
        verdad[etiquetados][comunes].astype(int),
        bloques[etiquetados][comunes],
        n_sorteos=args.sorteos,
        semilla=int(cfg["semilla"]),
    )

    print(f"Mejor: {mejor}")
    for nombre, r in sorted(filas.items(), key=lambda x: -x[1]["auc"]):
        bajo, alto = r["ic95"]
        estado = "EMPATE" if r["empate"] else "peor"
        print(
            f"  {nombre:24s} AUC {r['auc']:.4f} | "
            f"IC95 [{bajo:+.4f}, {alto:+.4f}] {estado}"
        )
    salida = Path(args.out)
    salida.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps({"mejor": mejor, "modelos": filas}, indent=2)
    salida.write_text(texto, encoding="utf-8")
    print(f"Escrito: {salida}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, rasterio.errors.RasterioIOError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
