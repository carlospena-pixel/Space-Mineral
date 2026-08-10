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

# Correr un experimento: deja el GeoTIFF en outputs/maps/ y el heatmap en outputs/figures/
python scripts/run_pipeline.py --config configs/tamarugal_kaolinite.yaml

# Validar contra cartografía: todavía no, scripts/evaluate.py es andamiaje (etapa 9)
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

Lo verificado hasta hoy es el preprocesamiento —la escena queda recortada,
remuestreada, en reflectancia y con su máscara de validez— y el mapa de
similitud espectral que produce el pipeline de extremo a extremo. **Ese mapa no
es una detección de caolinita**: mide distancia angular contra una firma de
laboratorio, y sin validación contra cartografía no hay forma de saber cuánto
de lo que se parece es el mineral (ver [Detección](#detección-un-mapa-de-ángulos-sin-validar)
más abajo). El estado etapa por etapa está en
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
| `kaolinite_sam_angle.png` | El hito de la Semana 3: el mapa de ángulo espectral del AOI completo con los ejes en UTM, al lado del histograma de los 3.999.908 ángulos válidos. Es la evidencia de coherencia espectral: la distribución tiene una moda marcada en 0,27 rad y una cola hacia los ángulos bajos, no la campana simétrica que daría el ruido, y el mapa dibuja la red de drenaje y el piedemonte, no manchas al azar. |

### Detección: un mapa de ángulos sin validar

`algorithms/sam.py` está implementado y endurecido: valida sus entradas y lanza
`ValueError` ante un cubo y una firma con distinto número de bandas o ante una
referencia degenerada, tolera los `NaN` del cubo enmascarado sin propagarlos, y
su fórmula está contrastada término a término contra el documento 05 del
proyecto. Los ángulos están verificados contra casos cuyo valor exacto se conoce
por geometría, no por comparación con otra implementación
(`docs/es/decisiones_tecnicas.md`, sección 8).

`python scripts/run_pipeline.py --config configs/tamarugal_kaolinite.yaml`
corre de extremo a extremo y produce `outputs/maps/kaolinite_sam_angle.tif`
(GeoTIFF `float32`, EPSG:32719, `NaN` como nodata) más el heatmap de arriba.
Medido sobre el AOI completo, con las 9 bandas de `SAM_BANDS`:

| | ángulo (rad) |
|---|---|
| mínimo | 0,0723 |
| percentil 1 | 0,2055 |
| mediana | 0,2742 |
| máximo | 0,6971 |

Barrido de umbrales, sobre 3.999.908 píxeles válidos:

| umbral (rad) | píxeles | % del AOI válido |
|---|---|---|
| 0,05 | 0 | 0,000 % |
| 0,08 | 5 | 0,000 % |
| 0,10 | 62 | 0,002 % |
| 0,15 | 4.513 | 0,113 % |
| 0,20 | 30.885 | 0,772 % |

**Nada de esto es caolinita detectada.** Son 62 píxeles sueltos de 4 millones
bajo el umbral que fija el config, y el ángulo espectral mide parecido con una
firma de laboratorio, no presencia de un mineral: cualquier superficie que en
9 bandas se parezca cae igual de bajo. La validación contra cartografía de
SERNAGEOMIN (`validation/`) sigue siendo andamiaje, así que no hay con qué
estimar cuántos de esos píxeles son el mineral. El umbral `0.1` tampoco se
cambia: espera un criterio de calibración y no otro número elegido a ojo
(`docs/es/decisiones_tecnicas.md`, sección 7, donde la misma medición sobre una
ventana de 256 × 256 px daba 0 de 65.536 píxeles).

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

python scripts/run_pipeline.py --config configs/tamarugal_kaolinite.yaml
```

`data/` is not versioned; see `docs/en/pipeline.md` for how to obtain it.

### Results

What is verified today is the preprocessing — the scene is cropped, resampled,
converted to reflectance and paired with its validity mask — plus the spectral
similarity map the pipeline produces end to end. **That map is not a kaolinite
detection**: it measures angular distance against a laboratory signature, and
without validation against geological mapping there is no way to tell how much
of what resembles the mineral actually is it (see
[Detection](#detection-an-unvalidated-angle-map) below). The stage-by-stage
status is in [docs/en/pipeline.md](docs/en/pipeline.md).

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
| `kaolinite_sam_angle.png` | The Week 3 milestone: the spectral angle map of the full AOI with UTM axes, next to the histogram of the 3,999,908 valid angles. It is the spectral-coherence evidence: the distribution has a sharp mode at 0.27 rad and a tail towards low angles rather than the symmetric bell noise would give, and the map traces the drainage network and the piedmont, not random blotches. |

#### Detection: an unvalidated angle map

`algorithms/sam.py` is implemented and hardened: it validates its inputs and
raises `ValueError` on a cube and a signature with different band counts or on a
degenerate reference, it tolerates `NaN` from the masked cube without
propagating them, and its formula has been checked term by term against the
project's document 05. The angles are verified against cases whose exact value
is known by geometry, not by comparison with another implementation
(`docs/en/technical_decisions.md`, section 8).

`python scripts/run_pipeline.py --config configs/tamarugal_kaolinite.yaml` runs
end to end and produces `outputs/maps/kaolinite_sam_angle.tif` (`float32`
GeoTIFF, EPSG:32719, `NaN` as nodata) plus the heatmap above. Measured over the
full AOI with the 9 bands of `SAM_BANDS`:

| | angle (rad) |
|---|---|
| minimum | 0.0723 |
| 1st percentile | 0.2055 |
| median | 0.2742 |
| maximum | 0.6971 |

Threshold sweep, over 3,999,908 valid pixels:

| threshold (rad) | pixels | % of valid AOI |
|---|---|---|
| 0.05 | 0 | 0.000 % |
| 0.08 | 5 | 0.000 % |
| 0.10 | 62 | 0.002 % |
| 0.15 | 4,513 | 0.113 % |
| 0.20 | 30,885 | 0.772 % |

**None of this is detected kaolinite.** It is 62 scattered pixels out of 4
million below the threshold the config sets, and the spectral angle measures
resemblance to a laboratory signature, not the presence of a mineral: any
surface that looks similar across 9 bands scores just as low. Validation
against SERNAGEOMIN mapping (`validation/`) is still scaffolding, so there is
nothing to estimate how many of those pixels are the mineral. The `0.1`
threshold is not changed either: it awaits a calibration criterion rather than
another number picked by eye (`docs/en/technical_decisions.md`, section 7,
where the same measurement over a 256 × 256 px window gave 0 out of 65,536).

## License

MIT — see [LICENSE](LICENSE).
