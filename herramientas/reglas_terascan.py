#!/usr/bin/env python3
"""Clasifica los mismos L2 con las reglas de TeraScan y con classify_ash, en la rejilla de TeraScan.

    herramientas/reglas_terascan.py --l2 CARPETA --plantilla TERASCAN.tif --salida DIR INSTANTE...

Sirve para separar, al comparar con TeraScan, lo que cambia por las reglas de lo que cambia
por los datos de entrada. Escribe dos carpetas en DIR:

    terascan_py/ceniza_INSTANTE.tif   reglas de TeraScan sobre nuestros L2
    nuestra/ceniza_INSTANTE.tif       classify_ash (perfil del Popocatépetl) sobre los mismos datos

Las reglas son las del script de TeraScan `ash_new_m8_altura` (agosto de 2024; copia en
/data/ceniza/terascan/ y descripción en doc/2026-11-05_comparacion_terascan.md):

    ΔT1 = BT13 − BT15    ΔT2 = BT11 − BT13    ΔT3 = BT07 − BT13
    noche (SZA > 85):        CA  ΔT1 < 0, ΔT2 > 0,    ΔT3 > 2
                             HAP ΔT1 < 1, ΔT2 > −0.5, ΔT3 > 2
                             LAP ΔT1 < 3, ΔT2 > −1,   ΔT3 > 2, BT14 < 273
    crepúsculo (70 a 85):    lo mismo, todo con R04 > umbral, y HAP con BT14 < 273
    día (SZA < 70):          lo mismo, todo con R04 > umbral (BT14 < 273 solo en LAP)
    SZA exactamente 70 u 85: 0
    nube: HAP → 4, LAP → 0. En lugar de la máscara de TeraScan se usa la de CSPP (ACM),
        según --nube: bcm (nublado o probablemente nublado; por omisión), acm3 (solo
        nublado) o ninguna

Supuestos: TeraScan recibe los archivos en orden alfabético (cloudmask, C04, C07, C11, C13,
C14, C15), y no se sabe si su R04 está en fracción o en porcentaje; por eso --r04 (0.3 tal
cual, o 0.003 si TeraScan usa porcentaje).

INSTANTE es YYYYjjjHHMM como en el nombre de los L2 (con el minuto real del escaneo); se
pueden pasar en un archivo con @lista.txt. Corre con el Python de lanot_ceniza instalado.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from pyproj import CRS, Transformer
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import detect_ash  # noqa: E402

SIN_DATOS = 255


def reglas_terascan(c04, c07, c11, c13, c14, c15, nube, sza, r04_min):
    """Clases de TeraScan: 0 sin ceniza, 1 CA, 2 HAP, 3 LAP, 4 HAP bajo nube."""
    dt1, dt2, dt3 = c13 - c15, c11 - c13, c07 - c13
    ca = (dt1 < 0) & (dt2 > 0) & (dt3 > 2)
    hap = (dt1 < 1) & (dt2 > -0.5) & (dt3 > 2)
    lap = (dt1 < 3) & (dt2 > -1) & (dt3 > 2) & (c14 < 273)
    frio = c14 < 273
    luz = c04 > r04_min

    noche = np.select([ca, hap, lap], [1, 2, 3], 0)
    crep = np.select([ca & luz, hap & luz & frio, lap & luz], [1, 2, 3], 0)
    dia = np.select([ca & luz, hap & luz, lap & luz], [1, 2, 3], 0)
    clase = np.select([sza > 85, (sza < 85) & (sza > 70), sza < 70], [noche, crep, dia], 0)

    clase = np.where((clase == 2) & (nube == 1), 4, clase)
    clase = np.where((clase == 3) & (nube == 1), 0, clase)
    return clase.astype(np.uint8)


def lee_cmi(ruta, ys, xs):
    with xr.open_dataset(ruta) as ds:
        return ds["CMI"].data[ys, xs]


def procesa(carpeta, instante, plantilla, salida, eph, ts, r04_min, mascara="bcm"):
    archivos, faltan = detect_ash.busca_archivos(carpeta, instante, detect_ash.PRODUCTOS + ["C14"])
    acm = sorted(carpeta.glob(f"*_ABI-L2-ACM?-*_s{instante}*.nc"))
    if faltan or not acm:
        raise FileNotFoundError(f"{instante}: faltan {', '.join(faltan + ([] if acm else ['ACM']))}")

    with xr.open_dataset(archivos["C07"]) as ds:
        g = ds["goes_imager_projection"]
        h = float(g.perspective_point_height)
        crs_goes = CRS.from_proj4(f"+proj=geos +h={h} +lon_0={g.longitude_of_projection_origin} "
                                  f"+sweep={g.sweep_angle_axis} +a={g.semi_major_axis} "
                                  f"+b={g.semi_minor_axis} +units=m +no_defs")
        x = ds["x"].values.astype(np.float64) * h
        y = ds["y"].values.astype(np.float64) * h
        inicio = detect_ash.parse_fecha(ds.attrs["time_coverage_start"]).replace(tzinfo=detect_ash.utc)

    # Recorte en la proyección GOES con margen, para que la reproyección no deje huecos.
    b = plantilla["bounds"]
    a_goes = Transformer.from_crs("EPSG:4326", crs_goes, always_xy=True)
    x0, y0, x1, y1 = detect_ash.limites_goes([[b.left, b.bottom], [b.right, b.top]], a_goes, margen=0.1)
    cols = np.where((x >= x0) & (x <= x1))[0]
    filas = np.where((y >= y0) & (y <= y1))[0]
    xs, ys = slice(cols[0], cols[-1] + 1), slice(filas[0], filas[-1] + 1)

    c04, c07, c11, c13, c14, c15 = (lee_cmi(archivos[p], ys, xs) for p in ("C04", "C07", "C11", "C13", "C14", "C15"))
    with xr.open_dataset(archivos["ACTP"]) as ds:
        fase = ds["Phase"].data[ys, xs]
    with xr.open_dataset(acm[-1]) as ds:
        if mascara == "bcm":
            nube = ds["BCM"].data[ys, xs]
        elif mascara == "acm3":
            nube = (ds["ACM"].data[ys, xs] == 3).astype(np.uint8)
        else:
            nube = np.zeros(c04.shape, np.uint8)

    lon, lat = Transformer.from_crs(crs_goes, "EPSG:4326", always_xy=True).transform(*np.meshgrid(x[xs], y[ys]))
    validos = (np.isfinite(c04) & np.isfinite(c07) & np.isfinite(c11) & np.isfinite(c13) & np.isfinite(c15)
               & np.isfinite(fase) & np.isfinite(lon) & np.isfinite(lat))
    sza = detect_ash.get_sun_zenith_angle(lat, lon, inicio, eph, ts)

    ts_py = reglas_terascan(c04, c07, c11, c13, c14, c15, nube, sza, r04_min)
    ts_py[~(validos & np.isfinite(c14))] = SIN_DATOS
    nuestra = detect_ash.classify_ash(c04, c07, c11, c13, c15, fase, sza, validos)

    res = abs(x[1] - x[0])
    origen = rasterio.transform.from_origin(x[xs][0] - res / 2, y[ys][0] + res / 2, res, res)
    for nombre, datos in (("terascan_py", ts_py), ("nuestra", nuestra)):
        destino = np.full(plantilla["shape"], SIN_DATOS, np.uint8)
        reproject(datos, destino, src_transform=origen, src_crs=crs_goes, dst_transform=plantilla["transform"],
                  dst_crs="EPSG:4326", resampling=Resampling.nearest, src_nodata=SIN_DATOS, dst_nodata=SIN_DATOS)
        carpeta_salida = salida / nombre
        carpeta_salida.mkdir(parents=True, exist_ok=True)
        with rasterio.open(carpeta_salida / f"ceniza_{instante}.tif", "w", driver="GTiff", height=destino.shape[0],
                           width=destino.shape[1], count=1, dtype="uint8", crs="EPSG:4326",
                           transform=plantilla["transform"], nodata=SIN_DATOS, compress="LZW") as d:
            d.write(destino, 1)
            if nombre == "terascan_py":
                d.update_tags(reglas=nombre, r04_min=str(r04_min), nube=mascara)
            else:
                d.update_tags(reglas=nombre)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--l2", type=Path, required=True, help="carpeta con los NetCDF L2 (incluye C14 y ACM)")
    ap.add_argument("--plantilla", type=Path, required=True, help="un GeoTIFF de TeraScan: de él se toma la rejilla")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--r04", type=float, default=0.3, help="umbral de R04 de TeraScan (0.3; 0.003 si es porcentaje)")
    ap.add_argument("--nube", choices=["bcm", "acm3", "ninguna"], default="bcm",
                    help="máscara de nubes de CSPP en lugar de la de TeraScan (por omisión, bcm)")
    ap.add_argument("instantes", nargs="+")
    args = ap.parse_args()

    instantes = []
    for i in args.instantes:
        instantes += Path(i[1:]).read_text().split() if i.startswith("@") else [i]

    with rasterio.open(args.plantilla) as d:
        plantilla = {"bounds": d.bounds, "shape": d.shape, "transform": d.transform}
    eph, ts = detect_ash.carga_efemerides()
    for n, inst in enumerate(instantes, 1):
        try:
            procesa(args.l2, inst, plantilla, args.salida, eph, ts, args.r04, args.nube)
            print(f"[{n}/{len(instantes)}] {inst}")
        except Exception as e:  # que un instante malo no detenga el resto
            print(f"[{n}/{len(instantes)}] {inst}: ERROR {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
