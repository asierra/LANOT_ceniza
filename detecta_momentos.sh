#! /bin/bash

cd /opt/LANOT_ceniza
for m in `cat ~/ceniza/instantes_animav2.txt`
do 
    echo "=== Procesando intervalo: $m ==="
    ./detect_ash.py --moment $m --clip ashpapergeo --output /data/ceniza/output/$m/ --date-tree --png > ~/ceniza/instantes_anima_$m.log 2>&1
    echo "Completado: $m (ver log en ~/ceniza/instantes_anima_$m.log)"
done

echo "=== Todos los intervalos procesados ===" 
