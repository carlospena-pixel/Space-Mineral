# Estado real del código — verificado el 1 de septiembre de 2026

**Método:** lectura directa de `src/mineralmap/**`, `scripts/**` y `git log`, más ejecución de `pytest`, `scripts/evaluate.py` y `scripts/verificar_cifras.py` sobre los datos reales. No se usó la documentación del repositorio como fuente para el estado; la documentación se actualizó *después*, contra lo que dice el código.

**Qué cambió respecto de la foto del 31 de agosto:** la etapa 9 cerró. La validación está implementada, medida y publicada, y **su resultado es negativo**. Ver la sección 3, que es la parte que importa.

---

## 1. Tabla de estado, etapa por etapa

| # | Etapa | Módulo | Estado en el código |
|---|---|---|---|
| 0 | Adquisición de la escena | `io/acquisition.py` | **Stub.** `download_scene` lanza `NotImplementedError`. La descarga se hace a mano desde CDSE |
| 1 | Localizar producto y bandas | `io/raster_io.py` | **Completa** |
| 2 | Leer el escalado del producto | `preprocessing/reflectance.py` | **Completa** |
| 3 | Recorte al AOI y remuestreo a 20 m | `preprocessing/resampling.py` | **Completa.** `resample_to_common_grid` sigue como stub, reservado para Nivel 2 |
| 4 | Escalar a reflectancia | `preprocessing/reflectance.py` | **Completa** |
| 5 | Máscara de validez desde SCL | `preprocessing/masking.py` | **Completa** |
| 6 | Construir y serializar el `Scene` | `preprocessing/scene_builder.py`, `io/raster_io.py` | **Completa.** `read_scene` quedó como stub huérfano; el `Scene` se serializa a `.npz` con `load_scene` |
| 7 | Firma de referencia USGS | `spectral/endmembers.py`, `usgs_library.py` | **Completa.** `srf.convolve_with_srf` es stub y no hace falta: el USGS publica la firma ya remuestreada a Sentinel-2 |
| 8 | Detección (SAM) | `algorithms/sam.py`, `base.py`, `pipeline.py` | **Completa y endurecida** |
| 9a | Verdad de terreno desde cartografía | `validation/geology.py` | **Completa** |
| 9b | Métricas cuantitativas | `validation/metrics.py` | **Completa** ← *era el pendiente de la foto anterior* |
| 9c | CLI de evaluación | `scripts/evaluate.py` | **Completa** |
| 9d | Figura de validación (ROC + histograma) | `visualization/validacion.py` | **Completa** |
| 10 | Visualización y exportación | `visualization/maps.py`, `spectra.py` | **Completa** |

**Nueve de las diez etapas están implementadas.** La única manual es la 0, y no bloquea nada mientras el producto `.SAFE` esté descargado.

---

## 2. Lo que se implementó para cerrar la etapa 9

| Archivo | Tamaño | Qué es |
|---|---|---|
| `src/mineralmap/validation/metrics.py` | 36.572 bytes | Las cinco métricas del contrato más precisión, recall, curva ROC, el filtro único de píxeles y las dos funciones orquestadoras |
| `scripts/evaluate.py` | 9.718 bytes | La CLI: parsea, llama al paquete e imprime |
| `src/mineralmap/visualization/validacion.py` | 8.758 bytes | Curva ROC e histograma del ángulo por clase |
| `tests/test_metrics.py` | 21.289 bytes | 42 pruebas, sin red y sin la escena de 196 MB |

Las métricas están en **NumPy puro**, sin `scikit-learn` en el camino de producción: los tests las contrastan contra valores calculados a mano, no contra otra implementación. `scikit-learn` aparece solo dentro de un test, como oráculo de contraste opcional.

---

## 3. El resultado de la validación, que es negativo

```
python scripts/evaluate.py outputs/maps/kaolinite_sam_angle.tif outputs/maps/ground_truth.tif
```

Sobre 242.967 píxeles evaluables (se descartan 3.756.783 ambiguos y 250 sin dato):

| | valor |
|---|---|
| verdaderos positivos / falsos positivos | 0 / 0 |
| falsos negativos / verdaderos negativos | 50.731 / 192.236 |
| precisión, recall, F1, IoU, kappa | 0,0000 |
| **ROC AUC** | **0,2403** |

**Cómo se lee esto, sin adornos.** Los ceros son un solo hecho contado cinco veces: con el umbral del config no hay ninguna detección dentro de las clases evaluables. El número que informa es el AUC, porque no depende del umbral, y **0,2403 está por debajo del 0,5 del azar**. Eso no significa que el detector no separe: significa que **separa al revés**. La mediana del ángulo espectral es 0,3288 rad dentro de las unidades declaradas positivo y 0,2712 rad dentro de las declaradas negativo — o sea, las unidades que la cartografía identifica como compatibles con alteración se parecen *menos* a la caolinita de laboratorio que las que identifica como no candidatas.

**No se ajustó nada para mejorar el número.** No se reclasificó ninguna unidad geológica, no se movió el umbral y no se cambió el filtro de píxeles.

**Ningún umbral lo arregla.** El que maximiza el índice de Youden es 0,4467 rad y alcanza J = 0,0034, indistinguible de cero. El que maximiza F1 es 0,4492 rad y detecta el 99,72 % de los píxeles: es el clasificador que dice «sí» a todo.

**Tres hipótesis, ninguna descartada:** que la arcilla expuesta esté en los botaderos de mina y no en la roca *in situ* (130 de las 131 detecciones caen ahí); que el barniz del desierto enmascare la firma en la superficie natural; o que 9 bandas a 20 m no basten para un rasgo de absorción que Sentinel-2 muestrea con una sola banda ancha.

La figura está en `outputs/figures/roc_kaolinite_sam.png`.

---

## 4. Cómo se cuenta esto hacia afuera

Esta es la parte delicada, y conviene tenerla decidida antes de que la pregunte alguien.

**Un resultado negativo medido vale más que un resultado positivo sin medir.** Hasta el 31 de agosto el proyecto tenía 131 detecciones y ninguna forma de saber si valían algo. Hoy tiene una respuesta cuantitativa. Que la respuesta sea «no» es información, y el hecho de haberla publicado sin maquillar es, en sí, el argumento metodológico más fuerte del repositorio.

**Lo que se puede afirmar sin exagerar:**

- Que el pipeline corre de extremo a extremo desde un archivo de configuración y es reproducible. **Sí.**
- Que la verdad de terreno está construida desde cartografía oficial y alineada píxel a píxel con el mapa de detección. **Sí.**
- Que el desempeño del detector está medido. **Sí**, desde hoy.
- Que el método detecta caolinita en este AOI. **No.** Y está medido, no supuesto.
- Que el método no sirve en general. **Tampoco se puede afirmar.** Se midió un mineral, en un AOI, con un sensor multiespectral, contra una carta litológica que no cartografía alteración. Cualquiera de esos cuatro puede ser la causa.

**Lo que NO conviene decir:** que invirtiendo el signo se obtiene un detector con AUC 0,76. Es aritméticamente cierto y metodológicamente falso: lo que separa en esa dirección no es caolinita, son diferencias litológicas generales que el ángulo contra *cualquier* firma habría capturado igual.

---

## 5. Lo que el código tiene y sigue siendo argumento técnico

**5.1 El contrato `Detector` evolucionó, y la etapa 9 lo aprovecha.** Cada detector declara las bandas que consume (`bands`) y la dirección de su puntaje (`higher_is_better`). En la Semana 6 esa declaración se volvió crítica: el AUC exige la dirección como argumento obligatorio, y `evaluate.py` la lee del contrato en vez de escribirla como constante. Calcular el AUC con el signo cambiado habría devuelto 0,7597 en vez de 0,2403 sin lanzar ninguna excepción, y los dos números se pueden defender en una presentación. Ese es exactamente el tipo de error que el diseño previene.

**5.2 `pipeline.py` es agnóstico al algoritmo.** No importa `SAM_BANDS` ni `threshold`; le pregunta todo al detector. Agregar Random Forest es escribir una clase y una entrada en el registro. En la Semana 6 se alinearon las firmas de `random_forest.py` y `unmixing.py` al contrato, que hasta ahora declaraban un argumento menos.

**5.3 `scripts/verificar_cifras.py` ahora cubre también las métricas.** Lee las tablas markdown de los documentos, recalcula cada cifra desde los GeoTIFF reales y falla si alguna no coincide. Cubre **80 cifras** publicadas en el README y en los dos documentos de decisiones técnicas. La regla del repositorio se mantiene: ninguna cifra publicada a mano queda sin un chequeo automático que la contradiga cuando envejezca.

**5.4 Un solo lugar decide qué píxel entra al cálculo.** `preparar_pares` es el único filtro. Si cada métrica filtrara por su cuenta, bastaría con que una olvidara excluir los píxeles ambiguos para que la tabla mezclara números calculados sobre poblaciones distintas —la matriz de confusión sobre 242.967 píxeles y el AUC sobre 3.993.936— presentados en la misma columna, sin que nada falle.

---

## 6. Estado de las pruebas y de la consistencia

```
194 passed, 1 skipped in 8.05s
OK: las 80 cifras publicadas coinciden con outputs/maps/kaolinite_sam_angle.tif.
```

`black`, `ruff` e `isort` pasan limpio sobre `src/`, `scripts/` y `tests/`.

La única prueba omitida necesita el archivo de longitudes de onda de splib07, que sigue sin descargarse. **Ninguna prueba depende de la escena de 196 MB ni de la red.**

---

## 7. Correcciones a la foto del 31 de agosto

Dos cosas que aquel documento afirmaba y que la verificación de hoy desmiente:

**7.1 No había trabajo sin commitear en `sam.py`.** El aviso de la sección 5 de aquel documento se basaba en la fecha de modificación del archivo. `git diff` sobre `sam.py` y `README.md` sale vacío: el contenido es idéntico al del último commit. La fecha se tocó sin cambiar el archivo.

**7.2 `error.txt` no contiene ningún error.** Es una corrida guardada de `pytest tests/test_sam.py` con 24 pruebas pasando. Lo que sí revela es que se ejecutó con el Python 3.12 global en vez del `.venv` del proyecto, que es 3.13.5. El `README.md` acierta al declarar 3.13; el intérprete del PATH no tiene `rasterio` ni `pytest` instalados, así que cualquier comando del README corrido sin activar el entorno falla por import.

---

## 8. Lo que queda pendiente

Nada de esto bloquea la etapa de validación, que está cerrada.

- **`angle_threshold_rad` sigue en 0,1** en el config. La calibración existe pero ninguno de los dos umbrales que propone es utilizable; cambiar el valor es decisión de la dueña del repositorio.
- **`raster_io.py::read_scene` está huérfano**: nada lo llama y nada lo necesita. Es el único stub del repositorio sin un caso de uso declarado en los tres niveles.
- **`spectral/srf.py::convolve_with_srf`** sigue como andamiaje, pero su justificación original ya no se sostiene: el USGS sí publica la firma remuestreada. Conserva sentido solo como verificación cruzada.
- **El archivo de longitudes de onda del USGS** sigue sin descargarse, y mantiene una prueba omitida.
- **Un análisis de sensibilidad** con los botaderos de mina declarados positivo, reportado aparte y sin reemplazar la corrida principal, es la única exploración legítima de la primera hipótesis de la sección 3.
