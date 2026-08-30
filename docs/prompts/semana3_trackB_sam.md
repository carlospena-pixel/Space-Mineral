# Track B — Semana 3 (SAM: fórmula, endurecimiento y caso analítico)

> Contraparte del prompt de Track A de Camila (`feat/track-a-maps`).
> Redactado el 2026-08-10 contra `main @ b154f77`, árbol limpio.

---

## Paso 0 — Antes de tocar código: acordar con Camila

Dos cosas por mensaje, antes de abrir Claude Code. Ninguna es opcional: las
cuatro primeras son contradicciones reales entre el roadmap y el repo, y
resolverlas después de escribir código cuesta el doble.

1. **Frontera de archivos confirmada.** Yo no toco `pipeline.py`,
   `io/raster_io.py`, `visualization/maps.py`, `scripts/run_pipeline.py`,
   `configs/*.yaml`, `.gitignore`, `tests/test_maps.py`,
   `tests/test_raster_io.py`, `tests/test_pipeline.py`. Ella no toca
   `algorithms/*`, `spectral/*`, `visualization/spectra.py`, `validation/*`,
   `tests/test_sam.py`, `tests/test_endmembers.py`, `tests/test_usgs_library.py`,
   `tests/test_spectra.py`, `notebooks/*`.
2. **Ninguno de los dos hace `git push` desde la herramienta de IA.**
3. **La tarea real de Track B esta semana.** El roadmap dice «implementar
   `SAM.predict`», pero eso ya está en `main` desde el commit `2efeb3c` con sus
   tests pasando. Acordar que Track B es *endurecer y demostrar* el detector, no
   escribirlo — y decidir si se adelanta `validation/metrics.py` (§ opcional).
4. **Dirección del puntaje: hay un conflicto de contrato vivo en el repo.**
   `algorithms/base.py::Detector` documenta «a mayor valor, mayor
   probabilidad/similitud de presencia», pero SAM devuelve un **ángulo**, donde
   **menor = más parecido**. Camila ya trabaja sobre la convención invertida
   (`cmap="viridis_r"`, «más oscuro = más parecido»). **No cambiar el signo ni
   la semántica de `predict` esta semana**: rompería su pipeline a mitad de
   sprint. Lo que sí hay que hacer es dejar la contradicción escrita en
   `decisiones_tecnicas.md` y acordar cuándo se resuelve.
5. **Idioma de los mensajes de commit.** El historial de `main` está en español
   (`feat(algorithms): implementar SAM con tests`) y el prompt de Track A pide
   Conventional Commits **en inglés**. Elijan uno y úsenlo los dos: un historial
   mitad y mitad se ve mal en un portafolio.

---

## Prompt para Claude Code — Track B, Semana 3

> Copiar todo lo que está entre las líneas `---` y pegarlo en Claude Code
> abierto en la raíz del repo.

---

Trabajo en el repo `Space-Mineral` (detección de caolinita con Sentinel-2 +
SAM). Soy Carlos y me toca el **Track B** de la Semana 3. Camila trabaja en
paralelo en el Track A sobre el mismo repo, en la rama `feat/track-a-maps`.

Antes de escribir código, lee estos archivos para tener el contexto real y no
inventar contratos:

- `docs/es/decisiones_tecnicas.md` — secciones 1 (contratos), 2 (bandas) y 7
  (comparación de firmas y el umbral que no detecta nada)
- `docs/es/pipeline.md` — tabla de estado y etapa 8
- `src/mineralmap/algorithms/sam.py` y `algorithms/base.py` — lo que voy a tocar
- `src/mineralmap/algorithms/random_forest.py`, `algorithms/unmixing.py` — el
  andamiaje de Nivel 2 y 3 que tiene que seguir encajando en el mismo contrato
- `src/mineralmap/config.py` — `BAND_ORDER`, `SAM_BANDS`, `band_wavelengths`
- `src/mineralmap/spectral/endmembers.py` — `get_reference_spectrum`,
  `validate_raw_band_order`, `_RAW_BAND_ORDER`
- `src/mineralmap/preprocessing/masking.py` — `apply_mask` (produce el cubo con
  `NaN` que va a recibir el detector) y su estilo de `ValueError`
- `src/mineralmap/visualization/spectra.py` — `normalize_signature`, que ya
  resuelve el caso «vector sin dirección» y fija el criterio a imitar
- `tests/test_sam.py`, `tests/test_endmembers.py`, `tests/test_masking.py` — el
  estándar de test del repo
- `outputs/scratch/PLAN_S2_TrackB.md` y
  `outputs/scratch/PROMPT_claude_code_S2_TrackB.md` — mis notas de la Semana 2
  (están en el disco pero no en git: `outputs/scratch/` está en `.gitignore`)

### Objetivo del hito

Dejar `SAM.predict` en estado de **no puede estar mal en silencio**, y
demostrarlo contra ángulos cuyo valor exacto se conoce por geometría, no por
comparación con otra implementación. Al cerrar:

- `predict()` valida sus entradas y falla ruidosamente donde hoy devuelve basura
  plausible.
- `tests/test_sam.py` contiene una batería de casos analíticos exactos.
- `pytest -q` pasa completo y con **más** tests que los 73 de partida.
- La fórmula implementada está contrastada contra el **documento 05**, o marcada
  explícitamente como NO VERIFICADA si no te paso el documento.

Este track **no** produce ningún mapa ni ninguna imagen. El mapa es el
entregable de Camila.

### Alcance: SOLO estos archivos

Camila trabaja en paralelo en Track A. **No toques nada de esta lista, ni para
arreglar un import, ni para formatear, ni para corregir un typo:**

`src/mineralmap/pipeline.py`, `src/mineralmap/io/raster_io.py`,
`src/mineralmap/visualization/maps.py`, `scripts/run_pipeline.py`,
`configs/default.yaml`, `configs/tamarugal_kaolinite.yaml`, `.gitignore`,
`tests/test_maps.py`, `tests/test_raster_io.py`, `tests/test_pipeline.py`.

Si crees que hay que cambiar algo ahí, **párate y dímelo en vez de cambiarlo**.

Los archivos que sí me pertenecen en esta tarea:

`src/mineralmap/algorithms/sam.py`, `src/mineralmap/algorithms/base.py`,
`tests/test_sam.py`, `docs/es/decisiones_tecnicas.md`,
`docs/en/technical_decisions.md`, `CHANGELOG.md`, `README.md`.

`src/mineralmap/validation/metrics.py` y `tests/test_metrics.py` solo si
llegamos a la sección opcional del final.

### Contratos que NO se negocian

1. **La firma `predict(self, cube, reference) -> np.ndarray` no cambia.** No
   agregues un parámetro `mask`, aunque parezca cómodo. Ese contrato es el
   mecanismo de escalabilidad Nivel 1 → 2 → 3 (`decisiones_tecnicas.md` §1.2);
   cambiarlo obliga a tocar `pipeline.py`, que esta semana es de Camila.
   Enmascarar es trabajo del consumidor vía `preprocessing.masking.apply_mask`.
2. **El detector DEBE tolerar `NaN` en el cubo.** El pipeline de Track A le pasa
   el cubo ya enmascarado con `apply_mask`, o sea con `NaN` en todas las bandas
   de los píxeles inválidos. **Cualquier validación que rechace un cubo con
   `NaN` rompe el Track A el mismo día en que se mergea.** Un píxel `NaN` debe
   devolver `NaN` y no contaminar a sus vecinos.
3. **El detector recibe 9 bandas, no 12.** El pipeline subconjunta el cubo a
   `SAM_BANDS` y pide la firma con
   `get_reference_spectrum(mineral, band_order=SAM_BANDS)`. Las validaciones de
   largo tienen que aceptar 9 sin chistar; lo que tienen que atrapar es la
   **mezcla** (cubo de 12 contra firma de 9).
4. **`band_names` es posicional**: `cube[i]` es `band_names[i]`. El producto
   punto asume esa alineación y no tiene forma de verificarla desde dentro.
5. **La dirección del puntaje no se toca esta semana.** SAM devuelve un ángulo
   (menor = más parecido), en tensión con el docstring de `Detector`. Documenta
   la tensión, no la resuelvas: ver §6.

### Trabajo a realizar

#### 1. Contrastar la fórmula contra el documento 05

Antes de tocar `sam.py`, **pídeme el documento 05**. Compara término a término
lo que trae contra lo implementado:

```
θ(x, r) = arccos( (x · r) / (‖x‖ · ‖r‖) )
```

Reporta cualquier diferencia en: normalización previa de los vectores, qué
bandas entran en la suma, unidad de salida (radianes vs grados), y si el
documento define el puntaje como el ángulo, como su coseno o como su
complemento. Si el documento define el score al revés que la implementación,
**no lo cambies**: es el punto 5 de los contratos. Anótalo y avísame.

Si no te paso el documento, sigue adelante pero marca la conformidad como **NO
VERIFICADA** en el informe final y en el CHANGELOG. No la des por buena.

#### 2. Endurecer `SAM.predict`

Los defectos concretos de la implementación actual, en orden de gravedad:

1. **No valida que `cube.shape[0] == reference.shape[0]`.** Hoy revienta con un
   error opaco de `np.einsum`. Es exactamente el fallo que va a ocurrir cuando
   alguien pase un cubo de `BAND_ORDER` (12) con una firma de `SAM_BANDS` (9), o
   al revés — el escenario que el Track A vuelve cotidiano esta semana. Debe
   lanzar `ValueError` **nombrando los dos largos**, en el estilo de mensaje de
   `apply_mask`.
2. **No valida dimensionalidad.** `cube` debe ser 3D y `reference` 1D. Un
   `reference` de forma `(n, 1)` hace broadcast y devuelve un resultado
   plausible con la forma equivocada.
3. **Referencia de norma cero** → `ValueError`. No hay dirección contra la cual
   medir un ángulo. `visualization/spectra.py::normalize_signature` ya lanza
   `ValueError` en ese caso: usa el mismo criterio y el mismo tono de mensaje,
   para que el repo tenga una sola respuesta a un vector sin dirección.
4. **Referencia con `NaN`** → decide y argumenta. Contamina el mapa entero sin
   lanzar nada, y a diferencia del cubo, una firma con `NaN` no es un caso
   legítimo: `get_reference_spectrum` no debería producirlo. Mi inclinación es
   `ValueError`, pero quiero tu argumento antes que tu código.
5. **Píxel de norma cero** (todas las bandas en 0). Hoy da `0/0 → NaN` con el
   `errstate` silenciado. Puede ser correcto, pero no está ni documentado ni
   testeado. Decídelo explícitamente, escríbelo en el docstring y cúbrelo.
6. **Precisión mixta.** `reference` se castea a `float64` pero `cube` no, así que
   el producto punto acumula en `float32`. Cerca de `cos = 1` el `arccos`
   amplifica ese error (su derivada diverge), y eso ya obligó al `atol=1e-6` del
   test existente. **No castees el cubo completo a `float64` sin medir**: el cubo
   real es `(12, 2000, 2000)`, o sea ~768 MB en `float64` contra ~384 MB en
   `float32`, y ese cubo tiene que caber en la máquina de Camila. Mide el error
   real, decide con el número a la vista y escribe el porqué en el comentario.
7. **Docstring**: afirma que los píxeles inválidos devuelven `NaN`. Verifica que
   sea cierto y fija esa promesa con un test.

Revisa también `threshold(angle_map, max_angle)`: hoy los `NaN` caen como
`False` por las semánticas de comparación de IEEE-754, lo cual es el
comportamiento deseado pero **por accidente, no por diseño**. Déjalo explícito
en el docstring y confirma que el test existente lo cubre a propósito.

#### 3. La batería de casos analíticos (el corazón del entregable)

En `tests/test_sam.py`, ángulos **exactos por construcción geométrica**, no
comparados contra otra librería. Cada test lleva en su docstring por qué el
valor esperado es ese.

| Caso | Referencia | Píxel | θ esperado |
|---|---|---|---|
| Ortogonal | `[1, 0]` | `[0, 1]` | `π/2` |
| 45° | `[1, 0]` | `[1, 1]` | `π/4` |
| 60° | `[1, 0, 0]` | `[1, 1, √2]` | `π/3` (dot = 1, ‖x‖ = 2 → cos = ½) |
| 30° | `[1, 0]` | `[√3, 1]` | `π/6` |
| Antiparalelo | `[1, 1]` | `[-1, -1]` | `π` (fija el clip inferior en −1) |
| Idéntico | `r` | `r` | `0` (ya existe) |
| Proporcional | `r` | `5·r` | `0` (ya existe, invariancia a albedo) |

**Tolerancias ajustadas, no `1e-6` por defecto.** Ortogonal, 45° y 60° son
exactos a precisión de máquina en `float64` (`atol=1e-12` o mejor). Solo el caso
`θ ≈ 0` necesita tolerancia relajada, y eso ya está justificado en el comentario
del test existente — no lo borres, es de las pocas explicaciones de precisión
numérica que hay en el repo.

Además de la tabla:

8. **Test-oráculo: vectorizado vs bucle.** Sobre un cubo aleatorio con semilla
   fija (`np.random.default_rng(0)`), calcula el ángulo píxel a píxel con un
   bucle `for` ingenuo y compáralo contra la salida de `predict`. Detecta
   cualquier error de ejes en el `einsum`: un `"bhw,b->hw"` mal escrito devuelve
   un mapa transpuesto que se ve perfectamente razonable.
9. **Rango de salida**: todo valor finito cae en `[0, π]`.
10. **`NaN` no contamina** — este es el test que protege el Track A. Un cubo con
    un píxel `NaN` en una sola banda devuelve `NaN` en ese píxel y valores
    finitos en todos sus vecinos. Escribe en el docstring que este test existe
    porque el pipeline entrega el cubo ya enmascarado con `apply_mask`.
11. **Invariancia a escala, versión fuerte**: escalar cada píxel de un cubo
    aleatorio por un factor positivo distinto no cambia el mapa de ángulos. Es la
    propiedad que justifica usar SAM sobre albedo variable, y el test de dos
    píxeles no la demuestra.
12. **Simetría**: `θ(x, r) == θ(r, x)`.
13. **`dtype` de entrada indiferente**: el mismo cubo en `float32` y en
    `float64` da el mismo resultado dentro de la tolerancia que mediste en §2.6.
14. **Un test por cada `ValueError` nuevo**, con
    `pytest.raises(ValueError, match=...)` verificando que el mensaje nombra el
    problema real (los dos largos que no calzan), no un texto genérico.
15. **Integración con `SAM_BANDS`**: un cubo sintético de 9 bandas contra una
    firma de 9 pasa sin error, y un cubo de 12 contra una firma de 9 levanta el
    `ValueError` del punto 1. Es el contrato con el Track A, escrito como test.

Los tests **no pueden depender de la escena real**: `data/` no se versiona y la
CI de GitHub no la tiene. Todo sintético. Si algún test necesitara la escena,
márcalo con `pytest.mark.skipif` sobre la existencia del archivo, como hace
`tests/test_scene_builder.py`.

#### 4. `algorithms/base.py`

Tócalo lo mínimo. Lo único que corresponde esta semana es dejar registrada en el
docstring de `Detector.predict` la tensión del punto 5 de los contratos: que el
contrato dice «a mayor valor, mayor evidencia» y que SAM devuelve un ángulo
donde menor es mejor. **No cambies la firma ni el sentido**: `random_forest.py` y
`unmixing.py` heredan de aquí y `pipeline.py` lo consume esta misma semana.

#### 5. Documentación

- `docs/es/decisiones_tecnicas.md`: sección nueva para SAM. La fórmula, su
  fuente (documento 05, o la marca de NO VERIFICADA), qué valida ahora y qué
  lanza, la decisión de precisión **con el número que mediste**, y la
  contradicción de dirección del puntaje escrita como deuda con fecha de
  revisión. Mismo tono que el resto del documento: qué falla, y sobre todo **qué
  falla en silencio**.
- `docs/en/technical_decisions.md`: la contraparte en inglés. Verifica primero si
  los dos documentos están sincronizados hoy; si ya divergen, avísame antes de
  escribir.
- `README.md`: la sección «Detección: pendiente» dice que `sam.py` «está
  implementado y testeado». Ajusta a lo que efectivamente hay ahora. **No
  escribas que se detectó caolinita** ni toques las cifras del AOI.
- `CHANGELOG.md`: entrada bajo `Added` / `Changed` con el nivel de detalle del
  resto del archivo — explica el porqué, no solo el qué.

`docs/es/pipeline.md` y `docs/en/pipeline.md` **son de Camila esta semana** (la
etapa 8 pasa de pendiente a implementada por su trabajo). No los toques.
`README.md`, `CHANGELOG.md` y los dos documentos de decisiones técnicas son
compartidos: escríbelos **al final, en un commit aparte de los de código**, para
que el conflicto con ella sea trivial de resolver.

### Estilo (no negociable, es el estándar del repo)

- Docstrings numpydoc **en español, sin tildes en el código**, con secciones
  `Parameters / Returns / Raises`. Mira `masking.py` o `endmembers.py` como
  referencia de largo y tono.
- Los comentarios explican **por qué esta decisión y no la obvia**, y qué se
  rompería si se revirtiera, con el modo de falla concreto. El repo tiene ese
  estándar en todos lados; no lo bajes. Nada de comentarios que repitan el
  código.
- `from __future__ import annotations` al inicio de cada módulo, type hints en
  todas las firmas públicas, 88 columnas (black/ruff/isort ya configurados).
- Un commit por cambio lógico. No hagas un commit gigante de «Semana 3».

### Git: qué haces tú y qué NO haces

Trabajo en paralelo con Camila sobre el mismo repo. Sin excepciones:

**Lo que SÍ haces:**

1. Antes de tocar nada, verifica que el árbol está limpio y que estás al día:

   ```
   git status
   git checkout main
   git pull
   git checkout -b feat/track-b-sam
   ```

   Si `git status` muestra cambios sin commitear que no son míos, **para y
   dímelo** antes de crear la rama.
2. Commitea en local, en esa rama, un commit por cambio lógico, con `git add` de
   **rutas explícitas**. Nunca `git add .` ni `git add -A`: es lo que arrastraría
   un archivo de Camila que quedó modificado en mi copia sin que yo lo note.
3. Al terminar, muéstrame `git log --oneline origin/main..HEAD` y
   `git diff --stat origin/main` para que yo revise antes de subir.

**Lo que NO haces, bajo ninguna circunstancia:**

- `git push`, en ninguna variante, ni con `--force-with-lease`.
- Abrir Pull Requests, ni `gh pr create`, ni la API de GitHub.
- Commitear en `main`, ni `git rebase` / `git reset` sobre `main`.
- `git reset --hard`, `git checkout .` ni ningún comando que descarte trabajo sin
  commitear.
- Reescribir commits que ya existan en `origin/main` (los de Camila incluidos).
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
pytest tests/test_sam.py -v
python -c "import numpy as np; from mineralmap.algorithms.sam import SAM; print(SAM().predict(np.array([[[0.0]],[[1.0]]]), np.array([1.0,0.0])))"
```

La última línea es la comprobación de humo del caso ortogonal: tiene que
imprimir `[[1.5707963...]]`, o sea `π/2`.

Y la prueba del contrato con el Track A: un cubo con `NaN` no revienta y no
contamina.

```
python -c "
import numpy as np
from mineralmap.algorithms.sam import SAM
c = np.ones((9, 2, 2)); c[:, 0, 0] = np.nan
m = SAM().predict(c, np.ones(9))
print(m); print('NaN solo en (0,0):', np.isnan(m).sum() == 1)
"
```

Si algo de este prompt contradice lo que encuentres en el código o en `docs/`,
**para y dímelo antes de resolverlo por tu cuenta.**

Al final, entrégame un resumen con: qué archivos tocaste, la lista de commits,
qué quedó sin hacer, qué decisiones tomaste que yo debería revisar, y **qué
supuestos quedaron marcados sin verificar**.

---

## Opcional — solo si §1 a §5 quedaron cerradas y verdes

`src/mineralmap/validation/metrics.py` es trabajo de la Semana 4 y **no toca
ningún archivo del Track A**, así que se puede adelantar sin riesgo de conflicto.
Hoy sus cinco funciones (`confusion_matrix`, `f1_score`, `iou_score`, `roc_auc`,
`cohen_kappa`) levantan `NotImplementedError`.

Si lo abordas: **en una rama aparte** (`feat/track-b-metrics`), con sus propios
commits, y con las mismas reglas de estilo y de git. Los tests van en
`tests/test_metrics.py` (nuevo) y deben ser sintéticos, con casos de valor
conocido a mano (una matriz de confusión de 2×2 escrita a mano, un F1 que se
puede calcular en papel). No lo mezcles con los commits de SAM: son dos hitos
distintos y el profesor va a leer el historial.

---

## Lo que hago YO después (no va en el prompt)

Claude Code deja todo commiteado en `feat/track-b-sam` sin subir nada.

```bash
# 1. Revisar antes de subir
git log --oneline origin/main..HEAD
git diff origin/main --stat
git log -p origin/main..HEAD
git log --format='%an <%ae>%n%b' origin/main..HEAD | grep -i "claude\|co-authored"
#    ^ que no devuelva nada: confirma que no quedó ninguna firma de la herramienta

# 2. Sincronizar con lo de Camila
git fetch origin
git rebase origin/main        # si hay conflicto: resolver, git add, git rebase --continue

# 3. Verificar que sigue verde después del rebase
pre-commit run --all-files
pytest -q

# 4. Subir la rama (primera vez)
git push -u origin feat/track-b-sam
```

Después el PR se abre en GitHub y se mergea con «Squash and merge». Al terminar:

```bash
git checkout main
git pull
git branch -d feat/track-b-sam
git push origin --delete feat/track-b-sam
```

Si un commit trajo la firma de la herramienta y todavía está en local, se limpia
con `git rebase -i origin/main` y `reword`.

**Orden de merge sugerido: Track B primero.** Track A consume `SAM.predict`; si
entra primero el pipeline y después las validaciones nuevas del detector, el
riesgo es que una validación mía haga fallar su pipeline ya mergeado. Al revés,
ella rebasa sobre un detector ya endurecido y lo descubre en su propia rama.

---

## Apéndice para Camila — qué cambia en su Track A

Pásale esto para que no se lleve sorpresas al rebasar.

**`SAM.predict` va a empezar a lanzar `ValueError`** donde hoy devolvía algo o
reventaba con un mensaje de `numpy`. Los casos nuevos: cubo y firma con distinto
número de bandas, `cube` que no es 3D, `reference` que no es 1D, y referencia
degenerada (norma cero o con `NaN`). El pipeline no debería topar con ninguno si
subconjunta a `SAM_BANDS` y pide la firma con `band_order=SAM_BANDS`, que es
justo lo que su prompt ya especifica.

**Lo que NO cambia, y que su pipeline puede seguir asumiendo:**

- La firma `predict(cube, reference)` es la misma.
- La salida sigue siendo un ángulo en **radianes**, `(alto, ancho)`, donde
  **menor = más parecido**. Su `cmap="viridis_r"` sigue siendo correcto.
- **Un cubo con `NaN` sigue siendo entrada legítima.** El cubo enmascarado con
  `apply_mask` es el caso de uso soportado y ahora tiene un test que lo fija: un
  píxel `NaN` devuelve `NaN` y no contamina a sus vecinos.
- El rango de salida es `[0, π]`, con `NaN` en los píxeles inválidos.
- `threshold(angle_map, max_angle)` sigue devolviendo `False` en los `NaN`.

**Archivos compartidos**, donde vamos a chocar y es trivial: `README.md`,
`CHANGELOG.md`, `docs/es/decisiones_tecnicas.md`,
`docs/en/technical_decisions.md`. Los dos escribimos al final de la misma
sección; se resuelve conservando ambos bloques. Los escribimos al final de cada
tarea, en un commit aparte de los de código.

**Deuda que dejo anotada y no resuelvo esta semana:** el docstring de `Detector`
dice «a mayor valor, mayor evidencia» y SAM devuelve lo contrario. Lo dejo
documentado en `decisiones_tecnicas.md` sin cambiar el código, porque cambiar el
signo a mitad de sprint le rompería el pipeline. Hay que decidirlo antes de que
entre el segundo detector.

**Sincronizar a diario** con `git fetch origin && git rebase origin/main`, no una
vez al final: un conflicto de dos días se resuelve en minutos y uno de dos
semanas obliga a rehacer trabajo.
