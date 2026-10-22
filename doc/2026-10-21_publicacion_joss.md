# Publicación del software en JOSS

- **Fecha:** 2026-10-21
- **Estado:** esqueleto en `paper/`. No se envía antes de que se publique el artículo científico.

## Contexto

hpsatviews no se pudo publicar en JOSS ni en SoftwareX porque no había un artículo científico que usara el software. Aquí sí lo hay: "Ash detection with ABI/GOES-16 images at Popocatépetl volcano, México" (Jiménez-Escudero, Gómez-Rodríguez, Nieto-Torres, Martin-Del-Pozzo, Aguilar-Sierra y Prado-Molina), que presenta el algoritmo ABI-Popocatépetl. Todos sus resultados se hicieron con este paquete (versión `90ad79f`). Manuscrito vigente: `~/Dropbox/cca/lanot/ceniza/fase2/Jimenez et al Ash detection REV.docx`. Se empieza con JOSS por ser el más corto; el borrador sirve también para ordenar ideas si después se elige SoftwareX.

**Autores:** Alejandro Aguilar Sierra (implementación; primer autor) y Víctor Manuel Jiménez Escudero (autor del algoritmo, del artículo y de la versión previa en TeraScan).

## Archivos

- `paper/paper.md`: secciones del formato actual de JOSS, con notas en español de lo que va en cada una.
- `paper/paper.bib`: referencias; las que dicen TODO faltan.
- `paper/crea_borrador.sh`: genera el PDF con inara (docker).

Se borraron el `paper.md` y el `references.bib` de la raíz (esqueleto de diciembre de 2025, sin contenido).

## Antes de enviar

- [ ] Revista, volumen y DOI del artículo (título y autores ya están).
- [ ] Versión de CSPP Geo AIT usada en operación.
- [ ] La sección 2.4 del artículo describe la implementación de diciembre: `generic_filter` y multiprocessing, "sub-arcsecond accuracy", ~10 s por escena CONUS y "0 = no ash". El texto de JOSS describe la versión actual; conviene que las dos no se contradigan (ver con Víctor).
- [ ] El artículo dice que HAP y LAP con fase superenfriada pasan a sin ceniza (P10 del plan de mejoras); afecta también a la clase 6.
- [ ] Revisar las reglas vigentes de JOSS (límite de palabras, secciones, declaración de IA).
- [ ] Licencia: `LICENSE` es GPL v3, `CITATION.cff` dice MIT.
- [ ] Versión: `CITATION.cff` dice 1.0.0 y `pyproject.toml` 0.2.0. Publicar un release y archivarlo en Zenodo (DOI).
- [ ] `pyproject.toml`: nombre completo del primer autor y una descripción real (hoy "Paquete mínimo instalable").
- [ ] `CITATION.cff`: corregir `preferred-citation` (dice "Sierra, A.") y, al publicar, citar el artículo de JOSS.
- [ ] `CONTRIBUTING.md`: cómo contribuir, reportar problemas y pedir ayuda.
- [ ] Documentación: el README está en español. Ver si JOSS pide documentación en inglés; quizá un README en inglés.
- [ ] Ejemplo reproducible para los revisores: datos pequeños o instrucciones para bajarlos (¿los recortes de `tests/`?).
- [ ] Fase 3 del plan de mejoras (P10, P11) resuelta, para que el código coincida con el texto del artículo.
