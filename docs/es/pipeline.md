# Pipeline

Este documento describe **el flujo**: qué se ejecuta, en qué orden, qué entra y
qué sale en cada etapa. Por qué cada decisión es la que es se justifica en
[decisiones_tecnicas.md](decisiones_tecnicas.md), y acá se enlaza en vez de
repetirlo.

## Estado de las etapas

| # | Etapa | Dónde vive | Estado |
|---|-------|------------|--------|
| 0 | Adquisición de la escena | `io/acquisition.py` | **Manual**: `download_scene()` es un stub |
| 1 | Localizar el producto y sus bandas | `io/raster_io.py` | Implementada |
| 2 | Leer el escalado del producto | `preprocessing/reflectance.py` | Implementada |
| 3 | Recortar al AOI y remuestrear a 20 m | `preprocessing/resampling.py` | Implementada |
| 4 | Escalar DN a reflectancia | `preprocessing/reflectance.py` | Implementada |
| 5 | Construir la máscara de validez | `preprocessing/masking.py` | Implementada |
| 6 | Entregar y serializar el `Scene` | `preprocessing/scene_builder.py`, `io/raster_io.py` | Implementada |
| 7 | Firma de referencia y comparación visual | `spectral/endmembers.py`, `visualization/spectra.py` | Implementada |
| 8 | Algoritmo de detección | `algorithms/sam.py`, `pipeline.py` | Implementada |
| 9 | Validación contra cartografía | `validation/` | **Parcial**: la capa de verdad existe; faltan las métricas |
| 10 | Visualización y exportación de resultados | `visualization/maps.py`, `io/raster_io.py` | Implementada |

Las etapas 1 a 6 son el preprocesamiento que cerró la Semana 2 y las encadena
una sola función, `build_scene_from_safe()`. Las etapas 7, 8 y 10 las encadena
`run_pipeline(config)`, que cerró la Semana 3: desde el YAML del experimento
hasta el GeoTIFF y el heatmap, sin pasos manuales. La única etapa sin
implementar es la 9.

## El flujo implementado: de `.SAFE` a `Scene`

```
data/raw/<escena>.SAFE
   |
   |-- find_safe_dir(root) ................ ruta del producto
   |-- read_l2a_scaling(safe_dir) ......... baseline, offset, quantification
   |-- find_band_file(safe_dir, banda) .... ruta del .jp2 + resolución nativa
   |
   v
read_band_on_grid(ruta, bounds, target_shape, resampling_for(...))
   |      recorta a la ventana del AOI y devuelve la banda ya en 20 m
   |
   +---- por cada banda de BAND_ORDER ----+       +---- banda SCL ----+
   |                                      |       |                   |
   v                                      |       v                   |
dn_to_reflectance(DN, offset, quant.)     |   build_cloud_mask(SCL, clases)
   |      float32 en [0,1], NaN sin dato  |       |   True = píxel válido
   v                                      |       v
cube (12, alto, ancho) -------------------+--> mask = mask_scl & ~isnan(cube).any(0)
   |
   v
Scene(cube, band_names, transform, crs, mask, meta)
   |
   +-- save_scene ---> data/interim/scene.npz
```

### 0. Adquisición de la escena

**Hoy es manual.** `io/acquisition.py::download_scene()` y su CLI
`scripts/download_scene.py` existen como andamiaje y levantan
`NotImplementedError`. El producto se descarga a mano desde el
[Copernicus Data Space](https://dataspace.copernicus.eu/) y se descomprime en
`data/raw/`, de modo que quede la carpeta
`S2B_MSIL2A_..._T19KDT_....SAFE` completa (el `.SAFE` es un directorio, no un
archivo). Nada de `data/` se versiona.

La única excepción es `data/external/`, donde vive la firma de referencia de la
caolinita (`S07SNTL2_Kaolinite_CM9_BECKb_AREF.txt`, de la USGS Spectral
Library 7): es un `.txt` chico y sí se versiona, para que el equipo pueda
correr los tests de `spectral/` sin descargar nada.

**Entra**: nada automatizado. **Sale**: `data/raw/<escena>.SAFE`.

### 1. Localizar el producto y sus bandas

**Funciones**: `find_safe_dir(root)` y `find_band_file(safe_dir, band, prefer)`,
en `io/raster_io.py`.

**Entra**: un directorio raíz (`data/raw/`) y un nombre canónico de banda
(`"B1"`, `"B8A"`, `"SCL"`).

**Sale**: la ruta del `.SAFE`, y por banda la ruta del `.jp2` junto a su
**resolución nativa** en metros.

**La decisión no obvia**: `find_band_file` no asume dónde está cada banda, la
busca en las carpetas `R20m`, `R10m` y `R60m` en ese orden y devuelve la
primera que exista. Un producto L2A publica varias bandas remuestreadas a
varias resoluciones, y la resolución nativa —la única que no pasó por un
remuestreo de ESA— depende de la banda: B8 solo existe a 10 m, B9 solo a 60 m,
el resto está a 20 m. Preferir siempre 20 m evita remuestrear lo que ya está en
la grilla objetivo, y devolver la resolución encontrada es lo que le permite a
la etapa 3 elegir el método de remuestreo correcto. La resolución de cada banda
queda registrada en `Scene.meta["bands_source"]`.

La traducción entre el nombre canónico sin cero (`B1`) y el token del archivo
con cero (`B01`) vive en `BAND_TOKEN`, generado desde `BAND_ORDER`
([decisiones técnicas §2](decisiones_tecnicas.md#band_order--12-bandas)).

### 2. Leer el escalado del producto

**Función**: `read_l2a_scaling(safe_dir)`, en `preprocessing/reflectance.py`.

**Entra**: la ruta del `.SAFE`.

**Sale**: `(baseline, offset, quantification)`. En esta escena:
`("05.11", -1000.0, 10000.0)`.

**La decisión no obvia**: los tres valores **se leen de `MTD_MSIL2A.xml`** y no
se fijan en el código. Dependen de con qué versión ESA procesó el producto, y
una escena reprocesada puede cambiarlos sin que cambie nada más; hardcodearlos
funciona hasta el día en que deja de funcionar y el error es un sesgo constante
en la reflectancia, no una excepción. Si el XML falta se usa el fallback
`("04.00", -1000.0, 10000.0)` con un `warnings.warn` explícito.

Por qué existe el offset y qué pasa si se aplica la fórmula antigua:
[decisiones técnicas §6](decisiones_tecnicas.md#6-reflectancia).

### 3. Recortar al AOI y remuestrear a 20 m

**Funciones**: `resampling_for(src_res_m, target_res_m, categorical)` y
`read_band_on_grid(path, bounds, target_shape, resampling, expected_crs)`, en
`preprocessing/resampling.py`. La ventana del AOI la resuelve antes
`_resolver_ventana()` en `scene_builder.py`.

**Entra**: la ruta del `.jp2`, los `bounds` del AOI en el CRS del tile
(EPSG:32719), la forma destino en píxeles y el método de remuestreo.

**Sale**: un arreglo 2D con la forma destino exacta y el dtype nativo del
archivo (enteros).

El AOI se puede pedir de tres formas: `None` usa `DEFAULT_AOI_WINDOW`
(`col_off=2700, row_off=650, 2000×2000` px a 20 m, o sea 40 × 40 km); una
`Window` se usa tal cual; un bbox WGS84 se reproyecta con `transform_bounds` y
se redondea a píxeles enteros. Si el AOI pedido no toca el tile es un
`ValueError`; si lo toca parcialmente se recorta con una advertencia.

**Las decisiones no obvias son dos**:

1. **El remuestreo ocurre en la lectura**, no sobre un `Scene` ya armado: se
   traduce el AOI a una ventana en la grilla nativa de cada banda y se le pide
   a GDAL que la entregue directamente con la forma destino. El cubo nace
   homogéneo a 20 m y nunca existe con bandas de resoluciones mezcladas.
2. **SCL se lee con `nearest` y nunca con `average`.** Es la única banda que se
   pide con `categorical=True`, y es lo que hace `scene_builder.py` al leerla.
   SCL es una etiqueta por píxel, no una medida: el promedio de «agua» (6) y
   «no clasificado» (7) da 6,5, que redondeado es «no clasificado» o «agua»
   según el azar del redondeo, y el promedio de «suelo desnudo» (5) y «nube de
   probabilidad alta» (9) da 7. Ninguna de esas clases estaba ahí. El error no
   levanta ninguna excepción: devuelve una máscara plausible y equivocada, que
   es la peor forma de estar mal. `resampling_for` lo resuelve antes de mirar
   las resoluciones, así que ni siquiera hay un camino en el que una banda
   categórica termine interpolada.

El detalle de qué método se usa en cada caso y la premisa que hace válido
recortar por coordenadas sin `warp`:
[decisiones técnicas §5](decisiones_tecnicas.md#5-remuestreo).

### 4. Escalar DN a reflectancia

**Función**: `dn_to_reflectance(dn_array, baseline, offset, quantification,
clip, nodata_dn)`, en `preprocessing/reflectance.py`.

**Entra**: la banda cruda en enteros (DN) que devolvió la etapa 3, más el
escalado que leyó la etapa 2.

**Sale**: la misma banda en `float32`, con reflectancia en `[0, 1]` y `NaN`
donde el producto no tenía dato.

**La decisión no obvia**: `DN == 0` pasa a `NaN` **antes** de escalar, no
después. El 0 es el valor de «sin dato» del producto; escalarlo con el offset
de -1000 daría -0,1, que el clip dejaría en 0,0: un valor perfectamente válido
y perfectamente falso, que contamina medias, percentiles y el realce de
contraste de las figuras sin dejar rastro.

### 5. Construir la máscara de validez

**Función**: `build_cloud_mask(scl_band, classes_to_mask)`, en
`preprocessing/masking.py`, con `DEFAULT_INVALID_CLASSES = [0, 1, 2, 3, 6, 8,
9, 10, 11]`.

**Entra**: la banda SCL ya recortada y remuestreada con `nearest` (etapa 3), y
la lista de clases a descartar.

**Sale**: una máscara booleana `(alto, ancho)` donde **`True` = píxel válido**.
Es el complemento de una máscara de nubes, pese al nombre de la función.

`scene_builder` la combina con un segundo criterio antes de guardarla:

```python
mask_final = mask_scl & ~np.isnan(cube).any(axis=0)
```

El segundo término atrapa los bordes del tile, donde SCL puede decir «suelo»
pero la banda no tiene señal.

**La decisión no obvia**: el cubo **se entrega sin enmascarar**. La validez
viaja aparte, en `Scene.mask`, y quien decide aplicarla es el consumidor. Un
píxel que se convirtió en `NaN` no se recupera sin releer el producto, mientras
que aplicar la máscara después siempre se puede; y hay consumidores legítimos
del cubo completo —estadísticas globales, un método que necesite el vecindario
entero—. El paso explícito para aplicarla es `apply_mask(cube, mask)`, que
devuelve una copia con `NaN` en todas las bandas de los píxeles inválidos.

Qué clase se descarta y por qué:
[decisiones técnicas §4](decisiones_tecnicas.md#4-máscara-de-validez).

### 6. Entregar y serializar el `Scene`

**Función**: `build_scene_from_safe(root, band_names, aoi, invalid_scl_classes,
verbose)`, en `preprocessing/scene_builder.py`. Es la que encadena las etapas 1
a 5.

**Entra**: el directorio con el `.SAFE`, las bandas pedidas (por defecto las 12
de `BAND_ORDER`) y el AOI.

**Sale**: un `Scene` con `cube` `(n_bandas, alto, ancho)` en `float32`,
`band_names`, `transform` del AOI recortado, `crs`, `mask` y `meta`.

`meta` registra de dónde salió el cubo: producto, tile, fecha de sensado,
baseline, offset, ventana del AOI, resolución nativa por banda, clases SCL
descartadas y la composición SCL del AOI. **Es documentación, no
configuración**: nada del pipeline toma de `meta` un parámetro que decida qué se
calcula. Se lee en dos lugares, y ninguno lo contradice: `_cache_coincide`
compara `meta["aoi_window"]` contra la ventana del config, donde lo único que
`meta` puede hacer es **vetar** el caché —nunca aporta el AOI, que siempre viene
del config—, y `_guardar_heatmap` lee `tile_id` y `sensing_date` para el título
de la figura, que es un uso cosmético y no entra en ningún cálculo
([decisiones técnicas §1.1](decisiones_tecnicas.md#11-scene--srcmineralmapioraster_iopy)).

`save_scene` / `load_scene` lo serializan a un único `.npz` —el cubo como
`float32`, la `transform` como sus 6 coeficientes, el CRS como WKT y `meta`
como JSON—. El JSON en vez de pickle es lo que permite cargar con
`allow_pickle=False`: abrir una escena nunca puede ejecutar código.

**El `.npz` no es reproducible byte a byte.** `meta` incluye `created_at`, así
que dos reconstrucciones del mismo AOI dan archivos con hash distinto aunque el
cubo sea idéntico. No afecta al criterio de reproducibilidad E1: el que tiene
que salir idéntico es el `.tif`, y sale. Se anota para que nadie use el hash del
`.npz` como identidad de contenido —es caché, no entregable, y no se versiona—.
El `created_at` se conserva a propósito: la procedencia del cubo vale más que un
hash que nadie compara.

### 7. Firma de referencia y comparación visual

**Funciones**: `get_reference_spectrum(mineral, band_order)`, en
`spectral/endmembers.py`, y `plot_spectra(signatures, band_order, normalize)`,
en `visualization/spectra.py`.

**Entra**: el nombre del mineral (`"kaolinite"`) y el orden de bandas del
consumidor —típicamente `scene.band_names`—.

**Sale**: un vector 1D de largo `len(band_order)`, alineado **posicionalmente**
con él.

**La decisión no obvia**: el consumidor fija el orden. La librería USGS tiene
el suyo (13 bandas, con B10) y el `Scene` tiene el suyo (12, sin B10); que la
conversión ocurra en un solo lugar y con el orden pedido explícitamente es lo
que evita que el SAM compare la reflectancia de B11 contra el valor de
referencia de B12 y devuelva un mapa impecablemente calculado y sin sentido.
Ese alineamiento está verificado en tres niveles
([decisiones técnicas §7](decisiones_tecnicas.md#resultado-de-la-verificación-de-alineamiento)).

## El flujo implementado: de `Config` a mapa

```
configs/cerro_colorado_kaolinite.yaml
   |
   |-- load_config(path) ................... Config (scene, aoi, mineral, algorithm, output)
   |
   v
run_pipeline(config)
   |
   |-- _normalizar_root_escena(scene.path) . directorio donde buscar el .SAFE
   |-- _resolver_aoi(aoi) .................. Window desde aoi.window_px
   |
   |   data/interim/scene.npz  --(si la ventana y las bandas calzan)-->  Scene
   |          ^                                                            |
   |          +--- si no: build_scene_from_safe(root, bands, aoi) ---------+
   |
   v
apply_mask(scene.cube, scene.mask)          NaN en los pixeles invalidos
   |
   +--> cube[indices de SAM_BANDS] .......... 9 bandas, no 12
   |
   |    get_reference_spectrum("kaolinite", band_order=SAM_BANDS)
   |                     |
   v                     v
_crear_detector(algorithm.name) -> Detector.predict(cube, reference)
   |
   v
mapa de angulos (alto, ancho), NaN donde ~scene.mask
   |
   +-- write_geotiff ---> outputs/maps/kaolinite_sam_angle.tif
   +-- plot_score_map --> outputs/figures/kaolinite_sam_angle.png
   +-- dict con rutas y estadisticas (lo que imprime la CLI)
```

### 8. Algoritmo de detección y su orquestador

**Funciones**: `SAM.predict(cube, reference)` y `threshold(angle_map,
max_angle)` en `algorithms/sam.py`; `run_pipeline(config)` en `pipeline.py`.

**Entra**: un `Config` cargado con `load_config`. De ahí salen la escena
(`scene.path`, `scene.bands`), el AOI (`aoi.window_px`), el mineral objetivo
(`mineral.target`), el algoritmo (`algorithm.name`) y las rutas de salida
(`output`).

**Sale**: el mapa de ángulo espectral en radianes `(alto, ancho)` con `NaN` en
los píxeles inválidos, más un `dict` con las rutas escritas y las estadísticas
del mapa. La función devuelve datos; imprimir es trabajo de la CLI.

**Las decisiones no obvias son cuatro**:

1. **El detector se instancia desde un registro**, no desde un `if`. `DETECTORS`
   mapea `algorithm.name` a la clase, y el resto del flujo no nombra a SAM.
   Agregar Random Forest es una clase en `algorithms/` y una entrada en ese
   diccionario ([decisiones técnicas §1.2](decisiones_tecnicas.md#12-detector--srcmineralmapalgorithmsbasepy)).
2. **`scene.path` se normaliza antes de buscar el producto.** Los configs
   apuntan a la carpeta `.SAFE` misma, pero `find_safe_dir(root)` busca
   carpetas `.SAFE` *bajo* `root`: pasarle la ruta del producto no encuentra
   nada y aborta con un `FileNotFoundError` que culpa a la escena de no estar
   descargada cuando está justo ahí. La normalización vive en el pipeline para
   no cambiarle el contrato a `find_safe_dir`, que ya tiene tests.
3. **El caché se verifica antes de usarse.** `data/interim/scene.npz` solo se
   reutiliza si su ventana y sus bandas son las que pide el config. Un caché
   que se usa a ciegas es el peor modo de fallo del proyecto: el pipeline corre
   entero, escribe un GeoTIFF válido y el mapa es de otro AOI. Lo que no se
   pueda verificar se trata como no coincidente y se relee el producto —tres
   minutos de lectura frente a un mapa equivocado—. `--no-cache` lo salta.
4. **`aoi.window_px` manda sobre `aoi.bbox`.** La ventana está expresada en la
   grilla de 20 m del tile, que es la definición exacta del AOI; el bbox en
   WGS84 es su equivalente redondeado. Si ganara el bbox, el recorte se
   correría unos píxeles sin que nada lo denunciara. Ésta es la etapa que
   estrena `window_px`: hasta la Semana 3 nadie la leía.

**El detector consume 9 bandas, no 12.** El `Scene` sigue naciendo con las 12 de
`BAND_ORDER` y el pipeline lo subconjunta a `SAM_BANDS` **por índice**, con el
mismo orden con que le pide la firma a `get_reference_spectrum`
([decisiones técnicas §2](decisiones_tecnicas.md#sam_bands--9-bandas-consumidas-por-el-detector-desde-la-semana-3)).

**Cero detecciones es un resultado, no un error.** El pipeline reporta cuántos
píxeles quedaron bajo `angle_threshold_rad` junto a un barrido de umbrales
(0,05 a 0,20 rad) y escribe el mapa de ángulos igualmente: el mapa es el
entregable, y el umbral espera un criterio de calibración. Sin ese barrido, un
resultado vacío no se distingue de un error de cálculo.

### 10. Visualización y exportación de resultados

**Funciones**: `write_geotiff(path, array, scene, band_descriptions)` en
`io/raster_io.py` y `plot_score_map(score_map, scene, title, p_low, p_high)` en
`visualization/maps.py`.

**Entra**: el mapa 2D que devolvió la etapa 8 y el `Scene` del que salió.

**Sale**: `outputs/maps/kaolinite_sam_angle.tif` (GeoTIFF `float32`, EPSG:32719,
`deflate`, `tiled`, `NaN` como nodata y la banda descrita) y
`outputs/figures/kaolinite_sam_angle.png` (mapa + histograma).

**Las decisiones no obvias son cuatro**:

1. **`write_geotiff` valida la forma espacial contra el `Scene`.** Escribir un
   mapa calculado sobre otra ventana produce un GeoTIFF impecable que se abre
   en cualquier SIG y cae sobre el terreno equivocado. Es el único modo de
   fallo de la función que no se nota, así que es un `ValueError` con las dos
   formas en el mensaje.
2. **No se escribe ningún tag propio** (fecha, usuario, ruta de origen): el
   archivo sale byte a byte idéntico en dos corridas seguidas, que es lo que
   permite comprobar la reproducibilidad comparando hashes. La trazabilidad ya
   viaja en `Scene.meta`.
3. **El nodata es `NaN` y no `0`.** Un ángulo de 0 rad es coincidencia perfecta
   con la firma: usarlo como centinela convertiría los píxeles enmascarados en
   las detecciones más fuertes del mapa.
4. **La figura son dos paneles.** El mapa dice *dónde*; el histograma dice *si
   hay algo que mirar*, y lo que hay que mirar en él es **si el extremo que
   interesa está sobrepoblado respecto de una campana**, no hacia dónde cae la
   cola larga. En este AOI la cola larga va hacia los ángulos **altos** —la
   asimetría es +0,76—, y aun así el histograma sostiene la coherencia
   espectral: 0,1 rad está a 5,2 desviaciones estándar bajo la media, donde una
   gaussiana daría 0,43 píxeles en 4 millones, y hay 62. El mapa solo no
   distingue un exceso así del ruido. La escala de color se recorta a los
   percentiles 2–98 y no al rango completo `[0, π]` —los ángulos del AOI
   completo ocupan de 0,07 a 0,70 rad—, los
   percentiles se calculan con `np.nanpercentile` (un solo `NaN` con
   `np.percentile` deja el panel plano sin lanzar nada) y los ejes van en
   coordenadas del CRS derivadas de `scene.transform`, no en índices de píxel.

## Cómo se corre

Desde la raíz del repositorio, con el entorno del
[README](../../README.md#quickstart) activo:

| Comando | Qué hace | Qué deja |
|---------|----------|----------|
| `python scripts/construir_scene.py` | Etapas 1 a 6 sobre el AOI por defecto e imprime el resumen | `data/interim/scene.npz` |
| `python scripts/visualizar_rgb.py` | Compuesto en color verdadero (B4/B3/B2) con realce por percentiles | `outputs/figures/scene_rgb.png` |
| `python scripts/visualizar_mascara.py` | Relee SCL sobre la ventana del `Scene` y la dibuja junto a `Scene.mask` | `outputs/figures/mascara_scl.png` |
| `python scripts/plot_kaolinite_signature.py` | Firma de referencia de la caolinita, banda a banda | `outputs/figures/kaolinite_signature.png` |
| `python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml` | Etapas 7, 8 y 10 de extremo a extremo: resuelve el `Scene`, corre el detector e imprime el resumen | `outputs/maps/kaolinite_sam_angle.tif` y `outputs/figures/kaolinite_sam_angle.png` |
| `python scripts/verificar_cifras.py` | Recalcula desde el `.tif` las cifras que el README y la sección 7 publican, las compara contra lo que dicen esos archivos y sale con código 1 si alguna no calza | Nada: solo lee e imprime |

`visualizar_rgb.py` y `visualizar_mascara.py` cargan `data/interim/scene.npz`
y, si no existe, construyen el `Scene` desde `data/raw/`.
`plot_kaolinite_signature.py` no necesita la escena: le basta el `.txt` de
`data/external/`. Es también el único que todavía dibuja sobre un eje de índice
de banda en vez de usar `plot_spectra`, que es lo que hacen el notebook 01 y la
figura `kaolinite_signature_vs_pixel.png`.

`notebooks/01_explore_sentinel2_scene.ipynb` recorre el mismo flujo de forma
interactiva y cierra con la verificación de alineamiento entre el cubo y la
firma de referencia.

## Etapa 9: la mitad hecha

### Lo que quedó hecho (Semana 4, Track A): la capa de verdad de terreno

`validation/geology.py` está implementado. El camino completo es:

```
scripts/descargar_geologia.py
   |
   |-- FeatureServer Chile_Geology, layers 439 y 437, paginado con resultOffset
   v
data/external/geologia/{pozo_almonte,mamina}.geojson   (EPSG:32719, versionados)
   |
   |-- load_geology_polygons(ruta) ......... GeoDataFrame, exige CRS y polígonos
   |-- clasificar_unidades(gdf, config) .... columna `clase` según el YAML
   |-- rasterize_ground_truth(gdf, scene) .. reproyecta y rasteriza a la grilla
   v
outputs/maps/ground_truth.tif   (2000x2000, mismo crs y transform que el mapa
                                 de ángulos; `write_geotiff` lo comprueba)
```

Lo encadena `build_ground_truth(config_path, scene)`, que además devuelve un
dict de trazabilidad (archivos usados, polígonos y píxeles por clase, fracción
del AOI, unidades sin clasificar). `scripts/construir_verdad_terreno.py` es la
CLI que lo corre e imprime.

La capa tiene **tres** valores: `1` positivo, `0` negativo y `255` ambiguo
(unidad sin clasificar o píxel fuera de todo polígono). El porqué de la tercera
clase está en [decisiones_tecnicas.md](decisiones_tecnicas.md), sección 9.

Qué unidad cuenta como positivo **no está en el código**: se declara en
`configs/verdad_terreno_cerro_colorado.yaml`, porque es un juicio geológico y no un
dato del mapa. Con ese YAML sin llenar el pipeline corre igual y produce una
capa 100 % ambigua, que es el estado en que está hoy.

La figura F5, `outputs/figures/overlay_deteccion_geologia.png`, superpone el
mapa de ángulos y los polígonos; la dibuja
`visualization/maps.py::plot_overlay_geologia`.

**Un detalle que hay que saber al consumir el .tif**: `write_geotiff` escribe
siempre float32 con `nodata=NaN`, así que `ground_truth.tif` trae `1.0`, `0.0`
y `255.0` en float32, no uint8. Los tres valores son exactos en float32, pero
quien lo lea tiene que castear antes de comparar por igualdad.

### Lo que falta: las métricas (Track B)

`validation/metrics.py` (matriz de confusión, F1, IoU, ROC/AUC, kappa) y
`scripts/evaluate.py` siguen siendo stubs completos: todas sus funciones
levantan `NotImplementedError`.

**Es lo que impide llamar «detección de caolinita» al mapa de la etapa 8.** Lo
que hay es un mapa de similitud espectral: dice a qué distancia angular está
cada píxel de la firma de laboratorio, no qué mineral hay en el suelo. La capa
de verdad de terreno es la referencia contra la cual medirlo, pero medir es lo
que todavía no se hizo. Quien lo haga tiene que excluir los `255` del cálculo.
Las cifras medidas están en la sección «Resultados» del
[README](../../README.md#resultados).

`io/raster_io.py::read_scene()` también sigue sin implementarse. Es la
contraparte de leer un `Scene` multibanda desde GeoTIFF y no bloquea nada: el
`Scene` se serializa con `save_scene`/`load_scene` a `.npz`, y `write_geotiff`
existe para exportar resultados, no para volver a leerlos.
