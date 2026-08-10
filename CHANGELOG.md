# Changelog

Todas las versiones notables de este proyecto se documentan en este archivo.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Unreleased]

### Added
- Estructura inicial del repositorio: paquete `mineralmap`, `configs/`, `scripts/`,
  `notebooks/`, `tests/` y `docs/` bilingües.
- Preprocesamiento implementado en el paquete (Semana 2, Track A):
  `preprocessing/reflectance.py` (escalado DN → reflectancia con el offset del
  baseline ≥ 04.00 y lectura de `MTD_MSIL2A.xml`), `preprocessing/masking.py`
  (máscara SCL con las 12 clases, `apply_mask` y `mask_summary`) y
  `preprocessing/resampling.py` (remuestreo en la lectura, `read_band_on_grid`
  y selector de método `resampling_for`).
- `preprocessing/scene_builder.py`: `build_scene_from_safe`, el orquestador que
  arma el `Scene` desde el producto `.SAFE` (localización de bandas, recorte al
  AOI, remuestreo a 20 m, reflectancia y máscara de validez).
- Localizadores de archivos en `io/raster_io.py`: `BAND_TOKEN`, `find_safe_dir`
  y `find_band_file`, que resuelven la resolución nativa de cada banda.
- `Scene.meta`: trazabilidad del producto de origen (tile, fecha, baseline,
  offset, ventana AOI, resolución nativa por banda y composición SCL del AOI),
  serializada como JSON en el `.npz`.
- `SAM_BANDS` en `config.py`: declara las 9 bandas que consumirá el detector
  espectral (excluye B1 y B9, atmosféricas, y B8, redundante con B8A). Solo
  declarado, sin consumidores todavía; cubierto por `tests/test_config.py`.
- Longitudes de onda como dato del proyecto (Semana 2, Track B):
  `BAND_WAVELENGTHS_NM`, `BAND_FWHM_NM` y el helper `band_wavelengths()` en
  `config.py`, con tablas separadas para S2A y S2B y `DEFAULT_PLATFORM = "S2B"`
  (la plataforma de la escena del proyecto). Incluyen B10 aunque `BAND_ORDER`
  no la tenga, porque el archivo de la librería USGS sí la trae y la validación
  de alineamiento la necesita. Verificadas contra SentiWiki (Copernicus), «S2
  Mission», tabla 3, derivada de las funciones de respuesta espectral de ESA
  (COPE-GSEG-EOPG-TN-15-0007).
- `spectral/usgs_library.py`: `load_usgs_wavelengths()`, que lee el archivo de
  longitudes de onda de splib07 (mismo formato ASCIIdata, mismo manejo de «no
  dato») y las convierte de micrómetros a nanómetros en un solo lugar, con un
  control de rango que denuncia un archivo que ya viniera en nanómetros.
- `spectral/endmembers.py`: `validate_raw_band_order()`, que ancla
  `_RAW_BAND_ORDER` —la única pieza que afirma qué banda es cada posición del
  archivo USGS— comprobando el orden creciente de longitud de onda contra la
  tabla de ESA y, si hay archivo de longitudes de onda, el desvío por banda.
  Junto a `find_usgs_wavelengths_file()` y las constantes
  `USGS_RESAMPLING_PLATFORM` y `DEFAULT_WAVELENGTH_TOLERANCE_NM`.
  **Falta descargar** el archivo de longitudes de onda que acompaña a la firma
  dentro del paquete `ASCIIdata_splib07*_rsSentinel2` de la USGS Spectral
  Library Version 7 (<https://www.sciencebase.gov/catalog/item/5807a2a2e4b0841e59e3a18d>).
  Su nombre exacto dentro del paquete no está confirmado, así que el buscador
  trabaja por patrón (cualquier `.txt` de `data/external/` que mencione
  «wavelength») en vez de fijar un nombre inventado. Mientras no esté, el test
  que compara las λ del archivo contra la tabla de ESA queda en `skipif` y el
  orden de `_RAW_BAND_ORDER` sigue anclado solo a evidencia física.
- `tests/test_endmembers.py`: se cubre el fallo silencioso más caro del
  proyecto — que pedir la firma con un `band_order` distinto del default
  (p. ej. `SAM_BANDS`) reordene los valores en vez de reasignarlos.
- `notebooks/01_explore_sentinel2_scene.ipynb`: el hito de Semana 2. Carga la
  escena sobre una submuestra de 256×256 px, la enmascara, la ubica con un RGB
  y superpone la firma de dos píxeles a la de referencia con las 12 bandas
  alineadas. Incluye la tabla de verificación de alineamiento
  (`idx | banda | λ_S2B | ref_USGS | píxel`) con `assert`s que hacen fallar el
  notebook si algo no cuadra. El píxel se elige con criterio explícito —el de
  menor ángulo SAM del AOI, más el central como control—, no «uno cualquiera».
  Corre completo con kernel reiniciado.
- `outputs/figures/kaolinite_signature_vs_pixel.png`: la evidencia del hito.
- `visualization/maps.py`: `percentile_stretch()` y `rgb_composite()`, extraídos
  de `scripts/visualizar_rgb.py` para que el notebook y el script produzcan el
  mismo RGB en vez de dos copias que pueden divergir sin verse mal. El realce
  ahora ignora los NaN: con `np.percentile`, un solo píxel enmascarado dejaba
  la imagen entera negra sin lanzar ningún error.
- `visualization/spectra.py`: `plot_spectra()` implementado (era un stub), más
  `normalize_signature()`. Eje x en longitud de onda real, normalización L2 por
  defecto —que es lo que ve el SAM, invariante al albedo— y corte explícito de
  la línea donde el sensor no muestreó (B9 → B11, con B10 ausente del L2A).
  Los NaN se propagan en vez de convertirse en cero.
- `tests/test_spectra.py`: cubre las tres decisiones anteriores sin depender de
  la escena, incluida la propiedad que hace útil el gráfico —dos firmas
  proporcionales quedan superpuestas con normalización L2—.
- `tests/test_scene_builder.py`: tres tests que blindan la frontera entre
  `preprocessing` y `spectral` sobre la escena real —que la firma pedida con
  `band_order=scene.band_names` traiga tantos valores como bandas el cubo, que
  `apply_mask` no deje el AOI entero en NaN ni mute el cubo original, y que
  subconjuntar el cubo por índice y pedir la firma por nombre lleguen a la
  misma banda—. Siguen bajo el `skipif` que ya tenía el archivo.
- `tests/test_maps.py`: cubre el realce por percentiles y el compuesto RGB sin
  depender de la escena.
- `tests/test_config.py`: el orden creciente de longitud de onda de
  `BAND_ORDER` pasa de ser una verificación manual de Track B a ser un test, y
  se exige correspondencia en ambas direcciones entre `BAND_ORDER` y la tabla
  de longitudes de onda.
- `docs/es/decisiones_tecnicas.md` y `docs/en/technical_decisions.md`: contratos
  de interfaz (`Scene`, `Detector`, `get_reference_spectrum`) y justificación de
  las decisiones de bandas, zona de estudio, máscara, remuestreo y reflectancia.
  Salda el entregable de documentación de Semana 0.
- CI en `.github/workflows/tests.yml`: corre `pytest` en Ubuntu sobre Python
  3.10 y 3.13 en cada push y pull request a `main`. Sin paso de lint hasta que
  `pre-commit run --all-files` pase limpio. Badge de estado en el README.
- `docs/es/pipeline.md` y `docs/en/pipeline.md`: el flujo real, etapa por etapa,
  desde el `.SAFE` hasta el `Scene` (`find_safe_dir`/`find_band_file` →
  `read_l2a_scaling` → `read_band_on_grid` → `dn_to_reflectance` →
  `build_cloud_mask` → `Scene`), con qué entra, qué sale y cuál es la decisión
  no obvia de cada una. Eran un placeholder desde Semana 0. La tabla de estado
  marca como pendientes de Nivel 1 lo que no existe —adquisición automática,
  orquestador, validación y visualización de resultados— para que el documento
  no prometa lo que no hay; el detector SAM se documenta como implementado pero
  sin nadie que lo corra. No duplica `decisiones_tecnicas.md`: cada decisión
  enlaza a la sección que la justifica.
- `scripts/visualizar_mascara.py`: CLI que produce la primera salida visual de
  `preprocessing/masking.py`, el módulo con las decisiones menos evidentes de la
  Semana 2 y el único que no se podía mirar. Relee la banda SCL del `.SAFE`
  sobre la misma ventana del `Scene` —derivada de su `transform` y su forma, no
  de `meta["aoi_window"]`, porque `meta` es documentación y no configuración— y
  con el mismo `nearest` (`resampling_for(..., categorical=True)`) con que la
  leyó el constructor.
- `visualization/maps.py`: `scl_to_rgb()` y `plot_scl_classes()`, más las
  constantes `SCL_COLORS` (la paleta con que Sen2Cor publica la Scene
  Classification) y `UNKNOWN_SCL_COLOR`. El SCL se colorea a mano en vez de
  dejarle un colormap a `imshow`: un colormap se escala a las clases presentes
  en el recorte, así que la misma clase saldría de un color en este AOI y de
  otro en el de al lado mientras la leyenda afirma que es la misma. La máscara
  se dibuja con `vmin=0, vmax=1` explícitos por el mismo motivo: sin ellos, una
  máscara sin un solo píxel inválido —el caso normal en este AOI— se dibuja
  negra, que es justo lo contrario de lo que significa.
- `outputs/figures/mascara_scl.png`: la evidencia de la máscara. A la izquierda
  el SCL coloreado, con leyenda de las 6 clases presentes y su porcentaje; a la
  derecha `Scene.mask`, con 99,9977 % de válidos y 92 píxeles descartados en el
  título. Los 92 descartados son píxeles sueltos, no una región.
- `tests/test_maps.py`: seis tests para las dos funciones nuevas. Cubren lo que
  falla sin lanzar nada: que el color de una clase no dependa de qué otras
  clases haya en el recorte, que un código fuera de `SCL_CLASSES` se pinte
  aparte en vez de confundirse con una clase declarada, que la leyenda solo
  nombre las clases presentes, que la máscara se dibuje con escala fija, que el
  título reporte válidos y descartados, y que dibujar un SCL y una máscara de
  formas distintas —dos ventanas distintas del tile— sea un error.

- `tests/test_sam.py` pasa de 4 a 24 tests (Semana 3, Track B). El núcleo es una
  batería de ángulos cuyo valor exacto se conoce **por construcción
  geométrica** —ortogonal → π/2, `[1,0]` contra `[1,1]` → π/4, `[1,0,0]` contra
  `[1,1,√2]` → π/3, `[1,0]` contra `[√3,1]` → π/6, antiparalelo → π— y no por
  comparación contra otra implementación de SAM: dos implementaciones que
  coinciden solo demuestran que coinciden, incluso si ambas se equivocan igual.
  Los casos exactos se verifican a `1e-12` y no al `1e-6` por defecto, porque
  una tolerancia holgada de más deja pasar justo lo que estos tests buscan; los
  dos que caen en los extremos de `arccos` van a `1e-7` por el piso de error
  intrínseco de esa función en ±1. Se suman un test-oráculo que compara la
  versión vectorizada contra un bucle `for` ingenuo sobre un cubo no cuadrado
  (un `einsum` con los ejes mal escritos no lanza nada: devuelve un mapa
  transpuesto que se ve razonable), la invariancia a escala en versión fuerte
  —cada píxel por un factor distinto—, el rango `[0, π]`, la simetría
  `θ(x, r) == θ(r, x)`, la independencia del `dtype` de entrada, un test por
  cada `ValueError` nuevo, y el contrato de bandas con el pipeline escrito como
  test: 9 contra 9 pasa, 12 contra 9 falla.
- `docs/*/decisiones_tecnicas.md` sección 8: el detector SAM. La fórmula y su
  contraste término a término contra el documento 05, la tabla de validaciones,
  la medición de precisión con los números a la vista, y la deuda de dirección
  del puntaje con fecha de revisión.
- `pipeline.py`: `run_pipeline(config)` implementado (era un stub). Encadena el
  hito de la Semana 3 completo —resolver el `Scene`, enmascarar, subconjuntar a
  `SAM_BANDS`, pedir la firma, correr el detector, escribir el GeoTIFF y el
  heatmap— y devuelve un `dict` con las rutas escritas y las estadísticas en
  vez de `None`: la función entrega datos y el script de CLI imprime. El
  detector se instancia desde `algorithm.name` a través del registro
  `DETECTORS`, así que el flujo no nombra a SAM en ninguna otra parte; agregar
  Random Forest es una clase y una entrada en ese diccionario. Primer consumidor
  de `SAM_BANDS` y de `aoi.window_px`, que estaban declarados sin que nadie los
  leyera.
- `io/raster_io.py`: `write_geotiff()` implementado (era un stub). Acepta un
  mapa 2D o un cubo 3D, escribe `float32` con `deflate`, `tiled`, el CRS y la
  `transform` del `Scene`, y `NaN` como nodata —un ángulo de 0 rad es
  coincidencia perfecta con la firma, así que usar 0 como centinela convertiría
  los píxeles enmascarados en las detecciones más fuertes del mapa—. Valida la
  forma espacial contra la del `Scene`: sin esa comprobación, un mapa calculado
  sobre otra ventana produce un GeoTIFF impecable, georreferenciado sobre el
  terreno equivocado, que no falla nunca. No escribe ningún tag propio (fecha,
  usuario, ruta), de modo que dos corridas dan el mismo archivo byte a byte y la
  reproducibilidad se comprueba comparando hashes. `read_scene()` sigue siendo
  un stub: es la contraparte de leer un `Scene` desde GeoTIFF y no bloquea nada.
- `visualization/maps.py`: `plot_score_map()` implementado (era un stub). Dos
  paneles: el mapa de ángulos con los ejes en coordenadas del CRS derivadas de
  `scene.transform` —no en índices de píxel, que no se pueden cruzar con
  ninguna otra capa— y el histograma de los ángulos válidos, que es el
  entregable de coherencia espectral: una cola hacia los ángulos bajos es
  evidencia de que el detector separa algo, y una campana simétrica es ruido con
  aspecto de resultado. La escala de color se recorta a los percentiles 2–98
  reusando las constantes del módulo, y los percentiles se calculan con
  `np.nanpercentile`: con `np.percentile` un solo `NaN` deja el panel entero
  plano sin lanzar nada.
- `scripts/run_pipeline.py`: acepta el config como `--config` además de la forma
  posicional con que nació, con error explícito si se pasan las dos o ninguna
  —elegir una en silencio correría el experimento con un config que nadie
  pidió—. Nuevo `--no-cache`, que reconstruye el `Scene` desde el `.SAFE`
  ignorando `data/interim/` (y sin sobrescribirlo).
- `outputs/maps/kaolinite_sam_angle.tif` y
  `outputs/figures/kaolinite_sam_angle.png`: las salidas del hito. El GeoTIFF no
  se versiona (regenerable y pesa 13 MB); el PNG sí, como el resto de las
  figuras.
- `tests/test_raster_io.py`: round-trip de `write_geotiff` (CRS, `transform`,
  dtype, nodata y valores leídos con `rasterio.open`), supervivencia de los
  `NaN`, escritura multibanda con descripciones, los tres `ValueError` y el test
  de reproducibilidad: dos escrituras del mismo mapa dan archivos con el mismo
  SHA-256.
- `tests/test_pipeline.py`: las tres piezas que el orquestador resuelve antes de
  tocar disco, extraídas a funciones propias para poder probarlas sin la escena
  —el registro de detectores, el resolutor de AOI (`window_px` sobre `bbox`) y
  la normalización de `scene.path`—.
- `tests/test_maps.py`: siete tests más para `plot_score_map`. Cubren que
  devuelva los dos paneles, que el colorbar declare el radián, que los ejes
  salgan en coordenadas del CRS, que un mapa con `NaN` no deje los límites del
  color en `NaN`, que la escala se recorte por percentiles, que el histograma
  cuente solo los píxeles válidos y que un mapa de forma distinta a la del
  `Scene` sea un error.

### Changed
- `SAM.predict` deja de fallar en silencio (Semana 3, Track B). Antes devolvía
  basura plausible o reventaba desde dentro de `np.einsum` con un mensaje sobre
  dimensiones de operandos que no menciona ni bandas ni firmas. Ahora lanza
  `ValueError` ante: cubo y firma con distinto número de bandas —nombrando **los
  dos largos**, porque el cruce concreto es `BAND_ORDER` (12) contra `SAM_BANDS`
  (9) y el pipeline lo vuelve cotidiano—, cubo que no es 3D, firma que no es 1D
  (una firma `(n, 1)` hacía broadcast y devolvía un mapa de la forma equivocada
  con valores plausibles), y firma degenerada, sea de norma cero —mismo criterio
  que `normalize_signature`— o con `NaN`, que volvía `NaN` el mapa completo y lo
  hacía indistinguible de una escena enteramente enmascarada.
  **No cambia** la firma `predict(cube, reference)`, ni el sentido del puntaje
  (ángulo en radianes, menor = más parecido), ni la tolerancia a `NaN` en el
  cubo: un cubo enmascarado con `apply_mask` es la entrada normal del detector.
- `SAM.predict` acumula el producto punto y la norma en `float64` vía el
  parámetro `dtype` de `np.einsum`, que fija el acumulador **sin castear el
  cubo**. Medido, no supuesto: acumulando en `float32` el error contra el cálculo
  en `float64` puro llegaba a 4,5 × 10⁻⁴ rad sobre píxeles casi idénticos a la
  firma, donde el ángulo verdadero era 1,3 × 10⁻⁵ rad —o sea 35 veces más chico
  que su propio error, y ese es justo el régimen de una detección—. Con el
  acumulador en `float64` baja a 3,9 × 10⁻⁸ rad, exactamente lo mismo que
  castear el cubo entero, y sin costo de memoria: el cubo real
  `(12, 2000, 2000)` sigue ocupando 183 MB en vez de los 366 MB de un `astype`.
- Se documentan dos comportamientos que ya existían pero no estaban escritos ni
  cubiertos: un píxel de norma cero devuelve `NaN` (devolver 0 lo declararía
  coincidencia perfecta y lo pintaría como la detección más fuerte del mapa), y
  `threshold()` descarta los `NaN` por la semántica de IEEE-754 y no por código,
  de modo que un `np.nan_to_num` «de limpieza» los convertiría en detecciones.
- `Detector.predict` deja anotada como deuda la contradicción de dirección del
  puntaje: el contrato dice «a mayor valor, mayor evidencia» y SAM devuelve un
  ángulo, donde menor es más parecido. **Solo se toca el texto, no el código.**
  Invertir el signo a mitad de sprint rompería el pipeline y la visualización
  del Track A sin lanzar ningún error. Y SAM no es el que se desvía: el
  documento 05 define el puntaje como el ángulo, y `viridis_r`,
  `angle_threshold_rad` y el `<=` de `threshold()` ya asumen esa dirección.
  Revisar antes del segundo detector.
- `pipeline.py` normaliza `scene.path` antes de buscar el producto: los configs
  apuntan a la carpeta `.SAFE` misma y `find_safe_dir(root)` busca carpetas
  `.SAFE` *bajo* `root`, así que pasarle la ruta del producto no encontraba nada
  y abortaba con un `FileNotFoundError` que culpaba a la escena de no estar
  descargada cuando estaba justo ahí. Era un bug latente: nadie lo había
  disparado porque nadie leía `scene.path` todavía. Se arregla en el pipeline y
  no en `find_safe_dir`, que ya tiene tests y otros consumidores.
- El `Scene` se cachea en `data/interim/scene.npz`, pero el caché **se verifica
  antes de usarse**: solo se reutiliza si su ventana y sus bandas son las que
  pide el config, y lo que no se pueda verificar (un AOI dado como `bbox`, un
  `.npz` sin `meta["aoi_window"]`) cuenta como no coincidente y se relee el
  producto. Un caché usado a ciegas es el peor modo de fallo del proyecto: el
  pipeline corre entero, escribe un GeoTIFF válido y el mapa es de otro AOI.
  `meta` sigue siendo documentación y no configuración —el AOI viene del config
  en todos los caminos—: lo único que puede hacer acá es vetar el caché.
- `configs/default.yaml`: `output` gana `maps_dir: outputs/maps/` y
  `figures_dir: outputs/figures/`. `configs/tamarugal_kaolinite.yaml` declara
  los nombres de salida del experimento (`angle_map`, `heatmap`).
  El roadmap nombra este archivo `chuqui_kaolinite.yaml`; el renombre a
  `tamarugal_kaolinite.yaml` fue deliberado cuando la zona cambió de
  Chuquicamata a Pampa del Tamarugal, y está documentado en la cabecera del
  propio YAML. No se crea ningún `chuqui_kaolinite.yaml`.
- `.gitignore`: `outputs/maps/` existe en un clon limpio vía `.gitkeep` para que
  el pipeline pueda escribir ahí sin crearla, pero sus `.tif` no se versionan.
  Mismo patrón que ya usaba `outputs/scratch/`.
- `docs/es/pipeline.md` y `docs/en/pipeline.md`: las etapas 8 y 10 pasan de
  «pendiente» a «implementada» en la tabla de estado, con el flujo real de
  `run_pipeline` descrito en el mismo formato Entra / Sale / La decisión no
  obvia de las etapas 1 a 7, más un diagrama de `Config` a mapa y la fila del
  comando en «Cómo se corre». «Lo que falta» queda solo con la etapa 9, que es
  justamente lo que impide llamar «detección de caolinita» al mapa.
- `README.md`: el quickstart invoca con `--config`, y «Resultados» reemplaza
  «Detección: pendiente» por las cifras medidas sobre el AOI completo —mínimo
  0,0723 rad, mediana 0,2742, máximo 0,6971— y el barrido de umbrales. **El
  umbral `0.1` del config sí deja píxeles bajo él en el AOI completo: 62 de
  3.999.908 (0,002 %).** La cifra de «ni un solo píxel» que traían el README y
  `pipeline.md` viene de `decisiones_tecnicas.md` §7, donde la medición se hizo
  sobre una ventana de 256 × 256 px (0 de 65.536): sigue siendo cierta para esa
  ventana y no se generaliza al AOI de 2000 × 2000. Aun así el repositorio no
  reporta caolinita detectada: 62 píxeles sueltos de 4 millones no son una
  detección, el ángulo espectral mide parecido con una firma de laboratorio y no
  presencia de un mineral, y la validación contra cartografía sigue sin existir.
- CI: se agrega el job `lint`, que corre `pre-commit` (black, ruff, isort,
  nbstripout) sobre todos los archivos. El workflow decía que el paso se
  agregaría cuando `pre-commit run --all-files` pasara limpio; ya pasa. Va como
  job aparte del de tests porque el formato no depende de la versión de Python.
- Todo el repositorio pasa `pre-commit run --all-files`: `black` reformateó
  cuatro archivos, `ruff` arregló tres errores y se acortaron a mano cinco
  docstrings que excedían las 88 columnas. Los notebooks ganaron el campo `id`
  por celda que exige nbformat 4.5+.
- El `Scene` pasa de 6 a 12 bandas (`BAND_ORDER`); `COMMON_BANDS` se conserva
  como subconjunto documentado, ya no como valor por defecto.
- Zona de estudio: de Chuquicamata a Pampa del Tamarugal (tile `T19KDT`), por
  disponibilidad de datos. `configs/chuqui_kaolinite.yaml` pasó a
  `configs/tamarugal_kaolinite.yaml`.
- Criterio único de máscara SCL: se descartan las clases `[0, 1, 2, 3, 6, 8, 9,
  10, 11]`, ahora incluyendo agua (6). Antes convivían dos criterios distintos
  en el repositorio.
- `scripts/construir_scene.py` queda como CLI delgado (`argparse`); toda su
  lógica se movió al paquete.
- Las figuras de `outputs/figures/` se versionan: son la evidencia de cada hito.
- `outputs/figures/` queda reservada a entregables. Las salidas exploratorias
  van a `outputs/scratch/`, que no se versiona;
  `scripts/explorar_banda_b12.py` escribe ahí y `banda_12_reflectancia.png`
  dejó de estar en el repositorio.
- `README.md` apuntaba a `configs/chuqui_kaolinite.yaml`, renombrado en el
  commit anterior; el quickstart usa ahora `configs/tamarugal_kaolinite.yaml`.
- `README.md`: la sección «Resultados» (ES y EN) deja de ser un placeholder.
  Documenta el AOI de 40 × 40 km sobre el tile `T19KDT`, el 99,92 % de suelo
  desnudo y el 99,9977 % de píxeles válidos —3.999.908 de 4.000.000, o sea 92
  descartados; las dos cifras salen de `Scene.meta["scl_summary"]`—, más una
  línea por cada figura de `outputs/figures/` explicando qué muestra. La
  detección de caolinita queda marcada como pendiente y sin cifras: el SAM está
  implementado y testeado, pero no hay orquestador que lo corra sobre la escena
  ni validación contra cartografía, así que no hay ningún resultado de
  detección que reportar. De paso, el árbol de «Estructura» decía que
  `outputs/` no se versiona, cuando `outputs/figures/*.png` sí lo hace desde el
  commit que fijó esa excepción en `.gitignore`.

### Removed
- `construir_scene_final()` de `scripts/construir_scene.py`: estaba marcada
  DEPRECADO y no la importaba nadie (verificado por búsqueda en todo el
  repositorio). Su reemplazo es `build_scene_from_safe()` directamente.
