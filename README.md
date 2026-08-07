# Spectral Mineral Mapping

[![tests](https://github.com/carlospena-pixel/Space-Mineral/actions/workflows/tests.yml/badge.svg)](https://github.com/carlospena-pixel/Space-Mineral/actions/workflows/tests.yml)

**ES** | [EN](#en)

Detección de minerales de alteración hidrotermal (caolinita, alunita, hematita, ...) a
partir de imágenes Sentinel-2 L2A, comparando contra la librería espectral USGS
splib07 y validando contra cartografía geológica de SERNAGEOMIN.

El repositorio está diseñado para escalar de **Nivel 1** (Spectral Angle Mapper) a
**Nivel 2** (Random Forest, más minerales) y **Nivel 3** (unmixing, validación
estadística formal, interfaz para geólogo) sin refactorizar. Ver
`docs/es/decisiones_tecnicas.md` y `docs/es/pipeline.md` para el detalle.

## Quickstart

```bash
# Entorno reproducible (rasterio/gdal vía conda-forge)
conda env create -f environment.yml
conda activate mineralmap

# Paquete instalable en modo editable
pip install -e ".[dev]"
pre-commit install

# Correr un experimento
python scripts/run_pipeline.py configs/tamarugal_kaolinite.yaml
python scripts/evaluate.py data/processed/tamarugal_kaolinite/score_map.tif data/external/sernageomin/...
```

Los datos (`data/`) no se versionan; ver `docs/es/pipeline.md` para cómo obtenerlos.

## Estructura

```
configs/      Experimentos declarativos (YAML)
data/         Datos crudos/externos/intermedios/procesados (no versionado)
src/mineralmap/  Paquete instalable: io, preprocessing, spectral, algorithms, validation, visualization
scripts/      Entrypoints CLI delgados
notebooks/    Exploración y prototipado
tests/        pytest
docs/         Documentación extendida (ES/EN)
outputs/      Figuras y mapas exportados (solo outputs/figures/*.png se versiona)
```

## Resultados

Lo verificado hasta hoy es el preprocesamiento: la escena queda recortada,
remuestreada, en reflectancia y con su máscara de validez. **Todavía no hay
ninguna detección de mineral** (ver [Detección](#detección-pendiente) más
abajo). El estado etapa por etapa está en
[docs/es/pipeline.md](docs/es/pipeline.md).

### La escena y su AOI

| | |
|---|---|
| Producto | `S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE` |
| Tile / CRS | `T19KDT` (Pampa del Tamarugal, Tarapacá) / EPSG:32719 |
| AOI | ventana `col_off=1000, row_off=1000, 2000 × 2000` px a 20 m, o sea **40 × 40 km** |
| Cubo | `(12, 2000, 2000)` `float32`, reflectancia en `[0, 1]`, baseline `05.11` |
| Suelo desnudo (SCL 5) | **99,92 %** del AOI |
| Píxeles válidos | **99,9977 %**: 3.999.908 de 4.000.000, o sea 92 descartados |

Las dos últimas cifras salen de `Scene.meta["scl_summary"]` y las imprime
`python scripts/construir_scene.py`. Son la condición que se buscaba al elegir
la zona: desierto despejado, sin nubes ni vegetación que tapen la superficie
que se quiere medir.

### Figuras (`outputs/figures/`)

| Figura | Qué muestra |
|---|---|
| `scene_rgb.png` | El AOI en color verdadero (B4/B3/B2) con realce por percentiles 2–98 banda a banda. Sirve para ubicarse: es la referencia visual de dónde caen las demás figuras. |
| `mascara_scl.png` | La clasificación SCL del AOI con su leyenda, al lado de la máscara de validez que sale de ella. Es la evidencia de las cifras de la tabla anterior: se ve que lo descartado son 92 píxeles sueltos y no una región. |
| `kaolinite_signature.png` | La firma de referencia de la caolinita (USGS splib07, muestra KGa-1) en las 12 bandas del contrato, con la caída B11 → B12 del rasgo de absorción Al–OH resaltada. El eje x es el índice de banda: es la figura anterior a `plot_spectra`. |
| `kaolinite_signature_vs_pixel.png` | Esa misma firma superpuesta a dos píxeles reales del AOI —el de menor ángulo SAM y el central como control—, con las 12 bandas alineadas, normalización L2 y el eje x en longitud de onda. Es el hito de la Semana 2: muestra que el cubo y la firma hablan de la misma banda, y de paso que ninguno de los dos píxeles acompaña la caída B11 → B12 de la caolinita. |

### Detección: pendiente

`algorithms/sam.py` está implementado y testeado, pero nada lo corre todavía
sobre la escena: `pipeline.py` levanta `NotImplementedError` y la validación
contra cartografía de SERNAGEOMIN (`validation/`) es andamiaje. Además, el
umbral que fija `configs/tamarugal_kaolinite.yaml` no dejaría ni un píxel bajo
él en la ventana del AOI donde se midió, y se mantiene a la espera de un
criterio de calibración
(`docs/es/decisiones_tecnicas.md`, sección 7). Hasta que eso exista, este
repositorio no reporta caolinita detectada.

---

<a id="en"></a>
## English

[![tests](https://github.com/carlospena-pixel/Space-Mineral/actions/workflows/tests.yml/badge.svg)](https://github.com/carlospena-pixel/Space-Mineral/actions/workflows/tests.yml)

Detection of hydrothermal alteration minerals (kaolinite, alunite, hematite, ...) from
Sentinel-2 L2A imagery, matched against the USGS splib07 spectral library and
validated against SERNAGEOMIN geological mapping.

The repository is designed to scale from **Level 1** (Spectral Angle Mapper) to
**Level 2** (Random Forest, more minerals) and **Level 3** (unmixing, formal
statistical validation, geologist-facing interface) without refactoring. See
`docs/en/technical_decisions.md` and `docs/en/pipeline.md` for details.

### Quickstart

```bash
conda env create -f environment.yml
conda activate mineralmap

pip install -e ".[dev]"
pre-commit install

python scripts/run_pipeline.py configs/tamarugal_kaolinite.yaml
```

`data/` is not versioned; see `docs/en/pipeline.md` for how to obtain it.

### Results

What is verified today is the preprocessing: the scene is cropped, resampled,
converted to reflectance and paired with its validity mask. **There is no
mineral detection yet** (see [Detection](#detection-pending) below). The
stage-by-stage status is in [docs/en/pipeline.md](docs/en/pipeline.md).

#### The scene and its AOI

| | |
|---|---|
| Product | `S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE` |
| Tile / CRS | `T19KDT` (Pampa del Tamarugal, Tarapacá Region, Chile) / EPSG:32719 |
| AOI | window `col_off=1000, row_off=1000, 2000 × 2000` px at 20 m, i.e. **40 × 40 km** |
| Cube | `(12, 2000, 2000)` `float32`, reflectance in `[0, 1]`, baseline `05.11` |
| Bare soil (SCL 5) | **99.92 %** of the AOI |
| Valid pixels | **99.9977 %**: 3,999,908 out of 4,000,000, i.e. 92 discarded |

The last two figures come from `Scene.meta["scl_summary"]` and are printed by
`python scripts/construir_scene.py`. They are the condition the study area was
chosen for: clear desert, with no cloud or vegetation covering the surface to
be measured.

#### Figures (`outputs/figures/`)

| Figure | What it shows |
|---|---|
| `scene_rgb.png` | The AOI in true colour (B4/B3/B2) with a 2–98 percentile stretch applied band by band. It is the visual reference for where everything else sits. |
| `mascara_scl.png` | The AOI's SCL classification with its legend, next to the validity mask derived from it. It is the evidence behind the table above: what gets discarded is 92 scattered pixels, not a region. |
| `kaolinite_signature.png` | The kaolinite reference signature (USGS splib07, sample KGa-1) across the 12 contract bands, highlighting the B11 → B12 drop of the Al–OH absorption feature. The x axis is the band index: this is the figure that predates `plot_spectra`. |
| `kaolinite_signature_vs_pixel.png` | That same signature overlaid on two real AOI pixels — the lowest SAM angle one and the central one as a control — with the 12 bands aligned, L2 normalisation and wavelength on the x axis. This is the Week 2 milestone: it shows that cube and signature talk about the same band, and incidentally that neither pixel follows kaolinite's B11 → B12 drop. |

#### Detection: pending

`algorithms/sam.py` is implemented and tested, but nothing runs it over the
scene yet: `pipeline.py` raises `NotImplementedError` and validation against
SERNAGEOMIN mapping (`validation/`) is scaffolding. On top of that, the
threshold set in `configs/tamarugal_kaolinite.yaml` would leave no pixel below
it over the AOI window where it was measured, and it stays as is pending a
calibration criterion
(`docs/en/technical_decisions.md`, section 7). Until that exists, this
repository reports no detected kaolinite.

## License

MIT — see [LICENSE](LICENSE).
