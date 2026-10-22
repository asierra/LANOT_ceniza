# Umbrales configurables por volcán (perfiles)

- **Fecha:** 2026-10-21
- **Estado:** aprobado en lo general; se implementa después de la reunión del 2026-10-23 (para que la regla de fase, P10, entre ya como tabla).

## Por qué

Los umbrales del algoritmo están calibrados para el Popocatépetl. El artículo dice que para otro volcán hay que recalibrarlos y ajustar los límites del ángulo cenital solar a la latitud. Hoy todo está escrito en el código (`classify_ash`, `CLIP_REGIONS`, `FASES_NUBE`), así que cambiar un umbral exige editar el código. El primer caso es un proyecto en Chile, que tiene su propio repositorio.

## Decisiones

1. **Formato TOML**, leído con `tomllib` (biblioteca estándar). Se sube `requires-python` a `>=3.11` (tahan tiene la 3.12).
2. **Los perfiles viven en el repositorio** (`perfiles/popocatepetl.toml`, versionados con el código). `--perfil NOMBRE` elige uno del repositorio y `--perfil RUTA.toml` acepta cualquier archivo. Sin `--perfil` se usa Popocatépetl: la operación no cambia.

## Diseño propuesto

- Un `dataclass` inmutable `Perfil`, leído del TOML, que recibe `classify_ash`.
- Contenido del perfil:
  - umbrales: ΔT1, ΔT2, ΔT3, R1.37, BT13, filtros de ΔT2 y ΔT3, kernel (tamaño y umbral);
  - límites del SZA (70° y 85° para el Popocatépetl);
  - regla de fase como tabla (clase × fase → clase resultante) y fases que cuentan como nube (clase 6);
  - región de recorte, coordenadas del volcán y dominio (CONUS o disco completo).
- Validación estricta: una clave desconocida o faltante es un error.
- El GeoTIFF guarda en sus metadatos el nombre y el hash del perfil.
- Pruebas: el perfil del Popocatépetl reproduce exactamente las pruebas de regresión actuales; pruebas de lectura y de errores del TOML.

## Lo que no se parametriza

La estructura del algoritmo: los tres bloques de iluminación, la fórmula del kernel y el orden de los filtros. Si otro volcán necesita otra lógica (otra banda, otro filtro), es código nuevo con sus pruebas.

## Pendiente

- Revisar con el repositorio del proyecto de Chile qué necesita (posiblemente disco completo, cada 10 min). La búsqueda de archivos ya acepta el dominio F, pero la lógica de instantes y de desfase supone CONUS en algunos lugares.
