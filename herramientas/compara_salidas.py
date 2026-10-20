#!/usr/bin/env python3
"""Compara dos carpetas de GeoTIFF de ceniza (por ejemplo, dos versiones de detect_ash.py).

    herramientas/compara_salidas.py DIR_A DIR_B [--detalle]

Empareja los archivos por instante (YYYYjjjHHMM en el nombre) y reporta:
- la matriz de confusión de clases en todos los instantes (filas A, columnas B);
- los instantes con píxeles distintos;
- los instantes en que la ceniza aparece o desaparece.

Lee los dos formatos que ha tenido la salida:
- 1 banda con valores de clase (desde mayo de 2026);
- RGBA de 4 bandas (diciembre de 2025): se decodifica por color. Ahí "sin ceniza" y
  "sin datos" son ambos transparentes y se cuentan como 0.
Entre mayo y octubre de 2026 el "sin ceniza" (0) se guardaba como 255. Para comparar esas
salidas con las de ahora, --une-sin-ceniza cuenta 0 y 255 juntos (como en RGBA).
Si las rejillas no coinciden, B se remuestrea a la de A (vecino más cercano).
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

CLASES = [0, 1, 2, 3, 4, 5, 6, 255]
NOMBRES = {0: "sin ceniza", 1: "CA", 2: "HAP", 3: "LAP", 4: "res.4", 5: "res.5", 6: "nube", 255: "sin datos"}
COLORES_RGBA = {(255, 0, 0): 1, (255, 165, 0): 2, (255, 255, 0): 3, (0, 255, 0): 4, (0, 0, 255): 5}


def lee(ruta):
    """Devuelve (clases, perfil, era_rgba)."""
    with rasterio.open(ruta) as d:
        perfil = {"crs": d.crs, "transform": d.transform, "shape": (d.height, d.width)}
        if d.count >= 4:
            r, g, b, a = d.read()[:4]
            c = np.zeros((d.height, d.width), np.uint8)
            for rgb, clase in COLORES_RGBA.items():
                c[(r == rgb[0]) & (g == rgb[1]) & (b == rgb[2]) & (a > 0)] = clase
            return c, perfil, True
        return d.read(1), perfil, False


def a_rejilla(c, origen, destino):
    if origen["shape"] == destino["shape"] and origen["transform"].almost_equals(destino["transform"]) \
            and origen["crs"] == destino["crs"]:
        return c
    out = np.full(destino["shape"], 255, np.uint8)
    reproject(c, out, src_transform=origen["transform"], src_crs=origen["crs"], dst_transform=destino["transform"],
              dst_crs=destino["crs"], resampling=Resampling.nearest, src_nodata=None, dst_nodata=255)
    return out


def por_instante(carpeta):
    archivos = {}
    for f in sorted(Path(carpeta).glob("*.tif")):
        m = re.search(r"(\d{11})", f.name)
        if m:
            archivos[m.group(1)] = f
    return archivos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--detalle", action="store_true", help="una línea por instante, aunque no haya diferencias")
    ap.add_argument("--une-sin-ceniza", action="store_true",
                    help="cuenta 'sin ceniza' (0) y 'sin datos' (255) como lo mismo")
    ap.add_argument("--solo-ceniza", action="store_true",
                    help="compara solo la ceniza: 0, nube (6) y sin datos (255) cuentan como sin ceniza")
    args = ap.parse_args()

    A, B = por_instante(args.a), por_instante(args.b)
    comunes = sorted(set(A) & set(B))
    for nombre, solo in (("A", set(A) - set(B)), ("B", set(B) - set(A))):
        if solo:
            print(f"Solo en {nombre}: {len(solo)} instantes ({', '.join(sorted(solo)[:5])}{'...' if len(solo) > 5 else ''})")
    if not comunes:
        sys.exit("No hay instantes en común.")

    idx = {c: i for i, c in enumerate(CLASES)}
    total = np.zeros((len(CLASES), len(CLASES)), np.int64)
    distintos, cambios_presencia = [], []
    rgba_visto = False
    for inst in comunes:
        ca, pa, ra = lee(A[inst])
        cb, pb, rb = lee(B[inst])
        cb = a_rejilla(cb, pb, pa)
        if args.solo_ceniza:
            ca = np.where(np.isin(ca, [1, 2, 3]), ca, 0)
            cb = np.where(np.isin(cb, [1, 2, 3]), cb, 0)
        if ra or rb or args.une_sin_ceniza:  # en RGBA, sin ceniza y sin datos no se distinguen
            rgba_visto = True
            ca = np.where(ca == 255, 0, ca)
            cb = np.where(cb == 255, 0, cb)
        m = np.zeros_like(total)
        np.add.at(m, (np.vectorize(idx.get)(ca).ravel(), np.vectorize(idx.get)(cb).ravel()), 1)
        total += m
        n = int((ca != cb).sum())
        ceniza_a, ceniza_b = int(np.isin(ca, [1, 2, 3]).sum()), int(np.isin(cb, [1, 2, 3]).sum())
        if n:
            distintos.append(inst)
        if (ceniza_a > 0) != (ceniza_b > 0):
            cambios_presencia.append((inst, ceniza_a, ceniza_b))
        if args.detalle or n:
            print(f"{inst}  píxeles distintos {n:7d}   con ceniza A {ceniza_a:6d}  B {ceniza_b:6d}")

    usadas = [i for i, c in enumerate(CLASES) if total[i].sum() or total[:, i].sum()]
    print(f"\n{len(comunes)} instantes comparados; {len(distintos)} con diferencias.")
    if rgba_visto:
        print("('sin ceniza' y 'sin datos' se cuentan juntos como 0: hay salidas RGBA o se pidió --une-sin-ceniza.)")
    print("\nMatriz de confusión (filas A, columnas B), todos los instantes:")
    print(" " * 12 + "".join(f"{NOMBRES[CLASES[j]]:>12s}" for j in usadas))
    for i in usadas:
        print(f"{NOMBRES[CLASES[i]]:>12s}" + "".join(f"{total[i, j]:12d}" for j in usadas))
    if cambios_presencia:
        print("\nInstantes en que la ceniza aparece o desaparece (píxeles con ceniza A -> B):")
        for inst, a, b in cambios_presencia:
            print(f"  {inst}: {a} -> {b}")


if __name__ == "__main__":
    main()
