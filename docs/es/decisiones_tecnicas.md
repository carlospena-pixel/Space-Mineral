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

**`meta` es documentación, no configuración.** Nada del pipeline lee de `meta`
para decidir qué hacer. Registra de dónde salió el cubo: `safe_name`,
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

### `SAM_BANDS` — 9 bandas, declarado y todavía no consumido

```
B2, B3, B4, B5, B6, B7, B8A, B11, B12
```

Es el subconjunto que consumirá el detector espectral. Hoy **solo está
declarado**: ningún módulo lo importa. La razón de declararlo antes de usarlo es
dejar la decisión escrita y testeada mientras el pipeline no existe.

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
| Tile | `T19KDT` (Pampa del Tamarugal, Región de Tarapacá) |
| Producto | `S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE` |
| CRS | EPSG:32719 (UTM 19S) |
| Ventana AOI | `col_off=1000, row_off=1000, width=2000, height=2000`, en la grilla de 20 m |
| Extensión | 40 × 40 km |
| Bbox WGS84 | `[-69.7673, -20.4377, -69.383, -20.075]` |

**La ventana en píxeles es la definición autoritativa; el bbox es informativo.**
La ventana define un recorte exacto y reproducible sobre la grilla del tile,
mientras que el bbox pasa por una reproyección y termina redondeado. Cuando se
pasa un bbox a `build_scene_from_safe`, se reproyecta con `transform_bounds`,
se convierte a ventana y se redondea con `round_offsets().round_lengths()`.
Ambos valores conviven en `configs/tamarugal_kaolinite.yaml` con esa jerarquía
anotada.

**La zona cambió respecto del plan original.** El proyecto apuntaba al distrito
de Chuquicamata (Calama, Región de Antofagasta); se movió a Pampa del Tamarugal
por disponibilidad de datos. El config `chuqui_kaolinite.yaml` quedó obsoleto y
fue renombrado a `tamarugal_kaolinite.yaml`. Solo hay una versión válida de este
dato: cualquier mención a Chuquicamata como zona de estudio activa en otro
archivo del repositorio es un residuo y debe corregirse.

La escena está prácticamente despejada: 99,9977 % de píxeles válidos en el AOI,
99,92 % clasificados como suelo desnudo. Es una condición deliberada —desierto
absoluto, sin vegetación ni nubes— porque el objetivo es detectar una firma
mineral en superficie y cualquier cobertura la enmascara.

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

Hay **dos mediciones a dos escalas distintas**, y se conservan las dos porque
dicen cosas diferentes. Ninguna reemplaza a la otra: la primera es la que se
hizo en Semana 2 sobre una submuestra, y la segunda es la del AOI que el
pipeline recorre hoy de extremo a extremo.

**Ventana de 256×256 px** (65.536 píxeles, 100 % válidos, todos suelo desnudo),
con el cubo enmascarado:

| bandas | mín | mediana | máx | bajo umbral 0,1 |
|--------|-----|---------|-----|-----------------|
| `SAM_BANDS` (9)   | 0,164 | 0,250 | 0,453 | 0 de 65.536 |
| `BAND_ORDER` (12) | 0,166 | 0,247 | 0,426 | 0 de 65.536 |

**AOI completo, 2000×2000 px** (3.999.908 píxeles válidos de 4.000.000, o sea
99,9977 %). Sale del resumen que imprime
`python scripts/run_pipeline.py --config configs/tamarugal_kaolinite.yaml`:

| bandas | mín | p1 | mediana | máx |
|--------|-----|----|---------|-----|
| `SAM_BANDS` (9) | 0,0723 | 0,2055 | 0,2742 | 0,6971 |

| umbral (rad) | píxeles | % del AOI válido |
|--------------|---------|------------------|
| 0,05 | 0 | 0,000 % |
| 0,08 | 5 | 0,000 % |
| 0,10 | **62** | 0,002 % |
| 0,15 | 4.513 | 0,113 % |
| 0,20 | 30.885 | 0,772 % |

Las dos tablas del AOI completo tienen **solo la fila de 9 bandas**: el
pipeline corre `SAM_BANDS` y es lo único que hay medido a esta escala. No se
repitió el experimento con `BAND_ORDER` sobre los 4 millones de píxeles, así
que esa fila no existe y no se estima.

#### Por qué las dos mediciones difieren tanto

El mínimo pasa de 0,164 a 0,0723 y el umbral de 0,1 pasa de dejar 0 píxeles a
dejar 62. Son dos efectos que actúan en el mismo sentido y que esta medición no
separa:

1. **Hay ~61 veces más muestras.** El mínimo de una muestra es un estadístico
   de orden extremo: crece hacia el centro de la distribución cuando hay pocas
   observaciones, simplemente porque la cola inferior no está poblada. 65.536
   píxeles no alcanzan para que aparezcan los 62 casos que en 3.999.908 caen
   bajo 0,1 —son 16 por cada millón—, y en una submuestra de ese tamaño lo
   esperable es encontrar cero aunque existan.
2. **El AOI completo es más heterogéneo.** La ventana chica son 5,12 × 5,12 km
   de suelo desnudo homogéneo; los 40 × 40 km del AOI incluyen la red de
   drenaje, el piedemonte, el pueblo y los campos regados. Que la mediana
   también se corra (0,250 → 0,2742) y que el máximo casi se duplique (0,453 →
   0,6971) es la señal de que no es solo tamaño muestral: son superficies que
   la ventana no contenía.

**Lo que se concluiría mal generalizando la ventana chica al AOI completo** es
que ningún umbral razonable separa nada y que la vía del SAM está agotada: con
0,15 rad quedan 4.513 píxeles, que es una población con la que sí se puede
trabajar. Y al revés, calibrar el umbral contra la ventana de 256×256 px
significaría ajustarlo sobre un recorte que no contiene la cola inferior que se
quiere detectar. Toda cifra de ángulo de este proyecto tiene que decir sobre
qué ventana se midió; sin ese dato no es comparable con ninguna otra.

#### La conclusión no cambia

`configs/tamarugal_kaolinite.yaml` fija `angle_threshold_rad: 0.1`. **Ese valor
sigue sin criterio de calibración**, y no se cambia en este trabajo a propósito:
hay que reemplazarlo por un criterio, no por otro número elegido a ojo. Que
ahora deje 62 píxeles en vez de 0 no lo valida —solo muestra que el 0 anterior
era un artefacto del tamaño de la ventana—.

**62 píxeles de 3.999.908 no son una detección de caolinita.** El ángulo
espectral mide parecido contra una firma de laboratorio, no presencia de un
mineral: cualquier superficie que en 9 bandas se le parezca cae igual de bajo.
Mientras `validation/` siga sin verdad de terreno (etapa 9 del
[pipeline](pipeline.md)) no hay con qué estimar cuántos de esos píxeles son el
mineral. La figura del notebook muestra el mecanismo sobre la ventana chica: la
referencia cae en picada de B11 a B12 por la absorción Al–OH y ninguno de los
dos píxeles graficados la acompaña.

Sobre la ventana de 256×256 px, las dos distribuciones —9 y 12 bandas— son
prácticamente la misma, que es lo esperado y no un argumento a favor de
ninguna. Quitar B1, B8 y B9 no cambia el resultado sobre desierto despejado
porque ahí las tres aportan poca varianza útil. La razón para preferir 9 sigue
siendo la de la sección 2, no el rendimiento; lo que este número aporta es que
el recorte **no cuesta nada**, que es lo que había que comprobar antes de
fijarlo.

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

### Deuda abierta: la dirección del puntaje

`Detector.predict` documenta «a mayor valor, mayor evidencia» y `SAM.predict`
devuelve un ángulo, donde **menor es más parecido**.

**No se resuelve en esta semana, a propósito.** Invertir el signo de SAM a mitad
de sprint rompería el pipeline y la visualización del Track A sin lanzar ningún
error: los mapas se seguirían dibujando, con la escala de color al revés. Y SAM
no es el que se desvía: el documento 05 define el puntaje como el ángulo, y
`viridis_r`, `angle_threshold_rad` y el `<=` de `threshold()` ya asumen esa
dirección. El que quedó redactado para un puntaje que ningún detector produce
todavía es el contrato de la sección 1.2.

Las dos salidas posibles:

1. Reescribir el contrato para admitir puntajes con **dirección declarada por
   cada detector** (un atributo de clase del tipo `higher_is_better`).
2. Normalizar todos los detectores a «mayor es mejor». Para SAM sería devolver
   el coseno en vez del ángulo, lo que además elimina el piso de error de
   `arccos` en los extremos, pero obliga a reescribir `threshold`, los configs y
   los mapas.

**Fecha de revisión: al cerrar la Semana 4, y en todo caso antes del primer
commit del segundo detector (Nivel 2, Random Forest).** A partir de ahí el
pipeline tiene que comparar puntajes de algoritmos distintos, y necesita saber
qué significan.
