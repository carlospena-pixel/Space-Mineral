# Space-Mineral: estado para trabajar

Detección de alteración hidrotermal en Cerro Colorado con Sentinel-2 y EMIT.
Si la documentación y el código difieren, manda el código.

## Entorno

```
conda env create -f environment.yml
conda activate mineralmap
pytest -q
pre-commit run --all-files
```

- Si ya existe un `mineralmap` anterior, no usar `conda env update` (agota la
  memoria al resolver). Crear uno nuevo al lado:
  `conda env create -n mineralmap-v2 -f environment.yml`.
- Sin conda (Python 3.10 o 3.13): `pip install -e ".[dev]"` en un venv. Las
  versiones no quedan fijas, así que las cifras pueden variar.

Los scripts se corren desde la raíz del repo, con el entorno activado.

## Datos (no van en git)

- `data/raw/`: `S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE`
  (Copernicus Browser; `download_scene.py` no está implementado).
- `data/raw/emit/`: `EMIT_L2B_MIN_002_20240716T190259.nc` y
  `EMIT_L2A_RFL_002_20240716T190259.nc` (NASA Earthdata, versión 002).

La geología y las firmas USGS necesarias ya vienen en `data/external/`.

## Orden de los scripts

```
python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml
python scripts/construir_verdad_terreno.py
python scripts/emit_to_grid.py
python scripts/emit_pistas.py
python scripts/comparar_modelos.py
python scripts/evaluar_lote.py modelos sensor pistas
python scripts/empate_modelos.py
python scripts/validar_familias.py
```

## Resultados vigentes

- SAM queda bajo el azar: AUC 0.24 en Sentinel-2 y 0.36 en EMIT.
  EMIT L2B caolinita: 0.68.
- B11/B8A ganó la validación cruzada (0.92) y falló en la prueba final (0.39).
  No hay un modelo validado.
- El 93 % de los positivos de esa validación cruzada es del Complejo Yabricoya.
- Dejando una familia de roca fuera, el mejor AUC macro es 0.71 (logística con
  Sentinel-2). Ningún modelo llega a 0.65 en las tres familias evaluables.

## Cuidado con

- **La prueba final ya se usó.** No elegir ni ajustar modelos con los bloques
  `prueba_final` de `configs/modelos_cerro_colorado.yaml`.
- La validación por familia usa hiperparámetros elegidos con una validación que
  incluía esas familias: no es del todo independiente.
- Los positivos son litologías elegidas por criterio, no alteración cartografiada.
- Verdad de terreno: 1 positivo, 0 negativo, 255 ambiguo. Nunca entrenar ni
  evaluar con 255 ni NaN.
- En SAM y SID menor es mejor. Declarar siempre la dirección en `evaluate.py`.
- En EMIT L2B, `mineral_id` usa la columna `index` de la biblioteca, no la
  posición de la fila. Arcillas y micas están en el grupo 2.
- Las firmas splib07b van en `data/external/splib07b/`. Un `.txt` con
  "wavelength" suelto en `data/external/` activa un test que espera 13 bandas.
- `run_pipeline.py` reescribe `outputs/figures/kaolinite_sam_angle.png`, que está
  versionado: revisar `git status` después de correrlo.
