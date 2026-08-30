# Track B — Semana 4 (validación: `metrics.py`, barrido de umbral, E3/E4/E5)

Fecha de redacción: 30 de agosto de 2026. Roadmap original: Semana 4 = 10–16 de
agosto. **Vamos con atraso de calendario**; el alcance de abajo está recortado a
lo que se puede cerrar sin la verdad de terreno, que hoy no existe en el repo.

---

## Paso 0 — Auditoría del estado real antes de escribir código

Verificado leyendo el repo el 30/08/2026 (rama `main`, árbol de trabajo).

### Lo que SÍ está cerrado (VERIFICADO, leído en el código)

| Semana | Track B | Evidencia en el repo |
|---|---|---|
| 0 | Esqueleto, contratos, CI | `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/tests.yml`, `docs/es/decisiones_tecnicas.md` |
| 1 | Firma de caolinita desde splib07 | `spectral/usgs_library.py`, `spectral/endmembers.py`, `outputs/figures/kaolinite_signature.png` |
| 2 | Alineamiento banda↔firma, λ de ESA | `config.py` (`BAND_WAVELENGTHS_NM`, `SAM_BANDS`), `validate_raw_band_order()`, `tests/test_endmembers.py` |
| 3 | SAM endurecido + casos analíticos | `algorithms/sam.py`, `tests/test_sam.py` (24 tests), `decisiones_tecnicas.md` §8 |
| 3 (A) | Pipeline de punta a punta | `pipeline.py`, `io/raster_io.write_geotiff`, `visualization/maps.plot_score_map` |

El estándar de código es alto y consistente: docstrings numpydoc en español sin
tildes, comentarios que justifican la decisión no obvia con su modo de falla,
validaciones que fallan ruidosamente. **La Semana 4 tiene que sostener ese nivel,
no bajarlo.**

### Lo que NO está y bloquea parte de la Semana 4

1. **No hay verdad de terreno. Ni un archivo.** `data/external/` contiene
   únicamente `S07SNTL2_Kaolinite_CM9_BECKb_AREF.txt` (la firma USGS).
   `validation/geology.py` sigue siendo dos `NotImplementedError`. Es Track A
   (Camila). **Sin esa capa, E4 (F1/IoU/AUC/kappa contra verdad) y E3
   (enriquecimiento espacial) no tienen entrada real.** VERIFICADO.

2. **La zona cambió y la verdad de terreno planificada no cubre el AOI.** El plan
   maestro y el roadmap fijan Chuquicamata/Calama y la **Carta Calama 1:50.000**
   del SERNAGEOMIN como verdad de terreno. El experimento real corre sobre
   `T19KDT`, Pampa del Tamarugal (bbox ≈ −69,77/−20,44 a −69,38/−20,08).
   La Carta Calama no cubre ese cuadrante. VERIFICADO (el cambio de zona está
   documentado en la cabecera de `configs/tamarugal_kaolinite.yaml`); INFERIDO
   que la carta no cubre el AOI, por las coordenadas. **Riesgo alto**: E3 exige
   "zonas de alteración documentadas" y hoy no hay evidencia en el repo de que
   el AOI tenga ninguna. Esto es lo primero que tienen que resolver con Camila,
   y no es un problema de código.

3. **Los artefactos de la Semana 3 no están en disco.** `data/interim/` está
   vacío y `outputs/maps/` solo tiene `.gitkeep`. El `.npz` del `Scene` y el
   GeoTIFF de ángulos son regenerables (y por eso están en `.gitignore`), pero
   la Semana 4 los consume: hay que correr el pipeline antes de medir nada.
   VERIFICADO.

4. **`validation/metrics.py` sigue en cinco `NotImplementedError`** y no existe
   `tests/test_metrics.py`. La sección opcional del prompt de la Semana 3 no se
   ejecutó. VERIFICADO.

### Las tres trampas técnicas de esta semana

**(a) La dirección del puntaje en la curva ROC.** SAM devuelve un ángulo:
*menor* es más parecido. `roc_auc(y_true, y_score)` asume por convención que
*mayor* es más positivo. Si le pasan el ángulo crudo, el AUC sale **invertido**
(0,18 en vez de 0,82) y no lanza ningún error: es un número plausible en el rango
correcto. Es exactamente la deuda que `algorithms/base.py` dejó anotada "para
antes del segundo detector" — llegó antes, por las métricas. Hay que resolverla
esta semana, explícitamente y por escrito.

**(b) El barrido de umbral ya existe, hardcodeado, en el archivo equivocado.**
`pipeline.py` tiene `THRESHOLD_SWEEP = (0.05, 0.08, 0.10, 0.15, 0.20)`.
`pipeline.py` es Track A. El barrido de la Semana 4 —el que produce la curva ROC
y elige el umbral— es Track B y **no debe implementarse ampliando esa constante**.

**(c) Los píxeles no son independientes.** Un F1 o un AUC por píxel sobre
4 millones de píxeles espacialmente autocorrelacionados exagera la significancia:
el tamaño de muestra efectivo es mucho menor que el número de píxeles. Esto no se
arregla con código, se declara en la documentación.

### El dato que define el alcance realista

Medición de la Semana 3 sobre 3.999.908 píxeles válidos (README, VERIFICADO):
ángulo mínimo 0,0723 rad, mediana 0,2742 rad. Bajo el umbral del config
(0,10 rad) caen **62 píxeles de 4 millones** (0,002 %). El README ya lo dice sin
adornos: *nada de eso es caolinita detectada*. La Semana 4 no va a convertir eso
en una detección; va a **medir cuán poco es**, con números defendibles. Ese es el
entregable honesto y es el que vale en una entrevista.

### Estudio previo

El roadmap dice "bloque conceptual 5 del documento 04". En el documento 04 ese
bloque se titula **Bloque 4 (Semana 4) — Validación y métricas** (es el quinto
contando el Bloque 0). No hay ambigüedad: es el de matriz de confusión, F1, IoU,
ROC/AUC, kappa, clay ratio y enriquecimiento espacial. Las dos preguntas de
control que hay que poder responder sin ayuda antes de pedir código:

1. Si mi detección tiene recall alto y precisión baja, ¿qué significa para un
   geólogo que va a muestrear en terreno?
2. ¿Por qué reporto AUC además de F1? ¿Qué me dice el AUC que el F1 no?

---

## Prompt para Claude Code — Track B, Semana 4

> Copiar todo lo que está entre las líneas `---` y pegarlo en Claude Code abierto
> en la raíz del repo.

---

Trabajo en el repo `Space-Mineral` (detección de caolinita con Sentinel-2 + SAM).
Soy Carlos y me toca el **Track B de la Semana 4: validación y métricas**. Camila
trabaja en paralelo en el Track A (rasterizar la verdad de terreno desde el
SERNAGEOMIN) sobre el mismo repo.

Antes de escribir una sola línea, lee estos archivos para tener el contexto real
y no inventar contratos:

- `README.md` — sección «Detección: un mapa de ángulos sin validar»: ahí están
  las cifras medidas del mapa (mínimo 0,0723 rad, mediana 0,2742 rad, 62 px bajo
  0,10 rad de 3.999.908 válidos). Son el punto de partida, no algo a mejorar.
- `docs/es/decisiones_tecnicas.md` — secciones 1 (contratos), 7 (comparación de
  firmas y el umbral que no detecta nada) y 8 (el detector SAM)
- `docs/es/pipeline.md` — tabla de estado y etapa 7 (validación)
- `src/mineralmap/validation/metrics.py` y `validation/geology.py` — los stubs
  que voy a tocar y el que NO voy a tocar
- `src/mineralmap/algorithms/base.py` — la deuda de dirección del puntaje anotada
  en el docstring de `Detector.predict`. Es central esta semana.
- `src/mineralmap/algorithms/sam.py` — `predict` y `threshold`
- `src/mineralmap/pipeline.py` — `THRESHOLD_SWEEP`, `_barrido_de_umbrales`,
  `_estadisticas_del_mapa`. **Léelo para no duplicarlo ni ampliarlo.**
- `src/mineralmap/config.py` — `BAND_ORDER`, `SAM_BANDS`, `band_wavelengths`
- `src/mineralmap/io/raster_io.py` — `Scene`, `load_scene`, `write_geotiff`
- `src/mineralmap/preprocessing/masking.py` — `apply_mask`, y su estilo de
  `ValueError`, que es el estándar a imitar
- `tests/test_sam.py` y `tests/test_masking.py` — el estándar de test del repo
- `docs/prompts/semana3_trackB_sam.md` — el prompt de la semana pasada; mismas
  reglas de estilo y de git

### Objetivo del hito

Dejar el proyecto con **una biblioteca de métricas verificada contra casos de
valor conocido a mano**, y con las dos partes de la validación que **no dependen
de la verdad de terreno** ya medidas sobre la escena real: el barrido de umbral y
el contraste con líneas base (E5). Al cerrar:

- `validation/metrics.py` implementado, sin `NotImplementedError`, sin depender
  de `Scene` ni de rasterio: entra `numpy`, sale `numpy`/`float`.
- `spectral/indices.py` nuevo, con el clay ratio B11/B12.
- `tests/test_metrics.py` nuevo, con casos calculables en papel.
- `scripts/sweep_threshold.py` nuevo: produce la tabla de métricas en
  `outputs/tables/`.
- E5 medido sobre la escena real: acuerdo SAM ↔ clay ratio, y SAM contra baseline
  aleatorio.
- E3 y E4 **implementados y testeados con datos sintéticos**, y declarados
  BLOQUEADOS sobre la escena real hasta que exista la verdad de terreno.

### Lo que este track NO hace, y no es negociable

1. **No inventes verdad de terreno.** No hay ningún archivo de SERNAGEOMIN en el
   repo (`data/external/` solo tiene la firma USGS de caolinita). No descargues
   uno, no dibujes polígonos "de ejemplo" sobre el AOI, no uses el clay ratio
   como si fuera verdad de terreno, y no generes una capa de verdad sintética que
   pueda terminar guardada en `data/` y confundirse después con una real. Los
   datos sintéticos de esta semana viven **solo dentro de `tests/`**.
2. **No cambies el umbral del config.** `angle_threshold_rad: 0.1` se queda como
   está. El barrido produce la evidencia para elegirlo; elegirlo es una decisión
   mía, con Camila, cuando exista la verdad de terreno.
3. **No toques `pipeline.py` ni `THRESHOLD_SWEEP`.** Es archivo del Track A y su
   barrido cumple otra función (resumen de la corrida). El barrido fino de la
   validación va en el módulo nuevo.
4. **No maquilles el resultado.** Si el acuerdo entre SAM y el clay ratio sale
   cercano a cero, eso es el hallazgo y se reporta así. La medición honesta de un
   resultado pobre vale más que un número inflado.

### Alcance: SOLO estos archivos

Míos en esta tarea:

`src/mineralmap/validation/metrics.py`, `src/mineralmap/spectral/indices.py`
(nuevo), `tests/test_metrics.py` (nuevo), `tests/test_indices.py` (nuevo),
`scripts/sweep_threshold.py` (nuevo), `docs/es/decisiones_tecnicas.md`,
`docs/en/technical_decisions.md`, `CHANGELOG.md`, `README.md`.

**No toques nada de esta lista, ni para arreglar un import, ni para formatear, ni
para corregir un typo:**

`src/mineralmap/pipeline.py`, `src/mineralmap/io/raster_io.py`,
`src/mineralmap/visualization/maps.py`, `src/mineralmap/validation/geology.py`,
`src/mineralmap/algorithms/base.py`, `src/mineralmap/algorithms/sam.py`,
`scripts/run_pipeline.py`, `scripts/evaluate.py`, `configs/*.yaml`, `.gitignore`,
`tests/test_maps.py`, `tests/test_raster_io.py`, `tests/test_pipeline.py`,
`tests/test_sam.py`.

Si crees que hay que cambiar algo ahí, **párate y dímelo en vez de cambiarlo.**

### Contratos que NO se negocian

1. **`metrics.py` no conoce el proyecto.** Sus funciones reciben arrays de numpy
   y devuelven números o arrays. Nada de `Scene`, nada de rasterio, nada de rutas.
   Es lo que permite testearlas sin la escena y reusarlas con Random Forest en
   Nivel 2.
2. **Las firmas existentes de `metrics.py` mandan**: `confusion_matrix(y_true,
   y_pred)`, `f1_score(y_true, y_pred)`, `iou_score(y_true, y_pred)`,
   `roc_auc(y_true, y_score)`, `cohen_kappa(y_true, y_pred)`. Puedes agregar
   parámetros con valor por defecto y funciones nuevas; no renombres ni cambies
   el orden de los que ya están.
3. **Los `NaN` son píxeles inválidos, no ceros.** El mapa de ángulos llega con
   `NaN` en lo enmascarado (nubes, agua, norma cero). Toda métrica tiene que
   excluirlos del denominador, no imputarlos. Un `np.nan_to_num` los convertiría
   en ángulo 0, o sea en las detecciones más fuertes del mapa: es el mismo error
   que `threshold()` documenta y evita.
4. **La dirección del puntaje se declara, no se adivina** (ver §1 abajo).

### Trabajo a realizar

#### 1. Resolver la dirección del puntaje, y hacerlo por escrito

Esta es la decisión de diseño de la semana y va **antes** que el código.

`Detector.predict` documenta «a mayor valor, mayor evidencia». `SAM.predict`
devuelve un ángulo, donde menor es más parecido. La deuda quedó anotada en
`base.py` con fecha de revisión «antes del segundo detector». Las métricas llegan
primero: `roc_auc(y_true, y_score)` asume por convención que mayor = más
positivo, y pasarle el ángulo crudo devuelve un AUC **invertido** (0,18 donde
debería decir 0,82) sin lanzar nada. Es un número plausible, en el rango
correcto, y completamente al revés.

Implementa la opción **A** salvo que encuentres un argumento mejor, en cuyo caso
párate y dímelo antes de codificar:

- **A (mínima e inmediata):** `roc_auc(y_true, y_score, greater_is_better=True)`.
  Con `False`, la función niega internamente el puntaje antes de rankear. Quien
  llama con un ángulo pasa `greater_is_better=False` explícitamente. El parámetro
  no tiene default silencioso que "haga lo correcto": el default es la convención
  estándar, y usar un ángulo obliga a escribirlo. Documenta en el docstring qué
  pasa si se omite, con el número concreto.
- **B (de fondo, NO esta semana):** normalizar los detectores a "mayor es mejor"
  devolviendo el coseno. Rompería `viridis_r`, `angle_threshold_rad` y el `<=` de
  `threshold()` sin lanzar ningún error. **No la hagas.** Déjala anotada.

La resolución se anota en `docs/es/decisiones_tecnicas.md` §8. **No edites el
párrafo de deuda de `algorithms/base.py`**: ese archivo queda fuera de alcance
esta semana y su docstring lo lee el Track A. Dime al final qué habría que
cambiar ahí y lo hago en un commit aparte, coordinado.

#### 2. `validation/metrics.py`

Implementa, en este orden y con tests que acompañen a cada una:

- `confusion_matrix(y_true, y_pred, valid=None)` → devuelve los cuatro conteos
  (TP, FP, FN, TN) en una estructura explícita (un `dict` o un `NamedTuple`, no
  una tupla pelada de cuatro enteros que se pueden ordenar mal al desempacar).
  `valid` es una máscara booleana opcional: donde es `False`, el píxel no entra
  en ningún conteo. Si es `None`, entran todos.
- `precision_recall(y_true, y_pred, valid=None)` — decide y documenta qué
  devuelve cuando el denominador es cero (sin detecciones no hay precisión).
  `np.nan` es defendible; `0.0` afirma "precisión perfecta al revés" y es
  mentira. Elige uno y justifícalo en el docstring.
- `f1_score(...)`, `iou_score(...)` — construidas sobre las anteriores, no
  recalculando la matriz por su cuenta.
- `cohen_kappa(...)` — con la fórmula escrita en el docstring y el término de
  acuerdo esperado por azar explicado. En un problema con 0,002 % de positivos,
  kappa se comporta de forma poco intuitiva: dilo.
- `roc_curve(y_true, y_score, valid=None, greater_is_better=True)` → devuelve
  (fpr, tpr, umbrales) barriendo **todos** los umbrales relevantes, no una grilla
  arbitraria de cinco valores.
- `roc_auc(...)` — por regla del trapecio sobre la curva anterior.
- `spatial_enrichment(detection, zones, valid=None)` (E3) → la razón entre la
  tasa de detección dentro de `zones` y la tasa fuera. Documenta qué significa 1
  (ninguna preferencia espacial), qué devuelve si no hay píxeles fuera, y por qué
  esta razón —y no la fracción cruda de detecciones dentro— es la métrica: la
  fracción cruda depende del tamaño de la zona y una zona que cubra el 90 % del
  AOI daría 0,9 aunque las detecciones fueran al azar.
- `agreement(mask_a, mask_b, valid=None)` (E5) → IoU y kappa entre dos máscaras
  binarias, sin asumir que una es verdad y la otra predicción. El clay ratio no
  es verdad de terreno; es una segunda opinión.

**Sobre `scikit-learn`:** está en las dependencias del proyecto. **Implementa las
métricas con numpy de todos modos** —son diez líneas cada una y tengo que poder
explicarlas en un code review— y usa sklearn **solo dentro de los tests**, como
oráculo independiente: `assert mi_f1 ≈ sklearn.metrics.f1_score(...)`. Así los
tests comparan contra una implementación de referencia sin que el código de
producción dependa de ella.

#### 3. `spectral/indices.py` (nuevo) — el clay ratio

`clay_ratio(cube, band_names)` → mapa 2D de B11/B12.

Por qué va en `spectral/` y no en `validation/`: es un índice espectral derivado
de la reflectancia, del mismo tipo que la firma de referencia; `validation/` es
comparación de máscaras. Meterlo en `metrics.py` obligaría a ese módulo a conocer
nombres de banda y rompería el contrato 1.

Detalles que no puedes saltarte:

- Recibe el cubo y `band_names`, y localiza B11 y B12 **por nombre**, no por
  índice fijo. El cubo llega a veces con las 12 bandas de `BAND_ORDER` y a veces
  con las 9 de `SAM_BANDS`: un índice fijo apunta a otra banda según cuál sea.
  `ValueError` si falta alguna de las dos, nombrando cuál.
- División por cero y `NaN`: B12 = 0 → `NaN` en ese píxel, no `inf`. Usa
  `np.errstate` como hace `sam.py`.
- Documenta la dirección: en la caolinita, B12 cae por la absorción Al–OH y B11
  es el hombro, así que el ratio B11/B12 **sube** donde hay arcilla. Es la
  dirección contraria al ángulo SAM, y por eso al cruzarlos hay que umbralizar
  cada uno en su propio sentido. Dilo en el docstring con esas palabras: es
  exactamente el error que voy a cometer dentro de dos semanas si no está escrito.
- El umbral del clay ratio no tiene un valor canónico. Deriva la máscara de
  arcilla por **percentil** del propio mapa (ej.: el 0,002 % superior, la misma
  tasa de positivos que SAM bajo 0,10 rad), no por un número absoluto inventado.
  Comparar dos máscaras con tasas de positivos muy distintas hace que el IoU mida
  la diferencia de tamaño y no el acuerdo espacial. Justifícalo en el código.

#### 4. `tests/test_metrics.py` y `tests/test_indices.py`

El estándar es el de `tests/test_sam.py`: casos cuyo valor exacto se conoce
**por construcción**, no por comparación con otra corrida.

Mínimo:

- Una matriz de confusión 2×2 escrita a mano con sus cuatro conteos, y el F1, el
  IoU y el kappa calculados en papel para esos mismos números.
- Clasificador perfecto → F1 = 1, IoU = 1, kappa = 1, AUC = 1.
- Clasificador que invierte todo → AUC = 0. **Este es el test que atrapa la
  dirección del puntaje** y tiene que existir con ese nombre.
- Puntaje aleatorio no correlacionado → AUC ≈ 0,5 con tolerancia declarada y
  semilla fija.
- `NaN` en el puntaje y máscara `valid`: los píxeles inválidos no entran en
  ningún conteo. Comprueba que meter mil píxeles `NaN` adicionales no cambia
  ninguna métrica.
- Caso degenerado: cero detecciones (que es el régimen real de este proyecto).
  Ninguna métrica puede lanzar una excepción no controlada ahí.
- Caso degenerado: `y_true` todo `False` → el AUC no está definido; decide qué
  hace y testéalo.
- Enriquecimiento: detecciones todas dentro de la zona → razón alta; detecciones
  repartidas en proporción al área → razón ≈ 1.
- Oráculo sklearn para F1, IoU (`jaccard_score`), kappa y AUC sobre un caso
  aleatorio con semilla fija.
- Clay ratio: cubo sintético donde B11 y B12 se conocen → ratio exacto;
  B12 = 0 → `NaN`; falta B11 → `ValueError`; cubo de 9 bandas y cubo de 12 bandas
  con las mismas B11/B12 dan **el mismo** mapa (el test que blinda la búsqueda
  por nombre).

#### 5. `scripts/sweep_threshold.py` (nuevo) — la tabla del hito

CLI que **no toca `pipeline.py`**. Toda la lógica reusable vive en los módulos;
el script parsea argumentos, llama e imprime, igual que `run_pipeline.py`.

```
python scripts/sweep_threshold.py --config configs/tamarugal_kaolinite.yaml
```

Qué hace:

1. Carga el `Scene` desde `data/interim/scene.npz` con `load_scene` y el mapa de
   ángulos desde el GeoTIFF con `rasterio`. **Si alguno no existe, aborta con un
   mensaje que diga exactamente qué comando correr para generarlo**
   (`python scripts/run_pipeline.py --config ...`). No lo regeneres tú: son
   minutos de lectura del `.SAFE`.
2. Verifica que la forma del GeoTIFF calza con la del `Scene` y aborta si no.
   Un mapa de otra ventana produciría una tabla impecable sobre el terreno
   equivocado.
3. Barre el umbral de ángulo sobre un rango derivado del **propio mapa** (de su
   mínimo a su mediana, con paso declarado), no sobre cinco números fijos, y para
   cada umbral reporta: umbral, píxeles detectados, % del AOI válido, y —cuando
   haya verdad de terreno— precisión, recall, F1, IoU, kappa.
4. Calcula el clay ratio, deriva su máscara por percentil a la misma tasa de
   positivos y reporta el acuerdo con SAM (IoU y kappa). **E5, medible hoy.**
5. Baseline aleatorio: máscara aleatoria con **la misma tasa de positivos** que
   SAM, semilla fija y declarada en la salida. Reporta el mismo acuerdo contra
   el clay ratio que reportaste para SAM. **La comparación que importa es
   SAM-vs-clay contra aleatorio-vs-clay**: sin verdad de terreno, la única
   afirmación defendible es «SAM coincide con el clay ratio más / igual / menos
   que el azar». Escríbelo así en la salida, sin prometer más.
6. Escribe la tabla en `outputs/tables/` como CSV (crea el directorio con un
   `.gitkeep` si no existe) y la imprime. Si resulta que `outputs/tables/` cae
   bajo alguna regla de `.gitignore`, **párate y dímelo**: no puedo tocar ese
   archivo esta semana.
7. Verdad de terreno: acepta `--truth <ruta a GeoTIFF>` **opcional**. Si no se
   pasa —el caso de hoy— el script corre igual, calcula todo lo que no la
   necesita, y dice en una línea explícita qué métricas quedaron sin calcular y
   por qué. Nada de rellenar E3/E4 con ceros ni con `None` silenciosos.

#### 6. Documentación

- `docs/es/decisiones_tecnicas.md` y su espejo en inglés: sección nueva de
  validación. Qué mide cada criterio (E3, E4, E5), la decisión de dirección del
  puntaje con el número concreto del AUC invertido, por qué el clay ratio se
  umbraliza por percentil, y **la advertencia de autocorrelación espacial**: los
  píxeles vecinos no son independientes, así que el tamaño de muestra efectivo es
  mucho menor que los 4 millones de píxeles y un F1 o un AUC calculado por píxel
  exagera la significancia. Es una limitación honesta del método, va escrita.
- `README.md`: la tabla de resultados del barrido y del acuerdo con el clay
  ratio, con el mismo tono del párrafo que ya existe («Nada de esto es caolinita
  detectada»). Si el acuerdo con el clay ratio es pobre, se dice que es pobre.
- `CHANGELOG.md`: entradas en `Added` y `Changed`, con el nivel de detalle del
  resto del archivo (qué se rompería si se revirtiera, no qué se agregó).
- Marca explícitamente como **BLOQUEADO POR TRACK A** todo lo que no se pudo
  medir: E3 sobre la escena real y E4 completo.

### Estilo (no negociable, es el estándar del repo)

- Docstrings numpydoc **en español, sin tildes en el código**, con secciones
  `Parameters / Returns / Raises`. Mira `masking.py` o `sam.py` como referencia
  de largo y tono.
- Los comentarios explican **por qué esta decisión y no la obvia**, y qué se
  rompería si se revirtiera, con el modo de falla concreto. El repo tiene ese
  estándar en todos lados; no lo bajes. Nada de comentarios que repitan el código.
- `from __future__ import annotations` al inicio de cada módulo, type hints en
  todas las firmas públicas, 88 columnas (black/ruff/isort ya configurados).
- Un commit por cambio lógico. No hagas un commit gigante de «Semana 4».

### Git: qué haces tú y qué NO haces

**Lo que SÍ haces:**

1. Antes de tocar nada:

   ```
   git status
   git checkout main
   git pull
   git checkout -b feat/track-b-metrics
   ```

   Si `git status` muestra cambios sin commitear que no son míos, **para y
   dímelo** antes de crear la rama.
2. Commitea en local, en esa rama, un commit por cambio lógico, con `git add` de
   **rutas explícitas**. Nunca `git add .` ni `git add -A`.
3. Al terminar, muéstrame `git log --oneline origin/main..HEAD` y
   `git diff --stat origin/main`.

**Lo que NO haces, bajo ninguna circunstancia:**

- `git push`, en ninguna variante, ni con `--force-with-lease`.
- Abrir Pull Requests, ni `gh pr create`, ni la API de GitHub.
- Commitear en `main`, ni `git rebase` / `git reset` sobre `main`.
- `git reset --hard`, `git checkout .` ni ningún comando que descarte trabajo sin
  commitear.
- Reescribir commits que ya existan en `origin/main`.
- Agregar el trailer `Co-Authored-By: Claude <noreply@anthropic.com>` ni la línea
  «Generated with Claude Code» a los mensajes de commit. El historial de este
  repo es parte de mi portafolio y de la evaluación del profesor: los commits van
  con mi autoría de git y un mensaje limpio, sin firmas de herramientas. Si tu
  configuración los añade por defecto, quítalos antes de commitear y avísame.

Si crees que necesitas uno de los comandos prohibidos, **para y explícame por
qué** en vez de ejecutarlo.

### Antes de decir que terminaste, corre y muéstrame la salida

```
pre-commit run --all-files
pytest -q
pytest tests/test_metrics.py tests/test_indices.py -v
```

`pytest -q` tiene que pasar con **más** tests de los que había al empezar (mide
el número de partida antes de tocar nada y dímelo).

Comprobación de humo de la dirección del puntaje: un puntaje perfectamente
invertido tiene que dar AUC = 0, no 1.

```
python -c "
import numpy as np
from mineralmap.validation.metrics import roc_auc
y = np.array([0,0,1,1], dtype=bool)
s = np.array([0.9,0.8,0.2,0.1])   # puntaje al reves: alto donde es negativo
print('crudo         :', roc_auc(y, s))
print('declarado     :', roc_auc(y, s, greater_is_better=False))
"
```

Comprobación de que los `NaN` no entran en ninguna cuenta:

```
python -c "
import numpy as np
from mineralmap.validation.metrics import f1_score
rng = np.random.default_rng(0)
t = rng.random(1000) > 0.5
p = rng.random(1000) > 0.5
base = f1_score(t, p)
t2 = np.concatenate([t, np.zeros(1000, bool)])
p2 = np.concatenate([p, np.zeros(1000, bool)])
v  = np.concatenate([np.ones(1000, bool), np.zeros(1000, bool)])
print(base, f1_score(t2, p2, valid=v), 'iguales:', np.isclose(base, f1_score(t2,p2,valid=v)))
"
```

Y la corrida real, si `data/interim/scene.npz` y el GeoTIFF existen:

```
python scripts/sweep_threshold.py --config configs/tamarugal_kaolinite.yaml
```

Si no existen, dime el comando que tengo que correr yo y **no lo corras tú**.

Si algo de este prompt contradice lo que encuentres en el código o en `docs/`,
**para y dímelo antes de resolverlo por tu cuenta.**

Al final, entrégame un resumen con: qué archivos tocaste, la lista de commits,
qué quedó sin hacer, qué decisiones tomaste que yo debería revisar, y **qué
supuestos quedaron marcados sin verificar**.

---

## Lo que hago YO después (no va en el prompt)

```bash
# 0. Regenerar los insumos de la semana (data/interim/ y outputs/maps/ estan vacios)
python scripts/run_pipeline.py --config configs/tamarugal_kaolinite.yaml

# 1. Revisar antes de subir
git log --oneline origin/main..HEAD
git diff origin/main --stat
git log -p origin/main..HEAD
git log --format='%an <%ae>%n%b' origin/main..HEAD | grep -i "claude\|co-authored"
#    ^ que no devuelva nada

# 2. Sincronizar con lo de Camila
git fetch origin
git rebase origin/main

# 3. Verificar que sigue verde
pre-commit run --all-files
pytest -q

# 4. Subir
git push -u origin feat/track-b-metrics
```

**Orden de merge sugerido: Track B primero otra vez.** `metrics.py` no depende de
`geology.py`; al revés sí, porque la verdad de terreno de Camila se va a evaluar
con mis métricas. Si entra primero su rasterización, la evalúa con funciones que
todavía lanzan `NotImplementedError`.

---

## Lo que tengo que hablar con Camila, y es más urgente que el código

1. **¿Qué carta geológica cubre Pampa del Tamarugal?** La Carta Calama del plan
   original no cubre el AOI de `T19KDT`. Sin una capa que cubra ese cuadrante, E3
   y E4 no se pueden cerrar sobre esta escena, y eso cambia el alcance del
   Nivel 1. Las salidas posibles son tres, y hay que elegir una esta semana:
   (a) encontrar la carta o el servicio ArcGIS REST del SERNAGEOMIN que cubra
   Tarapacá; (b) volver a un AOI en Calama, donde la verdad de terreno existe, y
   rehacer la corrida; (c) cerrar el Nivel 1 con E1, E2 y E5, declarando E3 y E4
   como no alcanzables con los datos disponibles y documentándolo como
   limitación. La (c) es defendible en una entrevista si está bien argumentada;
   lo indefendible es no decidir.
2. **El formato de la capa de verdad.** Que entregue un GeoTIFF booleano en la
   grilla exacta del `Scene` (mismo CRS, misma `transform`, misma forma), no un
   shapefile que yo tenga que rasterizar. La rasterización es Track A según el
   documento 05.
3. **`scripts/evaluate.py`** es un stub cuya firma (`predicted`, `ground_truth`)
   se solapa con mi `sweep_threshold.py`. Hay que decidir si sobrevive o se borra.
   Esta semana no lo toca nadie.
