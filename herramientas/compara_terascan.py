#!/usr/bin/env python3
"""Mapa de diferencias entre un GeoTIFF de TeraScan y uno nuestro del mismo instante.

    herramientas/compara_terascan.py TERASCAN.tif NUESTRO.tif [-o mapa.png] [--radio KM]

Sirve para ver los escaneos que herramientas/compara_salidas.py señala con más diferencias.
Requiere matplotlib (pip install matplotlib).

Lee los dos archivos con compara_salidas.lee y lleva el nuestro a la rejilla de TeraScan
(vecino más cercano). Clases de TeraScan (script ash_new_m8_altura): 1 CA, 2 HAP, 3 LAP y 4.
El 4 sale de "HAP bajo nube", pero su paleta lo pinta como "cloud" y casi todo lo que marca
está lejos del volcán; aquí no cuenta como ceniza (--cuenta-4 lo cuenta como HAP). TeraScan no
distingue "sin ceniza" de "sin datos". Las nuestras: 1 CA, 2 HAP, 3 LAP, 6 nube, 255 sin datos.

En el mapa:
    coincide       ceniza en los dos, misma clase
    otra clase     ceniza en los dos, distinta clase
    sobra          ceniza solo en la nuestra
    falta          ceniza solo en TeraScan; la nuestra dice sin ceniza o sin datos
    falta (nube)   ceniza solo en TeraScan; la nuestra dice nube (6)

Por omisión, el mapa se recorta a 150 km del Popocatépetl (--radio 0: región completa).
Ver doc/2026-11-05_comparacion_terascan.md.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compara_salidas import a_rejilla, lee  # noqa: E402

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
except ImportError:
    sys.exit("compara_terascan.py necesita matplotlib: pip install matplotlib")

VOLCAN = (19.023, -98.622)  # lat, lon
NUBE = 6
CATEGORIAS = [  # (valor en el mapa, nombre, color)
    (0, "fondo", "#f0f0f0"),
    (1, "coincide", "#2ca02c"),
    (2, "otra clase", "#ff7f0e"),
    (3, "sobra", "#d62728"),
    (4, "falta", "#1f77b4"),
    (5, "falta (nube)", "#9467bd"),
]


def compara(ts, nuestra, cuenta_4=False):
    """Mapa de categorías (ver CATEGORIAS) y conteo por categoría."""
    ts_clase = np.where(ts == 4, 2, ts)  # con cuenta_4, el HAP bajo nube cuenta como HAP
    ceniza_ts = np.isin(ts, [1, 2, 3, 4] if cuenta_4 else [1, 2, 3])
    ceniza_n = np.isin(nuestra, [1, 2, 3])
    mapa = np.zeros(ts.shape, np.uint8)
    mapa[ceniza_ts & ceniza_n & (ts_clase == nuestra)] = 1
    mapa[ceniza_ts & ceniza_n & (ts_clase != nuestra)] = 2
    mapa[~ceniza_ts & ceniza_n] = 3
    mapa[ceniza_ts & ~ceniza_n & (nuestra != NUBE)] = 4
    mapa[ceniza_ts & (nuestra == NUBE)] = 5
    conteo = {nombre: int((mapa == v).sum()) for v, nombre, _ in CATEGORIAS[1:]}
    conteo["TeraScan 4 (HAP bajo nube)"] = int((ts == 4).sum())
    return mapa, conteo


def ventana(perfil, radio_km):
    """Filas y columnas a menos de radio_km del volcán (aproximación plana)."""
    h, w = perfil["shape"]
    t = perfil["transform"]
    lon = t.c + t.a * (np.arange(w) + 0.5)
    lat = t.f + t.e * (np.arange(h) + 0.5)
    dlat = radio_km / 111.2
    dlon = dlat / np.cos(np.radians(VOLCAN[0]))
    filas = np.where(np.abs(lat - VOLCAN[0]) <= dlat)[0]
    cols = np.where(np.abs(lon - VOLCAN[1]) <= dlon)[0]
    return slice(filas[0], filas[-1] + 1), slice(cols[0], cols[-1] + 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("terascan", type=Path)
    ap.add_argument("nuestro", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="PNG de salida (por omisión, dif_<nuestro>.png)")
    ap.add_argument("--cuenta-4", action="store_true", help="cuenta el 4 de TeraScan como HAP")
    ap.add_argument("--radio", type=float, default=150, help="km alrededor del volcán (0: región completa)")
    args = ap.parse_args()

    ts, perfil, _ = lee(args.terascan)
    nuestra, perfil_n, _ = lee(args.nuestro)
    nuestra = a_rejilla(nuestra, perfil_n, perfil)
    mapa, conteo = compara(ts, nuestra, args.cuenta_4)

    print(f"TeraScan: {args.terascan.name}\nNuestro:  {args.nuestro.name}\n")
    for nombre, n in conteo.items():
        print(f"  {nombre:28s} {n:8d}")

    extension = None
    if args.radio > 0:
        filas, cols = ventana(perfil, args.radio)
        mapa = mapa[filas, cols]
        t = perfil["transform"]
        extension = [t.c + t.a * cols.start, t.c + t.a * cols.stop, t.f + t.e * filas.stop, t.f + t.e * filas.start]
    else:
        b = rasterio.transform.array_bounds(*perfil["shape"], perfil["transform"])
        extension = [b[0], b[2], b[1], b[3]]

    salida = args.output or Path(f"dif_{args.nuestro.stem}.png")
    plt.figure(figsize=(10, 9))
    plt.imshow(mapa, cmap=ListedColormap([c for _, _, c in CATEGORIAS]), vmin=0, vmax=len(CATEGORIAS) - 1,
               interpolation="nearest", extent=extension)
    plt.plot(VOLCAN[1], VOLCAN[0], "k^", markersize=8)
    plt.title(f"TeraScan contra la nuestra\n{args.terascan.name}  ·  {args.nuestro.name}", fontsize=11)
    plt.xlabel("longitud")
    plt.ylabel("latitud")
    plt.legend(handles=[mpatches.Patch(color=c, label=f"{nombre}: {conteo[nombre]}")
                        for _, nombre, c in CATEGORIAS[1:]], loc="lower right", fontsize=10)
    plt.tight_layout()
    plt.savefig(salida, dpi=120)
    print(f"\nMapa: {salida}")


if __name__ == "__main__":
    main()
