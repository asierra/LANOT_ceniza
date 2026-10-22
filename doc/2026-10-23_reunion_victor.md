# Reunión con Víctor: algoritmo, artículo y software

- **Fecha:** 2026-10-23, en lanot7
- **Preparado por:** Alejandro Aguilar Sierra
- **Detalle:** `doc/2026-10-19_plan_mejoras_operacion.md` (fase 3), `doc/2026-10-21_publicacion_joss.md` y `doc/2026-10-21_perfiles_umbrales.md`

## Resumen

1. **Para decidir:** tres reglas del código actual (fase de nube, ΔT3 sobre la ceniza confirmada, nube superenfriada).
2. **Artículo científico** (Journal of Applied Volcanology): en seis puntos el texto no coincide con el código con el que se calcularon los resultados. Hay que decidir si se corrigen en esta revisión.
3. **Software:** las mejoras de octubre no van en el artículo; van en un artículo de software nuevo (SoftwareX o JOSS), que se envía cuando se publique el científico.
4. **Perfiles de umbrales por volcán**, para el proyecto de Chile y otros.

Muestra usada en todos los conteos, salvo que se diga otra cosa: 63 escenas CONUS de GOES-16 (2024-02-27 cada hora y cada 5 min de 03:00 a 04:56 UTC, con ceniza de noche; 2019-03-01 de 11:02 a 15:02 UTC cada 15 min). "Región del artículo" = recorte `ashpaper` (102.4–96.3° O, 17.5–22.5° N).

---

## 1. Decisiones sobre el algoritmo (código actual)

### 1.1 Regla de fase de nube (P10)

| caso | código | texto del artículo | píxeles en la región del artículo (63 escenas) |
|---|---|---|---|
| HAP sobre nube superenfriada | sigue HAP | pasa a sin ceniza | 1 |
| HAP sobre nube de fase mixta | sigue HAP | pasa a sin ceniza | 6 |
| HAP con fase desconocida | sigue HAP | no dice | 0 |
| LAP sobre agua líquida | pasa a sin ceniza | no dice | 2 |
| LAP con fase desconocida | pasa a sin ceniza | no dice | 0 |

Para comparar: 836 píxeles de HAP en total. **La diferencia es de menos del 1 %.** Cualquiera de las dos reglas es defendible; la pregunta es cuál es la buena físicamente.

### 1.2 Filtro de ΔT3 sobre la ceniza confirmada (P11)

El código borra la ceniza confirmada **por el kernel** cuando ΔT3 ≤ 0. La confirmada por umbrales no se ve afectada, porque ya exige ΔT3 > 2. La versión revisada del artículo dice "the Confirmed Ash (CA) category remained unchanged"; **el manuscrito de abril decía lo contrario** ("pixels classified as CA or HAP were removed if … ΔT3 less than 0"), igual que el código.

- En la región del artículo el filtro borra **857 píxeles de CA**; quedan 3 100. Sin el filtro, la CA crecería 28 %.
- Esos 857 píxeles no parecen ceniza:
  - todos son de noche;
  - ninguno está a menos de 50 km del volcán, y solo 28 tocan la pluma;
  - 637 están sobre cielo despejado, con ΔT3 entre −2.6 y 0 K, lo típico de superficies frías de noche.
- **Propuesta:** conservar el filtro y regresar el texto a lo que decía en abril.
- **Pregunta:** ¿por qué cambió esa frase en la revisión? ¿La pidió un revisor?

### 1.3 Nube superenfriada en la clase "nube" (solo operación)

La operación tiene una clase nueva, **6 = nube: no se puede saber si hay ceniza** (fase mixta o hielo). No va en el artículo. Falta decidir si la fase superenfriada también cuenta: en la región, 2 894 píxeles pasarían de "sin ceniza" a "nube" (la clase 6 crecería 7 %). No cambia ninguna clase de ceniza.

---

## 2. Posibles ajustes al artículo científico

**Criterio:** el artículo se envió hace un año y describe el algoritmo con el que se calcularon los resultados. No se le agrega nada de las mejoras de octubre. Solo se corrige donde el texto no coincide con ese algoritmo.

### 2.1 Diferencias entre el texto y el código

Versiones: **diciembre de 2025** (`90ad79f`, la que se usó para los resultados) y **mayo de 2026** (`9dd4752`, "igualar terascan").

| regla | texto | diciembre | mayo |
|---|---|---|---|
| CA de día | exige R1.37 > 0.002 | no lo exige | lo exige |
| HAP con ΔT2 < −1.5 | pasa a sin ceniza | sigue HAP (LAP sobre agua) | pasa a sin ceniza |
| regla de fase (1.1) | hielo, mixta y superenfriada → sin ceniza | ver 1.1 | igual que diciembre |
| ΔT3 sobre la CA (1.2) | la CA no cambia | la CA por kernel se borra | igual que diciembre |
| límites del crepúsculo | 70° < SZA < 85° | 70° ≤ SZA ≤ 85° | 70° < SZA < 85° |
| precisión del SZA (sec. 2.4) | "sub-arcsecond accuracy" | error de 0.2° a 0.35° | igual que diciembre |

- Las dos primeras reglas **ya estaban en el texto** desde la metodología de noviembre de 2025 y el manuscrito de abril. El cambio de mayo ajustó el código al texto, así que esas reglas se quedan en el artículo.
- Lo que hay que confirmar es si **los números del artículo se recalcularon después del 4 de mayo**. Las estadísticas de `fase2` son del 22 al 29 de abril. Si no se recalcularon, se hicieron sin esas dos reglas (ver 2.2).
- El SZA: el error de diciembre (0.2° a 0.35°) no afecta los resultados de forma apreciable, pero "sub-arcsecond" es falso. Basta con quitar la frase; no hace falta mencionar la corrección.
- El crepúsculo: 0 píxeles de diferencia; es solo de redacción.

### 2.2 Cuánto cambian los resultados con las reglas de mayo

> **Pendiente:** corrida en tahan de diciembre contra mayo, recortadas a la región del artículo, en 26 días completos de los eventos del artículo (2019-03-28, 06-14 y 06-17; 13 días de 2023; 10 de 2024): unos 7 200 escaneos. Se llena al terminar.

No se pueden repetir los 7 casos de validación con VIIRS (Tabla 4): sus L2 no están en tahan ni en cirrus. Habría que regenerarlas desde las L1b.

En CONUS completo (63 escenas), de diciembre a hoy: la CA casi no cambia (3 de 31 737 píxeles), el HAP baja 41 % y el LAP 89 %, casi todo por la regla de ΔT2 < −1.5.

---

## 3. Mejoras del software (octubre de 2026)

No cambian el algoritmo del artículo, salvo donde se indica. Van en el artículo de software (sección 4).

### 3.1 Operación en tahan

- Cadena propia de baja latencia desde el 2026-10-18. CSPP Geo AIT 2.3.1 genera solo lo que usa el algoritmo (CMI, máscara de nubes y fase), en 4 segmentos.
- **Latencia total, del inicio del escaneo al GeoTIFF: ~4.3 min** (antes, ~8.6 min solo para tener la fase de nube). Responde al punto 14 del revisor.
- Cada falla se registra, con su causa, en el CSV de latencia. Un vigilante revisa cada 15 min que la cadena no se haya detenido y escribe `estado.json`.

### 3.2 Correcciones y mejoras del programa

| mejora | qué cambia en la clasificación (63 escenas, CONUS) |
|---|---|
| Kernel estadístico vectorizado: de 7.3 s con 16 procesos a 0.17 s con 1 | nada (0 píxeles) |
| Ángulo cenital solar: error de 0.2°–0.35° a ~0.003° (se mezclaba el marco J2000 con el tiempo sidéreo de la fecha) | 291 píxeles en 13 escenas de amanecer o atardecer |
| Crepúsculo 70° ≤ SZA ≤ 85°: los valores exactos 70 y 85 se quedaban sin bloque desde mayo | nada |
| Búsqueda estricta de archivos: la de mayo podía tomar el archivo de vientos (DMWC) como banda C07 | nada en la muestra |
| C14 deja de leerse: no se usa en la clasificación | nada |
| 0 = sin ceniza y 255 = sin datos (desde mayo eran el mismo valor), con estilo de QGIS (`.qml`) junto a cada GeoTIFF | ninguna clase de ceniza |
| Clase 6 = nube, ceniza no detectable (fase mixta o hielo) | ninguna clase de ceniza |
| 85 pruebas automáticas, con recortes de tres escenas reales (noche, crepúsculo y día) y una prueba por regla | — |
| Herramientas para correr cualquier versión y comparar salidas píxel por píxel | — |

**Ejemplo en QGIS:** `~/Dropbox/cca/lanot/ceniza/fase2/ejemplo_qgis/ejemplo_ceniza.qgz` (2024-02-27 a las 20:31 y a las 04:06 UTC, con mapa base y el volcán). Al abrir el GeoTIFF, QGIS carga el `.qml` solo: el 0 queda transparente y la leyenda muestra las 5 clases con nombre.

### 3.3 ¿Fue buena idea usar Skyfield para el ángulo cenital solar?

Sí. El código original de los estudiantes (`fase1/Codigo Completo.py`, con pvlib) calculaba **un solo ángulo para toda la imagen, en el subpunto del satélite** (0° N y 75.2° O, a unos 2 600 km del volcán). Toda la escena quedaba en el mismo bloque de día, crepúsculo o noche, y ese bloque correspondía a otro lugar. El diseño de 2025 calcula la posición del Sol una vez por imagen (Skyfield, efemérides JPL DE421) y el ángulo **por píxel** con trigonometría vectorizada. Eso es lo que permite los bloques por píxel que describe el artículo, en segundos. pvlib calcula punto por punto y sería lento con millones de píxeles. El único error fue de uso (marco J2000 con tiempo sidéreo de la fecha) y ya está corregido. Una fórmula analítica (NOAA, ~0.01°) bastaría para umbrales de 70° y 85°, pero no vale la pena cambiar.

Valores del GeoTIFF: 0 sin ceniza, 1 CA, 2 HAP, 3 LAP, 6 nube, 255 sin datos. El 4 y el 5 quedan reservados (eran "cloud" y "noise" en TeraScan).

---

## 4. Artículo de software (SoftwareX o JOSS)

- **Por qué ahora:** JOSS pide que el software se haya usado en investigación publicada. Con este artículo se cumple (hpsatviews no pudo publicarse por falta de eso).
- **Cuándo:** después de que se publique el artículo científico, al que cita.
- **Autores:** Alejandro Aguilar Sierra (implementación) y Víctor Manuel Jiménez Escudero (algoritmo, artículo y versión en TeraScan). Los demás coautores del artículo, en agradecimientos. **¿De acuerdo?**
- **Contenido:** qué hace el software, para qué sirve en operación (latencia de ~4.3 min contra ~30 min del VAAC de Washington), cómo está hecho, y qué cambió desde la versión del artículo y cuánto (sección 3).
- **Licencia:** GPL-3.0-or-later, la que ya tiene el repositorio y la misma de hpsatviews. `CITATION.cff` dice MIT por error. **¿De acuerdo?**
- **Revista:** SoftwareX si pesa más; JOSS como alternativa. El borrador está en formato JOSS (`paper/paper.md`) y sirve de base para cualquiera de las dos.

---

## 5. Perfiles de umbrales por volcán

Los umbrales están calibrados para el Popocatépetl. El artículo dice que para otro volcán hay que recalibrarlos y ajustar los límites del SZA a la latitud. Hoy eso exige editar el código.

**Propuesta:**
- Un archivo de perfil por volcán (`perfiles/popocatepetl.toml`, `perfiles/<volcán>.toml`) con todos los umbrales:
  - ΔT1, ΔT2 y ΔT3, R1.37 y BT13;
  - los filtros de ΔT2 y ΔT3;
  - el kernel (tamaño y umbral);
  - los límites del SZA;
  - **la regla de fase como tabla**;
  - la región y el dominio (CONUS o disco completo).
- Sin indicar perfil se usa el del Popocatépetl: la operación no cambia, y las pruebas lo comprueban.
- Cada GeoTIFF registra con qué perfil se hizo.
- La estructura del algoritmo (tres bloques, kernel, orden de los filtros) se queda en el código.

Primer uso: el proyecto de Chile (repositorio aparte). Para Chile probablemente haga falta el disco completo, cada 10 min.

**Preguntas para Víctor:**
- ¿Qué umbrales cree que cambiarían de un volcán a otro?
- ¿Hay algo del algoritmo que no sea un número y que también dependa del volcán?
