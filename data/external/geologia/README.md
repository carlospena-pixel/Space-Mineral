# Cartografia geologica del AOI del distrito Cerro Colorado

Poligonos litologicos que cubren el AOI del proyecto (tile T19KDT, EPSG:32719,
E 453.960-493.960 / N 7.747.040-7.787.040), usados para construir la capa de
verdad de terreno.

- `mamina.geojson` --- hoja Mamina. Con el AOI actual cubre el AOI **entero**.
- `pozo_almonte.geojson` --- hoja Pozo Almonte. Queda al oeste del AOI actual
  y hoy no aporta ningun poligono, pero se conserva: cubria el AOI anterior y
  la ventana ya se movio dos veces.

Descargados el 2026-08-18 con `scripts/descargar_geologia.py`.

## Por que dos hojas

El AOI **anterior** (lon -69,7673 a -69,383) cruzaba el limite entre ambas
cartas (Pozo Almonte cubre 70,00-69,50 W; Mamina cubre 69,50-69,00 W) y
necesitaba las dos. El AOI **actual** (lon -69,4412 a -69,0577) cae entero
dentro de Mamina. Se conservan las dos capas de todas formas: el codigo las
une sin costo y la ventana ya cambio dos veces.

La "Carta Calama" del plan original **no aplica**: Calama esta en la Region de
Antofagasta, a unos 250 km al sur. La zona de estudio cambio a Pampa del
Tamarugal en la Semana 2 y al distrito Cerro Colorado en la Semana 5.

## Fuente tecnica de los vectores

FeatureServer `Chile_Geology` de ArcGIS Online, una **digitalizacion de
terceros** (publicada por Stanford) de las cartas de SERNAGEOMIN:

- Base: <https://services.arcgis.com/7CRlmWNEbeCqEJ6a/arcgis/rest/services/Chile_Geology/FeatureServer>
- Layer 439 = `Chile-geo-pozoalmonte`
- Layer 437 = `Chile-geo-Mamina`

**Este servicio no declara licencia.** Se usa como insumo tecnico y no
sustituye a la fuente cartografica: la cita que corresponde es siempre la carta
original de SERNAGEOMIN, no el servicio. Si el trabajo se publica, hay que
resolver la procedencia de estos vectores antes.

## Cartas originales que hay que citar

- **Pozo Almonte (M204)** --- Vasquez, P. y Sepulveda, F.A. (2013). *Carta Pozo
  Almonte, Region de Tarapaca*. Servicio Nacional de Geologia y Mineria, Carta
  Geologica de Chile, Serie Geologia Basica 162-163 (junto con la Carta
  Iquique), escala 1:100.000.
- **Mamina (M303)** --- Tomlinson, A.J., Blanco, N. y Ladino, M. (2015). *Carta
  Mamina, Region de Tarapaca*. Servicio Nacional de Geologia y Mineria, Carta
  Geologica de Chile, Serie Geologia Basica 174, escala 1:100.000.

## Lo que estos datos NO son

SERNAGEOMIN publica un unico tema cartografico ("Geologia Basica") y **no**
publica poligonos de alteracion hidrotermal para el norte de Chile (verificado:
no hay WFS ni un servicio de alteracion en su organizacion ArcGIS). Estas
capas traen **litologia**, no alteracion. Por eso la verdad de terreno del
proyecto no se obtiene filtrando una columna: es una **seleccion de unidades**
declarada a mano en `configs/verdad_terreno_cerro_colorado.yaml`, y ese archivo
es
donde hay que discutir el criterio.
