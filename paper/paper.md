---
title: 'LANOT_ceniza: Low-latency operational detection of volcanic ash from GOES-R ABI Level 2 products'
tags:
  - Python
  - remote sensing
  - volcanic ash
  - GOES-R
  - ABI
  - Popocatépetl
authors:
  - name: Alejandro Aguilar Sierra
    orcid: 0000-0003-1018-8521
    affiliation: 1
  - name: Víctor Manuel Jiménez Escudero
    orcid: 0009-0004-7521-7551
    affiliation: 1
affiliations:
  - name: Laboratorio Nacional de Observación de la Tierra (LANOT), Universidad Nacional Autónoma de México (UNAM), Mexico
    index: 1
date: 21 October 2026
bibliography: paper.bib
---

<!--
Esqueleto (2026-10-21). Las notas en español dicen qué debe ir en cada sección;
se reemplazan por el texto en inglés. Formato de JOSS como en
~/lanot/hpsatviews/paper/paper.md. Pendientes en doc/2026-10-21_publicacion_joss.md.
-->

# Summary

- Qué es: un paquete de Python (`lanot-detect-ash`) que clasifica cada píxel de una
  escena GOES-R ABI en ceniza confirmada (CA), probabilidad alta (HAP), probabilidad
  baja (LAP), sin ceniza, nube (ceniza no detectable) y sin datos.
- Entradas: L2 CMIP de las bandas C04, C07, C11, C13 y C15, y la fase de nube (ACTP)
  de CSPP Geo AIT [@CSPPGeo]. Salida: GeoTIFF de una banda con tabla de colores y un
  estilo `.qml` para QGIS.
- Implementa el algoritmo de @JimenezEscudero_articulo, que viene de la versión previa
  en TeraScan.
- Corre en operación en LANOT cada 5 minutos para el Popocatépetl.

# Statement of need

- Problema: el Popocatépetl, a unos 70 km de la Ciudad de México, emite ceniza con
  frecuencia; la aviación y protección civil necesitan saber dónde está la ceniza en
  minutos, no en horas.
- Para quién: grupos de monitoreo operativo (LANOT, y quien reciba los productos:
  ¿CENAPRED, SMN, SENEAM?, confirmar) y para investigadores que quieran reproducir o
  extender el algoritmo del artículo.
- Por qué otra herramienta: la versión anterior dependía de TeraScan (comercial,
  cerrada). Esta es abierta, reproducible y se instala con `pip`.
- Latencia: de unos 9 min hasta tener la fase de nube en la cadena general a unos
  4.3 min de extremo a extremo con la cadena de baja latencia (ver
  `doc/2026-10-18_operacion_tahan.md`).

# State of the field

- Productos operativos de ceniza de NOAA: el producto L2 de ceniza de GOES-R y VOLCAT
  [@Pavolonis_TODO]. Diferencias: disponibilidad, licencia, adaptación regional.
- Herramientas generales: `satpy`/Pytroll [@Raspaud2018] y Geo2Grid hacen el RGB de
  ceniza para interpretación visual, pero no clasifican píxeles.
- TeraScan: la implementación previa del algoritmo; comercial.
- Lugar de LANOT_ceniza: implementación abierta y específica de un algoritmo publicado,
  pensada para operación de baja latencia, no una biblioteca general.

# Software design

- Un solo paso por escena: lectura de L2 → ángulo cenital solar → `classify_ash`
  → GeoTIFF. La clasificación es una función pura sobre arreglos, probada regla por
  regla.
- Ángulo cenital solar: posición del Sol una vez por escena con Skyfield
  [@Rhodes2019] y las efemérides DE421 [@Folkner2009], y trigonometría esférica
  vectorizada para todos los píxeles. Error ~0.003°.
- Kernel estadístico (media y desviación locales) con filtros uniformes sobre x y x²:
  de 7.3 s con 16 procesos a 0.17 s con 1 proceso, mismo resultado.
- Bloques de iluminación día / crepúsculo / noche según el ángulo cenital solar
  (70° y 85°).
- Formato de salida: valores enteros con significado fijo (0, 1–3, 6, 255) y NoData
  explícito; el `.qml` resuelve la transparencia y la leyenda en QGIS (la paleta de un
  TIFF no guarda alfa).
- Operación: búsqueda estricta de archivos, códigos de salida, CSV de latencia con
  estado y un vigilante que escribe `estado.json`.
- Pruebas: `pytest` con recortes de tres escenas reales (noche, crepúsculo, día) y
  pruebas unitarias por regla; herramientas para comparar dos versiones en escenas
  completas.
- Figura propuesta: diagrama del flujo, o un panel con la escena y la clasificación.

# Research impact statement

- El artículo científico [@JimenezEscudero_articulo] usó este software para todos sus
  resultados.
- En operación en LANOT desde el 2026-10-18: cada escaneo CONUS de GOES-19, con
  ~4.3 min de latencia.
- Reproducibilidad: la versión del artículo está identificada (`90ad79f`) y las
  diferencias con la versión actual están medidas en 63 escenas
  (`doc/2026-10-19_plan_mejoras_operacion.md`).
- ¿Usuarios externos de los productos? Confirmar.

# AI usage disclosure

- Seguir el modelo de hpsatviews: el algoritmo y el diseño son humanos.
- Declarar: Claude (Anthropic) en la refactorización de mayo de 2026, en la cadena de
  operación y en el plan de mejoras de octubre de 2026 (pruebas, kernel vectorizado,
  corrección del ángulo cenital solar, reporte de fallas), y en la redacción de este
  artículo. ¿Otras herramientas antes de mayo? Confirmar.
- Toda salida asistida se revisó y validó, con comparaciones píxel por píxel.

# Acknowledgements

- LANOT, UNAM. ¿Mismo apoyo que hpsatviews (Laboratorio Nacional SECIHTI 2025-2027,
  LN-2025-C-102)? Confirmar.
- SSEC/CIMSS por CSPP Geo y por los datos auxiliares de 2019.

# References
