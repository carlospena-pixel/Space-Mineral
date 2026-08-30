# Space Mineral — Descripción general del proyecto e insumos para la estrategia de comercialización

**Versión:** borrador 1.0 · 30 de agosto de 2026
**Uso previsto:** documento base para que un equipo comercial (o tú misma, o un asesor externo) formule la estrategia de comercialización sin necesidad de leer el repositorio técnico.

> Etiquetas: **VERIFICADO** (contrastado con repositorio o fuente pública) · **DECLARADO** (lo afirma el equipo) · **INFERIDO** (deducción) · **SUPUESTO** (relleno, reemplazar).

---

## 1. El proyecto en tres párrafos

**Qué es.** Space Mineral es un software que analiza imágenes de satélite y produce mapas de dónde es probable encontrar ciertos minerales en la superficie del terreno. Usa imágenes públicas y gratuitas del programa Copernicus de la Agencia Espacial Europea (satélites Sentinel-2), las compara contra una biblioteca de referencia del Servicio Geológico de Estados Unidos, y contrasta el resultado contra la cartografía geológica oficial chilena del SERNAGEOMIN.

**Cómo funciona.** Cada material de la superficie refleja la luz de manera distinta en distintas longitudes de onda, incluidas varias que el ojo humano no ve. Esa curva de reflexión es su **firma espectral**, algo así como una huella digital. El satélite mide esa curva en 13 bandas para cada cuadrado de 20 × 20 metros del terreno. El software compara la curva medida contra la curva de laboratorio del mineral buscado y calcula qué tan parecidas son. El resultado es un mapa de calor georreferenciado: se abre en cualquier software de mapas y se superpone sobre la geología conocida.

**Para qué sirve.** Para decidir dónde vale la pena ir a mirar en terreno, antes de gastar en una campaña. La minería del norte de Chile gasta cientos de millones de dólares al año explorando, y la mayor parte de ese gasto se toma sobre información escasa y cara de obtener. Un mapa satelital no reemplaza al geólogo ni al sondaje; ordena la fila de dónde partir.

---

## 2. Estado real del desarrollo

| Dimensión | Estado | Certeza |
|---|---|---|
| Pipeline de procesamiento de imagen a mapa | Funciona de extremo a extremo, es reproducible desde un archivo de configuración | VERIFICADO |
| Algoritmo de detección (SAM) | Implementado, con sus entradas validadas y su fórmula contrastada | VERIFICADO |
| Capa de verdad de terreno (cartografía SERNAGEOMIN rasterizada) | Construida | VERIFICADO |
| Métricas cuantitativas de desempeño (F1, IoU, ROC/AUC) | **No implementadas todavía** | VERIFICADO |
| Zona de prueba | Distrito Cerro Colorado, Precordillera de Tarapacá, ventana de 40 × 40 km | VERIFICADO |
| Madurez tecnológica | TRL 3, transitando a TRL 4 | INFERIDO |
| Validación comercial | Ninguna. Cero entrevistas de cliente documentadas, cero ventas | DECLARADO |

**La brecha que importa para comercializar:** el proyecto tiene validación técnica en curso y validación comercial en cero. Un fondo de escalamiento pide lo segundo; un fondo semilla pide lo primero. Eso determina a qué se puede postular hoy.

---

## 3. El hallazgo que debe orientar la estrategia comercial

Al contrastar las detecciones contra la geología cartografiada del área, el resultado fue nítido y contraintuitivo:

- **Cero** detecciones sobre las zonas de alteración hidrotermal documentadas.
- **130 de 131** detecciones sobre una sola unidad: los **botaderos de la mina Cerro Colorado**, que ocupan apenas el 1 % del área analizada.

**VERIFICADO** (README del repositorio).

**Qué significa.** En el desierto, la superficie natural está cubierta por costra y barniz —una pátina de óxidos que se forma con el tiempo— que tapa la señal espectral de la roca que hay debajo. En material removido y recién expuesto, como un botadero minero, la roca está desnuda y la señal aparece.

**Qué implica comercialmente.** El caso de uso donde la tecnología *ya funciona demostrablemente* es la caracterización de superficies mineras removidas: botaderos, relaves, pilas de lixiviación, caminos de faena, cortas abiertas. El caso de uso original —exploración en terreno virgen— es más ambicioso, tiene mercado más grande, y hoy no tiene evidencia a favor.

Esto abre dos rutas comerciales que conviene tener separadas en la cabeza:

### Ruta 1 — Monitoreo de superficies mineras expuestas (corto plazo)

- **Cliente:** áreas de medio ambiente, cierre de faenas y geometalurgia de la mediana y gran minería.
- **Dolor:** obligación regulatoria de caracterizar y monitorear depósitos de estériles y relaves; el muestreo físico es puntual, caro y no cubre la superficie completa.
- **Ventaja del satélite:** cobertura total del depósito, revisita cada ~5 días, costo marginal cercano a cero por repetición.
- **Gancho ambiental:** la presencia de arcillas y sulfatos se relaciona con el drenaje ácido de mina, que es un pasivo ambiental con presupuesto asignado y presión regulatoria.
- **Ciclo de venta:** largo (la gran minería compra lento), pero con presupuesto real y recurrente.

### Ruta 2 — Priorización de exploración (largo plazo)

- **Cliente:** empresas junior de exploración y consultoras geológicas.
- **Dolor:** decidir dónde perforar con presupuesto limitado.
- **Barrera técnica:** requiere resolver el problema del barniz del desierto y, probablemente, migrar a sensores hiperespectrales (PRISMA, EnMAP), que tienen cientos de bandas en lugar de trece.
- **Contexto de mercado adverso hoy:** el gasto de las junior cayó 13,4 % en 2025 mientras las grandes subieron a 53,4 % del presupuesto total. El segmento con el dolor más agudo es también el que tiene menos plata. **VERIFICADO** (Cochilco 2025).

**Recomendación:** construir el negocio sobre la Ruta 1 y usar la Ruta 2 como visión de escalamiento en el discurso de postulación e inversión. Vender lo que funciona, financiar lo que falta.

---

## 4. Tamaño y estructura del mercado (datos verificados)

| Dato | Cifra | Fuente |
|---|---|---|
| Presupuesto de exploración minera en Chile, 2025 | **US$ 874,7 millones** (máximo desde 2013) | Catastro Cochilco 2025 |
| Participación del cobre | 76 % (US$ 669,6 millones) | Cochilco 2025 |
| Oro / litio | US$ 135,9 M / US$ 49,0 M | Cochilco 2025 |
| Prospectos y proyectos catastrados | 235 (158 activos, 77 suspendidos) | Cochilco 2025 |
| Concentración territorial | Atacama, Antofagasta y Coquimbo suman más del 80 % de prospectos activos | Cochilco 2025 |
| Presupuesto mundial de exploración 2025 | US$ 12.401 millones (−0,6 %) | S&P Global vía Cochilco |
| Participación de América Latina | 26,5 % del gasto mundial | Cochilco 2025 |

Lo que **falta** para dimensionar el mercado alcanzable:

- Número de faenas mineras con obligación de monitoreo de depósitos en Chile (dato público, SERNAGEOMIN).
- Gasto anual promedio de una faena en caracterización y monitoreo de sus botaderos y relaves. **Requiere entrevistas.**
- Precio de lista de los servicios de teledetección comercial que compiten. **Requiere levantamiento.**

Sin esos tres datos, cualquier cifra de mercado alcanzable que se escriba es un número inventado, y los evaluadores de fondos lo detectan.

---

## 5. Insumos para la estrategia comercial

### 5.1 Propuesta de valor en una frase

> Mapas de caracterización mineralógica de superficies mineras, generados desde satélite, reproducibles y contrastados contra cartografía oficial: cobertura total del área, actualización cada pocos días y sin poner un pie en terreno.

### 5.2 Diferenciadores defendibles

1. **Reproducibilidad como característica de producto.** Cada análisis se define en un archivo de configuración; cualquier tercero puede regenerar el mismo resultado. En un rubro donde los informes de consultoría son cajas negras, poder reproducir un resultado es un argumento de venta ante un cliente técnico. **VERIFICADO** que el pipeline es declarativo.
2. **Validación contra cartografía oficial chilena.** No es un modelo entrenado en otro país y aplicado acá. **VERIFICADO.**
3. **Honestidad del entregable.** El producto entrega similitud espectral con su incertidumbre declarada, no un veredicto. Frente a un geólogo, esto genera confianza en vez de resistencia. **DECLARADO.**
4. **Costo del dato de entrada igual a cero.** Sentinel-2 es gratuito y con revisita de ~5 días. **VERIFICADO.**

### 5.3 Lo que no se debe prometer

- Identificación mineral definitiva. La resolución espectral de Sentinel-2 es ancha para eso, y el propio proyecto lo documenta. **VERIFICADO.**
- Cuantificación de abundancia ("hay 20 % de caolinita"). Está fuera de alcance del nivel actual. **VERIFICADO.**
- Estimación de reservas o de valor económico del yacimiento. **VERIFICADO** que está explícitamente fuera de alcance en el plan maestro.

Prometer cualquiera de las tres cosas destruye credibilidad ante el primer cliente técnico que lo pruebe.

### 5.4 Hipótesis de precio (todas SUPUESTO)

| Formato | Rango a testear | Qué valida |
|---|---|---|
| Informe único sobre un área definida | $800.000 – $2.500.000 CLP | Disposición a pagar por el entregable |
| Suscripción de monitoreo trimestral de un depósito | $300.000 – $900.000 CLP / trimestre | Valor de la serie de tiempo |
| Piloto pagado a precio reducido | $0 – $500.000 | Acceso al cliente para aprender |

El objetivo del primer año no es maximizar ingreso, es conseguir un cliente que pague algo y deje contar su nombre. Ese logo vale más que la plata en la siguiente postulación.

### 5.5 Camino a la primera venta (12 meses, propuesto)

1. **Meses 1–2 — Descubrimiento.** 15 entrevistas con áreas de medio ambiente y geología de faenas del norte. No vender: preguntar cómo caracterizan hoy sus botaderos, cuánto gastan y qué les falta.
2. **Meses 2–4 — Caso demostrativo.** Producir un informe completo sobre un botadero real usando datos públicos, sin pedirle nada al cliente. Es material de venta y evidencia técnica al mismo tiempo.
3. **Meses 4–6 — Validación de terreno.** Una campaña de muestreo sobre ese botadero, contrastando la predicción contra análisis mineralógico. Esto convierte el caso demostrativo en evidencia.
4. **Meses 6–9 — Piloto.** Un cliente, un depósito, precio simbólico, alcance acotado, carta de intención firmada.
5. **Meses 9–12 — Estandarización.** Que el informe salga igual sin importar quién lo genere.

### 5.6 Canales

- **Directo:** contacto con áreas técnicas de faenas. Lento pero es donde está la decisión.
- **Ferias y encuentros sectoriales:** Exponor (Antofagasta), Expomin (Santiago). Sirven más para conocer el vocabulario del cliente que para vender.
- **Programas de proveedores de la gran minería:** varias mineras tienen programas de innovación abierta con desafíos publicados. Es la vía más rápida a un piloto pagado. **Vale la pena revisarlos antes de diseñar el go-to-market.**
- **Universidad:** el respaldo académico y una posible incubadora abren puertas que una empresa sin historial no abre sola.

---

## 6. Riesgos comerciales

| Riesgo | Mitigación |
|---|---|
| El cliente considera que el dato satelital gratuito lo puede procesar internamente | Vender el método validado y el informe defendible, no el acceso al dato |
| Ciclo de venta de la gran minería más largo que el financiamiento disponible | Combinar un cliente ancla lento con estudios puntuales que generen caja |
| El equipo es estudiantil y sin trayectoria en el rubro | Sumar un asesor geológico con nombre reconocible; el respaldo transfiere credibilidad |
| Aparece un competidor con sensor hiperespectral | Competir en costo, frecuencia y reproducibilidad, no en resolución espectral |

---

## 7. Lo que hay que resolver antes de escribir la estrategia definitiva

1. **Decidir la ruta comercial ancla** (monitoreo de superficies expuestas vs. exploración). Todo lo demás depende de esa decisión.
2. **Hacer las 15 entrevistas.** Sin ellas, los segmentos y los precios de este documento siguen siendo hipótesis.
3. **Levantar la competencia con precios reales.**
4. **Cerrar la validación técnica.** Difícil vender un mapa cuyo desempeño todavía no se puede expresar en un número.

---

## Fuentes

- [Exploración minera en Chile marca su mayor nivel desde 2013 tras nuevo catastro de Cochilco — Reporte Minero](https://www.reporteminero.cl/noticia/exploraciones/2026/02/exploracion-minera-chile-2025-cochilco-catastro-presupuesto-cobre)
- [Presupuesto de exploración en Chile sobrepasa los US$874 millones en 2025 — Minería Chilena](https://www.mch.cl/presupuesto-de-exploracion-en-chile-sobrepasa-los-us874-millones-en-2025/)
- Repositorio del proyecto: `README.md`, `docs/recorrido/12_estado_y_pendientes.md`
