# Decisiones técnicas

Este documento registra las decisiones de diseño ya tomadas e implementadas en
el repositorio, con su justificación y con lo que se rompería si se revirtieran.
Cada una referencia el archivo y la función donde vive.

La restricción que ordena casi todo lo que sigue es que el proyecto escala por
niveles —Nivel 1 (Spectral Angle Mapper), Nivel 2 (Random Forest), Nivel 3
(unmixing)— y la arquitectura debe soportar los tres sin refactorizar.

## 1. Contratos de interfaz

Son las tres fronteras que separan los subsistemas. Mientras se respeten, cada
subsistema puede reescribirse por dentro sin tocar a los otros.

### 1.1 `Scene` — `src/mineralmap/io/raster_io.py`

Objeto que produce `preprocessing/` y que consumen `spectral/` y `algorithms/`.
No conoce formatos de archivo: es solo datos en memoria.

| Campo        | Tipo         | Forma / contenido |
|--------------|--------------|-------------------|
| `cube`       | `np.ndarray` | `(n_bandas, alto, ancho)`, `float32`, reflectancia en `[0, 1]` o `NaN` |
| `band_names` | `list[str]`  | Nombres canónicos, alineados **posicionalmente** con el eje 0 de `cube` |
| `transform`  | `Affine`     | Georreferenciación del AOI recortado, no del tile completo |
| `crs`        | `CRS`        | Sistema de referencia (EPSG:32719 en esta escena) |
| `mask`       | `np.ndarray` | `(alto, ancho)`, `bool` |
| `meta`       | `dict`       | Trazabilidad; por defecto `{}` |

Tres convenciones que no son negociables:

**`mask` es `True` donde el píxel es válido.** Es el complemento de una máscara
de nubes, no la máscara de nubes. La función que la construye se llama
`build_cloud_mask` por el contrato original del proyecto y esa discrepancia de
nombre está advertida en su docstring. Invertir la convención rompería
`apply_mask`, `build_scene_from_safe` y todos sus tests sin producir ningún
error visible: simplemente se analizarían las nubes en vez del suelo.

**El orden de `band_names` es posicional, no nominal.** `cube[i]` es la banda
`band_names[i]`. Nadie busca bandas por nombre dentro del cubo salvo la
visualización. Por eso `get_reference_spectrum` recibe un `band_order` y
devuelve un vector alineado con él: el producto punto del SAM asume esa
alineación y no tiene forma de verificarla.

**`meta` es documentación, no configuración.** El invariante exacto es que
**nada del pipeline toma de `meta` un parámetro que decida qué se calcula**: el
AOI, las bandas y el algoritmo vienen del config en todos los caminos. `meta` se
lee en dos lugares y ninguno lo contradice:

- `_cache_coincide` compara `meta["aoi_window"]` contra la ventana del config.
  Lo único que `meta` puede hacer ahí es **vetar** el caché; si falta o no
  calza, el `Scene` se reconstruye desde el `.SAFE`. Nunca aporta el AOI, solo
  puede rechazar uno cacheado.
- `_guardar_heatmap` lee `tile_id` y `sensing_date` para el **título de la
  figura**. Es un uso cosmético: no entra en ningún cálculo, y un `meta` vacío
  produce la misma figura con el título más corto.

Registra de dónde salió el cubo: `safe_name`,
`tile_id`, `sensing_date`, `processing_baseline`, `boa_offset`,
`quantification`, `aoi_window`, `bands_source` (banda → resolución nativa),
`invalid_scl_classes`, `scl_summary` y `created_at`. Se serializa como JSON
dentro del `.npz`, de modo que `load_scene` nunca necesita `allow_pickle=True`
y abrir una escena no puede ejecutar código. Un `.npz` anterior a la existencia
de `meta` se carga con `meta == {}` en vez de fallar.

### 1.2 `Detector` — `src/mineralmap/algorithms/base.py`

```python
class Detector(ABC):
    @abstractmethod
    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray: ...
```

Recibe el cubo `(n_bandas, alto, ancho)` y la firma de referencia
`(n_bandas,)`; devuelve un mapa de puntaje 2D `(alto, ancho)` donde a mayor
valor, mayor evidencia de presencia del mineral.

**Este es el mecanismo de escalabilidad del proyecto.** El pipeline no sabe qué
algoritmo está corriendo: construye un `Detector` a partir del YAML del
experimento (`algorithm.name`) y llama a `predict`. Pasar de Nivel 1 a Nivel 2
es agregar una clase en `algorithms/` y una línea en un config, no reescribir
el flujo. `SAM` (`algorithms/sam.py`) implementa el contrato hoy;
`random_forest.py` y `unmixing.py` son andamiaje intencional que lo implementará
después.

La consecuencia incómoda, y aceptada: la firma `predict(cube, reference)` está
pensada para métodos que comparan contra una firma. Un Random Forest entrenado
con muestras etiquetadas no usa `reference` de la misma manera. Se resolverá
cuando se implemente —probablemente ignorando el argumento o usándolo como
semilla de las muestras positivas—, pero la firma se mantiene porque cambiarla
obligaría a tocar el pipeline, que es justo lo que el contrato evita.

### 1.3 `get_reference_spectrum` — `src/mineralmap/spectral/endmembers.py`

```python
def get_reference_spectrum(mineral: str, band_order: list[str] = BAND_ORDER) -> np.ndarray
```

Devuelve un vector 1D de largo `len(band_order)` con la reflectancia de
referencia del mineral, alineado posicionalmente con `band_order`. Busca el
archivo USGS splib07 registrado en `ENDMEMBERS` bajo `data/external/`, descarta
B10 (que la librería trae pero el producto L2A no) y reordena los 12 valores
restantes. Lanza `KeyError` si el mineral no está registrado.

El punto de diseño es que **el consumidor fija el orden**. La librería USGS
tiene su propio orden y el `Scene` tiene el suyo; que la conversión ocurra acá,
en un solo lugar y con el orden pedido explícitamente, es lo que evita un
desalineamiento silencioso entre el cubo y la firma.

## 2. Bandas

### `BAND_ORDER` — 12 bandas

`src/mineralmap/config.py`. Es el contrato de bandas del proyecto:

```
B1, B2, B3, B4, B5, B6, B7, B8, B8A, B9, B11, B12
```

Nombres canónicos **sin cero a la izquierda**; los archivos `.jp2` del producto
usan `B01`, `B08`, y la traducción vive en `BAND_TOKEN` (`io/raster_io.py`),
generada programáticamente desde `BAND_ORDER` para que agregar una banda al
contrato no exija mantener también un diccionario a mano.

**No incluye B10** (cirrus, ~1375 nm) porque no existe en el producto L2A:
Sen2Cor la descarta durante la corrección atmosférica, ya que solo sirve para
detección de cirrus sobre el producto L1C. Incluirla haría fallar la
construcción del `Scene` con un `FileNotFoundError` al buscar un archivo que el
producto no trae.

### `COMMON_BANDS` — 6 bandas, ya no es el default

Subconjunto de bandas nativas a 20 m que se usó para el primer `Scene`. Dejó de
ser el valor por defecto cuando el `Scene` pasó a 12 bandas: el roadmap de
Track A pedía "resampleo de todas las bandas a 20 m", y `BAND_ORDER` es el
contrato fijado en Semana 0. Se conserva como subconjunto documentado y sigue
disponible en la CLI (`--bands common`).

### `BAND_WAVELENGTHS_NM` y `BAND_FWHM_NM` — la longitud de onda es un dato

`src/mineralmap/config.py`. Longitud de onda central y ancho de banda (FWHM) de
cada banda, en nanómetros, con **una tabla por plataforma** y
`DEFAULT_PLATFORM = "S2B"`, que es la de la escena del proyecto. El helper
`band_wavelengths(band_order, platform)` las devuelve alineadas posicionalmente
con el `band_order` pedido, con el mismo contrato que
`get_reference_spectrum`: el consumidor fija el orden.

**Por qué hay dos tablas.** S2A y S2B son dos satélites con dos copias físicas
del instrumento MSI, y sus filtros no salieron idénticos de fábrica. La
divergencia más grande cae justo en la banda que le importa a este proyecto:
B12 está centrada en 2202,4 nm en S2A y en 2185,7 nm en S2B, 16,7 nm de
diferencia. B12 es la que muestrea el doblete Al–OH de la caolinita
(2160/2200 nm), donde la reflectancia cambia rápido con la longitud de onda.
Usar la tabla de S2A sobre una escena S2B no lanza ningún error: corre el
centro de la banda dentro del rasgo de absorción y devuelve un gráfico y una
validación de alineamiento que se ven bien y están mal.

**Incluye B10** aunque `BAND_ORDER` no la tenga. El producto L2A no la trae,
pero el archivo de la librería USGS sí, y la validación del alineamiento de la
firma de referencia necesita saber dónde cae.

Los valores están verificados contra SentiWiki (Copernicus), «S2 Mission»,
tabla 3, derivada de las funciones de respuesta espectral de ESA
(COPE-GSEG-EOPG-TN-15-0007). Las longitudes de onda centrales coinciden con las
que circulan en el proyecto; algunos FWHM no (B8 de S2A aparece como 106 nm en
planillas derivadas y como 118 nm en la fuente). Manda la fuente citada. La
discrepancia no afecta a nada implementado hoy: el FWHM se declara a la espera
de `spectral/srf.py` y ningún módulo lo consume.

### `SAM_BANDS` — 9 bandas, consumidas por el detector desde la Semana 3

```
B2, B3, B4, B5, B6, B7, B8A, B11, B12
```

Es el subconjunto que consume el detector espectral. Estuvo declarado sin
consumidores durante la Semana 2 —la decisión se escribió y se testeó antes de
que existiera el pipeline— y desde la Semana 3 lo consume `run_pipeline`, que
subconjunta el cubo y pide la firma de referencia con estas nueve bandas.

**Quién lo importa hoy**: `algorithms/sam.py`, donde `SAM` lo declara como su
atributo `bands`. El pipeline ya no lo importa: le pregunta al detector qué
bandas quiere en vez de recortar a `SAM_BANDS` incondicionalmente (ver
[sección 8](#8-el-detector-sam)).

Las tres exclusiones respecto de `BAND_ORDER`, por motivos distintos:

- **B1** (443 nm, aerosol costero) existe para alimentar la corrección
  atmosférica. Su varianza informa sobre el estado de la atmósfera, no sobre la
  superficie.
- **B9** (945 nm, absorción de vapor de agua) tiene el mismo problema, y además
  es la única banda con resolución nativa de 60 m: es la de menor información
  real por píxel de todo el cubo.
- **B8** (833 nm, ancha) se solapa con **B8A** (865 nm, angosta), que cubre la
  misma región con mejor definición espectral. Conservar ambas le daría peso
  doble al infrarrojo cercano al calcular el ángulo espectral, que es una suma
  sobre bandas y no pondera por redundancia.

**El `Scene` sigue naciendo con las 12 bandas.** Subconjuntar después siempre se
puede; recuperar una banda que nunca se leyó del disco, no. El costo de las tres
bandas extra es memoria, y es barato comparado con volver a leer el producto.

## 3. Zona de estudio

| Parámetro | Valor |
|-----------|-------|
| Tile | `T19KDT` (distrito Cerro Colorado, Precordillera de Tarapacá) |
| Producto | `S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE` |
| CRS | EPSG:32719 (UTM 19S) |
| Ventana AOI | `col_off=2700, row_off=650, width=2000, height=2000`, en la grilla de 20 m |
| Extensión | 40 × 40 km, E 453.960–493.960 / N 7.747.040–7.787.040 |
| Bbox WGS84 | `[-69.4412, -20.3748, -69.0577, -20.0128]` |

**La ventana en píxeles es la definición autoritativa; el bbox es informativo.**
La ventana define un recorte exacto y reproducible sobre la grilla del tile,
mientras que el bbox pasa por una reproyección y termina redondeado. Cuando se
pasa un bbox a `build_scene_from_safe`, se reproyecta con `transform_bounds`,
se convierte a ventana y se redondea con `round_offsets().round_lengths()`.
Ambos valores conviven en `configs/cerro_colorado_kaolinite.yaml` con esa jerarquía
anotada.

**La zona cambió dos veces.** El proyecto apuntaba al distrito de Chuquicamata
(Calama, Región de Antofagasta); se movió a Pampa del Tamarugal en la Semana 2
por disponibilidad de datos, y en la Semana 5 se desplazó al noreste, al
distrito Cerro Colorado, porque sobre la pampa no había alteración cartografiada
contra la cual validar (sección 10). El config se llamó sucesivamente
`chuqui_kaolinite.yaml`, `tamarugal_kaolinite.yaml` y hoy
`cerro_colorado_kaolinite.yaml`. Solo hay una versión válida de este dato:
cualquier mención a Chuquicamata o a Tamarugal como zona de estudio activa en
otro archivo del repositorio es un residuo y debe corregirse.

La escena sigue prácticamente despejada: 99,8484 % de píxeles válidos en el AOI,
99,8085 % clasificados como suelo desnudo. Es una condición deliberada —desierto
absoluto, sin vegetación ni nubes— porque el objetivo es detectar una firma
mineral en superficie y cualquier cobertura la enmascara. Lo descartado es casi
todo sombra topográfica (0,1505 %), que es el precio de entrar en la
Precordillera: la ventana anterior, sobre la pampa plana, descartaba 92 píxeles
y ésta descarta 6.064. Sigue siendo despreciable frente a los 4 millones.

## 4. Máscara de validez

`src/mineralmap/preprocessing/masking.py`.

```python
DEFAULT_INVALID_CLASSES = [0, 1, 2, 3, 6, 8, 9, 10, 11]
```

Se descartan: nodata (0), saturado o defectuoso (1), sombra topográfica (2),
sombra de nube (3), agua (6), nube de probabilidad media (8), nube de
probabilidad alta (9), cirrus fino (10) y nieve o hielo (11).

Se conservan tres clases, cada una por su motivo:

- **5, suelo desnudo** es justamente el objetivo. Es donde la firma del mineral
  llega al sensor sin obstrucción.
- **4, vegetación** no es un píxel inválido, solo poco informativo para un
  mineral. Filtrarla es una decisión del algoritmo, no del preprocesamiento: el
  preprocesamiento no debería descartar dato que un método posterior podría
  querer usar —un Random Forest, por ejemplo, aprende del contraste—.
- **7, no clasificado** es la clase "no sé" de Sen2Cor. Descartarla implicaría
  confiar en su clasificación más de lo que corresponde sobre terreno árido,
  donde equivoca seguido.

El agua sí se descarta: su firma espectral no compite con la de un mineral y
solo aporta falsos positivos.

**La máscara no se aplica al cubo.** `build_scene_from_safe` entrega el cubo
crudo y la validez por separado en `Scene.mask`. Quien decide enmascarar es el
consumidor, no el constructor: un algoritmo puede querer estadísticas globales,
otro puede necesitar el vecindario completo, y una vez que un píxel se
convirtió en `NaN` no hay forma de recuperarlo sin releer el producto. El helper
explícito para aplicarla es `apply_mask(cube, mask)`, que devuelve una copia con
`NaN` en todas las bandas de los píxeles inválidos y valida las formas.

La máscara final combina dos criterios: `mask_scl & ~np.isnan(cube).any(axis=0)`.
El segundo término atrapa los bordes del tile, donde SCL puede decir "suelo"
pero la banda no tiene señal.

## 5. Remuestreo

`src/mineralmap/preprocessing/resampling.py`.

**El remuestreo ocurre en la lectura, no sobre un `Scene` ya armado.**
`read_band_on_grid` traduce los límites del AOI a una ventana en la grilla
nativa de cada banda y le pide a GDAL que la entregue directamente con la forma
de la grilla destino. El `Scene` nace homogéneo a 20 m y nunca existe un cubo
con bandas de resoluciones mezcladas. Remuestrear después sería interpolar dos
veces, y cada interpolación degrada la radiometría.

`resample_to_common_grid` queda como stub reservado para Nivel 2, cuando haya
que combinar objetos `Scene` provenientes de grillas distintas y ya no se pueda
resolver en la lectura.

El método lo elige `resampling_for(src_res_m, target_res_m, categorical)`:

| Caso | Método | Motivo | Banda en esta escena |
|------|--------|--------|----------------------|
| Categórico | `nearest` | Promediar etiquetas produce clases que no existen | SCL (R20m) |
| Submuestreo 10 → 20 m | `average` | Promediar los 4 píxeles conserva mejor la radiometría que quedarse con uno | B8 (R10m) |
| Sobremuestreo 60 → 20 m | `bilinear` | Interpolar suaviza el bloque en vez de replicarlo en escalones | B9 (R60m) |
| Misma resolución | `nearest` | Es la identidad; interpolar por gusto solo agrega error | B1–B7, B8A, B11, B12 |

El caso categórico es el importante: el promedio de "agua" y "nube" no es
"vegetación", pero eso es exactamente lo que devolvería un `average` sobre
etiquetas. Es un error clásico y caro porque no falla, solo entrega una máscara
plausible y equivocada.

**Premisa que hace válido todo esto**: dentro de un tile Sentinel-2 L2A, todas
las bandas comparten CRS y origen de tile, y sus resoluciones son múltiplos
exactos entre sí. Por eso alcanza con recortar por coordenadas y reescalar, sin
`warp`. Lo que la rompería: combinar tiles distintos, fechas distintas u otro
sensor. En ese caso habría que reproyectar de verdad. Para que la premisa no se
viole en silencio, `read_band_on_grid` acepta un `expected_crs` y lanza
`ValueError` si no coincide —recortar por coordenadas en el CRS equivocado no
produce error, produce basura—.

## 6. Reflectancia

`src/mineralmap/preprocessing/reflectance.py`.

```
reflectancia = (DN + offset) / quantification
```

En esta escena: `offset = -1000`, `quantification = 10000`, baseline `05.11`.
Los tres valores se **leen de `MTD_MSIL2A.xml`** (`read_l2a_scaling`), no se
fijan en el código: dependen de con qué versión ESA procesó el producto, y una
escena reprocesada puede cambiarlos sin que cambie nada más. El parseo ignora
los namespaces XML comparando solo la última parte del tag, porque el namespace
del PSD cambia entre versiones y anclarse a él rompe la lectura sin aviso. Si el
XML falta, se cae al fallback `("04.00", -1000.0, 10000.0)` con un
`warnings.warn` explícito.

**Por qué existe el offset.** Hasta el baseline 03.xx, el producto guardaba
`reflectancia × 10000`. Desde el baseline 04.00, Sen2Cor codifica las
reflectancias con un desplazamiento: guarda `reflectancia × 10000 + 1000`. El
desplazamiento permite representar reflectancias ligeramente negativas —un
resultado normal de la corrección atmosférica sobre superficies muy oscuras—
sin recurrir a enteros con signo. En el XML el valor aparece como
`BOA_ADD_OFFSET = -1000`: es un sumando negativo, equivalente a restar 1000.
Aplicar la fórmula antigua a un producto moderno da un error sistemático de
+0,1 en reflectancia, que sobre suelo árido es del orden del 40 % del valor
real.

**Por qué `DN == 0` pasa a `NaN`.** El 0 es el valor de "sin dato" del producto.
Escalarlo lo convertiría en `-0.1`, que el clip dejaría en `0.0`: un valor
perfectamente válido y perfectamente falso. Contamina toda estadística
posterior —medias, percentiles, el realce de contraste de las figuras— sin dejar
rastro. Por eso el nodata se identifica sobre los DN crudos, antes de escalar.

**Qué hace y qué cuesta el clip.** Con `clip=True` (el default) el resultado se
acota a `[0, 1]`. Lo que gana: las reflectancias fuera de ese rango son
artefactos de la corrección atmosférica, no medidas, y arrastrarlas ensucia
cualquier normalización posterior. Lo que cuesta: se pierde la información de
cuán fuera de rango estaba un píxel, que es un diagnóstico útil de zonas donde
Sen2Cor tuvo problemas. En el AOI actual el clip actúa sobre los píxeles más
brillantes (el máximo del cubo es exactamente `1.0`). `np.clip` propaga los
`NaN`, así que el nodata sobrevive al recorte; hay un test que lo verifica
explícitamente porque es el tipo de detalle que una implementación alternativa
rompería en silencio.

## 7. Comparación de firmas

`src/mineralmap/visualization/spectra.py`.

`plot_spectra` es la única forma en que un humano puede ver si el cubo y la
firma de referencia están hablando de la misma banda. Tres decisiones, cada una
porque la alternativa produce un gráfico que se ve bien y engaña.

**El eje x es la longitud de onda, no el índice de banda.** El índice miente
sobre las distancias: entre B8A (864 nm) y B11 (1610 nm) hay 745 nm, y entre B5
(704) y B6 (739) hay 35, pero en un eje por índice ambos saltos miden lo mismo.
Con el índice, la pendiente de cualquier tramo del gráfico no significa nada, y
la pendiente es justo lo que se lee para reconocer un rasgo de absorción.

**La normalización por defecto es L2.** El SAM compara direcciones, no
magnitudes: es invariante al albedo por construcción. Graficar en norma
unitaria es graficar exactamente lo que el algoritmo ve. Sin normalizar, la
firma de laboratorio de la caolinita (reflectancia AREF de la librería USGS) y
un píxel real de la escena (reflectancia superficial) quedan separados por un
factor grande —del orden de 2 a 4 según el píxel— y el gráfico sugiere un
desalineamiento que no existe. Los `NaN` se propagan en vez de convertirse en
cero: un `NaN` es «esta banda no se midió», y un cero es «esta banda midió
reflectancia nula», que es otro dato y que además mueve el factor de
normalización.

**Hay hueco explícito donde el sensor no muestreó.** Entre dos bandas
consecutivas del `band_order` que no son vecinas en el sensor, la línea se
corta. El caso concreto es B9 (945 nm) y B11 (1610 nm): B10 no existe en el
producto L2A, y unirlas con una recta continua dibuja una interpolación a lo
largo de 665 nm donde no hay ni una sola medición.

### Resultado de la verificación de alineamiento

Es el entregable de Track B de la Semana 2, y quedó cerrado en tres niveles:

1. **Contra la tabla de ESA, en un test que corre sin datos.** `BAND_ORDER`
   está en orden creciente de longitud de onda, y la tabla de longitudes de
   onda es exactamente `BAND_ORDER` más B10, comprobado en las dos direcciones
   (`tests/test_config.py`). `validate_raw_band_order()` extiende lo mismo a
   las 13 posiciones del archivo USGS (`tests/test_endmembers.py`).
2. **Contra la escena real**, en `tests/test_scene_builder.py`: la firma pedida
   con `band_order=scene.band_names` trae tantos valores como bandas tiene el
   cubo, y subconjuntar el cubo por índice y pedir la firma por nombre llegan a
   la misma banda. Son dos caminos distintos hacia la misma banda y nada los
   obliga a coincidir; si divergieran, el SAM compararía la reflectancia de B11
   contra el valor de referencia de B12 y devolvería un mapa impecablemente
   calculado y sin sentido.
3. **A la vista**, en `notebooks/01_explore_sentinel2_scene.ipynb`: tabla
   `idx | banda | λ | ref_USGS | píxel` seguida de `assert`s, y la figura
   `outputs/figures/kaolinite_signature_vs_pixel.png`.

**Lo que falta para cerrarlo del todo.** El orden de `_RAW_BAND_ORDER` —qué
banda es cada posición del archivo de splib07— sigue anclado a evidencia física
y no a la fuente: la posición 10 tiene una caída aislada que solo puede ser el
sobretono OH de ~1400 nm que muestrea B10. El archivo de longitudes de onda del
paquete `ASCIIdata_splib07*_rsSentinel2` no está en `data/external/`; mientras
no esté, el test que lo consume queda en `skipif`. Lo mismo vale para
`USGS_RESAMPLING_PLATFORM = "S2A"`, que está declarado sin verificar.

### El umbral del config sigue sin calibrar

**AOI completo, 2000×2000 px** (3.993.936 píxeles válidos de 4.000.000, o sea
99,8484 %). Sale del resumen que imprime
`python scripts/run_pipeline.py --config configs/cerro_colorado_kaolinite.yaml`:

| bandas | mín | p1 | mediana | máx |
|--------|-----|----|---------|-----|
| `SAM_BANDS` (9) | 0,0662 | 0,2004 | 0,2795 | 0,6859 |

| umbral (rad) | píxeles | % del AOI válido |
|--------------|---------|------------------|
| 0,05 | 0 | 0,000 % |
| 0,08 | 28 | 0,001 % |
| 0,10 | **131** | 0,003 % |
| 0,15 | 1.482 | 0,037 % |
| 0,20 | 38.672 | 0,968 % |

La tabla tiene **solo la fila de 9 bandas**: el pipeline corre `SAM_BANDS` y es
lo único que hay medido a esta escala. No se repitió el experimento con
`BAND_ORDER` sobre los 4 millones de píxeles, así que esa fila no existe y no
se estima.

Estas cifras son de la ventana de Cerro Colorado. Las del AOI anterior, sobre
la Pampa del Tamarugal, están en la sección 10 y en el `CHANGELOG.md`, que es
donde se cuenta el cambio; no se conservan aquí para que este documento tenga
un solo juego de números vigentes.

#### Qué son los 131 píxeles: sigue sin ser una detección

Lo que sigue es evidencia a favor, y no alcanza. **La dirección de un rasgo de
absorción no identifica un mineral**: sin cotejar contra verdad de terreno no
hay forma de separar caolinita de cualquier otra superficie que descienda entre
B11 y B12.

Los 131 píxeles bajo 0,1 rad **reproducen la absorción Al–OH en dirección**:

| | los 131 | fondo (3.993.805 válidos) | firma USGS KGa-1 |
|---|---|---|---|
| razón B12/B11 (mediana) | **0,663** | 1,000 | 0,507 |
| con razón < 1 | **131 de 131** | 50 % | — |
| reflectancia media, 9 bandas | 0,278 | 0,207 | — |

Los 131 descienden de B11 a B12 y ninguno toca el borde del AOI —el más cercano
está a 248 px—, así que no son artefactos de recorte. Se agrupan en 20
componentes conexas de 8 vecinos, la mayor de 79 píxeles: son parches, no ruido
de un píxel suelto. Y no están aislados en su entorno: **la mediana del
vecindario de 5 × 5** vale 0,1020 rad contra 0,2795 de la escena, y en 123 de
los 131 ese vecindario también queda bajo 0,15. Con la media del mismo
vecindario da 0,1143 y 121 de 131; se nombra el estadístico porque las dos
cifras difieren. El descenso es menos pronunciado que el de la firma de
laboratorio (0,663 contra 0,507), que es lo esperable de un píxel de 20 m donde
el mineral, si está, viene mezclado con todo lo demás que hay en 400 m².

#### Dónde caen: el dato que cambia la lectura

Desde la Semana 5 el AOI incluye alteración cartografiada, así que la pregunta
que antes no se podía formular ahora se puede contar:

| clase de la verdad de terreno | píxeles del AOI | detecciones a 0,1 rad |
|---|---|---|
| positivo (alteración cartografiada) | 50.773 (1,27 %) | **0** |
| negativo (no candidata) | 192.444 (4,81 %) | **0** |
| ambiguo (sin clasificar) | 3.756.783 (93,92 %) | **131** |

**130 de las 131 caen sobre una sola unidad**: `Depositos antropicos, botaderos
de mina`, los botaderos de la mina Cerro Colorado, 16,79 km² y 1,05 % del AOI.
La restante cae sobre una facies conglomerádica de la Formación Altos de Pica.

Eso explica de un golpe las tres cifras de arriba: los parches conexos, la
reflectancia media más alta que el fondo (0,278 contra 0,207) y la razón
B12/B11 uniformemente menor que 1 son lo que se espera de roca molida y recién
expuesta, sin la costra ni el barniz del desierto. El SAM está encontrando algo
real y espacialmente coherente —130 aciertos dentro del 1 % del área—, pero es
material removido, no geología *in situ*.

**Dentro de las unidades declaradas positivo el ángulo mínimo es 0,1541 rad**,
muy por encima del umbral: ni un solo píxel de alteración cartografiada se
parece a la caolinita a esta escala. Es el resultado que hay que poder explicar,
y la explicación más plausible es que la superficie natural del desierto está
cubierta por costra y barniz que enmascaran la firma, mientras que el material
de mina la expone.

#### El criterio de calibración ya existe (Semana 6)

`configs/cerro_colorado_kaolinite.yaml` fija `angle_threshold_rad: 0.1`. Hasta
la Semana 5 ese valor no tenía criterio de calibración y este documento decía
que calibrarlo exigía la curva ROC. **La curva ya existe** —
`validation/metrics.py` y `scripts/evaluate.py` están implementados — y lo que
dice es que no hay ningún umbral que rescate este mapa:

| criterio | umbral (rad) | valor alcanzado |
|---|---|---|
| índice de Youden | 0,4467 | 0,0034 |
| F1 máximo | 0,4492 | 0,3462 |

Los dos se reportan porque optimizan cosas distintas —Youden pesa igual los dos
tipos de error, F1 ignora los verdaderos negativos— y sobre una clase con
20,88 % de positivos no tienen por qué coincidir. Aquí, sin embargo, **ninguno
de los dos es utilizable**:

- El de Youden alcanza J = 0,0034. Un J de 0 es un clasificador que no separa
  nada; 0,0034 es indistinguible de eso.
- El de F1 máximo detecta 242.276 de los 242.967 píxeles evaluables, o sea el
  99,72 %. Es el clasificador que dice «sí» a todo, cuyo F1 sería 0,3455 por
  construcción; el 0,3462 que se reporta es esa cifra más el ruido de dejar
  fuera 691 píxeles. No es una calibración, es la tasa base disfrazada de
  resultado.

**El valor del config sigue siendo el heredado, 0,1 rad, y no se cambia aquí.**
Cambiarlo es decisión de la dueña del repositorio, y además ninguno de los dos
umbrales calibrados mejora nada que valga la pena mover: mover el umbral de
0,1 a 0,4467 convertiría 0 detecciones en casi 4 millones sin ganar poder
discriminante. Lo que la calibración aporta no es un número nuevo para el YAML,
es la evidencia de que **el problema no está en el umbral**. El detalle está en
la sección 11.

#### La conclusión no cambia

**131 píxeles de 3.993.936 no son una detección de caolinita.** El ángulo
espectral mide parecido contra una firma de laboratorio, no presencia de un
mineral: cualquier superficie que en 9 bandas se le parezca cae igual de bajo.
Ahora, además, se sabe *dónde* caen, y el lugar no es el que E3 pide.

## 8. El detector SAM

`src/mineralmap/algorithms/sam.py`.

### La fórmula y su fuente

Para un píxel `x` y la firma de referencia `r`, ambos vectores de `n_bandas`
componentes:

```
θ(x, r) = arccos( (x · r) / (‖x‖ · ‖r‖) )
```

**Contrastada término a término contra el documento 05 del proyecto**, que es
la fuente de la especificación:

| Aspecto | Documento 05 | Implementado |
|---------|--------------|--------------|
| Normalización previa de los vectores | Ninguna; la normalización va en el denominador | Igual |
| Unidad de salida | Radianes | Radianes (`np.arccos`) |
| Definición del puntaje | El ángulo mismo («ángulo pequeño = alta similitud») | El ángulo mismo |
| `clip(-1, 1)` antes del `arccos` | Prescrito, para evitar `NaN` por error numérico | Presente |
| Vectorización | `einsum`/broadcasting, sin bucles sobre píxeles | `einsum` |
| Bandas en la suma | 12 | `n_bandas`, y el pipeline pasa 9 |

La única divergencia es la última, y es **deliberada**: el documento 05 se
escribió cuando el contrato de bandas era `BAND_ORDER`, y el proyecto decidió
después que el detector consumiría `SAM_BANDS` (sección 2), con la medición de
la sección 7 mostrando que el recorte no cambia la distribución de ángulos. La
implementación no fija ningún número de bandas: valida que el cubo y la firma
coincidan entre sí, que es la propiedad que de verdad importa.

**Consecuencia sobre la dirección del puntaje.** El documento 05 define el
puntaje como el ángulo, o sea que menor es más parecido. Eso deja a `SAM`, al
`viridis_r` de los mapas, al `angle_threshold_rad` de los configs y al `<=` de
`threshold()` todos del mismo lado. Ver la deuda al final de esta sección.

### Qué valida ahora, y qué lanza

Antes, `predict` sólo fallaba desde adentro de `np.einsum`, con un mensaje sobre
dimensiones de operandos que no menciona bandas ni firmas. Ahora:

| Entrada | Reacción | Por qué no puede pasar en silencio |
|---------|----------|-------------------------------------|
| `cube` y `reference` con distinto número de bandas | `ValueError` nombrando **los dos largos** | Es el cruce `BAND_ORDER` (12) contra `SAM_BANDS` (9). El pipeline lo vuelve cotidiano |
| `cube` que no es 3D | `ValueError` con la forma recibida | Un cubo 2D es una firma, no una escena |
| `reference` que no es 1D | `ValueError` | Una firma `(n, 1)` hace broadcast y devuelve un mapa de la forma equivocada con valores plausibles |
| `reference` con `NaN` o `inf` | `ValueError` con las posiciones | Vuelve `NaN` el mapa completo, y un mapa todo `NaN` es indistinguible de una escena enteramente enmascarada |
| `reference` de norma cero | `ValueError` | No hay dirección contra la cual medir un ángulo. Mismo criterio que `normalize_signature` (sección 7) |

**Lo que deliberadamente NO valida: los `NaN` del cubo.** Un cubo con `NaN` es
la entrada normal del detector, no un caso patológico: el pipeline le entrega el
cubo ya enmascarado con `apply_mask` (sección 4). Un píxel `NaN` devuelve `NaN`
y no contamina a sus vecinos, y hay un test que fija esa promesa. Cualquier
validación que rechace un cubo con `NaN` rompe el pipeline entero.

La firma `predict(cube, reference)` **no cambió** y no se le agregó un parámetro
`mask`, aunque sería cómodo: es el mecanismo de escalabilidad de la sección 1.2,
y enmascarar es trabajo del consumidor.

### Dos comportamientos que existían sin estar escritos

- **Píxel de norma cero** (todas las bandas exactamente en 0) → `NaN`. Un vector
  nulo no tiene dirección, así que el ángulo contra él no es 0 ni π/2: no está
  definido. Devolver 0 lo declararía coincidencia perfecta y lo pintaría como la
  detección más fuerte del mapa. `NaN` lo saca por el mismo camino que un píxel
  enmascarado.
- **`threshold()` descarta los `NaN`**, que es lo correcto, pero eso sale de la
  semántica de IEEE-754 —toda comparación contra `NaN` es falsa— y no de código
  escrito para ello. Queda anotado porque una reimplementación que «limpiara»
  los `NaN` antes de comparar, por ejemplo con `np.nan_to_num`, los convertiría
  en `0.0` y por lo tanto en las detecciones más fuertes del mapa.

### Precisión: el acumulador es `float64`, el cubo sigue en `float32`

El producto punto y la norma del píxel se calculan con el parámetro `dtype` de
`np.einsum`, que fija el acumulador de la suma **sin castear el cubo**.

Medido sobre un cubo de 9 bandas contra el mismo cálculo en `float64` puro:

| Cubo | Acumulador `float32` (antes) | Acumulador `float64` (ahora) |
|------|------------------------------|------------------------------|
| Píxeles arbitrarios | 3,8 × 10⁻⁷ rad | 2,9 × 10⁻⁸ rad |
| Píxeles casi idénticos a la firma | **4,5 × 10⁻⁴ rad** | 3,9 × 10⁻⁸ rad |

**La fila que decide es la segunda, porque es el régimen de una detección.**
Cerca de coseno = 1 la derivada de `arccos` diverge y amplifica el redondeo: en
esa medición el ángulo verdadero era 1,3 × 10⁻⁵ rad, o sea que el error era **35
veces más grande que la cantidad que se estaba midiendo**. El ángulo era ruido
justo donde el mapa afirma haber encontrado algo.

El costo en memoria es cero, que es lo que hacía falta comprobar antes de
elegir. El cubo real del AOI, `(12, 2000, 2000)`, sigue ocupando 183 MB en
`float32`; un `cube.astype(np.float64)` habría costado 366 MB, y da exactamente
el mismo error que el acumulador (3,9 × 10⁻⁸ rad). Lo único que se materializa
en `float64` son los dos mapas `(alto, ancho)`, 30,5 MB cada uno.

Lo que no arregla: los ángulos muy cerca de 0 y de π siguen teniendo un piso de
error de ~2 × 10⁻⁸ rad, porque es la sensibilidad intrínseca de `arccos` en
±1 y no un problema de acumulación. Es irreducible mientras el puntaje sea el
ángulo y no su coseno.

### Los casos de prueba son analíticos, no comparativos

`tests/test_sam.py` verifica ángulos cuyo valor exacto se conoce **por
construcción geométrica** (ortogonal → π/2, `[1,0]` contra `[1,1]` → π/4,
`[1,0,0]` contra `[1,1,√2]` → π/3, `[1,0]` contra `[√3,1]` → π/6, antiparalelo
→ π), no comparando contra otra implementación de SAM: dos implementaciones que
coinciden sólo demuestran que coinciden, incluso si ambas se equivocan igual.
Los casos exactos se verifican a `1e-12`; los dos que caen en los extremos de
`arccos`, a `1e-7`, por el piso de error del párrafo anterior.

Hay además un test-oráculo que compara la versión vectorizada contra un bucle
`for` ingenuo sobre un cubo no cuadrado. Es el que atrapa un error de ejes en el
`einsum`: un `"bhw,b->hw"` mal escrito no lanza nada, devuelve un mapa
transpuesto que se ve perfectamente razonable.

### Resuelto: cada detector declara su dirección y sus bandas

`Detector.predict` documentaba «a mayor valor, mayor evidencia» y `SAM.predict`
devuelve un ángulo, donde **menor es más parecido**. La deuda quedó abierta en
la Semana 3 con fecha de revisión «al cerrar la Semana 4, y en todo caso antes
del primer commit del segundo detector». **Se adelantó**, porque la Semana 3
además publicó una afirmación arquitectónica falsa —`pipeline.py` y esta misma
sección decían que el flujo no nombra a SAM, y lo nombraba en cinco lugares— y
la salida honesta era volverla verdadera, no borrar la frase.

**Se eligió la salida 1**: la dirección la declara cada detector en el atributo
de clase `higher_is_better`, y quien binariza usa `Detector.detects()`. No se
eligió normalizar todo a «mayor es mejor» (para SAM, devolver el coseno) por
tres razones, en orden: el documento 05 del proyecto define el puntaje del SAM
como el ángulo, y cambiar SAM para que calzara con un contrato interno sería
invertir la jerarquía de fuentes; el ángulo en radianes es la unidad estándar
del SAM en la literatura de teledetección, y el coseno pierde la unidad física
y vuelve el mapa incomparable con cualquier publicación; y `viridis_r`,
`angle_threshold_rad` y el `<=` de `threshold()` ya están todos del mismo lado,
mientras que la salida 2 obliga a tocar los tres.

El cambio **no invierte ningún signo y no mueve un solo píxel** de la salida:
`SAM` declara `higher_is_better = False`, que es exactamente lo que el pipeline
asumía. Lo que cambia es que ahora está escrito en vez de supuesto.

**Qué falla arreglaba.** Un detector registrado en `DETECTORS` que respetara el
contrato —mayor valor, mayor evidencia— y devolviera 0,9 en todo el AOI, o sea
evidencia máxima, hacía que el barrido reportara cero píxeles bajo los cinco
umbrales, **sin lanzar nada**, porque el pipeline aplicaba el `<=` de SAM a
cualquier puntaje. Se habría descubierto el día del primer commit de Random
Forest, con el pipeline entero corriendo y reportando cero.

Junto con la dirección se declaran las **bandas**: `Detector.bands` dice qué
bandas consume el detector y en qué orden, y el pipeline subconjunta el cubo y
pide la firma de referencia con esa lista. Antes recortaba a `SAM_BANDS`
incondicionalmente, así que un detector con otras necesidades espectrales
recibía igual esas nueve. `SAM` declara `bands = tuple(SAM_BANDS)`.

`threshold(angle_map, max_angle)` se conserva tal cual: es pública, tiene tests
y otros consumidores. Lo único que cambió es que el pipeline ya no la usa.

**Lo que no se generalizó, a propósito.** Estas superficies siguen siendo
específicas del ángulo espectral, y está bien que lo sean mientras no exista el
segundo detector:

- La clave `angle_threshold_rad` de los configs.
- Las claves `angle` y `angle_map_path` del dict que devuelve `run_pipeline`.
- La línea `Angulo (rad)` de `_imprimir_resumen` y la constante
  `THRESHOLD_SWEEP`, cuyos cinco valores están en radianes.

Ninguna produce un resultado silenciosamente equivocado: son nombres y
unidades, y la comparación que sí podía estar mal ya la hace `detects()`.
Generalizarlas ahora es churn especulativo antes de saber qué necesita el
segundo detector; se renombran cuando entre y se sepa contra qué.


## 9. La capa de verdad de terreno

Tres decisiones de la Semana 4 que hay que poder defender en voz alta.

### 9.1 La Carta Calama no aplica; la reemplazan Pozo Almonte y Mamiña

El plan original nombraba la «Carta Calama» como fuente de la verdad de
terreno. **No sirve**: Calama está en la Región de Antofagasta, en torno a
22,45° S / 68,93° W, unos 250 km al sur del AOI. Es un residuo de cuando la
zona de estudio era Chuquicamata (ver sección 3): la zona se movió a Pampa del
Tamarugal en la Semana 2 y el plan escrito nunca se actualizó.

Las cartas 1:100.000 de SERNAGEOMIN que sí cubren el AOI son **dos**:

| Carta | Código | Serie Geología Básica | Año | Cobertura |
|---|---|---|---|---|
| Pozo Almonte | M204 | 162–163 (junto con Iquique) | 2013 | 70,00°–69,50° W · 20,50°–20,00° S |
| Mamiña | M303 | 174 | 2015 | 69,50°–69,00° W · 20,50°–20,00° S |

El AOI va de −69,7673° a −69,383° de longitud y **cruza el límite entre
ambas**: la mitad oeste cae en Pozo Almonte y la este en Mamiña. Hay que cargar
las dos y unirlas. Medido sobre los datos descargados, la unión cubre el AOI al
100 % (1600,0 de 1600 km²) y las hojas se solapan en una franja estrecha
(E 447.510–447.677), así que no queda hueco en la costura. `tests/test_geology.py`
comprueba ambas cosas cuando los GeoJSON están en disco.

Los vectores salen del FeatureServer `Chile_Geology`, una **digitalización de
terceros sin licencia declarada**. Se usa como insumo técnico; la cita que
corresponde es siempre la carta original. Ver
`data/external/geologia/README.md`.

### 9.2 No existe capa de alteración: el positivo lo elegimos nosotros

SERNAGEOMIN publica un único tema cartográfico («Geología Básica»), no publica
WFS y no tiene ningún servicio de alteración en su organización ArcGIS. **No
hay ninguna capa abierta de polígonos de alteración hidrotermal para el norte
de Chile.** El riesgo R5 del documento 08 lo anticipó; esto lo confirma.

La consecuencia es la decisión central de la semana: la verdad de terreno **no
se obtiene filtrando una columna**. Las cartas traen litología. El positivo es
una **selección de unidades litológicas** que el equipo declara aceptables como
compatibles con alteración argílica, y eso es un juicio geológico, no un dato
del mapa.

Por eso la selección no está en el código: vive en
`configs/verdad_terreno_cerro_colorado.yaml`, versionada, con una línea de
justificación por unidad y con la lista completa de las 38 unidades presentes
en el AOI y su superficie. Es lo primero que alguien va a cuestionar en una
defensa, y tiene que poder cuestionarlo leyendo un YAML, no leyendo Python.

**Hallazgo que hay que decir en la defensa antes de que lo pregunten:** dentro
de este AOI no hay ninguna unidad candidata a alteración. Las tres que se
esperaban existen en la hoja Mamiña y caen todas fuera:

| Unidad | Distancia al borde E del AOI |
|---|---|
| Brechas hidrotermales de turmalina (Cpx. Yabricoya) | 29,5 km |
| Complejo intrusivo Cerro Colorado | 10,3 km |
| Complejo Yabricoya (todas sus facies) | 19,1 km |

El AOI cae íntegramente sobre el relleno sedimentario de la Pampa del
Tamarugal: 96 % depósitos aluviales, salinos, eólicos y de piedemonte. Es una
cuenca de relleno, no el distrito de pórfido. La capa sigue sirviendo para
medir **falsos positivos** sobre un negativo bien fundado, que es la pregunta
que el mapa de ángulos no puede responder solo; lo que no permite estimar es el
recall. Medir detección positiva exige mover o ampliar el AOI unos 10–30 km al
este, y eso es una decisión de alcance del proyecto.

### 9.3 La clase `ambiguo` existe y no se colapsa a 0

La capa tiene tres valores, no dos:

| Valor | Significado |
|---|---|
| `1` | Positivo: unidad aceptada como compatible con alteración argílica |
| `0` | Negativo: unidad claramente no candidata (salares, eólicos, aluviales recientes, gravas) |
| `255` | Ambiguo: unidad no clasificada, o píxel fuera de todo polígono |

Los `255` **se excluyen** del cálculo de métricas. Forzar un binario 0/1
convertiría «no lo sé» en «no hay», que sobre una clase tan desbalanceada como
ésta es exactamente la sustitución que infla la precisión sin que nada falle:
cada píxel dudoso pasaría a contar como verdadero negativo y engordaría el
denominador de la especificidad con casos que nadie verificó.

El `255` es además el **default** de todo lo que el YAML no nombra, y el fill de
todo lo que ningún polígono cubre. El silencio significa «no lo sé», nunca «no
hay». `clasificar_unidades` avisa por `warnings.warn` cuántas unidades quedaron
sin clasificar y qué fracción de la superficie representan, para que un YAML mal
llenado no produzca en silencio una capa 100 % ambigua que se ve igual que una
capa correcta.

### 9.4 `all_touched=False` al rasterizar

Un píxel pertenece al polígono que **cubre su centro**. Con `all_touched=True`
se marcaría todo píxel que el polígono roce, lo que engorda cada área positiva
en un anillo de un píxel completo justo en los bordes —que es donde una carta
1:100.000 es menos confiable frente a píxeles de 20 m—. La precisión del
contacto entre unidades en esa carta es de varios píxeles; ensancharlo a
propósito solo agrega área positiva que no se puede defender.

Dos detalles relacionados, ambos testeados:

- **Se reproyecta siempre** con `.to_crs(scene.crs)` antes de rasterizar,
  aunque los polígonos ya vengan en 32719. Es idempotente en ese caso y es la
  red de seguridad contra el único modo de fallo que no se nota: unas
  coordenadas en grados contra una `transform` en metros no lanzan nada,
  simplemente no marcan nada, y la capa sale entera en `ambiguo` —que es justo
  el aspecto que tiene una capa correcta con el YAML sin llenar—.
- **No se aplica `scene.mask`.** Que un píxel sea válido (nubes, sombra, agua)
  y que esté cubierto por la cartografía son dos cosas distintas, y quien las
  combina es el consumidor. Es el mismo criterio con que `scene_builder`
  entrega la máscara SCL aparte en vez de aplicarla al cubo.
- Donde dos polígonos se pisan **gana el valor de clase más alto**, o sea el
  positivo sobre el negativo. Las dos hojas se solapan de verdad, así que el
  caso ocurre. Se elige el positivo porque es la clase rara: borrarla con un
  negativo la haría desaparecer sin dejar rastro, mientras que lo contrario solo
  agrega un área positiva que se ve en la figura.


## 10. El cambio de AOI de la Semana 5

Tres decisiones que hay que poder defender.

### 10.1 Por qué se movió el AOI: E3 no se podía cumplir

La Semana 4 dejó implementada la capa de verdad de terreno y, al construirla,
apareció el problema: **dentro del AOI de la Pampa del Tamarugal no había ni una
sola unidad con alteración hidrotermal cartografiada**. El 96 % del AOI era
relleno sedimentario —depósitos aluviales, salinos, eólicos y de piedemonte— y
las tres unidades candidatas de la hoja Mamiña caían todas fuera:

| Unidad | Distancia al borde E del AOI viejo |
|---|---|
| Brechas hidrotermales de turmalina (Cpx. Yabricoya) | 29,5 km |
| Complejo intrusivo Cerro Colorado | 10,3 km |
| Complejo Yabricoya (todas sus facies) | 19,1 km |

Con cero zonas de alteración documentadas, el criterio **E3** del Plan
Maestro —«las detecciones se concentran preferentemente en zonas de alteración
argílica/hidrotermal documentadas»— no se podía ni formular, y **E4** (recall,
F1, ROC/AUC) tampoco. No es que el resultado fuera malo: la pregunta no tenía
sentido sobre ese recorte.

La respuesta fue mover la ventana, no reformular el criterio. La ventana pasa de
`col_off=1000, row_off=1000` a `col_off=2700, row_off=650`. **No crece**: siguen
siendo 2000 × 2000 px a 20 m, o sea 40 × 40 km, y el `.npz` pesa lo mismo.

`row_off` baja de 1000 a 650 porque **Cerro Colorado está al noreste, no solo al
este**: su borde sur (N 7.782.431) quedaba 2,4 km por encima del borde norte del
AOI viejo, así que ampliar solo hacia el este lo habría dejado afuera. Con la
ventana nueva las tres unidades entran —Yabricoya se corta en su borde este, a
5,9 km— y la cartografía sigue cubriendo el AOI al 100 %.

Qué cambió en las cifras:

| | AOI Tamarugal | AOI Cerro Colorado |
|---|---|---|
| Ventana | `col_off=1000, row_off=1000` | `col_off=2700, row_off=650` |
| Píxeles válidos | 99,9977 % (92 descartados) | 99,8484 % (6.064 descartados) |
| Ángulo mín / mediana / máx | 0,0723 / 0,2742 / 0,6971 | 0,0662 / 0,2795 / 0,6859 |
| Detecciones a 0,1 rad | 62 | 131 |
| Positivo en la verdad de terreno | 0 px | 50.773 px (1,27 %) |

La caída de píxeles válidos es sombra topográfica: la ventana entra en la
Precordillera y tiene relieve. 0,15 % sigue siendo despreciable.

### 10.2 Qué se declaró positivo, y con qué criterio

`configs/verdad_terreno_cerro_colorado.yaml` declara **8 unidades como
positivo** (20,30 km², 1,27 % del AOI): las brechas hidrotermales de turmalina,
las dos facies del Complejo intrusivo Cerro Colorado y los pórfidos félsicos
—dacíticos, riodacíticos y riolíticos—, incluidos los del Complejo Yabricoya.
El criterio es alteración hidrotermal declarada en la carta, o litología
porfídica félsica del distrito.

**Diez unidades son negativo** (76,94 km², 4,81 %): eólicos activos, aluviales
activos, coluviales, deslizamientos y cobertura agrícola. Todo lo demás queda
ambiguo (93,92 %) y se excluye del cálculo de métricas.

La decisión discutible, y hay que decirla antes de que la pregunten: **las
facies plutónicas del Complejo Yabricoya no son positivo** pese a pertenecer al
complejo. Son 81,65 km², cuatro veces el positivo entero. Son monzogranitos y
sienogranitos, o sea roca de caja del batolito, no el sistema porfídico
mineralizado; incluirlas multiplicaría el positivo por cinco sin ninguna
alteración declarada y lo diluiría hasta volverlo inútil como referencia.

### 10.3 Cómo se clasificó la mina, y por qué eso decide E3

Dentro del AOI está la mina Cerro Colorado en operación. La carta la recoge como
`Depositos antropicos, botaderos de mina`: **16,79 km², el 1,05 % del AOI**.

Se clasificó como **ambiguo, de forma explícita y no por omisión**. Las dos
lecturas son reales y se anulan:

- A favor de positivo: el estéril de un pórfido *es* roca alterada, molida y
  expuesta. Espectralmente puede ser el sitio con más arcilla visible del AOI.
- A favor de negativo: un botadero no es una zona de alteración cartografiada
  sino una obra humana, y su ubicación no es la de la roca original.
- Y hay circularidad: la mina está ahí **porque** hay alteración. Declararla
  positivo casi garantiza el acierto en el punto más llamativo del mapa e
  inflaría el resultado sin sustento geológico.

**Esa decisión determina por completo la respuesta a E3**, y el dato lo
confirma: de las 131 detecciones a 0,1 rad, **130 caen exactamente sobre los
botaderos**. Con los botaderos declarados positivo, el 99,2 % de las detecciones
caería en positivo y E3 se cumpliría de forma espectacular. Con la clasificación
adoptada, **cero detecciones caen en positivo y E3 no se cumple**.

La honestidad exige decir las dos cosas y dejar la decisión donde se pueda
revisar. Lo que no cambia con ninguna clasificación es el hecho crudo: dentro de
las unidades de alteración cartografiada el ángulo mínimo es 0,1541 rad, muy por
encima del umbral. **Ninguna zona de alteración *in situ* del AOI se parece a la
caolinita a 20 m de resolución.** La explicación más plausible es que la costra
y el barniz del desierto enmascaran la firma en la superficie natural, mientras
que el material removido de la mina la expone.

## 11. El diseño de `metrics.py` y el resultado de la validación

`src/mineralmap/validation/metrics.py`, `scripts/evaluate.py`. Semana 6.

### 11.1 El resultado, primero

```bash
python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif outputs/maps/ground_truth.tif --figura
```

| | valor |
|---|---|
| píxeles evaluables | 242.967 |
| positivos evaluables | 50.731 |
| negativos evaluables | 192.236 |
| verdaderos positivos (VP) | 0 |
| falsos positivos (FP) | 0 |
| falsos negativos (FN) | 50.731 |
| verdaderos negativos (VN) | 192.236 |
| precisión | 0,0000 |
| recall | 0,0000 |
| F1 | 0,0000 |
| IoU | 0,0000 |
| kappa de Cohen | 0,0000 |
| ROC AUC | 0,2403 |

Los umbrales de calibración están en la sección 7. La figura es
`outputs/figures/roc_kaolinite_sam.png`.

**Los cinco ceros son un solo hecho.** Con el umbral del config no hay ninguna
detección dentro de las clases evaluables —las 131 del AOI caen todas en
ambiguo—, así que VP = FP = 0 y todo lo que se calcula a partir de la matriz de
confusión vale cero. No es un error: es lo que mide un detector que no detecta.

**El número que informa es el AUC, porque no depende del umbral.** Y 0,2403
está *por debajo* de 0,5. Eso no significa que el detector no separe: significa
que **separa al revés**.

| | ángulo (rad) |
|---|---|
| mediana dentro del positivo | 0,3288 |
| mediana dentro del negativo | 0,2712 |
| mínimo dentro del positivo | 0,1541 |
| mínimo dentro del negativo | 0,1597 |

Las unidades que la cartografía declara compatibles con alteración se parecen
**menos** a la caolinita de laboratorio que las que declara no candidatas. Un
AUC de 0,2403 equivale a decir que «ángulo grande» predice el positivo con
0,7597.

#### Qué no significa esto

No significa que invirtiendo el signo se obtenga un detector de alteración con
AUC 0,76. Lo que separa en esa dirección no es caolinita: son las diferencias
litológicas generales entre roca intrusiva y relleno sedimentario, que el
ángulo contra *cualquier* firma habría capturado igual. Un AUC de 0,76 obtenido
al revés de lo que el método declara medir no es un hallazgo, es un recordatorio
de que el SAM contra una sola firma no es un clasificador litológico.

#### Hipótesis, sin elegir entre ellas

Tres explicaciones compatibles con lo medido, ninguna descartada con los datos
de hoy:

1. **La arcilla expuesta está en los botaderos, no en la roca *in situ*.** Es lo
   que apuntan las 130 detecciones sobre `Depositos antropicos, botaderos de
   mina` (sección 10.3). Si es así, la verdad de terreno declara positivo el
   lugar equivocado —no porque esté mal construida, sino porque la cartografía
   litológica no es un mapa de alteración.
2. **Barniz del desierto y costra superficial enmascaran la firma.** La
   alteración *in situ* llevaría decenas de miles de años expuesta; el material
   de mina, décadas.
3. **9 bandas a 20 m no bastan.** El doblete Al–OH de la caolinita vive en
   2160/2200 nm y Sentinel-2 lo muestrea con una sola banda ancha (B12, centrada
   en 2185,7 nm en S2B). Separar caolinita de otras superficies con un solo
   punto dentro del rasgo es pedirle al sensor algo para lo que no está hecho.

La única exploración legítima de la primera hipótesis es una **segunda corrida
documentada** con los botaderos declarados positivo, reportada aparte y marcada
como análisis de sensibilidad. **No reemplaza la corrida principal**, y no se ha
hecho en este trabajo.

### 11.2 Por qué el ambiguo se excluye y no se colapsa a negativo

La regla vive en un solo sitio, `preparar_pares`, y eso es lo que impide que una
función la aplique y otra no. Un píxel entra al cálculo solo si su verdad de
terreno es positivo o negativo, su puntaje no es `NaN` y —si se pasa `--scene`—
la máscara del Scene lo declara válido.

El `255` significa «la cartografía no dice»; el `0` significa «la cartografía
dice que no hay». Colapsarlos convierte una ausencia de información en evidencia
negativa. Sobre este AOI, donde el 93,92 % del área es ambigua, esa sustitución
regala 3.756.783 verdaderos negativos: la exactitud saltaría del 79,12 % actual
al 98,73 % **sin que el detector acierte un solo píxel más**, y ninguna función
lanzaría una excepción. Es el argumento que ya justifica la clase `ambiguo` en
la sección 9.3, aplicado al cálculo en vez de a la construcción de la capa.

Los descartes se cuentan **con precedencia** (ambiguo → NaN en la verdad de
terreno → NaN en el puntaje → máscara), de modo que las cuatro causas más los
evaluados sumen exactamente los 4.000.000 de píxeles del AOI. Un desglose donde
las causas se solapan no cuadra con el total y obliga a quien lee la tabla a
adivinar si falta algo.

### 11.3 La dirección del puntaje es un argumento obligatorio

`roc_auc` y `curva_roc` exigen `higher_is_better` **sin valor por defecto y solo
por palabra clave**. Es la decisión de diseño más importante del módulo.

El puntaje del SAM es el ángulo espectral, donde menor es más evidencia. Un AUC
calculado con la dirección invertida da `1 - AUC`: **0,7597 en vez de 0,2403**.
Los dos son números válidos, ninguno lanza una excepción y los dos se pueden
defender en una presentación. Es el error más caro que puede cometer este
módulo, y es invisible en la salida.

De las dos salidas posibles —un parámetro explícito, o exigir que el llamador
pase el puntaje ya orientado— se eligió el **parámetro explícito**:

1. Un valor por defecto reintroduce exactamente el fallo que se quiere evitar.
   Sin default, el llamador no puede omitir la decisión.
2. `Detector.higher_is_better` ya existe como atributo del contrato (sección 8),
   así que la dirección viaja desde su única fuente de verdad:
   `scripts/evaluate.py` la lee de `DETECTORS[nombre].higher_is_better`, no de
   una constante escrita en el script.
3. Exigir el puntaje pre-orientado mueve la inversión de signo al llamador, o
   sea la duplica en cada sitio que mida, y deja mapas de ángulos negados dando
   vueltas por el código.
4. Por palabra clave, para que no pueda ocupar por posición el lugar de otro
   booleano.

Los umbrales que devuelve `curva_roc` salen **en las unidades originales del
puntaje**, no en las del puntaje orientado, porque su uso inmediato es
compararlos con `angle_threshold_rad` del config. Devolverlos negados obligaría
a que quien lee la figura recordara invertirlos.

### 11.4 Convención de empates del AUC

Se calcula por el estadístico de Mann-Whitney U con **rangos promedio**: los
píxeles con el mismo puntaje reciben todos el rango medio de su grupo. Es
idéntico a integrar la curva ROC con la **regla del trapecio** —cada grupo de
empates aporta el rectángulo medio y no un escalón— y es la misma convención de
`sklearn.metrics.roc_auc_score`.

Importa aquí, y no es una precaución teórica: el ángulo es continuo, pero se
almacena en `float32`, y sobre 242.967 píxeles evaluables hay solo 238.202
valores distintos, o sea **4.765 empates reales**. Resolverlos «a favor»
inflaría el AUC sin que nada fallara.

Por el mismo motivo `curva_roc` corta solo en el último índice de cada grupo de
empates: un corte dentro de un grupo daría un punto de la curva que ningún
umbral real puede alcanzar.

### 11.5 F1 e IoU sin ninguna detección devuelven 0,0

Es el caso que ocurre de verdad con este dataset, así que la decisión no es
académica. Con `VP = FP = 0` la precisión es 0/0, pero el recall es 0 y el F1
por su fórmula directa `2·VP / (2·VP + FP + FN)` también vale 0.

Se eligió `0.0` sobre `ValueError` porque lanzar obligaría a envolver la corrida
principal —la que hay que poder reportar— en un `try/except` cuyo único trabajo
sería imprimir un cero, y porque un detector que no detecta nada tiene
rendimiento nulo, no rendimiento indefinido. Se eligió `0.0` sobre `nan` porque
un `nan` se propaga en silencio a cualquier promedio o comparación posterior.

El caso genuinamente indefinido —ni positivos reales ni predichos— también
devuelve `0.0`: un conjunto sin un solo positivo real no es evidencia de acierto
perfecto. Ese conjunto ya lo rechaza `roc_auc`, que **lanza `ValueError` cuando
hay una sola clase presente** en vez de devolver `nan`. El AUC mide la capacidad
de ordenar positivos por delante de negativos; con una sola clase no hay ningún
par que ordenar, y un `nan` devuelto ahí acaba impreso en una tabla como si
fuera una medición.

### 11.6 NumPy puro en producción, `sklearn` solo como oráculo de test

Las cinco métricas están implementadas con NumPy, sin `scikit-learn` en el
camino de producción, por el mismo criterio de la sección 8: los tests las
contrastan contra literales calculados a mano, no contra otra implementación. Un
test que compara dos librerías solo demuestra que ambas coinciden, no que alguna
acierta.

`sklearn` sí aparece en `tests/test_metrics.py` como contraste **adicional**,
bajo `pytest.importorskip`, sobre 500 valores redondeados a 2 decimales para
forzar empates masivos: es donde las convenciones se separan, y comprobar que
coinciden ahí valida la decisión de 11.4 sin convertirla en la definición de lo
correcto.
