# Cartografia geologica del AOI de Tamarugal

Poligonos litologicos que cubren el AOI del proyecto (tile T19KDT, EPSG:32719,
E 419.960-459.960 / N 7.740.040-7.780.040), usados para construir la capa de
verdad de terreno de la Semana 4.

- `pozo_almonte.geojson` --- hoja Pozo Almonte, mitad **oeste** del AOI.
- `mamina.geojson` --- hoja Mamina, mitad **este** del AOI.

Descargados el 2026-08-18 con `scripts/descargar_geologia.py`.

## Por que dos hojas

El AOI va de lon -69,7673 a -69,383 y **cruza el limite** entre ambas cartas
(Pozo Almonte cubre 70,00-69,50 W; Mamina cubre 69,50-69,00 W). Ninguna de las
dos alcanza sola; su union si. La "Carta Calama" del plan original **no
aplica**: Calama esta en la Region de Antofagasta, a unos 250 km al sur. La
zona de estudio cambio a Pampa del Tamarugal en la Semana 2 y el plan escrito
nunca se actualizo.

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
declarada a mano en `configs/verdad_terreno_tamarugal.yaml`, y ese archivo es
donde hay que discutir el criterio.
