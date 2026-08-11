"""CLI: cotejo de las cifras publicadas en los documentos contra el GeoTIFF real.

Por que existe. El README y la seccion 7 de decisiones tecnicas publican la
distribucion de angulos y el barrido de umbrales del AOI. Esas cifras se
escribieron a mano copiandolas de una corrida, y una copia a mano se desactualiza
sin avisar: ya paso una vez, cuando el repositorio afirmaba "ni un solo pixel
bajo el umbral" con una medicion tomada sobre una ventana de 256x256 px mientras
el AOI completo dejaba 62. El documento no se rompe cuando miente, se lee igual
de bien.

Este script convierte esa comprobacion manual en una que se puede correr. NO
escribe nada: abre el .tif, recalcula cada cifra, la busca en los documentos
--parseandola de los propios archivos, no de una copia guardada aca-- y sale con
codigo 1 si alguna no calza.

Necesita el .tif, o sea la escena, asi que no va en CI: el runner de GitHub no
tiene el producto .SAFE. Se corre en local antes de publicar cambios de docs.

Uso (desde la raiz del repo):
    python scripts/verificar_cifras.py
    python scripts/verificar_cifras.py --tif outputs/maps/otro_mapa.tif
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

TIF_POR_DEFECTO = "outputs/maps/kaolinite_sam_angle.tif"

# Umbrales del barrido, los mismos de `pipeline.THRESHOLD_SWEEP`. Se repiten
# aca en vez de importarlos porque este script verifica lo que dicen los
# documentos, y tiene que fallar tambien si el pipeline cambia el barrido y los
# documentos se quedan con el viejo.
UMBRALES = (0.05, 0.08, 0.10, 0.15, 0.20)

# Tolerancia al comparar. Los documentos publican 4 decimales, asi que media
# unidad del ultimo decimal publicado es lo maximo que puede separar a una cifra
# correcta de su medicion.
TOLERANCIA = 5e-5


@dataclass(frozen=True)
class Documento:
    """Un archivo a verificar y la convencion numerica con que esta escrito.

    El separador decimal se declara por documento en vez de deducirse: "4.513"
    es cuatro mil quinientos trece en el README en espanol y cuatro coma
    quinientos trece en el ingles, y ninguna heuristica puede distinguirlos
    mirando solo el numero.
    """

    ruta: str
    decimal: str  # "," en los documentos ES, "." en los EN
    etiquetas: dict[str, str]  # nombre de la cifra -> rotulo de la fila


# Que se busca en cada documento. Las claves de `etiquetas` son las cifras que
# calcula `medir()`; los valores son el rotulo de la primera celda de la fila de
# la tabla markdown que la publica.
DOCUMENTOS: tuple[Documento, ...] = (
    Documento(
        ruta="README.md",
        decimal=",",
        etiquetas={
            "min": "mínimo",
            "p1": "percentil 1",
            "mediana": "mediana",
            "max": "máximo",
        },
    ),
    Documento(
        ruta="README.md",
        decimal=".",
        etiquetas={
            "min": "minimum",
            "p1": "1st percentile",
            "mediana": "median",
            "max": "maximum",
        },
    ),
    Documento(
        ruta="docs/es/decisiones_tecnicas.md",
        decimal=",",
        etiquetas={"fila_sam": "`SAM_BANDS` (9)"},
    ),
    Documento(
        ruta="docs/en/technical_decisions.md",
        decimal=".",
        etiquetas={"fila_sam": "`SAM_BANDS` (9)"},
    ),
)

# Orden de las columnas de la fila `SAM_BANDS (9)` de la tabla del AOI completo
# en la seccion 7: | bandas | min | p1 | mediana | max |.
COLUMNAS_FILA_SAM = ("min", "p1", "mediana", "max")


def _a_numero(texto: str, decimal: str) -> float | None:
    """Convierte una celda de tabla markdown a float, o None si no es un numero.

    Tolera el resaltado (`**62**`), el signo de porcentaje, los espacios y los
    separadores de miles de las dos convenciones. El separador de miles es
    siempre el que no es el decimal.
    """
    limpio = texto.strip().strip("*").replace("%", "").replace("`", "").strip()
    limpio = limpio.replace(" ", "").replace(" ", "").replace(" ", "")
    if not limpio:
        return None

    miles = "." if decimal == "," else ","
    limpio = limpio.replace(miles, "").replace(decimal, ".")

    try:
        return float(limpio)
    except ValueError:
        return None


def _celdas(linea: str) -> list[str]:
    """Celdas de una fila de tabla markdown, sin los pipes de los extremos."""
    return [celda.strip() for celda in linea.strip().strip("|").split("|")]


def _filas_de_tabla(texto: str) -> list[list[str]]:
    """Todas las filas de tabla markdown del documento, ya troceadas en celdas.

    Se descartan las lineas separadoras (`|---|---|`), que no traen datos.
    """
    filas = []
    for linea in texto.splitlines():
        if not linea.strip().startswith("|"):
            continue
        celdas = _celdas(linea)
        if all(re.fullmatch(r":?-{2,}:?", celda) for celda in celdas if celda):
            continue
        filas.append(celdas)
    return filas


def medir(ruta_tif: str) -> dict[str, float]:
    """Recalcula desde el .tif todas las cifras que los documentos publican."""
    with rasterio.open(ruta_tif) as src:
        mapa = src.read(1).astype(np.float64)

    validos = mapa[np.isfinite(mapa)]
    if validos.size == 0:
        raise ValueError(f"{ruta_tif} no tiene ni un pixel valido.")

    cifras = {
        "min": float(validos.min()),
        "p1": float(np.percentile(validos, 1)),
        "mediana": float(np.median(validos)),
        "max": float(validos.max()),
        "validos": float(validos.size),
    }
    for umbral in UMBRALES:
        cifras[f"umbral_{umbral:.2f}"] = float((validos <= umbral).sum())

    return cifras


def _declaradas(doc: Documento, texto: str) -> dict[str, float]:
    """Extrae del documento las cifras que declara, por rotulo de fila."""
    encontradas: dict[str, float] = {}

    for celdas in _filas_de_tabla(texto):
        if not celdas:
            continue
        rotulo = celdas[0].strip().strip("*").strip()

        for nombre, etiqueta in doc.etiquetas.items():
            if rotulo.lower() != etiqueta.lower():
                continue
            if nombre == "fila_sam":
                # | `SAM_BANDS` (9) | min | p1 | mediana | max |
                for columna, celda in zip(COLUMNAS_FILA_SAM, celdas[1:]):
                    valor = _a_numero(celda, doc.decimal)
                    if valor is not None:
                        encontradas[columna] = valor
            else:
                valor = _a_numero(celdas[1], doc.decimal)
                if valor is not None:
                    encontradas[nombre] = valor

        # Filas del barrido de umbrales: | 0,10 | 62 | 0,002 % |
        umbral = _a_numero(rotulo, doc.decimal)
        if umbral is not None and len(celdas) >= 2:
            for esperado in UMBRALES:
                if abs(umbral - esperado) < 1e-9:
                    pixeles = _a_numero(celdas[1], doc.decimal)
                    if pixeles is not None:
                        encontradas[f"umbral_{esperado:.2f}"] = pixeles

    return encontradas


def verificar(ruta_tif: str, raiz: Path) -> tuple[list[tuple], bool]:
    """Coteja cada cifra declarada contra la medida. Devuelve (filas, todo_ok)."""
    medidas = medir(ruta_tif)
    filas: list[tuple] = []
    todo_ok = True

    for doc in DOCUMENTOS:
        ruta = raiz / doc.ruta
        if not ruta.is_file():
            filas.append(("(archivo)", doc.ruta, "no existe", "FALTA"))
            todo_ok = False
            continue

        declaradas = _declaradas(doc, ruta.read_text(encoding="utf-8"))
        if not declaradas:
            # Un documento del que no se extrae ninguna cifra es un fallo, no un
            # exito vacio: significa que se renombro un rotulo de tabla y el
            # cotejo dejo de mirar lo que decia mirar.
            origen = f"{doc.ruta} [{doc.decimal}]"
            filas.append(("(ninguna)", origen, "-", "SIN CIFRAS"))
            todo_ok = False
            continue

        for nombre, declarada in sorted(declaradas.items()):
            medida = medidas.get(nombre)
            if medida is None:
                filas.append((nombre, doc.ruta, "no se mide", "DESCONOCIDA"))
                todo_ok = False
                continue

            # Las cifras de conteo son enteras y se comparan exacto; las de
            # angulo se publican redondeadas a 4 decimales.
            if nombre.startswith("umbral_") or nombre == "validos":
                ok = abs(declarada - medida) < 0.5
            else:
                ok = abs(declarada - medida) <= TOLERANCIA

            todo_ok = todo_ok and ok
            filas.append(
                (
                    f"{nombre} = {declarada:g}",
                    f"{doc.ruta} [{doc.decimal}]",
                    f"{medida:g}",
                    "OK" if ok else "NO CALZA",
                )
            )

    return filas, todo_ok


def _imprimir(filas: list[tuple]) -> None:
    """Imprime la tabla cifra | documento | medido | veredicto."""
    cabecera = ("cifra", "documento", "medido", "veredicto")
    anchos = [max(len(str(fila[i])) for fila in [cabecera, *filas]) for i in range(4)]
    linea = "  ".join("-" * ancho for ancho in anchos)

    print("  ".join(str(c).ljust(a) for c, a in zip(cabecera, anchos)))
    print(linea)
    for fila in filas:
        print("  ".join(str(c).ljust(a) for c, a in zip(fila, anchos)))


def main() -> None:
    """Coteja los documentos contra el .tif e imprime el resultado."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tif",
        default=TIF_POR_DEFECTO,
        help="GeoTIFF contra el que verificar (default: %(default)s)",
    )
    args = parser.parse_args()

    raiz = Path(__file__).resolve().parents[1]
    filas, todo_ok = verificar(args.tif, raiz)

    _imprimir(filas)
    print()
    if todo_ok:
        print(f"OK: las {len(filas)} cifras publicadas coinciden con {args.tif}.")
    else:
        fallidas = sum(1 for fila in filas if fila[3] != "OK")
        print(f"FALLA: {fallidas} de {len(filas)} cifras no coinciden con {args.tif}.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, rasterio.errors.RasterioIOError) as e:
        print(f"[ABORTADO] {e}")
        sys.exit(1)
