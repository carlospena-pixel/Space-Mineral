"""Entrypoint CLI: corre el pipeline completo a partir de un archivo de configuracion."""

import argparse

from mineralmap.config import load_config
from mineralmap.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="Ruta al YAML de configuracion del experimento")
    args = parser.parse_args()

    config = load_config(args.config)
    run_pipeline(config)


if __name__ == "__main__":
    main()
