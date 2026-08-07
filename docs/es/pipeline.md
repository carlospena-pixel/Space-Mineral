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
| 8 | Algoritmo de detección | `algorithms/sam.py` | Detector implementado, **sin orquestador** |
| 9 | Validación contra cartografía | `validation/` | **Pendiente de Nivel 1** |
| 10 | Visualización de resultados | `visualization/maps.py` | **Pendiente de Nivel 1** |

Las etapas 1 a 6 son el preprocesamiento que cerró la Semana 2 y las encadena
una sola función, `build_scene_from_safe()`. `pipeline.py` —el orquestador del
proyecto completo, el que iría de la etapa 7 a la 10— todavía levanta
`NotImplementedError`.

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
(`col_off=1000, row_off=1000, 2000×2000` px a 20 m, o sea 40 × 40 km); una
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
configuración**: nada del pipeline lee de `meta` para decidir qué hacer
([decisiones técnicas §1.1](decisiones_tecnicas.md#11-scene--srcmineralmapioraster_iopy)).

`save_scene` / `load_scene` lo serializan a un único `.npz` —el cubo como
`float32`, la `transform` como sus 6 coeficientes, el CRS como WKT y `meta`
como JSON—. El JSON en vez de pickle es lo que permite cargar con
`allow_pickle=False`: abrir una escena nunca puede ejecutar código.

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

## Cómo se corre

Desde la raíz del repositorio, con el entorno del
[README](../../README.md#quickstart) activo:

| Comando | Qué hace | Qué deja |
|---------|----------|----------|
| `python scripts/construir_scene.py` | Etapas 1 a 6 sobre el AOI por defecto e imprime el resumen | `data/interim/scene.npz` |
| `python scripts/visualizar_rgb.py` | Compuesto en color verdadero (B4/B3/B2) con realce por percentiles | `outputs/figures/scene_rgb.png` |
| `python scripts/visualizar_mascara.py` | Relee SCL sobre la ventana del `Scene` y la dibuja junto a `Scene.mask` | `outputs/figures/mascara_scl.png` |
| `python scripts/plot_kaolinite_signature.py` | Firma de referencia de la caolinita, banda a banda | `outputs/figures/kaolinite_signature.png` |

`visualizar_rgb.py` y `visualizar_mascara.py` cargan `data/interim/scene.npz`
y, si no existe, construyen el `Scene` desde `data/raw/`.
`plot_kaolinite_signature.py` no necesita la escena: le basta el `.txt` de
`data/external/`. Es también el único que todavía dibuja sobre un eje de índice
de banda en vez de usar `plot_spectra`, que es lo que hacen el notebook 01 y la
figura `kaolinite_signature_vs_pixel.png`.

`notebooks/01_explore_sentinel2_scene.ipynb` recorre el mismo flujo de forma
interactiva y cierra con la verificación de alineamiento entre el cubo y la
firma de referencia.

## Lo que falta: etapas 8 a 10, pendientes de Nivel 1

Nada de lo que sigue está conectado. Se documenta para que quede claro **qué
falta**, no para sugerir que existe.

**8. Algoritmo de detección.** `algorithms/sam.py` sí está implementado y
testeado: `SAM.predict(cube, reference)` devuelve el mapa de ángulo espectral,
y `threshold(angle_map, max_angle)` lo binariza. Lo que no existe es el
orquestador que lo corra sobre un `Scene`: `pipeline.py::run_pipeline(config)`
levanta `NotImplementedError`, y `scripts/run_pipeline.py` lo llama, así que el
quickstart del README todavía no produce un mapa. Además, el umbral que fija
`configs/tamarugal_kaolinite.yaml` (`angle_threshold_rad: 0.1`) **no detectaría
un solo píxel** en la ventana de 256 × 256 px del AOI donde se midió; el valor
sigue ahí a propósito, a la espera de un criterio de calibración y no de otro
número elegido a ojo
([decisiones técnicas §7](decisiones_tecnicas.md#el-umbral-del-config-no-detectaría-nada)).

**9. Validación contra cartografía.** `validation/geology.py` (cargar los
polígonos de SERNAGEOMIN y rasterizar la verdad de terreno) y
`validation/metrics.py` (matriz de confusión, F1, IoU, ROC/AUC, kappa) son
stubs completos: todas sus funciones levantan `NotImplementedError`. No hay
verdad de terreno descargada en `data/external/`.

**10. Visualización de resultados.** `visualization/maps.py::plot_score_map()`
es un stub. Lo implementado del módulo es lo que consume el preprocesamiento:
`percentile_stretch`, `rgb_composite`, `scl_to_rgb` y `plot_scl_classes`. Del
mismo modo, `io/raster_io.py::write_geotiff()` y `read_scene()` siguen sin
implementarse, así que todavía no hay forma de exportar un mapa de puntaje a
GeoTIFF.

**En consecuencia, el proyecto no reporta ninguna detección de caolinita.** Lo
verificado hasta hoy está en la sección «Resultados» del
[README](../../README.md#resultados).
