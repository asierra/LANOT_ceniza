---
title: 'LANOT_ceniza: a low-latency operational implementation of the ABI-Popocatépetl volcanic ash detection algorithm'
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
  - name: Laboratorio Nacional de Observación de la Tierra (LANOT), Instituto de Geografía, Universidad Nacional Autónoma de México (UNAM), Mexico
    index: 1
date: 21 October 2026
bibliography: paper.bib
---

<!--
Esqueleto (2026-10-21). Las notas en español dicen qué debe ir en cada sección;
se reemplazan por el texto en inglés. Formato de JOSS como en
~/lanot/hpsatviews/paper/paper.md. Pendientes en doc/2026-10-21_publicacion_joss.md.
Fuente del artículo: ~/Dropbox/cca/lanot/ceniza/fase2/Jimenez et al Ash detection REV.docx
-->

# Summary

- Qué es: un paquete de Python (`lanot-detect-ash`) que implementa el algoritmo
  ABI-Popocatépetl [@JimenezEscudero_articulo] y clasifica cada píxel de una escena
  GOES-R ABI en ceniza confirmada (CA), probabilidad alta (HAP), probabilidad baja
  (LAP), sin ceniza, nube (ceniza no detectable) y sin datos.
- Algoritmo en una línea: diferencias de temperatura de brillo (ΔT1 = 10.3−12.3 µm,
  ΔT2 = 8.5−10.3 µm, ΔT3 = 3.9−10.3 µm), reflectancia en 1.37 µm, BT en 10.3 µm,
  tres bloques de iluminación por ángulo cenital solar, un kernel estadístico de 5×5
  y la fase de nube de ABI.
- Entradas: L2 CMIP de las bandas C04, C07, C11, C13 y C15, y la fase de nube (ACTP),
  generadas con CSPP Geo AIT 2.3.1 [@CSPPGeo]. Salida: GeoTIFF de una banda con tabla de
  colores y un estilo `.qml` para QGIS.
- Corre en operación en LANOT cada 5 minutos. El artículo usó GOES-16; el software
  funciona igual con GOES-19 (GOES-East desde abril de 2025).

# Statement of need

- Problema: el Popocatépetl emite ceniza casi sin interrupción desde 1994, con unos
  30 millones de personas y tres aeropuertos internacionales en un radio de ~100 km
  (datos del artículo).
- Latencia: el VAAC de Washington suele emitir sus avisos hasta ~30 min después de
  observar la nube [@Vasconez2024]. Este software entrega el producto unos 4.3 min
  después del inicio del escaneo, contando CSPP (ver
  `doc/2026-10-18_operacion_tahan.md`).
- Para quién: SENEAM, protección civil y CENAPRED (los usuarios que nombra el
  artículo), y los investigadores que quieran reproducir el artículo o adaptar el
  algoritmo a otro volcán. El artículo dice que para eso hay que recalibrar los
  umbrales, no cambiar el código.
- Por qué otra herramienta: la versión previa estaba en TeraScan (comercial, cerrada).
  Esta es abierta, se instala con `pip` y no necesita licencias.

# State of the field

- Productos de NOAA: el algoritmo de ceniza de GOES-R [@Pavolonis2013; @Pavolonis2020]
  y VOLCAT [@Pavolonis2018]. Son globales y no se adaptan a las condiciones locales
  de un volcán; VOLCAT no es abierto (¿confirmar cómo se accede?).
- Sistemas operativos regionales: HOTVOLC en Francia [@Guehenneux2024].
- Para el Popocatépetl, @Juarez2024 compararon tres algoritmos con GOES-16, solo en
  eventos explosivos discretos.
- Herramientas generales: `satpy`/Pytroll [@Raspaud2018] hace el RGB de ceniza para
  interpretación visual, pero no clasifica píxeles.
- Lugar de LANOT_ceniza: una implementación abierta de un algoritmo publicado y
  validado, hecha para operación de baja latencia; no es una biblioteca general.

# Software design

- Un solo paso por escena: lectura de L2 → ángulo cenital solar → `classify_ash` →
  GeoTIFF. La clasificación es una función pura sobre arreglos, probada regla por regla.
- Pila: xarray, NumPy, SciPy, rioxarray/pyproj y rasterio [@Hoyer2017; @Harris2020].
- Ángulo cenital solar: posición del Sol una vez por escena con Skyfield
  [@Rhodes2019] y las efemérides DE421 [@Folkner2009], y trigonometría esférica
  vectorizada para todos los píxeles. Error ~0.003°.
- Kernel estadístico (media y desviación locales) con filtros uniformes sobre x y x²:
  de 7.3 s con 16 procesos a 0.17 s con 1 proceso, con el mismo resultado. La
  sección 2.4 del artículo describe la versión de diciembre (`generic_filter` y
  multiprocessing), y así se queda.
- Una subsección o párrafo "Changes since the published version": qué cambió desde
  `90ad79f` y cuánto cambia la clasificación (reglas de mayo, SZA, crepúsculo, C14,
  clase 6, 0/255). Datos en `doc/2026-10-19_plan_mejoras_operacion.md`.
- Recorte por región antes de cargar los arreglos y reproyección opcional a
  EPSG:4326 por vecino más cercano (para no mezclar clases).
- Formato de salida: valores enteros con significado fijo (0, 1–3, 6, 255) y NoData
  explícito. El `.qml` resuelve la transparencia y la leyenda en QGIS (la paleta de un
  TIFF no guarda alfa).
- Operación: búsqueda estricta de archivos, códigos de salida, CSV de latencia con
  estado y un vigilante que escribe `estado.json`.
- Pruebas: `pytest` con recortes de tres escenas reales (noche, crepúsculo, día) y
  pruebas unitarias por regla. Herramientas para comparar dos versiones en escenas
  completas.
- Figura propuesta: diagrama del flujo, o un panel con la escena y la clasificación
  (¿reusar la Fig. 2 del artículo, el esquema del algoritmo?).

# Research impact statement

- El artículo [@JimenezEscudero_articulo] usó este software para todos sus
  resultados: 662 emisiones de 2019, 2023 y 2024, 39 389 conjuntos de imágenes ABI,
  validadas con VIIRS y con la red de muestreo de ceniza.
- En operación en LANOT desde el 2026-10-18: cada escaneo CONUS de GOES-19, con
  ~4.3 min de latencia total.
- Reproducibilidad: la versión del artículo está identificada (`90ad79f`) y las
  diferencias con la versión actual están medidas en 63 escenas
  (`doc/2026-10-19_plan_mejoras_operacion.md`).
- Uso esperado: otros volcanes que ve GOES-East (el artículo menciona Colima y
  El Chichón), recalibrando los umbrales.

# AI usage disclosure

- Modelo: el de hpsatviews, adaptado. El algoritmo es de los autores del artículo; el
  diseño del software, la arquitectura y las decisiones técnicas son del primer autor.
- Uso: Claude (Anthropic) como asistente de código, bajo la dirección de un
  desarrollador con experiencia en cómputo de alto rendimiento y cómputo científico:
  refactorización (mayo de 2026), cadena de operación y plan de mejoras (octubre de
  2026: pruebas, kernel vectorizado, corrección del ángulo cenital solar, reporte de
  fallas) y redacción de este artículo.
- Todo cambio asistido se revisó y validó, con pruebas y comparaciones píxel por
  píxel contra la versión del artículo.

# Acknowledgements

- LANOT, UNAM, con apoyo del Laboratorio Nacional SECIHTI 2025-2027, proyecto
  LN-2025-C-102 (el mismo texto que en hpsatviews).
- SSEC/CIMSS por CSPP Geo, y Kathy Strabala por preparar los datos auxiliares de 2019.
- Coautores del artículo que no están aquí: Gabriela Gómez-Rodríguez (coautora del
  algoritmo), Amiel Nieto-Torres, Ana Lillian Martin-Del-Pozzo y Jorge Prado-Molina.

# References
