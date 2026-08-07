"""Entrypoint CLI: descarga una escena Sentinel-2 L2A.

Toda la logica vive en `mineralmap.io.acquisition`.
"""

import argparse

from mineralmap.io.acquisition import download_scene


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene_id", help="Identificador de la escena en CDSE")
    parser.add_argument("--dest", default="data/raw", help="Directorio de destino")
    args = parser.parse_args()

    download_scene(args.scene_id, args.dest)


if __name__ == "__main__":
    main()
