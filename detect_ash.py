#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import dataclasses
import datetime
import hashlib
import logging
import tomllib
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from affine import Affine
from dateutil.parser import parse as parse_fecha
from pyproj import CRS, Transformer
from rasterio.warp import Resampling
from scipy import ndimage
from skyfield.api import Loader, utc
import os
import re
import sys

# Configurar logger
logger = logging.getLogger(__name__)

# Códigos de salida de lanot-detect-ash (los usa operacion/procesa_ceniza.sh).
SALIDA_OK = 0
SALIDA_ERROR = 1        # error al procesar algún instante
SALIDA_USO = 2          # argumentos inválidos (el mismo código que usa argparse)
SALIDA_SIN_DATOS = 3    # faltan archivos para algún instante


# Rutas. Se pueden cambiar con variables de entorno.
#   LANOT_CENIZA_L2     carpeta de datos L2 por omisión (también con --path)
#   LANOT_SKYFIELD_DIR  carpeta con de421.bsp. Si no se da: la compartida de LANOT si
#                       tiene el archivo; si no, ~/.cache/lanot_ceniza, donde Skyfield lo
#                       descarga la primera vez (~17 MB).
l2_path = Path(os.environ.get("LANOT_CENIZA_L2", "/data/ceniza/l2"))
SKYFIELD_LANOT = Path("/usr/local/share/lanot/skyfield")


def carpeta_skyfield():
    """Carpeta de las efemérides de Skyfield (ver LANOT_SKYFIELD_DIR arriba)."""
    if os.environ.get("LANOT_SKYFIELD_DIR"):
        return Path(os.environ["LANOT_SKYFIELD_DIR"])
    if (SKYFIELD_LANOT / "de421.bsp").is_file():
        return SKYFIELD_LANOT
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "lanot_ceniza"


def carga_efemerides():
    """Efemérides DE421 y escala de tiempo de Skyfield."""
    carpeta = carpeta_skyfield()
    if not (carpeta / "de421.bsp").is_file():
        logger.info(f"No está {carpeta / 'de421.bsp'}; Skyfield lo descargará (~17 MB).")
        carpeta.mkdir(parents=True, exist_ok=True)
    loader = Loader(str(carpeta), verbose=False)
    return loader("de421.bsp"), loader.timescale()

# Regiones predefinidas para recorte, como puntos [lon, lat]: 2 puntos son esquinas opuestas
# de un rectángulo (aquí, suroeste y noreste); 3 o más, los vértices de un polígono.
CLIP_REGIONS = {
    'centromex': [[-107.2319400, 14.9386282], [-93.8363933, 22.7180385]],
    'popocatepetl': [[-100.2622042, 18.2893953], [-96.8495200, 20.5800993]],
    'ashpaper': [[-102.418, 17.547], [-96.294, 22.474]],
}

# Valores de la clasificación en el GeoTIFF: (color RGB, nombre en la leyenda, alfa en QGIS).
# 4 y 5 los usaban versiones anteriores (TeraScan; ver ash.cpt) y quedan reservados: no se
# producen, pero conservan su color por si vuelven.
SIN_DATOS = 255
CLASES = {
    0: ((0, 0, 0), "sin ceniza", 0),
    1: ((255, 0, 0), "ceniza confirmada", 255),
    2: ((255, 165, 0), "probabilidad alta", 255),
    3: ((255, 255, 0), "probabilidad baja", 255),
    4: ((0, 255, 0), "reservado: HAP sobre agua líquida", 255),
    5: ((0, 0, 255), "reservado: LAP sobre agua líquida", 255),
    6: ((160, 160, 160), "nube: ceniza no detectable", 255),
}
CLASES_EN_LEYENDA = [0, 1, 2, 3, 6]
NUBE = 6
ASH_COLORS = {v: rgb for v, (rgb, _, _) in CLASES.items()} | {SIN_DATOS: (0, 0, 0)}


def estilo_qml():
    """
    Estilo de QGIS para el GeoTIFF de ceniza. La paleta de un TIFF no guarda transparencia,
    así que sin este estilo QGIS dibuja el 0 (sin ceniza) en negro; con él, el 0 queda
    transparente y la leyenda muestra solo las clases en uso. QGIS lo carga solo si está
    junto al GeoTIFF con el mismo nombre (ceniza_X.tif y ceniza_X.qml).
    """
    entradas = "\n".join(
        f'        <paletteEntry value="{v}" color="#{r:02x}{g:02x}{b:02x}" alpha="{a}" label="{nombre}"/>'
        for v in CLASES_EN_LEYENDA for (r, g, b), nombre, a in [CLASES[v]])
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.44" styleCategories="Symbology">
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="1" alphaBand="-1">
      <colorPalette>
{entradas}
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
"""


# Nombres que acepta --clip: cada región, y la misma con 'geo' al final para reproyectar a lat/lon.
NOMBRES_CLIP = [n + sufijo for n in CLIP_REGIONS for sufijo in ("", "geo")]


def vertices_region(puntos):
    """
    Vértices [lon, lat] del contorno de una región. Con 2 puntos (esquinas opuestas) da las
    4 esquinas del rectángulo; con 3 o más, los mismos puntos.
    """
    v = np.asarray(puntos, dtype=np.float64)
    if v.ndim != 2 or v.shape[1] != 2 or len(v) < 2:
        raise ValueError(f"Una región es una lista de 2 o más puntos [lon, lat]; se recibió {puntos}")
    if not np.isfinite(v).all():
        raise ValueError(f"Región con coordenadas no finitas: {puntos}")
    if len(v) == 2:
        (lon0, lon1), (lat0, lat1) = np.sort(v[:, 0]), np.sort(v[:, 1])
        if lon0 == lon1 or lat0 == lat1:
            raise ValueError(f"Las dos esquinas de la región no forman un rectángulo: {puntos}")
        v = np.array([[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1]])
    return v


def limites_region(puntos):
    """Rectángulo (lon_min, lat_min, lon_max, lat_max) que contiene a la región."""
    v = vertices_region(puntos)
    return v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max()


def densifica(vertices, paso=0.05):
    """
    Puntos a lo largo de los bordes del contorno cerrado, separados a lo más `paso` grados.
    Los bordes son rectos en lat/lon; en la proyección GOES se curvan, así que no basta con
    transformar los vértices.
    """
    a = np.asarray(vertices, dtype=np.float64)
    b = np.roll(a, -1, axis=0)
    tramos = []
    for p, q in zip(a, b):
        n = max(1, int(np.ceil(np.abs(q - p).max() / paso)))
        t = np.arange(n)[:, None] / n
        tramos.append(p + t * (q - p))
    return np.concatenate(tramos)


def limites_goes(puntos, transformer, margen=0.0):
    """
    Rectángulo (x_min, y_min, x_max, y_max), en la proyección GOES, que contiene a la región.
    Transforma los bordes densificados, no solo dos esquinas. Con `margen` > 0 también incluye
    el rectángulo lat/lon de la región agrandado esa fracción por lado (lo que salga del
    disco visible en ese margen se ignora). Error si la región sale del disco visible.
    """
    v = vertices_region(puntos)
    x, y = transformer.transform(*densifica(v).T)
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError(f"La región sale del disco visible del satélite: {puntos}")
    if margen > 0:
        lon_min, lat_min, lon_max, lat_max = limites_region(puntos)
        dlon, dlat = (lon_max - lon_min) * margen, (lat_max - lat_min) * margen
        exp = [[lon_min - dlon, lat_min - dlat], [lon_max + dlon, lat_max + dlat]]
        xm, ym = transformer.transform(*densifica(vertices_region(exp)).T)
        ok = np.isfinite(xm) & np.isfinite(ym)
        x, y = np.concatenate([x, xm[ok]]), np.concatenate([y, ym[ok]])
    return x.min(), y.min(), x.max(), y.max()
 

# --- Perfiles de umbrales (perfiles/*.toml; diseño en doc/2026-10-21_perfiles_umbrales.md) ---

CARPETA_PERFILES = Path(__file__).resolve().parent / "perfiles"
PERFIL_POR_OMISION = "popocatepetl"
CLASES_PERFIL = {"sin_ceniza": 0, "ca": 1, "hap": 2, "lap": 3}
# Fases del producto ACTP, en el orden de sus valores (0 a 5).
FASES = ("despejado", "agua", "superenfriada", "mixta", "hielo", "desconocida")
BLOQUES = ("noche", "crepusculo", "dia")


@dataclasses.dataclass(frozen=True)
class Prueba:
    """Prueba de umbrales de una clase en un bloque de iluminación."""
    dt1_max: float                    # ΔT1 < dt1_max
    dt2_min: float                    # ΔT2 > dt2_min
    dt3_min: float                    # ΔT3 > dt3_min
    r137_min: float | None = None     # R1.37 > r137_min, si se da
    bt13_max: float | None = None     # BT13 < bt13_max, si se da


@dataclasses.dataclass(frozen=True)
class Perfil:
    """Umbrales de un volcán, leídos de un TOML con carga_perfil o perfil_de_dict."""
    nombre: str
    descripcion: str
    estado: str                       # "operacion" o "ejemplo" (sin calibrar)
    dia_max: float                    # día: SZA < dia_max
    noche_min: float                  # noche: SZA > noche_min
    kernel_tamano: int
    kernel_umbral: float
    kernel_ca_dt1_max: float
    kernel_hap_dt1_max: float
    pruebas: tuple                    # ((bloque, clase), Prueba) para noche/crepusculo/dia × ca/hap
    hap_dt2_min: float
    lap_dt2_min: float
    dt3_ca_hap_max: float
    dt3_lap_max: float
    tabla_fase: tuple                 # tabla_fase[clase][fase] -> clase; clase 0 a 3, fase 0 a 5
    fases_nube: tuple                 # fases (números) bajo las que "sin ceniza" pasa a NUBE
    dominio: str                      # "C" (CONUS) o "F" (disco completo)
    volcan: tuple                     # (lon, lat)
    region: str | tuple               # nombre de CLIP_REGIONS o puntos ((lon, lat), ...)
    sha256: str = ""                  # del archivo; vacío si no viene de un archivo

    def prueba(self, bloque, clase):
        return dict(self.pruebas)[(bloque, clase)]


def _claves(d, obligatorias, opcionales=(), donde=""):
    if not isinstance(d, dict):
        raise ValueError(f"perfil, {donde}: se esperaba una tabla")
    faltan = set(obligatorias) - set(d)
    sobran = set(d) - set(obligatorias) - set(opcionales)
    if faltan:
        raise ValueError(f"perfil, {donde}: faltan {sorted(faltan)}")
    if sobran:
        raise ValueError(f"perfil, {donde}: claves desconocidas {sorted(sobran)}")


def _numero(v, donde):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"perfil, {donde}: se esperaba un número, no {v!r}")
    return float(v)


def _dentro(lon, lat, puntos):
    """Punto en rectángulo (2 puntos) o en polígono (3 o más; regla de par e impar)."""
    v = vertices_region(puntos)
    adentro = False
    for (x0, y0), (x1, y1) in zip(v, np.roll(v, -1, axis=0)):
        if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
            adentro = not adentro
    return adentro


def perfil_de_dict(p, sha256=""):
    """Valida un perfil ya leído del TOML y lo convierte en Perfil. Error (ValueError) si
    falta o sobra una clave, o si un valor no tiene sentido."""
    _claves(p, ["perfil", "iluminacion", "kernel", *BLOQUES, "refinamiento_hap", "filtro_dt3",
                "fase", "region"], donde="raíz")
    meta = p["perfil"]
    _claves(meta, ["nombre", "descripcion", "estado"], donde="perfil")
    if meta["estado"] not in ("operacion", "ejemplo"):
        raise ValueError("perfil, perfil.estado: 'operacion' o 'ejemplo'")

    il = p["iluminacion"]
    _claves(il, ["dia_max", "noche_min"], donde="iluminacion")
    dia_max, noche_min = _numero(il["dia_max"], "dia_max"), _numero(il["noche_min"], "noche_min")
    if not 0 < dia_max < noche_min < 180:
        raise ValueError("perfil, iluminacion: debe cumplirse 0 < dia_max < noche_min < 180")

    k = p["kernel"]
    _claves(k, ["tamano", "umbral", "ca_dt1_max", "hap_dt1_max"], donde="kernel")
    if isinstance(k["tamano"], bool) or not isinstance(k["tamano"], int) or k["tamano"] < 3 or k["tamano"] % 2 == 0:
        raise ValueError("perfil, kernel.tamano: entero impar, 3 o más")

    pruebas = []
    for b in BLOQUES:
        _claves(p[b], ["ca", "hap"], donde=b)
        for c in ("ca", "hap"):
            u = p[b][c]
            _claves(u, ["dt1_max", "dt2_min", "dt3_min"], ["r137_min", "bt13_max"], donde=f"{b}.{c}")
            pruebas.append(((b, c), Prueba(**{n: _numero(v, f"{b}.{c}.{n}") for n, v in u.items()})))

    r = p["refinamiento_hap"]
    _claves(r, ["hap_dt2_min", "lap_dt2_min"], donde="refinamiento_hap")
    hap_dt2, lap_dt2 = _numero(r["hap_dt2_min"], "hap_dt2_min"), _numero(r["lap_dt2_min"], "lap_dt2_min")
    if lap_dt2 > hap_dt2:
        raise ValueError("perfil, refinamiento_hap: lap_dt2_min no puede ser mayor que hap_dt2_min")
    f3 = p["filtro_dt3"]
    _claves(f3, ["ca_hap_max", "lap_max"], donde="filtro_dt3")

    f = p["fase"]
    _claves(f, ["ca", "hap", "lap", "nube"], donde="fase")
    tabla = [tuple([0] * len(FASES))]  # sin ceniza se queda sin ceniza
    for c in ("ca", "hap", "lap"):
        _claves(f[c], FASES, donde=f"fase.{c}")
        malas = set(f[c].values()) - set(CLASES_PERFIL)
        if malas:
            raise ValueError(f"perfil, fase.{c}: {sorted(malas)} no es clase; solo {sorted(CLASES_PERFIL)}")
        tabla.append(tuple(CLASES_PERFIL[f[c][fase]] for fase in FASES))
    if not isinstance(f["nube"], list) or not set(f["nube"]) <= set(FASES):
        raise ValueError(f"perfil, fase.nube: lista de fases de {list(FASES)}")

    reg = p["region"]
    _claves(reg, ["dominio", "volcan"], ["recorte", "puntos"], donde="region")
    if reg["dominio"] not in ("C", "F"):
        raise ValueError("perfil, region.dominio: 'C' (CONUS) o 'F' (disco completo)")
    _claves(reg["volcan"], ["lat", "lon"], donde="region.volcan")
    volcan = (_numero(reg["volcan"]["lon"], "volcan.lon"), _numero(reg["volcan"]["lat"], "volcan.lat"))
    if ("recorte" in reg) == ("puntos" in reg):
        raise ValueError("perfil, region: recorte o puntos, uno de los dos")
    if "recorte" in reg:
        if reg["recorte"] not in CLIP_REGIONS:
            raise ValueError(f"perfil, region.recorte: {reg['recorte']!r} no es una de {list(CLIP_REGIONS)}")
        region, puntos = reg["recorte"], CLIP_REGIONS[reg["recorte"]]
    else:
        puntos = reg["puntos"]
        vertices_region(puntos)
        if not all(-180 <= q[0] <= 180 and -90 <= q[1] <= 90 for q in puntos):
            raise ValueError("perfil, region.puntos: cada punto es [lon, lat]")
        region = tuple((float(q[0]), float(q[1])) for q in puntos)
    if not _dentro(*volcan, puntos):
        raise ValueError("perfil, region: el volcán queda fuera de la región")

    return Perfil(
        nombre=meta["nombre"], descripcion=meta["descripcion"], estado=meta["estado"],
        dia_max=dia_max, noche_min=noche_min,
        kernel_tamano=k["tamano"], kernel_umbral=_numero(k["umbral"], "kernel.umbral"),
        kernel_ca_dt1_max=_numero(k["ca_dt1_max"], "kernel.ca_dt1_max"),
        kernel_hap_dt1_max=_numero(k["hap_dt1_max"], "kernel.hap_dt1_max"),
        pruebas=tuple(pruebas), hap_dt2_min=hap_dt2, lap_dt2_min=lap_dt2,
        dt3_ca_hap_max=_numero(f3["ca_hap_max"], "filtro_dt3.ca_hap_max"),
        dt3_lap_max=_numero(f3["lap_max"], "filtro_dt3.lap_max"),
        tabla_fase=tuple(tabla), fases_nube=tuple(FASES.index(x) for x in f["nube"]),
        dominio=reg["dominio"], volcan=volcan, region=region, sha256=sha256)


def carga_perfil(nombre_o_ruta=PERFIL_POR_OMISION):
    """
    Lee y valida un perfil. Un nombre (sin '/' ni '.toml') se busca en la carpeta perfiles/
    que viene con el programa; si no, es la ruta de un archivo TOML.
    """
    texto = str(nombre_o_ruta)
    if "/" in texto or texto.endswith(".toml"):
        ruta = Path(texto)
    else:
        ruta = CARPETA_PERFILES / f"{texto}.toml"
        if not ruta.is_file():
            hay = sorted(q.stem for q in CARPETA_PERFILES.glob("*.toml"))
            raise ValueError(f"No hay perfil '{texto}'. Perfiles disponibles: {hay}")
    datos = ruta.read_bytes()
    try:
        p = tomllib.loads(datos.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"{ruta}: no es un TOML válido: {e}") from e
    try:
        return perfil_de_dict(p, sha256=hashlib.sha256(datos).hexdigest())
    except ValueError as e:
        raise ValueError(f"{ruta}: {e}") from e


_perfil_por_omision = None


def perfil_por_omision():
    """El perfil del Popocatépetl, leído una sola vez."""
    global _perfil_por_omision
    if _perfil_por_omision is None:
        _perfil_por_omision = carga_perfil(PERFIL_POR_OMISION)
    return _perfil_por_omision


def get_moment(is_conus=True):
    """
    Instante (YYYYjjjHHMM) del escaneo más reciente que ya empezó:
    - CONUS: minutos terminados en 1 o 6;
    - disco completo: minutos múltiplos de 10.
    """
    t = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
    if is_conus:
        t -= datetime.timedelta(minutes=1)
        t = t.replace(minute=t.minute // 5 * 5) + datetime.timedelta(minutes=1)
    else:
        t = t.replace(minute=t.minute // 10 * 10)
    return t.strftime("%Y%j%H%M")


def normalize_moment(moment):
    """
    Normaliza el instante al formato juliano YYYYjjjHHMM.
    
    Detecta automáticamente si el instante está en formato:
    - Juliano (11 dígitos): YYYYjjjHHMM - lo retorna sin cambios
    - Gregoriano (12 dígitos): YYYYMMDDhhmm - lo convierte a juliano
    
    Args:
        moment (str): Momento en formato juliano u gregoriano
        
    Returns:
        tuple: (moment_julian, year, month, day) donde:
            - moment_julian es el instante en formato YYYYjjjHHMM
            - year, month, day son strings para construir rutas YYYY/MM/DD
    """
    if len(moment) == 12:
        # Formato gregoriano: YYYYMMDDhhmm
        year = moment[:4]
        month = moment[4:6]
        day = moment[6:8]
        hhmm = moment[8:12]
        
        # Convertir a día juliano
        date_obj = datetime.datetime.strptime(f"{year}{month}{day}", "%Y%m%d")
        julian_day = f"{date_obj.timetuple().tm_yday:03d}"
        
        # Construir instante en formato juliano
        moment_julian = f"{year}{julian_day}{hhmm}"
        
        logger.debug(f"Momento {moment} (gregoriano) normalizado a {moment_julian} (juliano).")
        return moment_julian, year, month, day
        
    elif len(moment) == 11:
        # Formato juliano: YYYYjjjHHMM
        year = moment[:4]
        julian_day = moment[4:7]
        
        # Convertir día juliano a mes/día
        date_obj = datetime.datetime.strptime(f"{year}{julian_day}", "%Y%j")
        month = f"{date_obj.month:02d}"
        day = f"{date_obj.day:02d}"
        
        logger.debug(f"Momento {moment} (juliano) confirmado.")
        return moment, year, month, day
    else:
        raise ValueError(f"Formato de instante inválido: '{moment}'. Debe tener 11 dígitos (YYYYjjjHHMM) o 12 dígitos (YYYYMMDDhhmm)")


def parse_moment_string(moment_str, interval_minutes=5):
    """
    Parsea un string de instante, que puede ser un único instante o un rango.

    Formatos soportados:
    - Momento único (Gregoriano): 'YYYYMMDDHHMM' (12 dígitos)
    - Momento único (Juliano): 'YYYYjjjHHMM' (11 dígitos)
    - Rango (Gregoriano): 'YYYYMMDDHHmm-HHmm' (ej. '202402270800-1430')
    - Rango (Juliano): 'YYYYjjjHHmm-HHmm' (ej. '20240580411-0426')

    Args:
        moment_str (str): El string de instante a parsear.
        interval_minutes (int): El incremento en minutos para generar instantes en un rango (por defecto 5 min).

    Returns:
        list[tuple]: Una lista de tuplas. Cada tupla contiene:
                     (moment_julian, year, month, day).
                     Esto evita recalcular la información de fecha repetidamente.
    """
    if '-' in moment_str:
        logger.info(f"Detectado rango de instantes: {moment_str}")
        
        # Determinar si es formato gregoriano (17 chars) o juliano (16 chars)
        if len(moment_str) == 17:  # Formato YYYYMMDDHHmm-HHmm (gregoriano)
            base_date_str = moment_str[:8]
            start_time_str = moment_str[8:12]
            end_time_str = moment_str[13:]

            try:
                start_dt = datetime.datetime.strptime(f"{base_date_str}{start_time_str}", "%Y%m%d%H%M").replace(tzinfo=utc)
                end_dt = datetime.datetime.strptime(f"{base_date_str}{end_time_str}", "%Y%m%d%H%M").replace(tzinfo=utc)
            except ValueError as e:
                raise ValueError(f"Formato de rango gregoriano inválido: {moment_str}. Error: {e}")
                
        elif len(moment_str) == 16:  # Formato YYYYjjjHHmm-HHmm (juliano)
            year = moment_str[:4]
            julian_day = moment_str[4:7]
            start_time_str = moment_str[7:11]
            end_time_str = moment_str[12:]
            
            try:
                # Convertir día juliano a fecha gregoriana
                base_dt = datetime.datetime.strptime(f"{year}{julian_day}", "%Y%j")
                start_dt = base_dt.replace(hour=int(start_time_str[:2]), minute=int(start_time_str[2:]), tzinfo=utc)
                end_dt = base_dt.replace(hour=int(end_time_str[:2]), minute=int(end_time_str[2:]), tzinfo=utc)
            except ValueError as e:
                raise ValueError(f"Formato de rango juliano inválido: {moment_str}. Error: {e}")
        else:
            raise ValueError(f"Longitud de rango no reconocida: '{moment_str}' (esperado 16 o 17 caracteres)")

        if start_dt > end_dt:
            raise ValueError("En el rango, la hora de inicio debe ser anterior a la hora de fin.")

        moments = []
        current_dt = start_dt
        while current_dt <= end_dt:
            # Formatear a Juliano YYYYjjjHHMM
            year = current_dt.strftime("%Y")
            month = current_dt.strftime("%m")
            day = current_dt.strftime("%d")
            julian_moment = f"{year}{current_dt.strftime('%j')}{current_dt.strftime('%H%M')}"
            moments.append((julian_moment, year, month, day))
            current_dt += datetime.timedelta(minutes=interval_minutes)
        
        logger.info(f"Rango expandido a {len(moments)} instantes (intervalo de {interval_minutes} min).")
        return moments

    elif len(moment_str) == 11 or len(moment_str) == 12:
        # Es un instante único, lo normalizamos y lo devolvemos en una lista con una tupla
        return [normalize_moment(moment_str)]
    else:
        raise ValueError(f"Formato de instante o rango no reconocido: '{moment_str}'")


def group_and_report_failures(failed_info, interval_minutes=5, verbose=False):
    """
    Agrupa instantes fallidos consecutivos en rangos y los imprime junto con las rutas.
    """
    if not failed_info:
        return

    logger.warning(f"\n--- Resumen de fallas ---\nNo se encontraron datos completos para {len(failed_info)} instantes.")

    # Extraer solo los instantes para el agrupamiento, manteniendo la referencia de las rutas
    failed_moments = sorted([info[0] for info in failed_info])
    moment_to_path = {info[0]: info[1] for info in failed_info}
    
    groups = []
    if len(failed_moments) > 0:
        start_of_group = failed_moments[0]
        for i in range(1, len(failed_moments)):
            # Convertir a datetime para comparar
            prev_dt = datetime.datetime.strptime(failed_moments[i-1], "%Y%j%H%M")
            curr_dt = datetime.datetime.strptime(failed_moments[i], "%Y%j%H%M")
            
            # Si el instante actual no es consecutivo al anterior, cerramos el grupo
            if (curr_dt - prev_dt) > datetime.timedelta(minutes=interval_minutes):
                groups.append((start_of_group, failed_moments[i-1]))
                start_of_group = failed_moments[i]
        # Añadir el último grupo
        groups.append((start_of_group, failed_moments[-1]))

    for start, end in groups:
        if start != end:
            logger.warning(f"  - Intervalo fallido: {start} a {end}")
        else:
            logger.warning(f"  - Instante fallido: {start}")
            
        if verbose:
            path_searched = moment_to_path[start]
            logger.warning(f"    Ruta buscada: {path_searched}")


def detect_goes_minute_offset(data_path, first_moment_info, use_date_tree=False, window_minutes=4):
    """
    Detecta el desfase real en minutos de los archivos GOES respecto a los instantes
    nominales generados (p. ej. :01/:06 en lugar de :00/:05, o :02/:07).

    Escanea el directorio de datos buscando cualquier archivo .nc cuya marca de
    tiempo caiga dentro de una ventana de ±window_minutes alrededor del primer
    instante del rango. El primer offset que produce una coincidencia se aplica
    a todos los demás instantes del rango.

    Args:
        data_path (Path): Ruta base de datos L2.
        first_moment_info (tuple): Primer (moment_julian, year, month, day) del rango.
        use_date_tree (bool): Si True, usa estructura YYYY/MM/DD para construir la ruta.
        window_minutes (int): Ventana de búsqueda en minutos alrededor del instante nominal.

    Returns:
        int: Desfase detectado en minutos (0 si no se detecta ninguno o si hay coincidencia exacta).
    """
    moment_julian, year, month, day = first_moment_info

    search_path = (data_path / year / month / day) if use_date_tree else data_path
    if not search_path.is_dir():
        return 0

    base_dt = datetime.datetime.strptime(moment_julian, "%Y%j%H%M")

    # Probar desde offset 0 hacia adelante, luego hacia atrás, para no asumir dirección
    offsets_to_try = sorted(range(-window_minutes, window_minutes + 1), key=abs)
    for offset in offsets_to_try:
        candidate_dt = base_dt + datetime.timedelta(minutes=offset)
        candidate_moment = (
            f"{candidate_dt.strftime('%Y')}"
            f"{candidate_dt.strftime('%j')}"
            f"{candidate_dt.strftime('%H%M')}"
        )
        if any(search_path.glob(f"*s{candidate_moment}*.nc")):
            if offset != 0:
                logger.info(
                    f"Desfase GOES detectado: {offset:+d} min "
                    f"(nominal {moment_julian} → archivo en {candidate_moment}). "
                    f"Ajustando todos los instantes del rango."
                )
            else:
                logger.debug("Sin desfase: archivos coinciden con el instante nominal.")
            return offset

    logger.debug(
        f"No se encontró ningún archivo cerca de {moment_julian} "
        f"(ventana ±{window_minutes} min). Sin ajuste de desfase."
    )
    return 0


# Productos L2 que usa el algoritmo.
# C14 (11.2 µm) no interviene en la clasificación y dejó de leerse en octubre de 2026 (P9).
PRODUCTOS = ["ACTP", "C04", "C07", "C11", "C13", "C15"]

# Nombre de un archivo L2 de ABI, por ejemplo:
#   OR_ABI-L2-CMIPC-M6C07_G16_s20240580406173_e20240580408558_c20240580409038.nc
#   CG_ABI-L2-ACTPC-M3_G16_s20190601332133_e20190601334517_c20252920848220.nc
# origen: OR (NOAA) o CG (CSPP Geo, local); dominio: C (CONUS), F (disco completo) o
# P (PACUS). Deja fuera L1b, MCMIP (multibanda), mesoescala (M1/M2) y otros productos.
_PATRON_L2 = re.compile(
    r"^(?P<origen>OR|CG)_ABI-L2-(?P<prod>CMIP|ACTP)(?P<dom>[CFP])-M(?P<modo>\d)(?:C(?P<banda>\d{2}))?"
    r"_(?P<sat>G\d{2})_s(?P<s>\d{14})_e\d{14}_c(?P<c>\d{14})\.nc$")


def _producto(m):
    """Nombre del producto ('ACTP', 'C07', ...) de un nombre de archivo ya reconocido."""
    if m["prod"] == "ACTP":
        return None if m["banda"] else "ACTP"
    return f"C{m['banda']}" if m["banda"] else None


def busca_archivos(carpeta, instante, productos=PRODUCTOS):
    """
    Busca en `carpeta` los archivos L2 de un instante (YYYYjjjHHMM).

    Todos deben ser del mismo satélite y dominio. Si un producto está repetido, prefiere
    CG_ (procesado en LANOT con CSPP Geo) sobre OR_, y entre iguales el de fecha de
    creación (_c) más reciente.

    Returns:
        (dict, list): {producto: Path} con lo encontrado y la lista de productos que faltan.

    Raises:
        ValueError: si hay juegos completos de más de un satélite o dominio.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        logger.debug(f"No existe la carpeta {carpeta}")
        return {}, list(productos)

    grupos = {}  # (satélite, dominio) -> producto -> [(es_cg, creación, ruta)]
    for ruta in carpeta.glob(f"*_s{instante}*.nc"):
        m = _PATRON_L2.match(ruta.name)
        prod = _producto(m) if m else None
        if prod in productos:
            grupos.setdefault((m["sat"], m["dom"]), {}).setdefault(prod, []).append(
                (m["origen"] == "CG", m["c"], ruta))

    completos = sorted(k for k, g in grupos.items() if all(p in g for p in productos))
    if len(completos) > 1:
        raise ValueError(f"Instante {instante}: hay juegos completos de varios satélites o dominios en "
                         f"{carpeta}: {', '.join(f'{sat} {dom}' for sat, dom in completos)}")
    if completos:
        grupo = grupos[completos[0]]
    elif grupos:
        grupo = max(grupos.values(), key=len)  # el más completo, para reportar lo que falta
    else:
        grupo = {}

    elegidos = {p: max(candidatos)[2] for p, candidatos in grupo.items()}
    for p, candidatos in grupo.items():
        if len(candidatos) > 1:
            logger.debug(f"{p}: {len(candidatos)} archivos, se usa {elegidos[p].name}")
    return elegidos, [p for p in productos if p not in elegidos]


def carpeta_del_instante(data_path, instant_info, use_date_tree=False):
    """Carpeta donde están los archivos de un instante: data_path o data_path/AAAA/MM/DD."""
    _, year, month, day = instant_info
    return Path(data_path) / year / month / day if use_date_tree else Path(data_path)


def get_sun_zenith_angle(lat_array, lon_array, image_time_dt, eph, ts):
    """
    Calcula el ángulo cenital solar para cada punto de un arreglo lat/lon.
    
    Skyfield no maneja bien arrays grandes, así que calculamos la posición
    del Sol (RA/Dec) una sola vez y luego usamos geometría esférica para
    calcular el ángulo cenital en cada píxel.
    """
    # Definir los objetos Sol y Tierra desde las efemérides
    sun = eph['sun']
    earth = eph['earth']
    
    image_time_sky = ts.from_datetime(image_time_dt)
    
    # --- 2. Calcular la posición del Sol (una sola vez) ---
    # Posición aparente del Sol vista desde el centro de la Tierra, con RA/Dec del
    # equinoccio de la fecha: el mismo marco que el tiempo sidéreo aparente (gast) que se
    # usa abajo. Hasta octubre de 2026 se usaba radec() a secas, que da coordenadas J2000;
    # al combinarlas con gast faltaba la precesión desde 2000 y el SZA salía con un error
    # de 0.2-0.4° (creciente con los años). Con el marco correcto el error es ~0.003°
    # (lo que queda es la paralaje y la diferencia entre latitud geodésica y geocéntrica).
    aparente = earth.at(image_time_sky).observe(sun).apparent()
    ra, dec, distance = aparente.radec(epoch='date')
    
    # Convertir RA/Dec a radianes
    sun_ra_rad = ra.radians
    sun_dec_rad = dec.radians
    
    # --- 3. Calcular el Ángulo Horario Local para cada punto ---
    # El Ángulo Horario Local (LHA) depende de la longitud y el tiempo
    
    # Calcular el Tiempo Sideral de Greenwich (GST) en radianes
    gst = image_time_sky.gast * 15.0 * np.pi / 180.0  # gast está en horas, convertimos a radianes
    
    # Convertir arrays de lat/lon a radianes
    lat_rad = np.deg2rad(lat_array)
    lon_rad = np.deg2rad(lon_array)
    
    # Calcular el Ángulo Horario Local (LHA) = GST + Longitud - RA
    lha = gst + lon_rad - sun_ra_rad
    
    # --- 4. Calcular el Ángulo Cenital Solar usando geometría esférica ---
    # cos(SZA) = sin(lat) * sin(dec) + cos(lat) * cos(dec) * cos(LHA)
    cos_sza = (np.sin(lat_rad) * np.sin(sun_dec_rad) + 
               np.cos(lat_rad) * np.cos(sun_dec_rad) * np.cos(lha))
    
    # Limitar valores al rango [-1, 1] para evitar errores numéricos
    cos_sza = np.clip(cos_sza, -1.0, 1.0)
    
    # Calcular el ángulo cenital en grados
    sza_array = np.rad2deg(np.arccos(cos_sza))
    
    # ¡Listo! sza_array tiene la misma forma que lat_array y lon_array
    logger.debug("\n--- Resultados ---")
    logger.debug(f"Forma del array SZA: {sza_array.shape}")
    logger.debug(f"SZA (min): {np.nanmin(sza_array):.2f}°")
    logger.debug(f"SZA (max): {np.nanmax(sza_array):.2f}°")
    
    return sza_array


def genera_media_dst(arreglo, kernel_size=5):
    """
    Media y desviación estándar local (ventana cuadrada de kernel_size), ignorando NaN.

    Equivale a generic_filter con np.nanmean y np.nanstd (ddof=0, ventana recortada en
    los bordes), pero con filtros uniformes sobre x, x² y el conteo de valores válidos:
    var = E[x²] - E[x]². Se calcula en float64 para que la resta no pierda precisión.
    Las ventanas sin ningún valor válido dan NaN.

    Args:
        arreglo (np.ndarray): arreglo 2D, puede contener NaN.
        kernel_size (int): lado de la ventana.

    Returns:
        tuple[np.ndarray, np.ndarray]: medias y desviaciones locales, en el dtype de entrada.
    """
    validos = np.isfinite(arreglo)
    x = np.where(validos, arreglo, 0).astype(np.float64)

    def suma_local(v):
        return ndimage.uniform_filter(v, size=kernel_size, mode='constant', cval=0.0) * kernel_size**2

    n = suma_local(validos.astype(np.float64))
    s1 = suma_local(x)
    s2 = suma_local(x * x)

    # uniform_filter acumula sumas: cuando la ventana tiene datos, n es un entero salvo
    # error de redondeo; con n < 0.5 la ventana no tiene datos.
    hay_datos = n > 0.5
    with np.errstate(invalid='ignore', divide='ignore'):
        media = np.where(hay_datos, s1 / n, np.nan)
        var = np.where(hay_datos, s2 / n - media * media, np.nan)
    dst = np.sqrt(np.maximum(var, 0.0, where=hay_datos, out=var))

    logger.debug(f"Kernel {kernel_size}x{kernel_size}: media y desviación de forma {media.shape}")
    return media.astype(arreglo.dtype, copy=False), dst.astype(arreglo.dtype, copy=False)


def classify_ash(c04, c07, c11, c13, c15, phase, sza, valid_data_mask, perfil=None) -> np.ndarray:
    """Clasifica ceniza volcánica a partir de arrays de temperatura de brillo.

    La estructura del algoritmo está aquí; los números vienen del perfil.

    Parámetros
    ----------
    c04, c07, c11, c13, c15 : np.ndarray
        Bandas GOES en temperatura de brillo (K) o reflectancia (c04).
    phase : np.ndarray
        Fase de la nube (ACTP), valores 0 a 5 (ver FASES).
    sza : np.ndarray
        Ángulo cenital solar en grados.
    valid_data_mask : np.ndarray (bool)
        Máscara de píxeles con datos válidos.
    perfil : Perfil
        Umbrales; por omisión, los del Popocatépetl.

    Retorna
    -------
    np.ndarray (uint8)
        Array de clasificación con nodata=255 aplicado.
    """
    p = perfil or perfil_por_omision()

    # Diferencias de brillo y temperatura (BTD)
    delta1 = c13 - c15
    delta2 = c11 - c13
    delta3 = c07 - c13

    # Máscaras de iluminación. El crepúsculo incluye los dos límites: con límites estrictos
    # (mayo de 2026) los valores exactos se quedaban sin bloque.
    mask_noche = sza > p.noche_min
    mask_dia = sza < p.dia_max
    mask_crepusculo = (sza >= p.dia_max) & (sza <= p.noche_min)

    # Textura: lo que marca el kernel entra como CA o HAP en los tres bloques.
    media, dst = genera_media_dst(delta1, kernel_size=p.kernel_tamano)
    textura = delta1 - (media * dst) < p.kernel_umbral
    nhood = np.select([textura & (delta1 < p.kernel_ca_dt1_max),
                       textura & (delta1 < p.kernel_hap_dt1_max)], [1, 2], default=0)

    def cumple(u):
        m = (delta1 < u.dt1_max) & (delta2 > u.dt2_min) & (delta3 > u.dt3_min)
        if u.r137_min is not None:
            m &= c04 > u.r137_min
        if u.bt13_max is not None:
            m &= c13 < u.bt13_max
        return m

    def bloque(b):
        return np.select([cumple(p.prueba(b, "ca")) | (nhood == 1),
                          cumple(p.prueba(b, "hap")) | (nhood == 2)], [1, 2], default=0)

    # Clasificación inicial por iluminación
    ceniza_tiempo = np.select(
        [mask_noche, mask_crepusculo, mask_dia],
        [bloque("noche"), bloque("crepusculo"), bloque("dia")],
        default=0
    )

    # Refinamiento de HAP por ΔT2: sigue HAP, pasa a LAP o se borra.
    cond_um1 = [
        ceniza_tiempo == 1,
        (ceniza_tiempo == 2) & (delta2 >= p.hap_dt2_min),
        (ceniza_tiempo == 2) & (delta2 >= p.lap_dt2_min),
        (ceniza_tiempo == 2) & (delta2 < p.lap_dt2_min)
    ]
    ceniza_um1 = np.select(cond_um1, [1, 2, 3, 0], default=ceniza_tiempo)

    # Filtro de ΔT3
    cond_um2 = [
        (ceniza_um1 <= 2) & (delta3 <= p.dt3_ca_hap_max),
        (ceniza_um1 >= 3) & (delta3 <= p.dt3_lap_max)
    ]
    ceniza_um2 = np.select(cond_um2, [0, 0], default=ceniza_um1)

    # Clase final según la fase de la nube (tabla del perfil). Fases fuera de 0 a 5 (o sin
    # dato) dejan la clase como está.
    fase = np.where(np.isfinite(phase), phase, -1).astype(np.int16)
    fase_conocida = (fase >= 0) & (fase < len(FASES))
    tabla = np.array(p.tabla_fase, dtype=np.uint8)
    ceniza = np.where(fase_conocida, tabla[ceniza_um2, np.clip(fase, 0, len(FASES) - 1)],
                      ceniza_um2).astype(np.uint8)

    # Sin ceniza bajo las fases de nube del perfil (en el Popocatépetl, mixta o hielo): no se
    # puede saber si hay ceniza. La superenfriada no entra por ahora (ver
    # doc/2026-10-19_plan_mejoras_operacion.md).
    ceniza[(ceniza == 0) & np.isin(phase, p.fases_nube)] = NUBE

    # Marcar píxeles sin datos válidos como 255 (nodata)
    ceniza[~valid_data_mask] = SIN_DATOS

    return ceniza


def process_instant(data_path, instant_info, output_path, clip_region=None, use_date_tree=False, eph=None, ts=None,
                    escribe_qml=True, perfil=None):
    """Procesa un instante: lee los datos GOES L2, clasifica ceniza y guarda el GeoTIFF.
    Los umbrales salen de `perfil` (por omisión, los del Popocatépetl)."""
    perfil = perfil or perfil_por_omision()
    logger.debug(f"Iniciando detección para el instante: {instant_info[0]}")
    
    # Validar y obtener los límites de la región de recorte si se especificó
    reproject_to_geo = False
    if clip_region:
        # Verificar si el nombre termina en "geo" para reproyectar
        if clip_region.endswith("geo"):
            reproject_to_geo = True
            base_region = clip_region[:-3]  # Remover "geo" del final
        else:
            base_region = clip_region
        
        if base_region not in CLIP_REGIONS:
            raise ValueError(f"Región '{base_region}' no reconocida. Regiones disponibles: {list(CLIP_REGIONS.keys())}")
        
        puntos = CLIP_REGIONS[base_region]
        if reproject_to_geo:
            logger.debug(f"Se aplicará recorte a región '{base_region}' y reproyección a lat/lon: {puntos}")
        else:
            logger.debug(f"Se aplicará recorte a región '{base_region}': {puntos}")
    else:
        puntos = None

    carpeta = carpeta_del_instante(data_path, instant_info, use_date_tree)
    file_paths, faltan = busca_archivos(carpeta, instant_info[0])
    if faltan:
        raise FileNotFoundError(f"Faltan {', '.join(faltan)} para el instante {instant_info[0]} en {carpeta}.")
    for prod, ruta in file_paths.items():
        logger.debug(f"{prod}: {ruta}")

    # Usamos xarray para abrir los archivos NetCDF
    logger.debug("\nLeyendo datos con xarray...")
    ds_c07 = xr.open_dataset(file_paths["C07"])
    
    # Obtener parámetros de proyección GOES desde el NetCDF
    goes_proj = ds_c07['goes_imager_projection']
    
    # Construir el CRS usando el string Proj4 de GOES-16
    proj_string = (f"+proj=geos +h={goes_proj.perspective_point_height} "
                   f"+lon_0={goes_proj.longitude_of_projection_origin} "
                   f"+sweep={goes_proj.sweep_angle_axis} "
                   f"+a={goes_proj.semi_major_axis} "
                   f"+b={goes_proj.semi_minor_axis} "
                   f"+units=m +no_defs")
    
    crs_goes = CRS.from_proj4(proj_string)
    
    # Obtener las coordenadas x e y completas
    goes_height = float(goes_proj.perspective_point_height)
    x_coords_full = ds_c07['x'].values.astype(np.float64) * goes_height
    y_coords_full = ds_c07['y'].values.astype(np.float64) * goes_height
    
    # --- Determinar índices de recorte si se especificó una región ---
    if puntos:
        logger.debug(f"\nCalculando índices de recorte para región: {puntos}")
        transformer_to_goes = Transformer.from_crs("EPSG:4326", crs_goes, always_xy=True)
        # Si se va a reproyectar a lat/lon, se recorta con un margen de 10 % por lado para
        # que la reproyección no quede con huecos en las orillas.
        x_min, y_min, x_max, y_max = limites_goes(puntos, transformer_to_goes,
                                                  margen=0.1 if reproject_to_geo else 0.0)
        logger.debug(f"Límites en la proyección GOES (m): x[{x_min:.0f}, {x_max:.0f}], y[{y_min:.0f}, {y_max:.0f}]")

        # Encontrar los índices más cercanos en los arrays de coordenadas
        # Para x (columnas)
        x_idx_min = np.argmin(np.abs(x_coords_full - x_min))
        x_idx_max = np.argmin(np.abs(x_coords_full - x_max))
        # Para y (filas) - recordar que y puede estar en orden descendente
        y_idx_min = np.argmin(np.abs(y_coords_full - y_max))  # y_max corresponde al índice menor (arriba)
        y_idx_max = np.argmin(np.abs(y_coords_full - y_min))  # y_min corresponde al índice mayor (abajo)
        
        # Asegurar orden correcto
        if x_idx_min > x_idx_max:
            x_idx_min, x_idx_max = x_idx_max, x_idx_min
        if y_idx_min > y_idx_max:
            y_idx_min, y_idx_max = y_idx_max, y_idx_min
        
        # Añadir 1 al índice máximo para incluir el píxel en el slice
        x_slice = slice(x_idx_min, x_idx_max + 1)
        y_slice = slice(y_idx_min, y_idx_max + 1)
        
        # Extraer las coordenadas recortadas
        x_coords = x_coords_full[x_slice]
        y_coords = y_coords_full[y_slice]
        
        logger.debug(f"Índices de recorte: y[{y_idx_min}:{y_idx_max+1}], x[{x_idx_min}:{x_idx_max+1}]")
        logger.debug(f"Tamaño recortado: {len(y_coords)} x {len(x_coords)} píxeles")
    else:
        # Sin recorte, usar todo el dominio
        x_coords = x_coords_full
        y_coords = y_coords_full
        x_slice = slice(None)
        y_slice = slice(None)
    
   # Configurar geo_template con la información espacial
    geo_template = ds_c07['CMI']
    
    # --- Construir la geotransformación manualmente (CORREGIDO) ---
    try:
        # CASO A: Metadatos presentes (vienen en Radianes -> Convertimos a Metros)
        if 'scale_factor' in ds_c07['x'].attrs:
            x_res_meters = float(ds_c07['x'].attrs['scale_factor']) * goes_height
            y_res_meters = float(ds_c07['y'].attrs['scale_factor']) * goes_height
        elif 'scale_factor' in ds_c07['x'].encoding:
            x_res_meters = float(ds_c07['x'].encoding['scale_factor']) * goes_height
            y_res_meters = float(ds_c07['y'].encoding['scale_factor']) * goes_height
        else:
            # CASO B: Sin metadatos, calculamos desde los datos
            # x_coords_full ya está en metros (se multiplicó por la altura del satélite).
            # Por lo tanto, NO multiplicamos por goes_height aquí.
            x_res_meters = (x_coords_full[-1] - x_coords_full[0]) / (len(x_coords_full) - 1)
            y_res_meters = (y_coords_full[-1] - y_coords_full[0]) / (len(y_coords_full) - 1)
            
    except Exception as e:
        logger.warning(f"Usando resolución fallback para banda IR: {e}")
        # Fallback (Radianes -> Metros)
        x_res_meters = 0.000056 * goes_height
        y_res_meters = -0.000056 * goes_height

    # Debug para verificar que no sean valores astronómicos (debe ser ~2000.0)
    logger.debug(f"Resolución calculada (m): X={x_res_meters:.2f}, Y={y_res_meters:.2f}")

    # Normalizar signos y asignar
    x_res = abs(x_res_meters)
    y_res = -abs(y_res_meters) # Y negativo (Norte -> Sur)

    # 4. Coordenada de la esquina superior izquierda (Upper Left)
    # x_coords[0] es el CENTRO del píxel. Restamos medio píxel.
    x_ul = x_coords[0] - (x_res / 2.0)
    y_ul = y_coords[0] - (y_res / 2.0)
    
    geotransform = Affine(x_res, 0.0, x_ul, 0.0, y_res, y_ul)
    
    # Leemos las demás variables, aplicando el recorte si es necesario
    logger.debug("\nCargando datos de las bandas y productos...")
    
    # Cargar datos y cerrar datasets inmediatamente para liberar recursos
    with xr.open_dataset(file_paths["C04"]) as ds:
        c04 = ds['CMI'].data[y_slice, x_slice]
    
    c07 = ds_c07['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["C11"]) as ds:
        c11 = ds['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["C13"]) as ds:
        c13 = ds['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["C15"]) as ds:
        c15 = ds['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["ACTP"]) as ds:
        phase = ds['Phase'].data[y_slice, x_slice]
    
    logger.debug(f"Forma de los arrays cargados: {c07.shape}")
    
    # Crear máscara de datos válidos (píxeles que tienen datos en todas las bandas)
    # Si alguna banda tiene NaN, el píxel se marcará como sin datos
    valid_data_mask = (
        np.isfinite(c04) & np.isfinite(c07) & np.isfinite(c11) & 
        np.isfinite(c13) & np.isfinite(c15) & 
        np.isfinite(phase)
    )
    
    # Calculamos lat/lon a partir de las coordenadas GOES x/y (ya recortadas)
    # Creamos una malla 2D con las coordenadas x/y
    x_2d, y_2d = np.meshgrid(x_coords, y_coords)
    
    # Transformar de proyección GOES a lat/lon (EPSG:4326)
    transformer = Transformer.from_crs(crs_goes, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x_2d, y_2d)
    
    # Actualizar máscara: también marcar como inválidos los píxeles fuera del disco visible
    valid_data_mask = valid_data_mask & np.isfinite(lon) & np.isfinite(lat)
    
    logger.debug("\n--- Coordenadas calculadas ---")
    logger.debug(f"Forma de lat/lon: {lat.shape}")
    logger.debug(f"Rango de latitud: [{np.nanmin(lat):.2f}, {np.nanmax(lat):.2f}]")
    logger.debug(f"Rango de longitud: [{np.nanmin(lon):.2f}, {np.nanmax(lon):.2f}]")

    # Obtenemos fecha y hora de los datos desde el atributo time_coverage_start
    # que está en formato ISO 8601
    time_coverage_start = ds_c07.attrs['time_coverage_start']
    
    # Cerrar el dataset C07 ya que no lo necesitamos más
    ds_c07.close()
    
    # Parsear el string ISO 8601 a datetime
    image_time_dt = parse_fecha(time_coverage_start).replace(tzinfo=utc)

    logger.debug(f"Fecha y hora {image_time_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    sza = get_sun_zenith_angle(lat, lon, image_time_dt, eph, ts)

    # --- Clasificación de ceniza ---
    ceniza = classify_ash(c04, c07, c11, c13, c15, phase, sza, valid_data_mask, perfil=perfil)

    logger.debug("\n--- Clasificación final de ceniza ---")
    logger.debug(f"Forma del array final: {ceniza.shape}")
    logger.debug(f"Valores únicos en la clasificación: {np.unique(ceniza)}")
    logger.debug(f"Píxeles sin datos (nodata=255): {np.sum(~valid_data_mask)} de {ceniza.size} ({100*np.sum(~valid_data_mask)/ceniza.size:.2f}%)")

    # --- Guardado en GeoTIFF ---
    # Creamos un DataArray de xarray con el resultado, usando la plantilla geoespacial
    output_da = xr.DataArray(
        data=ceniza.astype(np.uint8), # Los datos de la clasificación
        coords={
            'y': y_coords, # Las coordenadas Y en metros que calculamos (ya recortadas)
            'x': x_coords  # Las coordenadas X en metros que calculamos (ya recortadas)
        },
        dims=geo_template.dims,
        name="ash_detection",
        attrs={"long_name": "Ash Detection Classification", "units": "category"}
    )
    # Asignamos la información de proyección (CRS) y la geotransformación
    output_da.rio.write_crs(crs_goes, inplace=True)
    output_da.rio.write_transform(geotransform, inplace=True)
    output_da.rio.write_nodata(255, inplace=True)

    # Reproyectar a coordenadas geográficas si se especificó
    if puntos and reproject_to_geo:
        logger.debug("\nReproyectando a coordenadas geográficas (EPSG:4326)...")
        
        # Límites EXACTOS en lat/lon: el rectángulo que contiene a la región, sin margen
        lon_min, lat_min, lon_max, lat_max = limites_region(puntos)
        
        logger.debug(f"Límites geográficos objetivo: lon[{lon_min}, {lon_max}], lat[{lat_min}, {lat_max}]")
        
        # Calcular resolución y dimensiones objetivo
        
        # Definir una resolución objetivo razonable (~0.02° ≈ 2km)
        # Esto es aproximadamente equivalente a la resolución GOES en esta latitud
        target_resolution_deg = 0.02
        
        # Calcular las dimensiones necesarias para cubrir el rectángulo con esta resolución
        lon_range = lon_max - lon_min
        lat_range = lat_max - lat_min
        
        dst_width = int(np.round(lon_range / target_resolution_deg))
        dst_height = int(np.round(lat_range / target_resolution_deg))
        
        # Ahora calcular la resolución EXACTA necesaria para que el rectángulo sea preciso
        exact_lon_res = lon_range / dst_width
        exact_lat_res = lat_range / dst_height
        
        # Crear transformación afín exacta
        dst_transform = Affine(
            exact_lon_res, 0.0, lon_min,
            0.0, -exact_lat_res, lat_max
        )
        
        logger.debug(f"Resolución objetivo: lon={exact_lon_res:.6f}°, lat={exact_lat_res:.6f}°")
        logger.debug(f"Dimensiones objetivo: {dst_height} x {dst_width} píxeles")
        
        # Reproyectar directamente con transformación y dimensiones exactas
        output_da = output_da.rio.reproject(
            dst_crs="EPSG:4326",
            shape=(dst_height, dst_width),
            transform=dst_transform,
            resampling=Resampling.nearest,
            nodata=255
        )
        
        logger.debug(f"Forma después de reproyección: {output_da.shape}")
        logger.debug(f"Límites después de reproyección: {output_da.rio.bounds()}")
        logger.debug("CRS final: EPSG:4326 (lat/lon)")

    logger.debug(f"\nGuardando resultado en: {output_path}")
    
    # Usar los datos del output_da (que pueden estar reproyectados).
    # 0 = sin ceniza, 1-3 = clases, 255 = sin datos (NoData).
    data_to_save = output_da.values.astype(np.uint8)
    color_table = dict(ASH_COLORS)

    height, width = data_to_save.shape
    
    # Guardar como GeoTIFF de 1 banda con colormap incrustado
    
    # Obtener transform y CRS del DataArray original
    transform = output_da.rio.transform()
    crs = output_da.rio.crs
    
    with rasterio.open(
        output_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype=rasterio.uint8,
        crs=crs,
        transform=transform,
        compress='LZW',
        nodata=255
    ) as dst:
        dst.write_colormap(1, color_table)
        dst.write(data_to_save, 1)
        # Con qué umbrales se hizo: nombre del perfil y hash del archivo.
        dst.update_tags(perfil=perfil.nombre, perfil_sha256=perfil.sha256)

    if escribe_qml:
        Path(output_path).with_suffix(".qml").write_text(estilo_qml())
    logger.info(f"GeoTIFF guardado: {Path(output_path).resolve()}")

def main():
    parser = argparse.ArgumentParser(description="Detecta ceniza volcánica a partir de datos GOES L2.")
    parser.add_argument('-p', '--path', type=Path, default=l2_path, 
                        help=f"Ruta al directorio de datos L2. Por defecto: {l2_path} (o LANOT_CENIZA_L2)")
    parser.add_argument('-m', '--instant', '--moment', dest='instant', type=str, default=None, 
                        help="Instante o rango a procesar. Formatos: 'YYYYjjjHHMM', 'YYYYMMDDHHMM', o 'YYYYMMDDHHmm-HHmm'. "
                             "Por defecto, se calcula el más reciente.")
    parser.add_argument('-o', '--output', type=str, default=None, 
                        help="Ruta de salida para el GeoTIFF. Puede ser un archivo (ej: 'resultado.tif') o un directorio (ej: '/data/salida/'). "
                             "Si es un directorio, se genera automáticamente el nombre 'ceniza_[instante].tif' (o con sufijo '_geo' si se reproyecta). "
                             "Por defecto: './ceniza_[instante].tif'")
    parser.add_argument('-c', '--clip', type=str, choices=NOMBRES_CLIP, default=None, 
                        help=f"Región para recortar el resultado final. Agrega 'geo' al final para reproyectar a lat/lon. Opciones: {', '.join(CLIP_REGIONS.keys())} (o con sufijo 'geo')")
    parser.add_argument('--perfil', type=str, default=PERFIL_POR_OMISION,
                        help="Perfil de umbrales: un nombre de la carpeta perfiles/ "
                             f"({', '.join(sorted(q.stem for q in CARPETA_PERFILES.glob('*.toml')))}) "
                             f"o la ruta de un archivo .toml. Por defecto: {PERFIL_POR_OMISION}")
    parser.add_argument('--date-tree', action='store_true', 
                        help="Usa estructura de directorios YYYY/MM/DD dentro de --path para localizar los archivos según el instante especificado")
    parser.add_argument('--dry-run', action='store_true',
                        help="Realiza una verificación de archivos para el instante o rango especificado sin procesar los datos. "
                             "Informa qué instantes tienen datos completos y cuáles no.")
    parser.add_argument('--sin-qml', action='store_true',
                        help="No escribir el estilo de QGIS (.qml) junto al GeoTIFF.")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Modo verbose: muestra información detallada del procesamiento. "
                             "Por defecto, solo se muestran mensajes esenciales de progreso.")


    args = parser.parse_args()
    
    # Configurar nivel de logging según --verbose
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(message)s', force=True)

    try:
        perfil = carga_perfil(args.perfil)
    except (ValueError, OSError) as e:
        logger.error(f"Error en el perfil: {e}")
        sys.exit(SALIDA_USO)
    if perfil.estado != "operacion":
        logger.warning(f"El perfil '{perfil.nombre}' es un ejemplo sin calibrar ({perfil.descripcion}).")
    logger.debug(f"Perfil: {perfil.nombre} (sha256 {perfil.sha256[:12]})")

    # --- 1. Determinar la lista de instantes a procesar ---
    if args.instant:
        try:
            instant_list = parse_moment_string(args.instant)
        except ValueError as e:
            logger.error(f"Error: {e}")
            sys.exit(SALIDA_USO)
    else:
        instant_list = [normalize_moment(get_moment())]

    # --- 1b. Detectar y aplicar desfase de minutos GOES ---
    # Los archivos GOES-CONUS no siempre empiezan en minutos múltiplos de 5;
    # pueden tener un offset de +1 o +2 min (:01/:06 o :02/:07). Se detecta
    # automáticamente a partir del primer instante del rango.
    if len(instant_list) > 1:
        offset = detect_goes_minute_offset(args.path, instant_list[0], use_date_tree=args.date_tree)
        if offset != 0:
            adjusted = []
            for (instant_julian, _y, _mo, _d) in instant_list:
                dt = datetime.datetime.strptime(instant_julian, "%Y%j%H%M") + datetime.timedelta(minutes=offset)
                new_julian = f"{dt.strftime('%Y')}{dt.strftime('%j')}{dt.strftime('%H%M')}"
                adjusted.append((new_julian, dt.strftime('%Y'), dt.strftime('%m'), dt.strftime('%d')))
            instant_list = adjusted

    # --- 2. Verificación de archivos (Pre-flight check) ---
    logger.debug("\n--- Verificando disponibilidad de archivos ---")
    instantes_validos = []
    instantes_fallidos = []

    for instant_info in instant_list:
        carpeta = carpeta_del_instante(args.path, instant_info, args.date_tree)
        try:
            _, faltan = busca_archivos(carpeta, instant_info[0])
        except ValueError as e:
            logger.error(f"Error: {e}")
            faltan = ["(ambiguo)"]
        if faltan:
            logger.debug(f"{instant_info[0]}: faltan {', '.join(faltan)}")
            instantes_fallidos.append((instant_info[0], carpeta))
        else:
            instantes_validos.append(instant_info)

    # --- 3. Reportar resultados de la verificación ---
    group_and_report_failures(instantes_fallidos, verbose=args.verbose)

    if instantes_validos:
        logger.info(f"\nSe encontraron datos completos para {len(instantes_validos)} instantes.")
    
    if not instantes_validos:
        logger.info("\nNo se encontraron datos completos para ningún instante en el rango especificado. Terminando.")
        sys.exit(SALIDA_SIN_DATOS)

    if args.dry_run:
        logger.info("\nModo 'dry-run' activado. No se realizará ningún procesamiento. Terminando.")
        sys.exit(SALIDA_SIN_DATOS if instantes_fallidos else SALIDA_OK)

    # --- 4. Procesar instantes válidos ---
    logger.info(f"\n--- Iniciando procesamiento para {len(instantes_validos)} instantes válidos ---")
    
    # Cargar recursos pesados una sola vez
    logger.debug("Cargando efemérides de Skyfield (una sola vez)...")
    eph_global, ts_global = carga_efemerides()
    
    # Contadores para estadísticas
    instantes_exitosos = 0
    instantes_con_error = 0
    
    for i, instant_info in enumerate(instantes_validos):
        instant_str = instant_info[0]
        logger.info(f"\n[{i+1}/{len(instantes_validos)}] Procesando instante: {instant_str}")
        
        # Generar nombre de archivo de salida para cada instante
        if args.output:
            outp = str(args.output)
            output_path = Path(outp)
            
            is_directory = (
                outp.endswith(os.path.sep) or
                output_path.is_dir() or
                (not output_path.exists() and not outp.endswith('.tif'))
            )
            
            if is_directory:
                output_dir = output_path
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.error(f"No se pudo crear el directorio de salida '{output_dir}': {e}")
                    raise
                if args.clip and args.clip.endswith('geo'):
                    filename = f"ceniza_{instant_str}_geo.tif"
                else:
                    filename = f"ceniza_{instant_str}.tif"
                output_file = output_dir / filename
            else:
                if i > 0:
                    logger.warning("Se especificó un único archivo de salida para un rango. Solo se procesa el primer instante válido.")
                    break
                output_file = output_path
        else:
            if args.clip and args.clip.endswith('geo'):
                output_file = Path(f"./ceniza_{instant_str}_geo.tif")
            else:
                output_file = Path(f"./ceniza_{instant_str}.tif")

        try:
            process_instant(
                data_path=args.path,
                instant_info=instant_info,
                output_path=output_file,
                clip_region=args.clip,
                use_date_tree=args.date_tree,
                eph=eph_global,
                ts=ts_global,
                escribe_qml=not args.sin_qml,
                perfil=perfil,
            )
            instantes_exitosos += 1
        except Exception:
            instantes_con_error += 1
            logger.exception(f"\n*** Error crítico procesando instante {instant_str}:")
            logger.debug("Continuando con el siguiente instante...")
            continue

    # Mostrar estadísticas finales
    logger.info("\n--- Procesamiento completado. ---")
    logger.info(f"Instantes procesados exitosamente: {instantes_exitosos} de {len(instantes_validos)}")
    if instantes_con_error > 0:
        logger.info(f"Instantes con error: {instantes_con_error}")
    if instantes_con_error:
        sys.exit(SALIDA_ERROR)
    if instantes_fallidos:
        sys.exit(SALIDA_SIN_DATOS)
    sys.exit(SALIDA_OK)

if __name__ == "__main__":
    main()
