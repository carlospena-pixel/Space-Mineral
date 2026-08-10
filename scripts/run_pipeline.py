"""Entrypoint CLI: corre el pipeline completo desde un archivo de configuracion.

Toda la logica vive en `mineralmap.pipeline.run_pipeline`; este archivo solo
parsea argumentos, llama al paquete e imprime las rutas escritas.
"""

from __future__ import annotations

import argparse
import sys

from mineralmap.config import load_config
from mineralmap.pipeline import run_pipeline


def _parsear_argumentos() -> argparse.Namespace:
    """Acepta el config como posicional o como --config, pero no ambos.

    El script nacio con el config posicional y el hito de la Semana 3 lo
    invoca como `--config`. Se aceptan las dos formas para no romper lo que ya
    estaba escrito en el README ni en los apuntes del equipo, y se rechaza
    pasar las dos a la vez: si difirieran, elegir una en silencio correria el
    experimento con un config que nadie pidio.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "config_posicional",
        nargs="?",
        default=None,
        metavar="CONFIG",
        help="Ruta al YAML de configuracion del experimento",
    )
    parser.add_argument(
        "--config",
        dest="config_opcion",
        default=None,
        help="Misma ruta, como opcion nombrada (forma preferida)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Reconstruye el Scene desde el .SAFE ignorando data/interim/",
    )
    args = parser.parse_args()

    if args.config_posicional and args.config_opcion:
        parser.error(
            "recibi el config dos veces "
            f"({args.config_posicional!r} y {args.config_opcion!r}); pasa solo uno."
        )
    if not args.config_posicional and not args.config_opcion:
        parser.error("falta el config; usa --config configs/<experimento>.yaml")

    args.config = args.config_posicional or args.config_opcion
    return args


def main() -> None:
    """Carga el config, corre el pipeline e imprime las rutas escritas."""
    args = _parsear_argumentos()

    config = load_config(args.config)
    # --no-cache fuerza False; sin el, decide `preprocessing.cache_scene`.
    resultado = run_pipeline(config, use_cache=False if args.no_cache else None)

    print(f"Mapa georreferenciado: {resultado['angle_map_path']}")
    print(f"Heatmap              : {resultado['heatmap_path']}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
