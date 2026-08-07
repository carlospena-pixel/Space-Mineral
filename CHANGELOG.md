# Changelog

Todas las versiones notables de este proyecto se documentan en este archivo.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

### Added
- Estructura inicial del repositorio: paquete `mineralmap`, `configs/`, `scripts/`,
  `notebooks/`, `tests/` y `docs/` bilingües.
- Preprocesamiento implementado en el paquete (Semana 2, Track A):
  `preprocessing/reflectance.py` (escalado DN → reflectancia con el offset del
  baseline ≥ 04.00 y lectura de `MTD_MSIL2A.xml`), `preprocessing/masking.py`
  (máscara SCL con las 12 clases, `apply_mask` y `mask_summary`) y
  `preprocessing/resampling.py` (remuestreo en la lectura, `read_band_on_grid`
  y selector de método `resampling_for`).
- `preprocessing/scene_builder.py`: `build_scene_from_safe`, el orquestador que
  arma el `Scene` desde el producto `.SAFE` (localización de bandas, recorte al
  AOI, remuestreo a 20 m, reflectancia y máscara de validez).
- Localizadores de archivos en `io/raster_io.py`: `BAND_TOKEN`, `find_safe_dir`
  y `find_band_file`, que resuelven la resolución nativa de cada banda.
- `Scene.meta`: trazabilidad del producto de origen (tile, fecha, baseline,
  offset, ventana AOI, resolución nativa por banda y composición SCL del AOI),
  serializada como JSON en el `.npz`.
- `SAM_BANDS` en `config.py`: declara las 9 bandas que consumirá el detector
  espectral (excluye B1 y B9, atmosféricas, y B8, redundante con B8A). Solo
  declarado, sin consumidores todavía; cubierto por `tests/test_config.py`.
- Longitudes de onda como dato del proyecto (Semana 2, Track B):
  `BAND_WAVELENGTHS_NM`, `BAND_FWHM_NM` y el helper `band_wavelengths()` en
  `config.py`, con tablas separadas para S2A y S2B y `DEFAULT_PLATFORM = "S2B"`
  (la plataforma de la escena del proyecto). Incluyen B10 aunque `BAND_ORDER`
  no la tenga, porque el archivo de la librería USGS sí la trae y la validación
  de alineamiento la necesita. Verificadas contra SentiWiki (Copernicus), «S2
  Mission», tabla 3, derivada de las funciones de respuesta espectral de ESA
  (COPE-GSEG-EOPG-TN-15-0007).
- `tests/test_config.py`: el orden creciente de longitud de onda de
  `BAND_ORDER` pasa de ser una verificación manual de Track B a ser un test, y
  se exige correspondencia en ambas direcciones entre `BAND_ORDER` y la tabla
  de longitudes de onda.
- `docs/es/decisiones_tecnicas.md` y `docs/en/technical_decisions.md`: contratos
  de interfaz (`Scene`, `Detector`, `get_reference_spectrum`) y justificación de
  las decisiones de bandas, zona de estudio, máscara, remuestreo y reflectancia.
  Salda el entregable de documentación de Semana 0.
- CI en `.github/workflows/tests.yml`: corre `pytest` en Ubuntu sobre Python
  3.10 y 3.13 en cada push y pull request a `main`. Sin paso de lint hasta que
  `pre-commit run --all-files` pase limpio. Badge de estado en el README.

### Changed
- El `Scene` pasa de 6 a 12 bandas (`BAND_ORDER`); `COMMON_BANDS` se conserva
  como subconjunto documentado, ya no como valor por defecto.
- Zona de estudio: de Chuquicamata a Pampa del Tamarugal (tile `T19KDT`), por
  disponibilidad de datos. `configs/chuqui_kaolinite.yaml` pasó a
  `configs/tamarugal_kaolinite.yaml`.
- Criterio único de máscara SCL: se descartan las clases `[0, 1, 2, 3, 6, 8, 9,
  10, 11]`, ahora incluyendo agua (6). Antes convivían dos criterios distintos
  en el repositorio.
- `scripts/construir_scene.py` queda como CLI delgado (`argparse`); toda su
  lógica se movió al paquete.
- Las figuras de `outputs/figures/` se versionan: son la evidencia de cada hito.
- `outputs/figures/` queda reservada a entregables. Las salidas exploratorias
  van a `outputs/scratch/`, que no se versiona;
  `scripts/explorar_banda_b12.py` escribe ahí y `banda_12_reflectancia.png`
  dejó de estar en el repositorio.
- `README.md` apuntaba a `configs/chuqui_kaolinite.yaml`, renombrado en el
  commit anterior; el quickstart usa ahora `configs/tamarugal_kaolinite.yaml`.
