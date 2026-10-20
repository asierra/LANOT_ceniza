#!/usr/bin/env python3
"""Recorta a una región los NetCDF L2 que usa detect_ash.py, para las pruebas de regresión.

Conserva los nombres de archivo, la proyección, las coordenadas y la codificación
(enteros empaquetados con scale_factor/add_offset), así que los valores
decodificados son idénticos a los del archivo original.

    python3 genera_fixture.py --l2 /data/ceniza/l2/2019/03/01 --instante 20190601332 \
        --bbox -100.262 20.580 -96.850 18.289 --salida tests/datos/l2

bbox: lon_min lat_max lon_max lat_min, el mismo orden que CLIP_REGIONS en detect_ash.py.
"""
import argparse
import re
from pathlib import Path

import numpy as np
import xarray as xr
from pyproj import CRS, Transformer

# Producto -> patrón del nombre. Mismos productos que lee detect_ash.py.
PRODUCTOS = {
    "ACTP": r"ACTPC-M\d_",
    "C04": r"CMIPC-M\dC04_",
    "C07": r"CMIPC-M\dC07_",
    "C11": r"CMIPC-M\dC11_",
    "C13": r"CMIPC-M\dC13_",
    "C15": r"CMIPC-M\dC15_",
}
VARIABLES = {"ACTP": "Phase"}  # las bandas usan CMI


def indices_region(ds, bbox, margen=2):
    """Índices (y, x) que cubren el bbox geográfico en la rejilla GOES del archivo."""
    p = ds["goes_imager_projection"]
    h = float(p.perspective_point_height)
    crs = CRS.from_proj4(
        f"+proj=geos +h={h} +lon_0={p.longitude_of_projection_origin} "
        f"+sweep={p.sweep_angle_axis} +a={p.semi_major_axis} +b={p.semi_minor_axis} +units=m +no_defs")
    a_goes = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    lon_min, lat_max, lon_max, lat_min = bbox
    esquinas = [(lon_min, lat_min), (lon_min, lat_max), (lon_max, lat_min), (lon_max, lat_max)]
    xs, ys = zip(*(a_goes.transform(lo, la) for lo, la in esquinas))
    x = ds["x"].values * h
    y = ds["y"].values * h
    ix = np.where((x >= min(xs)) & (x <= max(xs)))[0]
    iy = np.where((y >= min(ys)) & (y <= max(ys)))[0]
    return (slice(max(iy[0] - margen, 0), iy[-1] + 1 + margen),
            slice(max(ix[0] - margen, 0), ix[-1] + 1 + margen))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--l2", type=Path, required=True, help="carpeta con los NetCDF L2 del instante")
    ap.add_argument("--instante", required=True, help="YYYYjjjHHMM")
    ap.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("LON_MIN", "LAT_MAX", "LON_MAX", "LAT_MIN"))
    ap.add_argument("--salida", type=Path, required=True)
    args = ap.parse_args()

    candidatos = sorted(args.l2.glob(f"*_s{args.instante}*.nc"))
    archivos = {}
    for prod, patron in PRODUCTOS.items():
        f = [c for c in candidatos if re.search(patron, c.name)]
        if not f:
            raise SystemExit(f"Falta {prod} para {args.instante} en {args.l2}")
        archivos[prod] = f[0]

    with xr.open_dataset(archivos["C07"]) as ds:
        sy, sx = indices_region(ds, args.bbox)

    args.salida.mkdir(parents=True, exist_ok=True)
    for prod, f in archivos.items():
        var = VARIABLES.get(prod, "CMI")
        with xr.open_dataset(f) as ds:
            sub = ds[[var, "goes_imager_projection"]].isel(y=sy, x=sx)
            sub.attrs = {k: ds.attrs[k] for k in ("time_coverage_start", "time_coverage_end", "platform_ID",
                                                   "scene_id", "dataset_name") if k in ds.attrs}
            enc = {var: {**{k: v for k, v in ds[var].encoding.items()
                            if k in ("dtype", "scale_factor", "add_offset", "_FillValue")},
                         "zlib": True, "complevel": 9}}
            for c in ("x", "y"):
                enc[c] = {k: v for k, v in ds[c].encoding.items() if k in ("dtype", "scale_factor", "add_offset")}
            sub.to_netcdf(args.salida / f.name, encoding=enc)
        print(f"{args.salida / f.name}  {sub[var].shape}")


if __name__ == "__main__":
    main()
