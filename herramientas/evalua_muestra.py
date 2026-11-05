#!/usr/bin/env python3
"""Evalúa TeraScan, las reglas de TeraScan en Python y la nuestra contra los avisos del VAAC.

    herramientas/evalua_muestra.py --terascan DIR --muestra DIR --avisos avisos_popocatepetl.csv

--muestra tiene una carpeta por día (AAAAjjj/) con las salidas de reglas_terascan.py
(terascan_py/ y nuestra/). --terascan, los GeoTIFF de TeraScan. --avisos, el CSV de
avisos_vaac.py.

Por escaneo cuenta los píxeles de ceniza a menos de --radio km del volcán (ceniza: 1 a 3, y el
4 de TeraScan) y escribe MUESTRA/escaneos.csv. Luego reporta:

- por aviso del VAAC, si cada salida ve ceniza en algún escaneo a ±--ventana minutos de la
  hora de observación, separando la ceniza vista por el satélite de la solo estimada;
- por día, en cuántos escaneos ve ceniza cada salida.

Una salida "ve ceniza" en un escaneo si tiene al menos --minimo píxeles cerca del volcán. Solo
se cuentan los escaneos que existen en las tres salidas.
"""
import argparse
import collections
import csv
import datetime
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compara_salidas import a_rejilla, lee, por_instante  # noqa: E402

VOLCAN = (19.023, -98.622)
SALIDAS = ("terascan", "reglas_ts", "nuestra")


def cerca_del_volcan(perfil, radio_km):
    h, w = perfil["shape"]
    t = perfil["transform"]
    lon = t.c + t.a * (np.arange(w) + 0.5)
    lat = t.f + t.e * (np.arange(h) + 0.5)
    lon, lat = np.meshgrid(lon, lat)
    p1, p2 = np.radians(lat), np.radians(VOLCAN[0])
    c = np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(np.radians(lon - VOLCAN[1]))
    return 6371 * np.arccos(np.clip(c, -1, 1)) < radio_km


def instante_a_fecha(inst):
    return datetime.datetime.strptime(inst, "%Y%j%H%M")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--terascan", type=Path, required=True)
    ap.add_argument("--muestra", type=Path, required=True)
    ap.add_argument("--avisos", type=Path, required=True)
    ap.add_argument("--radio", type=float, default=100, help="km alrededor del volcán")
    ap.add_argument("--minimo", type=int, default=1, help="píxeles para decir que hay ceniza")
    ap.add_argument("--ventana", type=int, default=15, help="minutos alrededor de la hora del aviso")
    args = ap.parse_args()

    ts = por_instante(args.terascan)
    escaneos = {}  # instante -> {salida: píxeles}
    mascara = None
    for dia in sorted(d for d in args.muestra.iterdir() if (d / "nuestra").is_dir()):
        py, nu = por_instante(dia / "terascan_py"), por_instante(dia / "nuestra")
        for inst in sorted(set(py) & set(nu) & set(ts)):
            a, pa, _ = lee(ts[inst])
            if mascara is None:
                mascara = cerca_del_volcan(pa, args.radio)
            fila = {"terascan": int((np.isin(a, [1, 2, 3, 4]) & mascara).sum())}
            for nombre, ruta in (("reglas_ts", py[inst]), ("nuestra", nu[inst])):
                b, pb, _ = lee(ruta)
                b = a_rejilla(b, pb, pa)
                fila[nombre] = int((np.isin(b, [1, 2, 3, 4]) & mascara).sum())
            escaneos[inst] = fila
    if not escaneos:
        sys.exit("No hay escaneos con las tres salidas.")

    with open(args.muestra / "escaneos.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["instante", "fecha_utc", *SALIDAS])
        for inst, fila in sorted(escaneos.items()):
            w.writerow([inst, instante_a_fecha(inst).strftime("%Y-%m-%d %H:%M"), *(fila[s] for s in SALIDAS)])

    ve = {inst: {s: fila[s] >= args.minimo for s in SALIDAS} for inst, fila in escaneos.items()}
    tiempos = sorted((instante_a_fecha(i), i) for i in escaneos)
    dias = {t.date() for t, _ in tiempos}

    # Por aviso
    print(f"Ceniza: ≥ {args.minimo} píxeles a < {args.radio:g} km del volcán. {len(escaneos)} escaneos en {len(dias)} días.\n")
    print(f"Avisos del VAAC: ¿alguna salida ve ceniza a ±{args.ventana} min de la observación?")
    aciertos = collections.defaultdict(lambda: collections.Counter())
    detalle = []
    for r in csv.DictReader(open(args.avisos)):
        if not r["observacion"] or r["ceniza_sat"] == "no":
            continue
        t = datetime.datetime.strptime(r["observacion"], "%Y-%m-%d %H:%M")
        if t.date() not in dias:
            continue
        cerca = [i for tt, i in tiempos if abs((tt - t).total_seconds()) <= args.ventana * 60]
        if not cerca:
            continue
        tipo = "vista por satélite" if r["ceniza_sat"] == "sí" else "estimada (no vista)"
        aciertos[tipo]["avisos"] += 1
        res = {s: any(ve[i][s] for i in cerca) for s in SALIDAS}
        for s in SALIDAS:
            aciertos[tipo][s] += res[s]
        detalle.append((r["observacion"], tipo, res))
    print(f"  {'tipo':22s} {'avisos':>6s}" + "".join(f"{s:>11s}" for s in SALIDAS))
    for tipo, c in aciertos.items():
        print(f"  {tipo:22s} {c['avisos']:6d}" + "".join(f"{c[s]:11d}" for s in SALIDAS))
    print("\n  Avisos que alguna salida no ve:")
    for obs, tipo, res in detalle:
        if not all(res.values()):
            print(f"    {obs}  {tipo:20s} " + "  ".join(f"{s}={'sí' if res[s] else 'no'}" for s in SALIDAS))

    # Por día
    print("\nPor día: escaneos con ceniza (de los escaneos con las tres salidas)")
    print(f"  {'día':10s} {'escaneos':>8s}" + "".join(f"{s:>11s}" for s in SALIDAS))
    for d in sorted(dias):
        insts = [i for t, i in tiempos if t.date() == d]
        print(f"  {d}  {len(insts):8d}" + "".join(f"{sum(ve[i][s] for i in insts):11d}" for s in SALIDAS))
    print(f"\nPor escaneo: {args.muestra / 'escaneos.csv'}")


if __name__ == "__main__":
    main()
