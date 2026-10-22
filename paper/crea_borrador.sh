#!/bin/bash
# Genera paper.pdf con la herramienta oficial de JOSS (inara), como en hpsatviews.
cd "$(dirname "$0")" || exit 1
docker run --rm \
  --volume "$PWD":/data \
  --user "$(id -u):$(id -g)" \
  --env JOURNAL=joss \
  openjournals/inara
