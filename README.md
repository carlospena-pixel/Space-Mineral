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

# Alternativa con venv: el entorno local está construido con Python 3.13.
# Para reconstruirlo desde cero (borrar .venv y volver a instalar):
#   py -3.13 -m venv .venv
#   .venv\Scripts\python.exe -m pip install -e ".[dev]"
# No uses `python -m venv`: toma la primera versión del PATH, que puede no ser
# la 3.13 y deja site-packages incoherente con el intérprete.

# Paquete instalable en modo editable
pip install -e ".[dev]"
pre-commit install

# Correr un experimento: deja el GeoTIFF en outputs/maps/ y el heatmap en outputs/figures/
python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml

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
| Tile / CRS | `T19KDT` (distrito Cerro Colorado, Precordillera de Tarapacá) / EPSG:32719 |
| AOI | ventana `col_off=2700, row_off=650, 2000 × 2000` px a 20 m, o sea **40 × 40 km** |
| Extensión | E 453.960–493.960 / N 7.747.040–7.787.040 (EPSG:32719) |
| Cubo | `(12, 2000, 2000)` `float32`, reflectancia en `[0, 1]`, baseline `05.11` |
| Suelo desnudo (SCL 5) | **99,8085 %** del AOI |
| Píxeles válidos | **99,8484 %**: 3.993.936 de 4.000.000, o sea 6.064 descartados |

Las dos últimas cifras salen de `Scene.meta["scl_summary"]` y las imprime
`python scripts/construir_scene.py`. Son la condición que se buscaba al elegir
la zona: desierto despejado, sin nubes ni vegetación que tapen la superficie
que se quiere medir. Lo descartado es casi todo sombra topográfica
(0,1505 % del AOI): la ventana entra en la Precordillera y tiene relieve,
a diferencia de la ventana anterior sobre la pampa plana.

**El AOI se movió en la Semana 5.** La ventana anterior
(`col_off=1000, row_off=1000`) caía íntegra sobre el relleno sedimentario
de la Pampa del Tamarugal, sin una sola unidad con alteración hidrotermal
cartografiada, así que el criterio E3 del plan —«las detecciones se
concentran preferentemente en zonas de alteración documentadas»— no se
podía ni formular. La ventana nueva se desplaza al noreste para incluir el
distrito de pórfido cuprífero Cerro Colorado. El detalle está en
[docs/es/decisiones_tecnicas.md](docs/es/decisiones_tecnicas.md),
sección 10.

### Figuras (`outputs/figures/`)

| Figura | Qué muestra |
|---|---|
| `scene_rgb.png` | El AOI en color verdadero (B4/B3/B2) con realce por percentiles 2–98 banda a banda. Sirve para ubicarse: es la referencia visual de dónde caen las demás figuras. |
| `mascara_scl.png` | La clasificación SCL del AOI con su leyenda, al lado de la máscara de validez que sale de ella. Es la evidencia de las cifras de la tabla anterior: se ve que lo descartado son 6.064 píxeles de sombra topográfica en el relieve del este, no una región tapada por nubes. |
| `kaolinite_signature.png` | La firma de referencia de la caolinita (USGS splib07, muestra KGa-1) en las 12 bandas del contrato, con la caída B11 → B12 del rasgo de absorción Al–OH resaltada. El eje x es el índice de banda: es la figura anterior a `plot_spectra`. |
| `kaolinite_signature_vs_pixel.png` | Esa misma firma superpuesta a dos píxeles reales de la **ventana de exploración de 256 × 256 px** del notebook (no del AOI completo): el de menor ángulo SAM de esa ventana —0,1701 rad— y el central como control. Con las 12 bandas alineadas, normalización L2 y el eje x en longitud de onda. Es el hito de la Semana 2: muestra que el cubo y la firma hablan de la misma banda, y de paso que el píxel graficado no reproduce la caída **pronunciada** de la caolinita entre B11 y B12 (razón 0,953 contra 0,507 de la firma USGS): desciende, pero apenas. |
| `kaolinite_sam_angle.png` | El hito de la Semana 3: el mapa de ángulo espectral del AOI completo con los ejes en UTM, al lado del histograma de los 3.993.936 ángulos válidos. La distribución **no** es simétrica —la asimetría es +0,55 y la cola larga va hacia los ángulos **altos**—. En el extremo bajo hay un exceso, pero modesto: 0,1 rad está a 4,3 desviaciones estándar bajo la media, donde una gaussiana daría 40 píxeles en 4 millones. Hay 131, o sea unas 3 veces el ruido. Sobre el AOI anterior esa razón era de 143 veces; la diferencia no es que el detector empeorara sino que este AOI tiene mucha más variedad litológica y su distribución de ángulos es más ancha. |

### Detección: un mapa de ángulos sin validar

`algorithms/sam.py` está implementado y endurecido: valida sus entradas y lanza
`ValueError` ante un cubo y una firma con distinto número de bandas o ante una
referencia degenerada, tolera los `NaN` del cubo enmascarado sin propagarlos, y
su fórmula está contrastada término a término contra el documento 05 del
proyecto. Los ángulos están verificados contra casos cuyo valor exacto se conoce
por geometría, no por comparación con otra implementación
(`docs/es/decisiones_tecnicas.md`, sección 8).

`python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml`
corre de extremo a extremo y produce `outputs/maps/kaolinite_sam_angle.tif`
(GeoTIFF `float32`, EPSG:32719, `NaN` como nodata) más el heatmap de arriba.
Medido sobre el AOI completo, con las 9 bandas de `SAM_BANDS`:

| | ángulo (rad) |
|---|---|
| mínimo | 0,0662 |
| percentil 1 | 0,2004 |
| mediana | 0,2795 |
| máximo | 0,6859 |

Barrido de umbrales, sobre 3.993.936 píxeles válidos:

| umbral (rad) | píxeles | % del AOI válido |
|---|---|---|
| 0,05 | 0 | 0,000 % |
| 0,08 | 28 | 0,001 % |
| 0,10 | 131 | 0,003 % |
| 0,15 | 1.482 | 0,037 % |
| 0,20 | 38.672 | 0,968 % |

**Nada de esto es caolinita detectada.** Son 131 píxeles sueltos de 4 millones
bajo el umbral que fija el config, y el ángulo espectral mide parecido con una
firma de laboratorio, no presencia de un mineral: cualquier superficie que en
9 bandas se parezca cae igual de bajo. El umbral `0.1` no se cambia: espera un
criterio de calibración y no otro número elegido a ojo
(`docs/es/decisiones_tecnicas.md`, sección 7).

#### Dónde caen esas 131 detecciones

Desde la Semana 4 existe la capa de verdad de terreno
(`outputs/maps/ground_truth.tif`), así que la pregunta se puede contar. Es un
conteo, no una métrica: F1, IoU y ROC/AUC siguen sin implementarse.

| clase de la verdad de terreno | píxeles del AOI | detecciones a 0,1 rad |
|---|---|---|
| positivo (alteración cartografiada) | 50.773 (1,27 %) | **0** |
| negativo (no candidata) | 192.444 (4,81 %) | **0** |
| ambiguo (sin clasificar) | 3.756.783 (93,92 %) | **131** |

**Las 131 detecciones caen fuera de toda unidad de alteración cartografiada.**
Y no están repartidas: **130 de las 131 caen sobre una sola unidad**,
`Depositos antropicos, botaderos de mina` —los botaderos de la mina Cerro
Colorado, que ocupan 16,79 km², el 1,05 % del AOI—. La 131 cae sobre una
facies conglomerádica de la Formación Altos de Pica.

La lectura más simple es que el SAM está encontrando roca molida y recién
expuesta, sin la costra ni el barniz del desierto que cubren la superficie
natural, y que en esa roca hay arcilla. Es un resultado espacialmente
coherentísimo —130 aciertos en el 1 % del área— pero **no** valida la
detección de alteración *in situ*, que es lo que pide E3: dentro de las
unidades declaradas positivo el ángulo mínimo es 0,1541 rad, muy por encima
del umbral. Cómo se clasifican los botaderos decide por completo la respuesta
a E3, y por eso está declarado y argumentado en
`configs/verdad_terreno_cerro_colorado.yaml` en vez de resolverse por omisión.

### Validación: qué se puede medir sin verdad de terreno

La biblioteca de métricas (`validation/metrics.py`) está implementada y
verificada: matriz de confusión, precisión, recall, F1, IoU, kappa, curva ROC y
AUC, enriquecimiento espacial y acuerdo entre máscaras. Los valores esperados de
los tests salen de una matriz de confusión escrita a mano y calculada en papel,
y se contrastan además contra `scikit-learn` como oráculo independiente.

El barrido de umbral y el contraste con líneas base se corren así:

```bash
python scripts/sweep_threshold.py --config configs/tamarugal_kaolinite.yaml
```

**Los tres criterios de validación, y cuál se puede cerrar hoy:**

| Criterio | Qué pregunta | Estado |
|---|---|---|
| E3 — enriquecimiento espacial | ¿Las detecciones caen en zonas de alteración documentadas? | **BLOQUEADO POR TRACK A** |
| E4 — métricas contra verdad | ¿Cuántas detecciones son correctas? | **BLOQUEADO POR TRACK A** |
| E5 — contraste con líneas base | ¿La detección coincide con una segunda opinión más que el azar? | Medible |

**E3 y E4 están bloqueados y no por falta de código.** Las funciones existen y
están probadas con datos sintéticos; lo que no existe es la capa de verdad de
terreno. `data/external/` solo contiene la firma USGS de caolinita y
`validation/geology.py` sigue siendo dos `NotImplementedError` (Track A). Y hay
un problema anterior a ese: el AOI es `T19KDT`, Pampa del Tamarugal, y la Carta
Calama 1:50.000 que el plan original fijaba como verdad de terreno **no cubre
ese cuadrante**. Implementar `geology.py` no lo resuelve solo.

`sweep_threshold.py` corre igual sin verdad de terreno: calcula lo que no la
necesita y declara por nombre qué quedó sin medir. Las columnas de E4 del CSV
quedan **vacías, no en cero**, porque un cero se leería como una medición.

**E5 sí se puede medir, y las cifras están pendientes de correr.** El contraste
compara tres máscaras a la misma tasa de positivos —SAM bajo el umbral del
config, el clay ratio B11/B12 por percentil, y una aleatoria de semilla fija— y
la única afirmación defendible que produce es *«SAM coincide con el clay ratio
más / igual / menos que el azar»*. **Eso no dice que SAM detecte caolinita**: el
clay ratio no es verdad de terreno, es una segunda opinión sobre las mismas dos
bandas de la misma imagen, y los dos criterios pueden equivocarse juntos. Las
cifras concretas se publican aquí cuando el barrido corra sobre el mapa
regenerado; no se rellenan a mano mientras tanto.

Una limitación que vale para todo lo anterior y que no se arregla con código:
los píxeles vecinos no son independientes. El **tamaño de muestra efectivo es
mucho menor que los 3.999.908 píxeles válidos**, así que un F1 o un AUC por
píxel exagera la significancia (`docs/es/decisiones_tecnicas.md`, sección 11).

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

# venv alternative: the local environment is built with Python 3.13. To rebuild
# it from scratch, delete .venv and run:
#   py -3.13 -m venv .venv
#   .venv\Scripts\python.exe -m pip install -e ".[dev]"
# Do not use `python -m venv`: it picks the first version on PATH, which may not
# be 3.13 and leaves site-packages inconsistent with the interpreter.

pip install -e ".[dev]"
pre-commit install

python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml
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
| Tile / CRS | `T19KDT` (Cerro Colorado district, Tarapacá Precordillera, Chile) / EPSG:32719 |
| AOI | window `col_off=2700, row_off=650, 2000 × 2000` px at 20 m, i.e. **40 × 40 km** |
| Extent | E 453,960–493,960 / N 7,747,040–7,787,040 (EPSG:32719) |
| Cube | `(12, 2000, 2000)` `float32`, reflectance in `[0, 1]`, baseline `05.11` |
| Bare soil (SCL 5) | **99.8085 %** of the AOI |
| Valid pixels | **99.8484 %**: 3,993,936 out of 4,000,000, i.e. 6,064 discarded |

The last two figures come from `Scene.meta["scl_summary"]` and are printed by
`python scripts/construir_scene.py`. They are the condition the study area was
chosen for: clear desert, with no cloud or vegetation covering the surface to
be measured. What gets discarded is almost entirely topographic shadow
(0.1505 % of the AOI): the window reaches into the Precordillera and has
relief, unlike the previous window over the flat pampa.

**The AOI moved in Week 5.** The previous window
(`col_off=1000, row_off=1000`) fell entirely on the sedimentary fill of the
Pampa del Tamarugal, without a single mapped hydrothermal alteration unit, so
criterion E3 of the plan — "detections concentrate preferentially in
documented alteration zones" — could not even be stated. The new window
shifts northeast to take in the Cerro Colorado porphyry copper district. The
details are in
[docs/en/technical_decisions.md](docs/en/technical_decisions.md), section 10.

#### Figures (`outputs/figures/`)

| Figure | What it shows |
|---|---|
| `scene_rgb.png` | The AOI in true colour (B4/B3/B2) with a 2–98 percentile stretch applied band by band. It is the visual reference for where everything else sits. |
| `mascara_scl.png` | The AOI's SCL classification with its legend, next to the validity mask derived from it. It is the evidence behind the table above: what gets discarded is 6,064 pixels of topographic shadow over the relief in the east, not a region hidden by cloud. |
| `kaolinite_signature.png` | The kaolinite reference signature (USGS splib07, sample KGa-1) across the 12 contract bands, highlighting the B11 → B12 drop of the Al–OH absorption feature. The x axis is the band index: this is the figure that predates `plot_spectra`. |
| `kaolinite_signature_vs_pixel.png` | That same signature overlaid on two real pixels from the notebook's **256 × 256 px exploration window** (not the full AOI): that window's lowest SAM angle pixel — 0.1701 rad — and the central one as a control. With the 12 bands aligned, L2 normalisation and wavelength on the x axis. This is the Week 2 milestone: it shows that cube and signature talk about the same band, and incidentally that the plotted pixel does not reproduce kaolinite's **steep** B11 → B12 drop (ratio 0.953 against the USGS signature's 0.507): it does descend, but barely. |
| `kaolinite_sam_angle.png` | The Week 3 milestone: the spectral angle map of the full AOI with UTM axes, next to the histogram of the 3,993,936 valid angles. The distribution is **not** symmetric — skewness is +0.55 and the long tail runs towards **high** angles. There is an excess at the low end, but a modest one: 0.1 rad sits 4.3 standard deviations below the mean, where a Gaussian would give 40 pixels in 4 million. There are 131, about 3 times the noise. Over the previous AOI that ratio was 143 times; the difference is not that the detector got worse but that this AOI holds far more lithological variety and its angle distribution is correspondingly wider. |

#### Detection: an unvalidated angle map

`algorithms/sam.py` is implemented and hardened: it validates its inputs and
raises `ValueError` on a cube and a signature with different band counts or on a
degenerate reference, it tolerates `NaN` from the masked cube without
propagating them, and its formula has been checked term by term against the
project's document 05. The angles are verified against cases whose exact value
is known by geometry, not by comparison with another implementation
(`docs/en/technical_decisions.md`, section 8).

`python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml`
runs end to end and produces `outputs/maps/kaolinite_sam_angle.tif` (`float32`
GeoTIFF, EPSG:32719, `NaN` as nodata) plus the heatmap above. Measured over the
full AOI with the 9 bands of `SAM_BANDS`:

| | angle (rad) |
|---|---|
| minimum | 0.0662 |
| 1st percentile | 0.2004 |
| median | 0.2795 |
| maximum | 0.6859 |

Threshold sweep, over 3,993,936 valid pixels:

| threshold (rad) | pixels | % of valid AOI |
|---|---|---|
| 0.05 | 0 | 0.000 % |
| 0.08 | 28 | 0.001 % |
| 0.10 | 131 | 0.003 % |
| 0.15 | 1,482 | 0.037 % |
| 0.20 | 38,672 | 0.968 % |

**None of this is detected kaolinite.** It is 131 scattered pixels out of 4
million below the threshold the config sets, and the spectral angle measures
resemblance to a laboratory signature, not the presence of a mineral: any
surface that looks similar across 9 bands scores just as low. The `0.1`
threshold is not changed either: it awaits a calibration criterion rather than
another number picked by eye (`docs/en/technical_decisions.md`, section 7).

##### Where those 131 detections fall

Since Week 4 the ground-truth layer exists (`outputs/maps/ground_truth.tif`), so
the question can be counted. This is a count, not a metric: F1, IoU and ROC/AUC
remain unimplemented.

| ground-truth class | AOI pixels | detections at 0.1 rad |
|---|---|---|
| positive (mapped alteration) | 50,773 (1.27 %) | **0** |
| negative (non-candidate) | 192,444 (4.81 %) | **0** |
| ambiguous (unclassified) | 3,756,783 (93.92 %) | **131** |

**All 131 detections fall outside every mapped alteration unit.** And they are
not scattered: **130 of the 131 land on a single unit**, `Depositos antropicos,
botaderos de mina` — the waste dumps of the Cerro Colorado mine, covering
16.79 km², 1.05 % of the AOI. The 131st falls on a conglomeratic facies of the
Altos de Pica Formation.

The simplest reading is that SAM is finding crushed, freshly exposed rock —
without the desert crust and varnish that coat the natural surface — and that
this rock contains clay. It is an extremely coherent spatial result — 130 hits
inside 1 % of the area — but it does **not** validate detection of *in situ*
alteration, which is what E3 asks for: within the units declared positive the
minimum angle is 0.1541 rad, well above the threshold. How the waste dumps get
classified decides the answer to E3 outright, which is why it is declared and
argued in `configs/verdad_terreno_cerro_colorado.yaml` rather than settled by
omission.

#### Validation: what can be measured without ground truth

The metrics library (`validation/metrics.py`) is implemented and verified:
confusion matrix, precision, recall, F1, IoU, kappa, ROC curve and AUC, spatial
enrichment and agreement between masks. The expected values in the tests come
from a confusion matrix written out by hand and computed on paper, and are
additionally checked against `scikit-learn` as an independent oracle.

The threshold sweep and the baseline contrast are run with:

```bash
python scripts/sweep_threshold.py --config configs/tamarugal_kaolinite.yaml
```

**The three validation criteria, and which one can be closed today:**

| Criterion | What it asks | Status |
|---|---|---|
| E3 — spatial enrichment | Do detections fall inside documented alteration zones? | **BLOCKED BY TRACK A** |
| E4 — metrics against ground truth | How many detections are correct? | **BLOCKED BY TRACK A** |
| E5 — contrast against baselines | Does the detection agree with a second opinion more than chance? | Measurable |

**E3 and E4 are blocked, and not for lack of code.** The functions exist and are
tested against synthetic data; what does not exist is the ground-truth layer.
`data/external/` only holds the USGS kaolinite signature and
`validation/geology.py` is still two `NotImplementedError` (Track A). And there
is a problem upstream of that: the AOI is `T19KDT`, Pampa del Tamarugal, and the
Carta Calama 1:50,000 that the original plan named as ground truth **does not
cover that quadrant**. Implementing `geology.py` does not resolve that on its
own.

`sweep_threshold.py` runs anyway without ground truth: it computes what does not
need it and names explicitly what was left unmeasured. The E4 columns of the CSV
are left **empty, not zero**, because a zero would read as a measurement.

**E5 can be measured, and the figures are pending a run.** The contrast compares
three masks at the same positive rate — SAM under the config threshold, the
B11/B12 clay ratio by percentile, and a random one with a fixed seed — and the
only defensible claim it produces is *"SAM agrees with the clay ratio more / the
same as / less than chance"*. **That does not say SAM detects kaolinite**: the
clay ratio is not ground truth, it is a second opinion over the same two bands of
the same image, and the two criteria can be wrong together. The concrete figures
are published here once the sweep runs over the regenerated map; they are not
filled in by hand in the meantime.

One limitation that applies to all of the above and cannot be fixed in code:
neighbouring pixels are not independent. The **effective sample size is much
smaller than the 3,999,908 valid pixels**, so a per-pixel F1 or AUC overstates
significance (`docs/en/technical_decisions.md`, section 11).

## License

MIT — see [LICENSE](LICENSE).
