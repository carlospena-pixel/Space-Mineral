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
- `spectral/usgs_library.py`: `load_usgs_wavelengths()`, que lee el archivo de
  longitudes de onda de splib07 (mismo formato ASCIIdata, mismo manejo de «no
  dato») y las convierte de micrómetros a nanómetros en un solo lugar, con un
  control de rango que denuncia un archivo que ya viniera en nanómetros.
- `spectral/endmembers.py`: `validate_raw_band_order()`, que ancla
  `_RAW_BAND_ORDER` —la única pieza que afirma qué banda es cada posición del
  archivo USGS— comprobando el orden creciente de longitud de onda contra la
  tabla de ESA y, si hay archivo de longitudes de onda, el desvío por banda.
  Junto a `find_usgs_wavelengths_file()` y las constantes
  `USGS_RESAMPLING_PLATFORM` y `DEFAULT_WAVELENGTH_TOLERANCE_NM`.
  **Falta descargar** el archivo de longitudes de onda que acompaña a la firma
  dentro del paquete `ASCIIdata_splib07*_rsSentinel2` de la USGS Spectral
  Library Version 7 (<https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d>).
  Su nombre exacto dentro del paquete no está confirmado, así que el buscador
  trabaja por patrón (cualquier `.txt` de `data/external/` que mencione
  «wavelength») en vez de fijar un nombre inventado. Mientras no esté, el test
  que compara las λ del archivo contra la tabla de ESA queda en `skipif` y el
  orden de `_RAW_BAND_ORDER` sigue anclado solo a evidencia física.
- `tests/test_endmembers.py`: se cubre el fallo silencioso más caro del
  proyecto — que pedir la firma con un `band_order` distinto del default
  (p. ej. `SAM_BANDS`) reordene los valores en vez de reasignarlos.
- `notebooks/01_explore_sentinel2_scene.ipynb`: el hito de Semana 2. Carga la
  escena sobre una submuestra de 256×256 px, la enmascara, la ubica con un RGB
  y superpone la firma de dos píxeles a la de referencia con las 12 bandas
  alineadas. Incluye la tabla de verificación de alineamiento
  (`idx | banda | λ_S2B | ref_USGS | píxel`) con `assert`s que hacen fallar el
  notebook si algo no cuadra. El píxel se elige con criterio explícito —el de
  menor ángulo SAM del AOI, más el central como control—, no «uno cualquiera».
  Corre completo con kernel reiniciado.
- `outputs/figures/kaolinite_signature_vs_pixel.png`: la evidencia del hito.
- `visualization/maps.py`: `percentile_stretch()` y `rgb_composite()`, extraídos
  de `scripts/visualizar_rgb.py` para que el notebook y el script produzcan el
  mismo RGB en vez de dos copias que pueden divergir sin verse mal. El realce
  ahora ignora los NaN: con `np.percentile`, un solo píxel enmascarado dejaba
  la imagen entera negra sin lanzar ningún error.
- `visualization/spectra.py`: `plot_spectra()` implementado (era un stub), más
  `normalize_signature()`. Eje x en longitud de onda real, normalización L2 por
  defecto —que es lo que ve el SAM, invariante al albedo— y corte explícito de
  la línea donde el sensor no muestreó (B9 → B11, con B10 ausente del L2A).
  Los NaN se propagan en vez de convertirse en cero.
- `tests/test_spectra.py`: cubre las tres decisiones anteriores sin depender de
  la escena, incluida la propiedad que hace útil el gráfico —dos firmas
  proporcionales quedan superpuestas con normalización L2—.
- `tests/test_scene_builder.py`: tres tests que blindan la frontera entre
  `preprocessing` y `spectral` sobre la escena real —que la firma pedida con
  `band_order=scene.band_names` traiga tantos valores como bandas el cubo, que
  `apply_mask` no deje el AOI entero en NaN ni mute el cubo original, y que
  subconjuntar el cubo por índice y pedir la firma por nombre lleguen a la
  misma banda—. Siguen bajo el `skipif` que ya tenía el archivo.
- `tests/test_maps.py`: cubre el realce por percentiles y el compuesto RGB sin
  depender de la escena.
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
- CI: se agrega el job `lint`, que corre `pre-commit` (black, ruff, isort,
  nbstripout) sobre todos los archivos. El workflow decía que el paso se
  agregaría cuando `pre-commit run --all-files` pasara limpio; ya pasa. Va como
  job aparte del de tests porque el formato no depende de la versión de Python.
- Todo el repositorio pasa `pre-commit run --all-files`: `black` reformateó
  cuatro archivos, `ruff` arregló tres errores y se acortaron a mano cinco
  docstrings que excedían las 88 columnas. Los notebooks ganaron el campo `id`
  por celda que exige nbformat 4.5+.
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

### Removed
- `construir_scene_final()` de `scripts/construir_scene.py`: estaba marcada
  DEPRECADO y no la importaba nadie (verificado por búsqueda en todo el
  repositorio). Su reemplazo es `build_scene_from_safe()` directamente.
