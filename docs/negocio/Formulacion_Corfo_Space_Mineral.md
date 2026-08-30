# Space Mineral — Formulación de proyecto para postulación a fondos públicos (Corfo / ANID)

**Versión:** borrador 1.0 · 30 de agosto de 2026
**Autoras/es:** Camila (dirección técnica) y Carlos Peña — *DECLARADO, confirmar roles formales*
**Estado del proyecto:** cierre de la etapa de validación técnica (Nivel 1)

> **Etiquetas de certeza usadas en todo el documento**
> - **VERIFICADO** — contrastado contra el repositorio, un documento del proyecto o una fuente pública citada.
> - **DECLARADO** — lo afirma el equipo, sin documento de respaldo todavía.
> - **INFERIDO** — deducción razonada a partir de datos verificados.
> - **SUPUESTO** — cifra o afirmación de relleno, puesta para que el documento sea utilizable. Hay que reemplazarla antes de postular.
>
> Ninguna cifra de este documento debe entrar a un formulario de postulación con etiqueta SUPUESTO sin reemplazarla primero.

---

## 0. Advertencia antes de usar este documento

El repositorio dice hoy que la **etapa 9 (validación contra cartografía) está pendiente**: `validation/metrics.py` tiene `f1_score`, `iou_score`, `roc_auc` y `cohen_kappa` como `NotImplementedError`, y `scripts/evaluate.py` es andamiaje. Lo que sí existe es la capa de verdad de terreno (`outputs/maps/ground_truth.tif`) y un conteo de dónde caen las detecciones. **VERIFICADO** (`docs/recorrido/12_estado_y_pendientes.md`, `README.md`).

Consecuencia práctica: hoy el proyecto **no puede afirmar en una postulación que la detección está validada**. Puede afirmar que el pipeline es reproducible, que la verdad de terreno está construida y que el primer contraste espacial arrojó un resultado interpretable. Esa distinción es la diferencia entre un proyecto sólido y uno que se cae en la evaluación técnica, donde suele haber un geólogo o un teledetectista leyendo.

Segunda advertencia, del mismo peso: el resultado medido dice que **130 de 131 detecciones caen sobre botaderos de mina**, y **cero sobre las unidades de alteración hidrotermal cartografiadas** (**VERIFICADO**, README). Eso no respalda la propuesta de valor "priorizar exploración greenfield". Respalda otra cosa, que es explotable comercialmente y está desarrollada en la sección 3.2.

---

## 1. Identificación del proyecto

| Campo | Contenido |
|---|---|
| Nombre | **Space Mineral** — Mapeo espectral de minerales de alteración desde satélite |
| Línea | Deep tech / teledetección aplicada a minería |
| Sector económico | Minería, servicios de exploración y monitoreo ambiental minero |
| Región de ejecución | *A definir según el fondo* (ver documento de fondos, sección de estrategia regional) |
| Etapa | Prototipo funcional con validación técnica en curso — **TRL 3, transitando a TRL 4** (INFERIDO) |
| Repositorio | `github.com/carlospena-pixel/Space-Mineral` (**VERIFICADO**, badge de CI en README) |

**Qué significa TRL.** *Technology Readiness Level* es la escala de 1 a 9 que usan Corfo, ANID y la industria para decir cuán maduro está un desarrollo. TRL 1 es una idea con base científica; TRL 3 es prueba de concepto en laboratorio; TRL 6 es prototipo demostrado en entorno relevante; TRL 9 es producto operando en el mercado. Se declara en casi todos los formularios de postulación, así que conviene tenerlo definido y defendible.

---

## 2. Problema

### 2.1 El problema, en una frase

Explorar minerales cuesta caro y falla casi siempre: la decisión de dónde perforar se toma con información de terreno costosa y espacialmente escasa, y cada campaña de sondaje que se hace en la zona equivocada quema capital sin generar información nueva.

### 2.2 Magnitud, con cifras verificables

- Chile destinó **US$ 874,7 millones a exploración minera en 2025**, el nivel más alto desde 2013. **VERIFICADO** (Catastro Cochilco 2025, vía Reporte Minero, feb. 2026).
- El **76 % de ese presupuesto (US$ 669,6 millones) va a cobre**. **VERIFICADO** (misma fuente).
- El catastro identifica **235 prospectos y proyectos, de los cuales 158 están activos y 77 suspendidos**. **VERIFICADO**.
- **Atacama, Antofagasta y Coquimbo concentran más del 80 % de los prospectos activos.** **VERIFICADO**.
- El presupuesto mundial de exploración fue de **US$ 12.401 millones en 2025**, con América Latina capturando el 26,5 %. **VERIFICADO**.
- Las **junior** (empresas exploradoras pequeñas, sin producción, que viven de levantar capital para explorar) **redujeron su gasto un 13,4 %**, mientras las grandes mineras subieron al 53,4 % del presupuesto. **VERIFICADO**.

Ese último dato es el que hay que subrayar en una postulación: **el capital de exploración se está concentrando y volviendo más averso al riesgo**. Una herramienta que permita descartar zonas barato, antes de mover una camioneta, tiene su mercado justo ahí.

### 2.3 Por qué el problema persiste

- La información espectral satelital gratuita (Sentinel-2, 13 bandas) existe hace años, pero convertirla en un mapa defendible exige preprocesamiento riguroso, una librería espectral de referencia y validación contra cartografía. Eso no está empaquetado. **INFERIDO**, a partir del propio esfuerzo del proyecto.
- Los productos comerciales que sí lo hacen bien usan sensores hiperespectrales (cientos de bandas) de acceso pagado, y su costo los deja fuera del alcance de una junior. **SUPUESTO — requiere levantamiento de competencia con precios reales antes de postular.**

---

## 3. Solución

### 3.1 Descripción técnica

Software en Python que toma una escena Sentinel-2 nivel L2A (reflectancia de superficie, ya corregida de atmósfera) y produce un mapa georreferenciado de similitud espectral con un mineral de referencia de la librería USGS splib07, validado contra la cartografía geológica del SERNAGEOMIN.

Flujo, etapa por etapa (**VERIFICADO** contra `docs/recorrido/12_estado_y_pendientes.md`):

| # | Etapa | Estado hoy |
|---|---|---|
| 0 | Adquisición de la escena | Manual (descarga desde CDSE) |
| 1–2 | Localizar producto, bandas y escalado | Implementada |
| 3 | Recorte al área de interés y remuestreo a 20 m | Implementada |
| 4 | Escalado a reflectancia | Implementada |
| 5 | Máscara de validez (nube, sombra, agua) desde la capa SCL | Implementada |
| 6 | Serialización de la escena | Implementada |
| 7 | Firma de referencia USGS remuestreada a las bandas de Sentinel-2 | Implementada |
| 8 | Detección por Spectral Angle Mapper (SAM) | Implementada y endurecida |
| 9 | **Validación cuantitativa contra cartografía** | **Pendiente** |
| 10 | Visualización y exportación (GeoTIFF + PNG) | Implementada |

**Qué es SAM (Spectral Angle Mapper).** Trata la firma espectral de cada píxel como un vector de N números (uno por banda) y mide el ángulo entre ese vector y el del mineral de referencia. Ángulo chico significa curvas parecidas. Su virtud es que mide dirección y no magnitud, así que un mismo material más o menos iluminado da casi el mismo ángulo. No necesita datos de entrenamiento.

### 3.2 El hallazgo que cambia la propuesta de valor

Sobre el AOI de 40 × 40 km del distrito Cerro Colorado (Tarapacá), con umbral 0,1 rad:

| Clase de la verdad de terreno | Píxeles del AOI | Detecciones |
|---|---|---|
| Alteración hidrotermal cartografiada | 50.773 (1,27 %) | **0** |
| No candidata | 192.444 (4,81 %) | **0** |
| Sin clasificar | 3.756.783 (93,92 %) | **131** |

**130 de las 131 detecciones caen sobre una sola unidad: "Depósitos antrópicos, botaderos de mina"**, que ocupa el 1,05 % del área. **VERIFICADO** (README, sección Detección).

La lectura honesta: el detector encuentra **roca molida y recién expuesta**, sin la costra ni el barniz del desierto que cubren la superficie natural. En terreno virgen la señal de arcilla queda tapada; en material removido, no.

Esto se puede contar de dos maneras en una postulación, y la elección importa:

- **Camino A (exploración greenfield).** Mantener la propuesta original. Requiere resolver el problema del barniz del desierto y, muy probablemente, migrar a sensores hiperespectrales (PRISMA, EnMAP) que sí resuelven el doblete de absorción Al–OH en 2,16/2,20 µm que Sentinel-2 solo insinúa en su banda B12. Es más ambicioso, más caro y más largo. Encaja con fondos de I+D (Startup Ciencia, Crea y Valida).
- **Camino B (superficies removidas).** Reorientar el caso de uso hacia **botaderos, relaves y pasivos ambientales mineros**: superficies expuestas donde la señal ya demostró funcionar, con clientes que tienen obligación regulatoria de caracterizarlos y monitorearlos. Caracterizar arcillas y sulfatos en un botadero se conecta con drenaje ácido de mina, que es un problema ambiental con presupuesto asignado. Es un camino más corto a la primera venta, y calza con la prioridad 2026 de Corfo en descarbonización y economía circular.

**Recomendación:** postular con el Camino B como caso de uso ancla y el Camino A como visión de escalamiento. Un evaluador premia que el equipo haya dejado que el dato lo corrija; eso es evidencia de método, no de fracaso. **INFERIDO.**

### 3.3 Innovación declarada

Lo que se propone como novedoso no es SAM, que tiene décadas. Es la combinación de: pipeline declarativo y reproducible (todo experimento es un archivo YAML), validación obligatoria contra cartografía oficial del SERNAGEOMIN, y honestidad metodológica en la salida (el producto entrega un mapa de similitud con su incertidumbre declarada, no un "aquí hay mineral"). **DECLARADO** — hay que contrastarlo contra el estado del arte antes de postular, sección 8.

---

## 4. Propuesta de valor y modelo de negocio

### 4.1 Propuesta de valor

> Para equipos de exploración y de gestión ambiental minera que necesitan decidir dónde invertir esfuerzo de terreno, Space Mineral entrega mapas de alteración mineralógica derivados de satélite, reproducibles y validados contra cartografía oficial, que permiten descartar y priorizar zonas antes de comprometer una campaña de terreno.

### 4.2 Segmentos de cliente (hipótesis, todos SUPUESTO hasta entrevistar)

1. **Junior de exploración** — presupuesto ajustado, alta sensibilidad al costo de terreno. 77 proyectos suspendidos en el catastro sugieren un segmento bajo presión de capital.
2. **Áreas de medio ambiente y cierre de faenas de la gran minería** — obligación regulatoria de caracterizar y monitorear depósitos. Menos sensibles al precio, ciclo de venta más largo.
3. **Consultoras geológicas y de ingeniería** — compran capacidad técnica que no quieren desarrollar internamente. Canal indirecto.
4. **SERNAGEOMIN y organismos públicos** — potencial usuario y, sobre todo, potencial validador. Su respaldo vale más como credencial que como venta.

### 4.3 Modelo de ingresos (hipótesis, SUPUESTO)

| Modelo | Descripción | Cuándo aplicarlo |
|---|---|---|
| Estudio por encargo | Un informe por área de interés, precio por km² o por proyecto | Primeras ventas, valida disposición a pagar |
| Suscripción de monitoreo | Reprocesamiento periódico de la misma zona (Sentinel-2 revisita cada ~5 días) | Cuando el caso de uso sea monitoreo de botaderos/relaves |
| Licencia de software | El cliente corre el pipeline en su infraestructura | Etapa tardía, requiere producto empaquetado |

El modelo de suscripción es el que sostiene una valorización, porque la revisita del satélite convierte un estudio puntual en una serie de tiempo. **INFERIDO.**

---

## 5. Objetivos del proyecto a postular

**Objetivo general (SUPUESTO, ajustar al fondo elegido).**
Desarrollar y validar un servicio de caracterización mineralógica de superficies mineras expuestas a partir de imágenes satelitales gratuitas, alcanzando TRL 5 y una primera validación con un cliente real en la macrozona norte.

**Objetivos específicos.**

1. Cerrar la etapa 9: implementar las métricas de validación (matriz de confusión, F1, IoU, ROC/AUC, kappa de Cohen) y reportar el desempeño del detector con su intervalo de confianza.
2. Calibrar el umbral de decisión con un criterio estadístico documentado, reemplazando el valor 0,1 rad fijado por convención.
3. Extender la detección a alunita y hematita (Nivel 2) y comparar SAM contra Random Forest sobre la misma verdad de terreno.
4. Ejecutar una campaña de validación en terreno sobre al menos un botadero, con muestreo y análisis mineralógico independiente.
5. Empaquetar el pipeline en un servicio operable por un tercero, con informe estandarizado de salida.
6. Validar comercialmente la propuesta con al menos 15 entrevistas a clientes potenciales y una carta de intención de compra.

---

## 6. Plan de trabajo e hitos (12 meses, SUPUESTO — ajustar a las bases del fondo)

| Mes | Hito | Entregable verificable |
|---|---|---|
| 1–2 | Métricas de validación implementadas | `evaluate.py` corre y emite reporte con F1, IoU y AUC |
| 2–3 | Umbral calibrado con criterio documentado | Nota técnica con la curva ROC y el criterio de corte |
| 3–5 | Nivel 2: alunita y hematita, SAM vs. Random Forest | Tabla comparativa de desempeño por mineral |
| 4–6 | Descubrimiento de cliente | 15 entrevistas documentadas, perfil de cliente ideal |
| 6–8 | Campaña de terreno sobre botadero | Informe de muestreo y contraste con la predicción |
| 8–10 | Producto empaquetado e informe estandarizado | Un tercero genera un informe sin ayuda del equipo |
| 10–12 | Piloto con cliente | Carta de intención o primer contrato |

---

## 7. Presupuesto referencial (SUPUESTO — reemplazar con cotizaciones reales)

Escenario dimensionado para un subsidio de $15.000.000 con 25 % de aporte propio (formato Semilla Inicia).

| Ítem | Monto | Origen |
|---|---|---|
| Recurso humano (desarrollo, 6 meses parciales) | $6.000.000 | Subsidio |
| Campaña de terreno (traslado, muestreo, análisis de laboratorio) | $3.500.000 | Subsidio |
| Cómputo en la nube y almacenamiento | $1.200.000 | Subsidio |
| Asesoría geológica especializada | $2.500.000 | Subsidio |
| Constitución legal, contabilidad y propiedad intelectual | $800.000 | Subsidio |
| Difusión, participación en ferias del sector | $1.000.000 | Subsidio |
| **Subtotal subsidio** | **$15.000.000** | |
| Horas del equipo valorizadas | $4.000.000 | Aporte propio |
| Equipamiento propio (equipos de cómputo) | $1.000.000 | Aporte propio |
| **Total proyecto** | **$20.000.000** | |

Nota: los fondos suelen exigir que el aporte propio se desglose entre **pecuniario** (plata que se transfiere) y **valorizado** (horas y activos que ya se tienen). Las proporciones permitidas cambian entre bases; hay que leerlas antes de fijar este cuadro.

---

## 8. Estado del arte y competencia — **pendiente, bloquea la postulación**

Ningún fondo aprueba un proyecto sin esta sección resuelta. Falta levantar:

- Servicios comerciales de mapeo mineral por teledetección con operación en Chile, con sus precios de lista.
- Herramientas gratuitas o de bajo costo que resuelvan lo mismo (plugins de QGIS, ENVI, Google Earth Engine con scripts publicados).
- Publicaciones recientes sobre detección de arcillas con Sentinel-2 en el desierto de Atacama, para acreditar que el equipo conoce el límite del sensor y no lo está descubriendo tarde.
- Patentes o software registrado en el dominio.

**Esta es la brecha más grande del documento.** Sin ella, "innovación" queda como afirmación sin respaldo, y ese criterio pesa 40 % en la evaluación de Semilla Inicia (**VERIFICADO**).

---

## 9. Equipo

| Integrante | Rol | Estado |
|---|---|---|
| Camila | Dirección técnica, teledetección y validación | **DECLARADO** |
| Carlos Peña | Desarrollo, arquitectura del pipeline | **DECLARADO** |
| *Vacante* | Perfil geológico o comercial | **Pendiente** |

Dos observaciones que afectan directamente el puntaje:

- Semilla Inicia evalúa **Equipo con 30 % de ponderación**, y postular en solitario topea ese criterio en 3,0 de 5,0. **VERIFICADO**. Postular de a dos ya evita ese techo.
- Startup Ciencia exige **equipo mínimo de tres personas**: director de proyecto, gestor de proyecto y personal científico-técnico. **VERIFICADO**. Si ese es el fondo elegido, hay que sumar a alguien antes del cierre.

Un perfil geológico en el equipo, aunque sea como asesor formalizado, resuelve dos problemas a la vez: sube el puntaje de equipo y da credibilidad técnica ante evaluadores del área.

---

## 10. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| La resolución espectral de Sentinel-2 no basta para identificación mineral definitiva | **Alta — ya observado** | Alto | Reposicionar el producto como priorización y descarte, no identificación; roadmap hacia hiperespectral (PRISMA, EnMAP) |
| El barniz del desierto tapa la señal en superficie natural | **Alta — ya observado** | Alto | Enfocar el caso de uso en superficies removidas (Camino B) |
| No hay disposición a pagar en el segmento junior | Media | Alto | Descubrimiento de cliente antes de construir más producto |
| El equipo no tiene dedicación completa (carga académica) | Alta | Medio | Declararlo en la postulación con un plan de horas realista; los fondos castigan más el incumplimiento que la dedicación parcial declarada |
| Dependencia de datos de terceros (CDSE, USGS, SERNAGEOMIN) | Baja | Medio | Las tres fuentes son públicas y estables; documentar versiones usadas |

---

## 11. Impacto esperado

- **Económico:** reducción del costo de la etapa temprana de exploración y del monitoreo de depósitos mineros. Cuantificar con un cliente piloto. **SUPUESTO.**
- **Ambiental:** caracterización periódica de botaderos y relaves con datos gratuitos, aplicable a seguimiento de drenaje ácido. Este es el ángulo que conecta con las prioridades 2026 de Corfo (descarbonización, economía circular). **VERIFICADO** que esas son prioridades declaradas de las convocatorias 2026.
- **Territorial:** desarrollo de capacidad tecnológica en las regiones mineras del norte, donde se concentra más del 80 % de los prospectos activos. **VERIFICADO.**

---

## 12. Qué falta antes de que este documento sea postulable

1. Cerrar la etapa 9 y tener métricas reportables. *Sin esto, no hay proyecto que defender.*
2. Levantar el estado del arte y la competencia con fuentes (sección 8).
3. Decidir Camino A o Camino B, y escribir la propuesta de valor en función de esa decisión.
4. Reemplazar todo lo marcado SUPUESTO por cifras cotizadas o entrevistas reales.
5. Definir la figura legal y la región de ejecución, que dependen del fondo elegido.
6. Sumar al menos un integrante o asesor formalizado.

---

## Fuentes

- [Exploración minera en Chile marca su mayor nivel desde 2013 tras nuevo catastro de Cochilco — Reporte Minero](https://www.reporteminero.cl/noticia/exploraciones/2026/02/exploracion-minera-chile-2025-cochilco-catastro-presupuesto-cobre)
- [Semilla Inicia — CORFO](https://www.corfo.gob.cl/sites/cpp/programa/semilla-inicia/)
- [Startup Ciencia 2026 — ANID](https://anid.cl/concursos/startup-ciencia-2026/)
- Repositorio del proyecto: `README.md`, `docs/recorrido/12_estado_y_pendientes.md`, `configs/cerro_colorado_kaolinite.yaml`
