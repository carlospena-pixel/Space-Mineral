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

# Construir la verdad de terreno desde la cartografía SERNAGEOMIN
python scripts/construir_verdad_terreno.py

# Validar contra cartografía: tabla de métricas + curva ROC en outputs/figures/
python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif \
    outputs/maps/ground_truth.tif --figura
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
(`outputs/maps/ground_truth.tif`), así que la pregunta se puede contar.

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

#### Las métricas

Desde la Semana 6 el conteo anterior tiene métricas detrás. Las produce

```bash
python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif outputs/maps/ground_truth.tif --figura
```

que descarta los 3.756.783 píxeles ambiguos y los 250 sin dato, y calcula sobre
los que quedan:

| | valor |
|---|---|
| píxeles evaluables | 242.967 |
| F1 (umbral 0,10) | 0,0000 |
| IoU (umbral 0,10) | 0,0000 |
| kappa de Cohen | 0,0000 |
| AUC de la curva ROC | 0,2403 |

**El resultado es negativo y no se maquilla.** Los tres ceros son el mismo
hecho contado tres veces: con el umbral del config no hay ni una detección
dentro de las clases evaluables, así que no hay nada que acertar. El número
que informa es el AUC, porque no depende del umbral: **0,2403 está por debajo
de 0,5**, y eso no significa que el detector no separe, sino que **separa al
revés**. La mediana del ángulo es 0,3288 rad dentro del positivo y 0,2712 rad
dentro del negativo: las unidades que la cartografía declara compatibles con
alteración se parecen *menos* a la caolinita de laboratorio que las que declara
no candidatas.

`outputs/figures/roc_kaolinite_sam.png` muestra las dos cosas a la vez: la
curva por debajo de la diagonal y las dos distribuciones que lo explican, con
el umbral de 0,1 rad cayendo a la izquierda de ambas sin tocar ninguna.

Ninguna calibración rescata esto. El umbral que maximiza el índice de Youden es
0,4467 rad y consigue J = 0,0034 —separación indistinguible de cero—, y el que
maximiza F1 es 0,4492 rad, que detecta 242.276 de los 242.967 píxeles: es el
clasificador que dice «sí» a todo, cuyo F1 sería 0,3455 de todos modos. El
detalle y las hipótesis están en
[docs/es/decisiones_tecnicas.md](docs/es/decisiones_tecnicas.md), secciones 7
y 11. **El `angle_threshold_rad` del config sigue en 0,1**: ahora existe el
criterio de calibración que faltaba, y lo que dice es que ningún umbral de este
mapa separa las clases.

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

# Build the ground-truth layer from SERNAGEOMIN mapping
python scripts/construir_verdad_terreno.py

# Validate against the mapping: metrics table + ROC curve in outputs/figures/
python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif \
    outputs/maps/ground_truth.tif --figura
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
the question can be counted.

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

##### The metrics

Since Week 6 the count above has metrics behind it. They are produced by

```bash
python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif outputs/maps/ground_truth.tif --figura
```

which discards the 3,756,783 ambiguous pixels and the 250 with no data, and
computes over what is left:

| | value |
|---|---|
| evaluable pixels | 242,967 |
| F1 (threshold 0.10) | 0.0000 |
| IoU (threshold 0.10) | 0.0000 |
| Cohen's kappa | 0.0000 |
| ROC curve AUC | 0.2403 |

**The result is negative and is not dressed up.** The three zeros are the same
fact counted three times: at the config threshold there is not a single
detection inside the evaluable classes, so there is nothing to get right. The
informative number is the AUC, because it does not depend on the threshold:
**0.2403 sits below 0.5**, which does not mean the detector fails to separate
— it means it **separates the wrong way round**. The median angle is 0.3288 rad
inside the positive class and 0.2712 rad inside the negative one: the units the
mapping declares compatible with alteration resemble laboratory kaolinite
*less* than the ones it declares non-candidates.

`outputs/figures/roc_kaolinite_sam.png` shows both at once: the curve below the
diagonal, and the two distributions that explain it, with the 0.1 rad threshold
falling to the left of both without touching either.

No calibration rescues this. The threshold maximising the Youden index is
0.4467 rad and reaches J = 0.0034 — separation indistinguishable from zero —
and the one maximising F1 is 0.4492 rad, which detects 242,276 of the 242,967
pixels: it is the classifier that says "yes" to everything, whose F1 would be
0.3455 anyway. The detail and the hypotheses are in
[docs/en/technical_decisions.md](docs/en/technical_decisions.md), sections 7
and 11. **The config's `angle_threshold_rad` stays at 0.1**: the calibration
criterion that was missing now exists, and what it says is that no threshold on
this map separates the classes.

## License

MIT — see [LICENSE](LICENSE).
