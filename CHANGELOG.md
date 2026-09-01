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
- `SAM_BANDS` en `config.py`: declara las 9 bandas que consume el detector
  espectral (excluye B1 y B9, atmosféricas, y B8, redundante con B8A). Se
  declaró en la Semana 2 sin consumidores —la decisión escrita y testeada antes
  de que existiera el pipeline, cubierta por `tests/test_config.py`— y desde la
  Semana 3 lo consume `SAM`, que lo declara como su atributo `bands`.
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
  entregable de coherencia espectral: lo que hay que mirar en él es si el
  extremo que interesa está sobrepoblado respecto de una campana, no hacia
  dónde cae la cola larga. La escala de color se recorta a los percentiles 2–98
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

#### Semana 4, Track A: la capa de verdad de terreno

- `validation/geology.py` implementado. `load_geology_polygons()` (lee el
  vectorial y exige CRS y geometrías de polígono), `clasificar_unidades()`
  (asigna la clase según el YAML y avisa por `warnings.warn` cuántas unidades
  quedaron sin clasificar y qué superficie representan),
  `rasterize_ground_truth()` (reproyecta a `scene.crs` y quema los polígonos a
  la grilla exacta del `Scene`, con `all_touched=False`) y `build_ground_truth()`
  (orquesta el camino completo y devuelve el raster más un dict de
  trazabilidad). También `cargar_config_verdad()`, que valida el YAML y rechaza
  una unidad declarada como positivo y negativo a la vez.
- `scripts/descargar_geologia.py`: descarga las dos hojas 1:100.000 de
  SERNAGEOMIN que cubren el AOI —Pozo Almonte (M204) y Mamiña (M303)— desde el
  FeatureServer `Chile_Geology`, paginando con `resultOffset`, y las deja en
  EPSG:32719 bajo `data/external/geologia/`. Imprime por capa el n° de features,
  el CRS, el bbox y la tabla de unidades con conteo y área, que es el insumo con
  que se llena el YAML. Solo `urllib` de la stdlib: no se agregó `requests`.
- `data/external/geologia/`: los dos GeoJSON (1.449 y 1.309 polígonos) y su
  README con la fuente, la fecha, la advertencia de que es una digitalización de
  terceros sin licencia declarada y la cita de las cartas originales. Se
  versionan mediante una excepción explícita en `.gitignore`, con el mismo
  criterio que las firmas `.txt`: son livianos, no se regeneran desde ningún dato
  local y son la evidencia reproducible de contra qué se validó.
- `configs/verdad_terreno_tamarugal.yaml` (renombrado a
  `verdad_terreno_cerro_colorado.yaml` en la Semana 5): el mapeo unidad → clase,
  revisable
  sin leer código. Llega con las listas **vacías** a propósito —la selección es
  un juicio geológico y la hace una persona— y con la lista completa de las 38
  unidades presentes en el AOI, su superficie y una propuesta comentada por
  unidad.
- `scripts/construir_verdad_terreno.py`: CLI que carga el `Scene`, construye la
  capa, la escribe en `outputs/maps/ground_truth.tif` con `write_geotiff` e
  imprime la trazabilidad completa.
- `visualization/maps.py::plot_overlay_geologia()`: la figura F5, el mapa de
  ángulos con los polígonos geológicos encima, ejes en UTM, barra de escala y
  leyenda que nombra las tres clases incluso cuando alguna no está presente.
  La produce `scripts/figura_overlay_geologia.py` en
  `outputs/figures/overlay_deteccion_geologia.png`, leyendo el `.tif` ya escrito
  en vez de recalcular el SAM.
- `tests/test_geology.py`: 22 tests sin red y sin la escena de 196 MB, sobre un
  `Scene` sintético de 10×10 px y polígonos de coordenadas conocidas. Cubren la
  alineación con el `Scene`, la corrección geométrica contada a mano, la
  reproyección desde 4326 —el fallo que no se nota—, el `fill` a 255, el
  comportamiento de `all_touched` en un píxel rozado, las unidades sin clasificar
  con su warning, la normalización de espacios en las etiquetas y los errores con
  mensaje útil. Dos tests con `skipif` verifican, cuando los GeoJSON reales están
  en disco, que la unión de ambas hojas contenga el bbox del AOI y que no haya
  hueco en la costura.

#### Semana 5: el AOI se movió al distrito Cerro Colorado

- **Se reubicó la ventana del AOI** de `col_off=1000, row_off=1000` a
  `col_off=2700, row_off=650`, sobre el mismo tile `T19KDT` y la misma escena.
  Sigue midiendo 2000 × 2000 px a 20 m (40 × 40 km): la ventana se desplaza al
  noreste, no crece.

  **El motivo es que el criterio E3 del Plan Maestro no se podía cumplir.** Al
  construir la capa de verdad de terreno en la Semana 4 se descubrió que dentro
  del AOI de la Pampa del Tamarugal no había **ni una sola unidad con alteración
  hidrotermal cartografiada**: el 96 % era relleno sedimentario, y las tres
  unidades candidatas de la hoja Mamiña caían fuera —las brechas hidrotermales a
  29,5 km del borde este, el Complejo intrusivo Cerro Colorado a 10,3 km y el
  Complejo Yabricoya a 19,1 km—. Con cero zonas documentadas, «las detecciones
  se concentran preferentemente en zonas de alteración documentadas» no se podía
  ni formular, y E4 (recall, F1, ROC/AUC) tampoco.

  `row_off` baja de 1000 a 650 porque Cerro Colorado está al **noreste**: su
  borde sur quedaba 2,4 km por encima del borde norte del AOI anterior, así que
  ampliar solo hacia el este lo habría dejado afuera.

  Qué cambió en las cifras publicadas:

  | | AOI Tamarugal | AOI Cerro Colorado |
  |---|---|---|
  | Píxeles válidos | 99,9977 % (92 descartados) | 99,8484 % (6.064 descartados) |
  | Suelo desnudo (SCL 5) | 99,92 % | 99,8085 % |
  | Ángulo mín / p1 / mediana / máx | 0,0723 / 0,2055 / 0,2742 / 0,6971 | 0,0662 / 0,2004 / 0,2795 / 0,6859 |
  | Detecciones a 0,1 rad | 62 | 131 |
  | Positivo en la verdad de terreno | 0 px | 50.773 px (1,27 %) |
  | Exceso sobre el ruido a 0,1 rad | 143 × | 3 × |

  La caída de píxeles válidos es sombra topográfica (0,1505 % del AOI): la
  ventana entra en la Precordillera y tiene relieve. El exceso sobre el ruido
  baja porque este AOI tiene mucha más variedad litológica y su distribución de
  ángulos es más ancha, no porque el detector empeorara.

- **Configs renombrados con `git mv`** para conservar el historial:
  `tamarugal_kaolinite.yaml` → `cerro_colorado_kaolinite.yaml` y
  `verdad_terreno_tamarugal.yaml` → `verdad_terreno_cerro_colorado.yaml`. El
  archivo del experimento ya se había llamado `chuqui_kaolinite.yaml`; dejarlo
  como «tamarugal» apuntando a Cerro Colorado repetiría el error que aquel
  rename vino a corregir. `DEFAULT_AOI_WINDOW` en `scene_builder.py` se movió
  con él: si divergen, entrar por el config y entrar sin él dan dos zonas de
  estudio distintas y ninguna de las dos falla.

- **El YAML de verdad de terreno se llenó**, con propuesta marcada unidad por
  unidad. 8 unidades positivo (20,30 km², 1,27 % del AOI): brechas hidrotermales
  de turmalina, ambas facies del Complejo intrusivo Cerro Colorado y los
  pórfidos félsicos. 10 unidades negativo (76,94 km², 4,81 %). El resto,
  ambiguo (93,92 %). Las facies plutónicas del Complejo Yabricoya (81,65 km²)
  **no** son positivo pese a pertenecer al complejo: son roca de caja, no el
  sistema porfídico, e incluirlas multiplicaría el positivo por cinco sin
  alteración declarada.

- **Los botaderos de la mina Cerro Colorado (16,79 km², 1,05 % del AOI) se
  clasificaron como ambiguo de forma explícita**, no por omisión, porque las dos
  lecturas defendibles se anulan y porque la mina está donde está *porque* hay
  alteración —declararla positivo casi garantizaría el acierto—. La decisión
  resultó determinante: **de las 131 detecciones a 0,1 rad, 130 caen exactamente
  sobre esos botaderos**. Con ellos declarados positivo, el 99,2 % de las
  detecciones caería en positivo y E3 se cumpliría; con la clasificación
  adoptada, **cero detecciones caen en positivo y E3 no se cumple**. Dentro de
  las unidades de alteración cartografiada el ángulo mínimo es 0,1541 rad, muy
  por encima del umbral.

- **Todas las cifras publicadas se rehicieron** en `README.md` (ambos idiomas),
  `docs/{es,en}/pipeline.md` y `docs/{es,en}/decisiones_tecnicas.md`, y
  `scripts/verificar_cifras.py` vuelve a pasar limpio sobre las 36 que coteja.
  Se agregó la sección 10 a los dos documentos de decisiones técnicas con las
  tres cosas que hay que poder defender. Las cifras del AOI anterior **no** se
  conservan como referencia en los documentos: se cuentan una sola vez, aquí y
  en esa sección 10.

- **Todas las figuras se regeneraron** sobre la ventana nueva: `scene_rgb.png`,
  `mascara_scl.png`, `kaolinite_sam_angle.png`, `kaolinite_signature.png`,
  `kaolinite_signature_vs_pixel.png`, `overlay_deteccion_geologia.png` y las de
  `outputs/scratch/`. La ventana de exploración del notebook se movió a
  `col_off=2700, row_off=650` para que siga compartiendo esquina con la
  autoritativa.

- **Tests actualizados a la ventana nueva**: `tests/test_pipeline.py`
  (`WINDOW_PX`, el bbox y `VENTANA_DEFAULT`) y `tests/test_geology.py`
  (`AOI_BBOX` y los dos tests atados al AOI anterior). Se agregó
  `test_las_unidades_de_alteracion_caen_dentro_del_aoi`, que ancla la razón de
  ser de la ventana: sin esas unidades adentro no hay positivo posible y E3
  vuelve a ser informulable.


#### Semana 6: las métricas de validación, y el resultado que dan

- **`validation/metrics.py` implementado**, con las cinco métricas del stub más
  las piezas que hacían falta para poder defenderlas: `confusion_matrix`,
  `precision_score`, `recall_score`, `f1_score`, `iou_score`, `cohen_kappa`,
  `roc_auc`, `curva_roc`, `preparar_pares`, `evaluar_deteccion` y
  `evaluar_desde_rasters`. Todo en NumPy puro; `scikit-learn` aparece solo
  dentro de los tests, bajo `pytest.importorskip`, como oráculo de contraste.

  Tres decisiones de diseño que no son obvias y que están argumentadas en
  `docs/es/decisiones_tecnicas.md`, sección 11:

  **`preparar_pares` es el único sitio que decide qué píxel entra al cálculo.**
  Si cada métrica aplicara su propio filtro, bastaría con que una olvidara
  excluir los ambiguos para que la tabla mezclara números calculados sobre
  poblaciones distintas —la matriz de confusión sobre 242.967 píxeles y el AUC
  sobre 3.993.936— presentados en la misma columna, sin que nada falle.

  **El AUC exige la dirección del puntaje como argumento obligatorio y por
  palabra clave.** El ángulo del SAM va al revés: menor es más evidencia. Un AUC
  calculado con la dirección invertida devuelve `1 - AUC` —0,7597 en vez de
  0,2403—, no lanza ninguna excepción y se puede defender en una presentación.
  La dirección viaja desde `Detector.higher_is_better`, su única fuente de
  verdad, y no desde una constante escrita en el script.

  **El AUC promedia los empates** (Mann-Whitney U con rangos promedio,
  equivalente a la regla del trapecio). No es una precaución teórica: sobre los
  242.967 píxeles evaluables hay 238.202 valores distintos, o sea 4.765 empates
  reales, porque el ángulo se almacena en `float32`.

  F1 e IoU devuelven `0.0` —no `ValueError` ni `nan`— cuando no hay ninguna
  detección predicha, porque ése es exactamente el caso de la corrida principal
  y hay que poder reportarlo. `roc_auc`, en cambio, **lanza `ValueError` con una
  sola clase presente**: un `nan` devuelto ahí acabaría impreso en una tabla
  como si fuera una medición.

- **`scripts/evaluate.py` implementado**, siguiendo el patrón de
  `construir_verdad_terreno.py`: solo parsea argumentos, llama al paquete e
  imprime. Argumentos `--threshold`, `--scene`, `--out` (JSON), `--figura` y
  `--config`. El umbral y la dirección salen del config del experimento, no de
  constantes del script. Antes de comparar nada, aborta si los dos GeoTIFF no
  comparten CRS, transform y forma: dos rásteres desalineados producen una
  matriz de confusión y un AUC impecables sobre pares de píxeles que no son el
  mismo punto del terreno, y no hay inspección de la salida que lo delate.

- **`visualization/validacion.py`**: `plot_curva_roc` y
  `plot_histograma_por_clase`. Van en la misma figura a propósito, porque un AUC
  solo no distingue «las distribuciones se superponen» de «están separadas, pero
  al revés», y esas dos lecturas llevan a decisiones opuestas. La figura es
  `outputs/figures/roc_kaolinite_sam.png`.

- **`tests/test_metrics.py`**: 42 pruebas, todas con valores calculados a mano y
  escritos como literales, sin red y sin la escena de 196 MB. Cubren la
  exclusión de los `255` y de los `NaN`, la complementariedad `AUC + AUC' = 1`
  al invertir la dirección, el caso desbalanceado en que un clasificador que
  dice «no» a todo tiene 98 % de exactitud y F1 = 0, y los fallos ruidosos.

- **El resultado, que es negativo y se reporta tal cual.** Sobre 242.967 píxeles
  evaluables (se descartan 3.756.783 ambiguos y 250 sin dato):

  | | valor |
  |---|---|
  | VP / FP / FN / VN | 0 / 0 / 50.731 / 192.236 |
  | precisión, recall, F1, IoU, kappa | 0,0000 |
  | **ROC AUC** | **0,2403** |

  Los ceros son un solo hecho contado cinco veces: con el umbral del config no
  hay ninguna detección dentro de las clases evaluables. El número que informa
  es el AUC, porque no depende del umbral, y **0,2403 está por debajo del 0,5
  del azar**: el detector no es que no separe, es que **separa al revés**. La
  mediana del ángulo es 0,3288 rad dentro del positivo y 0,2712 dentro del
  negativo — las unidades que la cartografía declara compatibles con alteración
  se parecen *menos* a la caolinita de laboratorio que las que declara no
  candidatas.

  No se ajustó nada para mejorar el número. No se reclasificó ninguna unidad del
  YAML, no se movió el umbral y no se cambió el filtro de píxeles. Las tres
  hipótesis que podrían explicarlo —que la arcilla expuesta esté en los
  botaderos y no en la roca *in situ*, que el barniz del desierto enmascare la
  firma, o que 9 bandas a 20 m no basten para separar caolinita de otras
  superficies— están en decisiones técnicas, sección 11.1, sin elegir entre
  ellas.

- **La calibración del umbral existe, y no rescata nada.** El umbral que
  maximiza el índice de Youden es 0,4467 rad y alcanza J = 0,0034, separación
  indistinguible de cero. El que maximiza F1 es 0,4492 rad y detecta 242.276 de
  los 242.967 píxeles: es el clasificador que dice «sí» a todo, cuyo F1 sería
  0,3455 por construcción. **`angle_threshold_rad` sigue en 0,1 en el config**:
  lo que la calibración aporta no es un número nuevo para el YAML, es la
  evidencia de que el problema no está en el umbral. Cambiarlo es decisión de la
  dueña del repositorio.

### Changed

#### Cierre de la Semana 3: seis defectos de documentación y arquitectura

- **El pipeline decía no conocer a SAM, y lo nombraba en cinco lugares.**
  `pipeline.py` afirmaba «el pipeline no menciona SAM en ninguna otra parte del
  encadenado» mientras importaba `SAM_BANDS` y `threshold`, recortaba el cubo a
  las nueve bandas de SAM incondicionalmente y binarizaba con el `<=` del
  ángulo. **Qué fallaba**: un detector que respetara el contrato de `base.py`
  —a mayor valor, mayor evidencia— y devolviera 0,9 en todo el AOI, o sea
  evidencia máxima, hacía que el barrido reportara cero píxeles bajo los cinco
  umbrales sin lanzar nada; y recibía las bandas de SAM aunque necesitara otras.
  Se habría descubierto el día del primer commit de Random Forest, con el
  pipeline entero corriendo y reportando cero. **Qué se hizo**: `Detector` gana
  `higher_is_better`, `bands` y el método `detects()`; `SAM` declara `False` y
  sus nueve bandas; el pipeline instancia el detector antes de subconjuntar y le
  pregunta las dos cosas. `threshold()` se conserva intacta —es pública y tiene
  tests—, solo dejó de usarla el pipeline. `SAM_BANDS` ya no se importa en
  `pipeline.py`, y esa ausencia es la prueba de que el acoplamiento se fue. La
  salida no cambia un solo píxel: `higher_is_better = False` es exactamente lo
  que el flujo asumía.
- **La cola del histograma estaba descrita al revés.** El README, los dos
  `pipeline.md`, el docstring de `plot_score_map` y este mismo archivo decían
  «una cola hacia los ángulos bajos, no la campana simétrica que daría el
  ruido». Medido: la asimetría es **+0,7586** y la cola larga va hacia los
  ángulos **altos**. **Qué fallaba**: la evidencia de coherencia espectral del
  hito estaba justificada con una propiedad que los datos no tienen, y quien
  mirara la figura vería lo contrario de lo escrito. **Qué se hizo**: se
  reemplaza por la afirmación correcta, que además es más fuerte —0,1 rad está
  a 5,2 desviaciones estándar bajo la media, donde una gaussiana daría 0,43
  píxeles en 4 millones y hay 62, o sea 143 veces el ruido— y en el docstring
  por su forma general: el histograma sirve para ver si el extremo que interesa
  está sobrepoblado respecto de una campana, no hacia dónde cae la cola larga.
- **La figura `kaolinite_signature_vs_pixel.png` se presentaba sin acotar su
  ventana.** El README decía «dos píxeles reales del AOI», y el notebook que la
  produce usa la ventana de exploración de 256 × 256 px: su píxel de menor
  ángulo tiene 0,1640 rad, mientras que el del AOI de 2000 × 2000 tiene 0,0723
  y está en (1757, 667). **Qué fallaba**: es exactamente el error que la sección
  7 declara prohibido —«toda cifra de ángulo tiene que decir sobre qué ventana
  se midió»— cometido tres filas más abajo de la tabla que define el AOI como
  los 2000 × 2000. **Qué se hizo**: se acota a la ventana del notebook y se
  nombra el ángulo del píxel a la vista.
- **La conclusión sobre la caída B11 → B12 era falsa a la escala del AOI.** El
  README decía «ninguno de los dos píxeles acompaña la caída B11 → B12». Medido:
  los 62 píxeles bajo 0,1 rad descienden **los 62** (razón B12/B11 mediana
  0,679) contra un fondo con mediana 1,011 donde solo el 44 % desciende algo, y
  el píxel de la propia figura también desciende, apenas (0,944 contra el 0,507
  de la firma USGS). **Qué se hizo**: en el README, el matiz correcto —el píxel
  no reproduce la caída *pronunciada*, no que no caiga—; y en la sección 7 de
  los dos documentos de decisiones técnicas, el hallazgo que no estaba escrito
  en ninguna parte: los 62 están sobre suelo desnudo (SCL 5 los 62), con
  reflectancia media 0,391 contra 0,229 del fondo, en 26 componentes conexas,
  ninguno a menos de 7 px del borde, y con la mediana del vecindario de 5 × 5
  sin el píxel central en 0,1394 rad contra 0,2742 de la escena —38 de los 62
  con ese vecindario también bajo 0,15—. El estadístico va nombrado porque
  cambia la respuesta: la media del mismo vecindario da 0,1522 y 28 de 62.
  Encabezado dejando claro que **sigue sin ser una detección**: la dirección de
  un rasgo de absorción no identifica un mineral mientras la etapa 9 no exista.
- **Pedir una banda que el `Scene` no trae fallaba con un mensaje anónimo.** Es
  la superficie que estrenó `detector.bands`: `scene.band_names.index(banda)`
  lanzaba `'B99' is not in list`, que es ruidoso —no es un fallo silencioso—
  pero no dice quién pidió esa banda ni cuáles hay disponibles, así que había
  que abrir el código para ubicar el problema. El repositorio ya se exige lo
  contrario en `_crear_detector` y en `find_band_file`. **Qué se hizo**: un
  `ValueError` previo que nombra la clase del detector, las bandas que faltan y
  las que el `Scene` sí trae, y apunta a los dos sitios donde puede estar el
  error (el atributo `bands` o `scene.bands` del config).
- **`SAM_BANDS` seguía titulado «declarado y todavía no consumido».** Lo consume
  el pipeline desde la Semana 3, y este archivo lo afirmaba y lo negaba con 25
  líneas de diferencia. **Qué se hizo**: se retitula a «consumidas por el
  detector desde la Semana 3» en los dos documentos, se corrige el cuerpo, se
  reconcilia la entrada contradictoria de este CHANGELOG y se actualizan los dos
  enlaces que apuntaban al ancla vieja, que si no quedaban rotos.
- **El invariante de `Scene.meta` estaba escrito más fuerte de lo que el código
  cumple.** Cuatro documentos decían «nada del pipeline lee de `meta` para
  decidir qué hacer», y el pipeline lee `meta["aoi_window"]` para vetar el caché
  y `tile_id`/`sensing_date` para el título de la figura. **Qué se hizo**: el
  código está bien y no se toca; se lleva a los cuatro documentos la versión
  precisa que ya vivía en el docstring de `_cache_coincide` —nada del pipeline
  *toma de `meta` un parámetro que decida qué se calcula*, el AOI viene del
  config en todos los caminos y lo único que `meta` puede hacer es **vetar** el
  caché— y se menciona además el uso cosmético del título.
- **El `.npz` no es reproducible byte a byte** y no estaba dicho en ninguna
  parte. `meta["created_at"]` hace que dos reconstrucciones del mismo AOI den
  hashes distintos aunque el cubo sea idéntico. No afecta a E1 —el `.tif` sí
  sale idéntico— y el `created_at` se conserva a propósito, porque la
  procedencia vale más que un hash que nadie compara. Se anota en la etapa 6 de
  los dos `pipeline.md` para que nadie use ese hash como identidad de contenido.
- `scripts/verificar_cifras.py`: CLI que recalcula desde el `.tif` las cifras
  que publican el README y la sección 7, las parsea de los propios documentos
  —tolerando la coma decimal del ES y el punto del EN, y los separadores de
  miles de los dos— y sale con código 1 si alguna no calza. Existe porque que
  las cifras coincidan con la corrida era una comprobación manual que ya falló
  una vez. No escribe nada y no va en CI: necesita la escena, que el runner de
  GitHub no tiene.
- Tests de regresión de todo lo anterior: que el pipeline respete la dirección
  declarada por el detector y subconjunte con las bandas que declara, que
  `detects` herede el sentido del contrato y no cuente los `NaN`, los cinco
  casos de `_cache_coincide`, y que el GeoTIFF no lleve los tags TIFF de fecha,
  usuario, software ni XMP —promesa que hasta ahora vivía solo en un comentario
  y que es la que sostiene E1—.
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

#### Semana 6: deudas técnicas cerradas de paso

- `algorithms/random_forest.py` y `algorithms/unmixing.py`: **firmas alineadas
  al contrato**. Ambas declaraban `predict(self, cube)`, un argumento menos que
  `Detector.predict(self, cube, reference)`. Python no comprueba las firmas al
  heredar, así que la contradicción no rompía nada mientras el cuerpo lanzara
  `NotImplementedError` — pero el día que alguien escribiera el cuerpo, el
  pipeline lo habría llamado con dos argumentos y habría reventado con un
  `TypeError` a mitad de una corrida larga, lejos de la causa. El cuerpo sigue
  igual. El `fit()` que ninguna de las dos hereda del contrato se conserva,
  documentado explícitamente como extensión fuera de `Detector`: un clasificador
  supervisado necesita un paso previo con estado, y resolver ese hueco es
  trabajo de Nivel 2, no algo que se decida de pasada.

- `scripts/verificar_cifras.py`: **también coteja las métricas nuevas**. Se le
  añadieron `--ground-truth` y `--config`, y la regla del repo se mantiene: 80
  cifras publicadas a mano en README, `decisiones_tecnicas.md` y
  `technical_decisions.md` tienen ahora un chequeo automático que las contradice
  cuando envejezcan. Los rótulos de los dos bloques del README (ES y EN) deben
  ser textualmente distintos, porque el archivo es uno solo y cada pasada lo
  recorre entero: un rótulo compartido haría que la pasada ES leyera la fila EN
  con la convención decimal equivocada, y «0.2403» interpretado como español da
  2403.

- Documentación actualizada al estado real: la etapa 9 pasa de «parcial» a
  implementada en `docs/es/pipeline.md` y `docs/en/pipeline.md`, la sección 7 de
  decisiones técnicas deja de decir que el umbral «espera un criterio», y el
  README publica la tabla de métricas en sus dos bloques.

### Removed
- `construir_scene_final()` de `scripts/construir_scene.py`: estaba marcada
  DEPRECADO y no la importaba nadie (verificado por búsqueda en todo el
  repositorio). Su reemplazo es `build_scene_from_safe()` directamente.
