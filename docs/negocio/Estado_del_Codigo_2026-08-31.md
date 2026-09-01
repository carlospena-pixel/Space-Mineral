# Estado real del código — verificado el 31 de agosto de 2026

**Método:** lectura directa de `src/mineralmap/**`, `scripts/**` y `.git/logs/HEAD`. No se usó la documentación del repositorio como fuente, porque está atrasada respecto del código (ver sección 4).

---

## 1. Tabla de estado, etapa por etapa

| # | Etapa | Módulo | Estado en el código |
|---|---|---|---|
| 0 | Adquisición de la escena | `io/acquisition.py` | **Stub.** `download_scene` lanza `NotImplementedError`. La descarga se hace a mano desde CDSE |
| 1 | Localizar producto y bandas | `io/raster_io.py` | **Completa** |
| 2 | Leer el escalado del producto | `preprocessing/reflectance.py` | **Completa** |
| 3 | Recorte al AOI y remuestreo a 20 m | `preprocessing/resampling.py` | **Completa.** `resample_to_common_grid` (línea 124) sigue como stub, reservado para Nivel 2 |
| 4 | Escalar a reflectancia | `preprocessing/reflectance.py` | **Completa** |
| 5 | Máscara de validez desde SCL | `preprocessing/masking.py` | **Completa** |
| 6 | Construir y serializar el `Scene` | `preprocessing/scene_builder.py`, `io/raster_io.py` | **Completa.** `read_scene` (línea 160) quedó como stub; el `Scene` se serializa a `.npz` con `load_scene` |
| 7 | Firma de referencia USGS | `spectral/endmembers.py`, `usgs_library.py` | **Completa.** `srf.convolve_with_srf` es stub y no hace falta: el USGS publica la firma ya remuestreada a Sentinel-2 |
| 8 | Detección (SAM) | `algorithms/sam.py`, `base.py`, `pipeline.py` | **Completa y endurecida** |
| 9a | Verdad de terreno desde cartografía | `validation/geology.py` | **Completa** ← *la documentación dice que esto es andamiaje. Ya no lo es* |
| 9b | **Métricas cuantitativas** | `validation/metrics.py` | **Pendiente.** Las cinco funciones lanzan `NotImplementedError` |
| 9c | CLI de evaluación | `scripts/evaluate.py` | **Pendiente.** `main` lanza `NotImplementedError` |
| 10 | Visualización y exportación | `visualization/maps.py`, `spectra.py` | **Completa** |

---

## 2. Lo único que falta para cerrar la validación

Cinco funciones en un archivo de 398 bytes, más la CLI que las llama:

```
src/mineralmap/validation/metrics.py
  confusion_matrix(y_true, y_pred)   línea 4   → NotImplementedError
  f1_score(y_true, y_pred)           línea 8   → NotImplementedError
  iou_score(y_true, y_pred)          línea 12  → NotImplementedError
  roc_auc(y_true, y_score)           línea 16  → NotImplementedError
  cohen_kappa(y_true, y_pred)        línea 20  → NotImplementedError

scripts/evaluate.py
  main()                             línea 13  → NotImplementedError
```

Los dos insumos que estas funciones necesitan **ya existen y están alineados píxel a píxel**:

- `outputs/maps/kaolinite_sam_angle.tif` — el mapa de ángulos, producido por `pipeline.py`.
- `outputs/maps/ground_truth.tif` — la verdad de terreno, producida por `scripts/construir_verdad_terreno.py`.

Es decir: la parte difícil de la etapa 9 —rasterizar la cartografía del SERNAGEOMIN a la grilla exacta del `Scene`— está hecha. Lo que queda es aritmética sobre dos arreglos del mismo tamaño.

---

## 3. Lo que el código tiene y la documentación no menciona

Tres cosas que aparecen en el código y que valen como argumento técnico en cualquier postulación:

**3.1 El contrato `Detector` evolucionó.** `algorithms/base.py` ya no asume que "mayor puntaje es más evidencia". Cada detector declara ahora las bandas que consume (`bands`) y la dirección de su puntaje (`higher_is_better`), y el pipeline binariza llamando a `detects()` en vez de comparar a mano. El propio docstring explica por qué: con el contrato anterior, un detector que devolviera evidencia máxima en todo el AOI se habría reportado como cero detecciones sin lanzar ningún error. Eso es diseño defensivo real, no decorativo.

**3.2 `pipeline.py` es agnóstico al algoritmo.** No importa `SAM_BANDS` ni `threshold`; le pregunta todo al detector. Agregar Random Forest es escribir una clase y una entrada en el registro.

**3.3 `scripts/verificar_cifras.py` existe y hace algo poco común.** Lee las tablas markdown de los documentos del proyecto, recalcula cada cifra desde el GeoTIFF real y falla si alguna no coincide. Es control de consistencia automatizado entre documentación y datos. En una postulación esto se cuenta bajo "rigor metodológico" y no es un adorno: es la respuesta a la pregunta de cómo sabemos que lo que dice el informe es lo que dice el dato.

---

## 4. Dónde está desactualizada la documentación

| Documento | Qué afirma | Qué dice el código |
|---|---|---|
| `docs/recorrido/12_estado_y_pendientes.md` | `validation/geology.py` es andamiaje: `load_geology_polygons` y `rasterize_ground_truth` sin implementar | Ambas están implementadas, más `cargar_config_verdad`, `clasificar_unidades` y `build_ground_truth`. El módulo tiene 18.707 bytes |
| `docs/recorrido/12_estado_y_pendientes.md` | Contradicción 3: los stubs de Random Forest y unmixing declaran `predict(self, cube)`, con un argumento menos que el contrato | Sigue siendo cierto hoy. No revienta porque ambos lanzan `NotImplementedError`, pero explotaría el día que se implementen |

---

## 5. Estado de git

Últimos dos commits, ambos del 30 de agosto de 2026:

- `feat(config): reubicar el AOI al distrito Cerro Colorado para cumplir E3`
- `docs: documentar la version de Python del entorno y como reconstruirlo`

**Aviso:** `src/mineralmap/algorithms/sam.py` tiene fecha de modificación posterior al último commit. Es probable que haya trabajo sin commitear en ese archivo. Conviene revisarlo antes de seguir, porque `sam.py` es el corazón del detector.

---

## 6. Dos precisiones sobre la descripción del proyecto

Ambas salen del código y afectan cómo se describe Space Mineral hacia afuera.

**6.1 El AOI ya no es la Pampa del Tamarugal.** El commit del 30 de agosto movió la ventana al **distrito Cerro Colorado, Precordillera de Tarapacá** (`configs/cerro_colorado_kaolinite.yaml`, ventana `col_off=2700, row_off=650`, 2000 × 2000 px a 20 m = 40 × 40 km). El motivo está escrito en el propio config: la ventana anterior caía íntegra sobre relleno sedimentario, con **cero unidades de alteración hidrotermal cartografiadas**, así que el criterio E3 del plan maestro no se podía ni formular. Cualquier descripción del proyecto que diga "Pampa del Tamarugal" quedó atrás por un día.

**6.2 Bandas.** Sentinel-2 captura 13 bandas. El `Scene` del proyecto trabaja con **12** (`BAND_ORDER` en `config.py`) y SAM consume **9** (`SAM_BANDS`). Los tres números son correctos, cada uno en su contexto, pero conviene no mezclarlos al describir el proyecto.

---

## 7. Qué se puede afirmar hoy sin exagerar

- Que el pipeline corre de extremo a extremo desde un archivo de configuración y es reproducible. **Sí.**
- Que la verdad de terreno está construida desde cartografía oficial y alineada con el mapa de detección. **Sí.**
- Que las detecciones se cruzaron contra esa cartografía. **Sí**, como conteo.
- Que el desempeño del detector está medido. **Todavía no.** Eso llega con `metrics.py`.
- Que el software detecta caolinita. **No**, y el propio proyecto lo dice: mide similitud espectral con una firma de laboratorio.
