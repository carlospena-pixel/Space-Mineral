"""Entrypoint CLI: calcula metricas de un mapa de salida contra la verdad de terreno."""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predicted", help="Ruta al mapa de salida (GeoTIFF)")
    parser.add_argument("ground_truth", help="Ruta a la verdad de terreno (GeoTIFF/vector)")
    parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
