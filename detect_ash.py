#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime
import xarray as xr
import numpy as np
from scipy import ndimage
from pathlib import Path
from skyfield.api import utc
from skyfield.api import Topos, load
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
from PIL import Image
from mapdrawer import MapDrawer


# Ruta al directorio de datos L2
l2_path = Path("/data/ceniza/l2")

# Regiones predefinidas para recorte [lon_min, lat_max, lon_max, lat_min]
CLIP_REGIONS = {
    'centromex': [-107.2319400, 22.7180385, -93.8363933, 14.9386282],
    'popocatepetl': [-100.2622042, 20.5800993, -96.8495200, 18.2893953],
    'ashpaper': [-102.418,22.474,-96.294,17.547],
}

# Generar versiones "geo" de las regiones automáticamente
CLIP_REGIONS_WITH_GEO = CLIP_REGIONS.copy()
for region_name, bbox in CLIP_REGIONS.items():
    CLIP_REGIONS_WITH_GEO[f"{region_name}geo"] = bbox
 
def get_moment(is_conus=True):
    """
    Calcula la fecha y hora más reciente según el dominio:
    - Si conus: minutos terminados en 1 o 6 (01, 06, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56)
    - Si full disk: minutos múltiplos de 10 (00, 10, 20, 30, 40, 50)
    """
    ahora_utc = datetime.datetime.now(datetime.timezone.utc)

    if is_conus:
        minuto_actual = ahora_utc.minute
        
        # Encontrar el minuto más reciente terminado en 1 o 6
        # Primero calculamos el minuto base (múltiplo de 5 más cercano hacia abajo)
        base = (minuto_actual // 5) * 5
        
        # Determinamos cuál es el minuto válido más reciente
        if base % 10 == 0:  # base termina en 0 (ej: 0, 10, 20, 30, 40, 50)
            # El más reciente terminado en 1 o 6 sería base + 1 si no hemos pasado,
            # o base - 4 (el terminado en 6 anterior)
            if minuto_actual >= base + 1:
                minuto_redondeado = base + 1
            else:
                minuto_redondeado = base - 4 if base >= 4 else 56
                if minuto_redondeado == 56 and base < 4:
                    # Retroceder una hora
                    ahora_utc = ahora_utc.replace(hour=ahora_utc.hour - 1 if ahora_utc.hour > 0 else 23)
                    if ahora_utc.hour == 23:
                        ahora_utc = ahora_utc - datetime.timedelta(days=1)
        else:  # base termina en 5 (ej: 5, 15, 25, 35, 45, 55)
            # El más reciente terminado en 1 o 6 sería base + 1 (terminado en 6) si no hemos pasado,
            # o base - 4 (el terminado en 1)
            if minuto_actual >= base + 1:
                minuto_redondeado = base + 1
            else:
                minuto_redondeado = base - 4
    else:
        # Para Full Disk: múltiplos de 10
        minuto_redondeado = (ahora_utc.minute // 10) * 10

    # Crear el nuevo objeto datetime con los minutos ajustados
    dt_ajustado = ahora_utc.replace(minute=minuto_redondeado, second=0, microsecond=0)  

    # Formatear la fecha al formato "YYYYjjjhhmm"
    moment = dt_ajustado.strftime("%Y%j%H%M")
    return moment


def normalize_moment(moment):
    """
    Normaliza el momento al formato juliano YYYYjjjHHMM.
    
    Detecta automáticamente si el momento está en formato:
    - Juliano (11 dígitos): YYYYjjjHHMM - lo retorna sin cambios
    - Gregoriano (12 dígitos): YYYYMMDDhhmm - lo convierte a juliano
    
    Args:
        moment (str): Momento en formato juliano u gregoriano
        
    Returns:
        tuple: (moment_julian, year, month, day) donde:
            - moment_julian es el momento en formato YYYYjjjHHMM
            - year, month, day son strings para construir rutas YYYY/MM/DD
    """
    from datetime import datetime
    
    if len(moment) == 12:
        # Formato gregoriano: YYYYMMDDhhmm
        year = moment[:4]
        month = moment[4:6]
        day = moment[6:8]
        hhmm = moment[8:12]
        
        # Convertir a día juliano
        date_obj = datetime.strptime(f"{year}{month}{day}", "%Y%m%d")
        julian_day = f"{date_obj.timetuple().tm_yday:03d}"
        
        # Construir momento en formato juliano
        moment_julian = f"{year}{julian_day}{hhmm}"
        
        print(f"Momento {moment} (gregoriano) normalizado a {moment_julian} (juliano).")
        return moment_julian, year, month, day
        
    elif len(moment) == 11:
        # Formato juliano: YYYYjjjHHMM
        year = moment[:4]
        julian_day = moment[4:7]
        
        # Convertir día juliano a mes/día
        date_obj = datetime.strptime(f"{year}{julian_day}", "%Y%j")
        month = f"{date_obj.month:02d}"
        day = f"{date_obj.day:02d}"
        
        print(f"Momento {moment} (juliano) confirmado.")
        return moment, year, month, day
    else:
        raise ValueError(f"Formato de momento inválido: '{moment}'. Debe tener 11 dígitos (YYYYjjjHHMM) o 12 dígitos (YYYYMMDDhhmm)")


def parse_moment_string(moment_str, interval_minutes=5):
    """
    Parsea un string de momento, que puede ser un único momento o un rango.

    Formatos soportados:
    - Momento único (Gregoriano): 'YYYYMMDDHHMM' (12 dígitos)
    - Momento único (Juliano): 'YYYYjjjHHMM' (11 dígitos)
    - Rango (Gregoriano): 'YYYYMMDDHHmm-HHmm' (ej. '202402270800-1430')
    - Rango (Juliano): 'YYYYjjjHHmm-HHmm' (ej. '20240580411-0426')

    Args:
        moment_str (str): El string de momento a parsear.
        interval_minutes (int): El incremento en minutos para generar momentos en un rango (por defecto 5 min).

    Returns:
        list[tuple]: Una lista de tuplas. Cada tupla contiene:
                     (moment_julian, year, month, day).
                     Esto evita recalcular la información de fecha repetidamente.
    """
    if '-' in moment_str:
        print(f"Detectado rango de momentos: {moment_str}")
        
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
        
        print(f"Rango expandido a {len(moments)} momentos (intervalo de {interval_minutes} min).")
        return moments

    elif len(moment_str) == 11 or len(moment_str) == 12:
        # Es un momento único, lo normalizamos y lo devolvemos en una lista con una tupla
        return [normalize_moment(moment_str)]
    else:
        raise ValueError(f"Formato de momento o rango no reconocido: '{moment_str}'")


def group_and_report_failures(failed_moments, interval_minutes=5):
    """
    Agrupa momentos fallidos consecutivos en rangos y los imprime.
    """
    if not failed_moments:
        return

    print("\n--- Resumen de Fallas ---")
    print(f"Advertencia: No se encontraron datos completos para {len(failed_moments)} momentos.")

    # Ordenar por si acaso, aunque deberían venir ordenados
    failed_moments.sort()
    
    groups = []
    if len(failed_moments) > 0:
        start_of_group = failed_moments[0]
        for i in range(1, len(failed_moments)):
            # Convertir a datetime para comparar
            prev_dt = datetime.datetime.strptime(failed_moments[i-1], "%Y%j%H%M")
            curr_dt = datetime.datetime.strptime(failed_moments[i], "%Y%j%H%M")
            
            # Si el momento actual no es consecutivo al anterior, cerramos el grupo
            if (curr_dt - prev_dt) > datetime.timedelta(minutes=interval_minutes):
                groups.append((start_of_group, failed_moments[i-1]))
                start_of_group = failed_moments[i]
        # Añadir el último grupo
        groups.append((start_of_group, failed_moments[-1]))

    for start, end in groups:
        print(f"  - Intervalo fallido: {start} a {end}" if start != end else f"  - Momento fallido: {start}")


def get_filelist_from_path(data_path, moment_info, products, use_date_tree=False, verbose=True):
    """
    Busca archivos en un directorio que coincidan con un momento 'YYYYjjjhhmm" 
    y que contengan uno de los identificadores de 'products' en su nombre.
    
    Args:
        data_path (Path): Ruta base donde buscar los archivos
        moment_info (tuple): Tupla con (moment_julian, year, month, day).
        products (list): Lista de productos a buscar
        use_date_tree (bool): Si True, usa la estructura YYYY/MM/DD derivada de moment.
        verbose (bool): Si True, imprime información detallada del proceso de búsqueda.
    """
    
    # Desempaquetar la información del momento
    moment_julian, year, month, day = moment_info
    
    # Construir la ruta de búsqueda
    if use_date_tree:
        # Construir la ruta completa usando los componentes de fecha
        search_path = data_path / year / month / day
    else:
        search_path = data_path
    
    # Usar el momento en formato juliano para buscar archivos
    # Patrón completo YYYYjjjHHMM para buscar archivos que coincidan con el momento
    patron_base = f"*s{moment_julian}*.nc"

    if verbose:
        print(f"Buscando archivos en: {search_path}")
        print(f"Usando patrón base: {patron_base}")

    # Comprobar si el directorio existe antes de buscar
    if not search_path.is_dir():
        if verbose:
            print(f"Error: El directorio '{search_path}' no existe. Por favor, comprueba la ruta.")
        return []
    
    # Obtenemos *todos* los archivos que coinciden con el tiempo (patrón base)
    archivos_por_tiempo = list(search_path.glob(patron_base))
    
    if verbose:
        print(f"Encontrados {len(archivos_por_tiempo)} archivos que coinciden con el patrón de tiempo.")
    
    # Diccionario para agrupar archivos por producto: producto -> lista de paths
    archivos_por_producto = {prod: [] for prod in products}
    
    import re

    for p in archivos_por_tiempo:
        p_name = p.name
        for prod in products:
            # Lógica de coincidencia para diferentes tipos de productos:
            # - Bandas espectrales (C04, C07, etc.): buscar "M6C07_" o "CMIPC-M6C07_"
            # - ACTP: buscar "ACTPC-" (Cloud Top Phase)
            if prod.startswith('C'):
                # Para bandas: admitir múltiples formatos históricos y actuales.
                # Ejemplos en la práctica:
                #  - OR_ABI-L2-CMIPC-M3C07_G16_s20190600802133_...  (M3)
                #  - OR_ABI-L2-CMIPC-M6C07_G16_s...                 (M6)
                #  - ...-C07_G16_...  (variantes)
                # La forma más robusta es aceptar si la etiqueta de banda (ej. 'C07')
                # aparece en el nombre del archivo en contextos razonables.
                # Usamos una expresión regular simple para evitar coincidencias parciales raras.
                band_code = prod  # e.g. 'C07'
                # Buscar patrones como 'M3C07', 'M6C07', '-C07_', '_C07_', 'C07_G16', etc.
                if re.search(rf"M\d+C{band_code[1:]}\b", p_name) or re.search(rf"[^A-Za-z0-9]{band_code}[^A-Za-z0-9]", p_name) or (band_code in p_name):
                    archivos_por_producto[prod].append(p)
                    break
            elif prod == 'ACTP':
                # Para ACTP: el archivo se llama ACTPC (con C al final)
                if "ACTPC-" in p_name or "-ACTP_" in p_name or "-ACTPC-" in p_name or "ACTP" in p_name:
                    archivos_por_producto[prod].append(p)
                    break
            else:
                # Para otros productos: búsqueda estándar
                if f"-{prod}_" in p_name or f"-{prod}-" in p_name or prod in p_name:
                    archivos_por_producto[prod].append(p)
                    break
    
    # Resolver duplicados: preferir CG_ sobre OR_
    lista_archivos = []
    for prod in products:
        candidatos = archivos_por_producto[prod]
        
        if len(candidatos) == 0:
            continue
        elif len(candidatos) == 1:
            lista_archivos.append(str(candidatos[0]))
        else:
            # Hay duplicados: preferir CG_ sobre OR_
            cg_files = [p for p in candidatos if p.name.startswith('CG_')]
            if cg_files:
                lista_archivos.append(str(cg_files[0]))
                if len(cg_files) > 1 or len(candidatos) > len(cg_files):
                    if verbose: print(f"  Nota: Se encontraron {len(candidatos)} archivos para {prod}, usando {cg_files[0].name} (preferencia CG_)")
            else:
                # No hay CG_, usar el primero que encontremos
                lista_archivos.append(str(candidatos[0]))
                if len(candidatos) > 1:
                    if verbose: print(f"  Nota: Se encontraron {len(candidatos)} archivos para {prod}, usando {candidatos[0].name}")
    
    return lista_archivos
    

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
    # Observamos el Sol desde el centro de la Tierra
    astrometric = earth.at(image_time_sky).observe(sun)
    ra, dec, distance = astrometric.radec()
    
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
    print("\n--- Resultados ---")
    print(f"Forma del array SZA: {sza_array.shape}")
    print(f"SZA (min): {np.nanmin(sza_array):.2f}°")
    print(f"SZA (max): {np.nanmax(sza_array):.2f}°")
    
    return sza_array


def _process_block_std(args):
    """
    Función auxiliar para procesar un bloque del array en paralelo.
    Calcula la desviación estándar local para un bloque específico.
    """
    block, kernel_size = args
    return ndimage.generic_filter(
        block,
        np.nanstd,
        size=kernel_size,
        mode='constant',
        cval=np.nan
    )


def genera_media_dst(arreglo, kernel_size=5, n_jobs=None):
    """
    Calcula la media y la desviación estándar local (kernel) de un arreglo, ignorando NaNs.

    Para la media, utiliza un método optimizado con uniform_filter para mayor rendimiento.
    Para la desviación estándar, utiliza procesamiento paralelo dividiendo el array en bloques.

    Args:
        arreglo (np.ndarray): El arreglo de entrada, puede contener NaNs.
        kernel_size (int): El tamaño de la ventana cuadrada para el cálculo.
        n_jobs (int, optional): Número de procesos paralelos. Si es None, usa todos los cores disponibles.

    Returns:
        tuple[np.ndarray, np.ndarray]: Una tupla conteniendo el arreglo de medias locales
                                       y el arreglo de desviaciones estándar locales.
    """
    # --- Media (Método optimizado para manejar NaNs) ---
    # 1. Copia del arreglo con NaNs reemplazados por 0
    V = arreglo.copy()
    V[np.isnan(V)] = 0
    # 2. Suma local usando el filtro uniforme (muy rápido)
    suma_local = ndimage.uniform_filter(V, size=kernel_size, mode='constant', cval=0) * (kernel_size**2)

    # 3. Arreglo para contar los elementos no-NaN en la ventana
    N = np.ones(arreglo.shape)
    N[np.isnan(arreglo)] = 0
    # 4. Conteo local de elementos no-NaN
    conteo_local = ndimage.uniform_filter(N, size=kernel_size, mode='constant', cval=0) * (kernel_size**2)
    
    # 5. Calcular la media, evitando división por cero
    kernel_media = np.divide(suma_local, conteo_local, where=conteo_local!=0, out=np.full(arreglo.shape, np.nan))

    # --- Desviación Estándar (usando procesamiento paralelo) ---
    if n_jobs is None:
        n_jobs = max(1, multiprocessing.cpu_count() - 2)  # Dejar 2 cores libres
    
    # Si el array es pequeño o n_jobs=1, usar procesamiento secuencial
    if n_jobs == 1 or arreglo.size < 1000000:  # < 1M píxeles
        kernel_std = ndimage.generic_filter(
            arreglo, 
            np.nanstd, 
            size=kernel_size,
            mode='constant',
            cval=np.nan
        )
    else:
        # Dividir el array en bloques horizontales con overlap
        rows, cols = arreglo.shape
        overlap = kernel_size // 2
        
        # Calcular número óptimo de bloques (uno por proceso)
        n_blocks = min(n_jobs, rows // (kernel_size * 10))  # Bloques no muy pequeños
        n_blocks = max(1, n_blocks)
        
        rows_per_block = rows // n_blocks
        
        blocks = []
        indices = []
        
        for i in range(n_blocks):
            start_row = i * rows_per_block
            if i == n_blocks - 1:
                end_row = rows
            else:
                end_row = (i + 1) * rows_per_block
            
            # Agregar overlap para evitar problemas en los bordes
            block_start = max(0, start_row - overlap)
            block_end = min(rows, end_row + overlap)
            
            block = arreglo[block_start:block_end, :]
            blocks.append((block, kernel_size))
            indices.append((start_row, end_row, block_start))
        
        # Procesar bloques en paralelo
        with ProcessPoolExecutor(max_workers=n_jobs) as executor:
            results = list(executor.map(_process_block_std, blocks))
        
        # Ensamblar los resultados
        kernel_std = np.empty(arreglo.shape, dtype=arreglo.dtype)
        for i, result in enumerate(results):
            start_row, end_row, block_start = indices[i]
            offset = start_row - block_start
            result_slice = result[offset:offset + (end_row - start_row), :]
            kernel_std[start_row:end_row, :] = result_slice
    
    print(f"\n--- Resultados del Kernel ({kernel_size}x{kernel_size}) ---")
    print(f"Forma del array de Media: {kernel_media.shape}")
    print(f"Forma del array de Desv. Estándar: {kernel_std.shape}")
    if n_jobs > 1:
        print(f"Procesamiento paralelo con {n_jobs} procesos")

    return kernel_media, kernel_std


def create_color_png(data_array, output_path, color_table_path=None, bounds=None, timestamp=None, lanot_dir='/usr/local/share/lanot', crs=None):
    """
    Crea una imagen PNG a color a partir del array de clasificación de ceniza,
    con mapa base dibujado usando MapDrawer.
    
    Args:
        data_array (np.ndarray): Array 2D con valores de clasificación (0-5)
        output_path (Path or str): Ruta del archivo PNG de salida
        color_table_path (Path or str, optional): Ruta al archivo .cpt con la paleta de colores.
                                                   Por defecto usa ash.cpt en el mismo directorio.
        bounds (tuple, optional): Límites geográficos (lon_min, lat_max, lon_max, lat_min) en WGS84.
                                  Si se proporciona, dibuja líneas costeras y logo.
        timestamp (datetime, optional): Fecha/hora de la imagen para mostrar en el PNG.
        lanot_dir (str): Directorio base de recursos LANOT (shapefiles, logos)
        crs (str or CRS, optional): Sistema de coordenadas de la imagen. Si es None o 'EPSG:4326',
                                    usa proyección lineal. Si es otra proyección (ej: GOES), 
                                    MapDrawer reproyectará las capas correctamente.
    
    Returns:
        None
    """
    # Paleta de colores por defecto basada en ash.cpt
    default_colors = {
        0: (0, 0, 0),       # clear - negro
        1: (255, 0, 0),     # ash - rojo
        2: (255, 165, 0),   # probable - naranja
        3: (255, 255, 0),   # baja probable - amarillo
        4: (0, 255, 0),     # cloud - verde
        5: (0, 0, 255)      # noise - azul
    }
    
    # Si se proporciona un archivo .cpt, intentar leerlo
    if color_table_path:
        try:
            colors = {}
            with open(color_table_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and not line.startswith('B') and not line.startswith('F') and not line.startswith('N'):
                        parts = line.split(';')[0].split()
                        if len(parts) >= 4:
                            value = int(parts[0])
                            r, g, b = int(parts[1]), int(parts[2]), int(parts[3])
                            colors[value] = (r, g, b)
            if colors:
                default_colors.update(colors)
                print(f"Paleta de colores cargada desde: {color_table_path}")
        except Exception as e:
            print(f"Advertencia: No se pudo leer {color_table_path}, usando paleta por defecto. Error: {e}")
    
    # Crear arrays RGB
    height, width = data_array.shape
    rgb_array = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Aplicar colores según el valor de clasificación
    for value, color in default_colors.items():
        mask = (data_array == value)
        rgb_array[mask] = color
    
    # Crear imagen PIL
    img = Image.fromarray(rgb_array, mode='RGB')
    
    # Si se proporcionan límites geográficos, usar MapDrawer para dibujar mapa
    if bounds is not None:
        try:
            lon_min, lat_max, lon_max, lat_min = bounds
            
            # Determinar si necesitamos usar proyección o modo lineal
            # Si la imagen está en EPSG:4326 o no tiene CRS, usar modo lineal (None)
            # Si está en otra proyección (ej: GOES), convertir a clave corta si es posible
            target_crs = None
            if crs is not None:
                crs_str = crs.to_string() if hasattr(crs, 'to_string') else str(crs)
                if crs_str != 'EPSG:4326':
                    # Intentar detectar si es una proyección GOES y usar clave corta
                    proj4_str = crs.to_proj4() if hasattr(crs, 'to_proj4') else crs_str
                    
                    # Detectar GOES-16 (lon_0=-75)
                    if 'geos' in proj4_str.lower() and 'lon_0=-75' in proj4_str:
                        target_crs = 'goes16'
                    # Detectar GOES-17/18 (lon_0=-137)
                    elif 'geos' in proj4_str.lower() and 'lon_0=-137' in proj4_str:
                        target_crs = 'goes18'  # Usar goes18 como default para -137
                    else:
                        # Usar el CRS completo si no es GOES o no se reconoce
                        target_crs = crs_str
            
            # Inicializar MapDrawer
            mapper = MapDrawer(lanot_dir=lanot_dir, target_crs=target_crs)
            mapper.set_image(img)
            mapper.set_bounds(lon_min, lat_max, lon_max, lat_min)
            
            # Selección de capas según tamaño del dominio: si es local (span pequeño) solo MEXSTATES
            lon_span = abs(lon_max - lon_min)
            lat_span = abs(lat_max - lat_min)
            if lon_span < 20 and lat_span < 20:
                layer_selection = ("MEXSTATES",)
                print("Dominio local detectado; dibujando solo capa MEXSTATES.")
            else:
                layer_selection = ("COASTLINE", "COUNTRIES", "MEXSTATES")
                print("Dominio amplio; dibujando capas COASTLINE, COUNTRIES y MEXSTATES.")
            for layer_key in layer_selection:
                try:
                    mapper.draw_layer(layer_key, color='white', width=0.5)
                except Exception as e:
                    print(f"  No se pudo dibujar capa {layer_key}: {e}")
            
            # Dibujar logo LANOT
            try:
                mapper.draw_logo(logosize=128, position=1)  # Upper-right
            except Exception as e:
                print(f"  No se pudo dibujar logo: {e}")
            
            # Dibujar fecha/hora en esquina inferior izquierda (posición 2)
            if timestamp is not None:
                try:
                    mapper.draw_fecha(timestamp, position=3, fontsize=16, color='yellow')
                except Exception as e:
                    print(f"  No se pudo dibujar fecha: {e}")
            
            # Dibujar leyenda automática con la paleta actual (solo clases 1–3)
            try:
                etiquetas = {
                    1: 'Ash',
                    2: 'Probable Ash',
                    3: 'Possible Ash',
                }
                # Solo mostramos clases 1–3 en la leyenda
                orden = [1, 2, 3]
                items = [(etiquetas[v], default_colors[v]) for v in orden if v in default_colors]
                # Colocar la leyenda encima de la fecha (fecha: position=2),
                # aplicando un desplazamiento vertical sencillo.
                mapper.draw_legend(items=items, position=2, fontsize=14, border_color='black') #, vertical_offset=40)
            except Exception as e:
                print(f"  No se pudo dibujar la leyenda: {e}")
                
        except Exception as e:
            print(f"Advertencia: No se pudo usar MapDrawer para decorar el mapa: {e}")
            print("  Se guardará solo la imagen de clasificación.")
    
    # Guardar imagen
    img.save(output_path)
    print(f"Imagen PNG guardada en: {output_path}")


def main(data_path, moment_info, output_path, clip_region=None, create_png=False, use_date_tree=False, eph=None, ts=None):
    """Función principal para ejecutar el proceso de detección de cenizas."""
    print(f"Iniciando detección para el momento: {moment_info[0]}")
    
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
            print(f"Error: Región '{base_region}' no reconocida. Regiones disponibles: {list(CLIP_REGIONS.keys())}")
            return
        
        bbox = CLIP_REGIONS[base_region]
        if reproject_to_geo:
            print(f"Se aplicará recorte a región '{base_region}' y reproyección a lat/lon: {bbox}")
        else:
            print(f"Se aplicará recorte a región '{base_region}': {bbox}")
    else:
        bbox = None

    # Si se especifica un archivo NAV, no lo buscamos en el directorio
    # NOTA: El archivo NAV ya no es necesario, se calculan lat/lon desde la proyección
    productos = ["ACTP", "C04", "C07", "C11", "C13", "C14", "C15"]
    
    archivos = get_filelist_from_path(data_path, moment_info, productos, use_date_tree=use_date_tree)
    if not archivos:
        print(f"Error: No se encontró ningún archivo con este momento {moment_info[0]}.")
        return
    if len(archivos) != len(productos):
        print(f"Error: Se encontraron {len(archivos)} archivos, pero se esperaban {len(productos)}. (Momento: {moment_info[0]})")
        return
    
    print(f"Se encontraron los {len(archivos)} archivos requeridos.")
    
    # Creamos un diccionario para almacenar las rutas de los archivos por producto.
    file_paths = {}
    for archivo_path in archivos:
        # Identificamos a qué producto pertenece cada archivo
        for prod in productos:
            # La lógica debe coincidir con la de get_filelist_from_path
            is_band_product = prod.startswith("C") and "CMIP" in str(archivo_path) and prod in str(archivo_path)
            is_other_product = not prod.startswith("C") and prod in str(archivo_path) 

            if is_band_product or is_other_product:
                print(f"Asociando {prod} con: {archivo_path}")
                file_paths[prod] = archivo_path
                break # Pasamos al siguiente archivo una vez que encontramos su producto
    
    print("\n¡Éxito! Todos los productos requeridos fueron encontrados.")

    # Usamos xarray para abrir los archivos NetCDF
    print("\nLeyendo datos con xarray...")
    ds_c07 = xr.open_dataset(file_paths["C07"])
    
    # Obtener parámetros de proyección GOES desde el NetCDF
    goes_proj = ds_c07['goes_imager_projection']
    
    # Construir el CRS usando el string Proj4 de GOES-16
    from pyproj import CRS, Transformer
    from affine import Affine
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
    if bbox:
        print(f"\nCalculando índices de recorte para región: {bbox}")
        # bbox = [lon_min, lat_max, lon_max, lat_min]
        lon_min, lat_max, lon_max, lat_min = bbox
        
        # Transformar coordenadas geográficas a proyección GOES
        transformer_to_goes = Transformer.from_crs("EPSG:4326", crs_goes, always_xy=True)
        
        # Si vamos a reproyectar a geográficas, expandir el bbox en proyección GOES
        # para asegurar cobertura completa después de la reproyección
        if reproject_to_geo:
            # Expandir el bbox geográfico en ~10% en cada dirección
            lon_margin = (lon_max - lon_min) * 0.1
            lat_margin = (lat_max - lat_min) * 0.1
            
            lon_min_exp = lon_min - lon_margin
            lon_max_exp = lon_max + lon_margin
            lat_min_exp = lat_min - lat_margin
            lat_max_exp = lat_max + lat_margin
            
            print(f"Bbox expandido para reproyección: lon[{lon_min_exp:.4f}, {lon_max_exp:.4f}], lat[{lat_min_exp:.4f}, {lat_max_exp:.4f}]")
            
            # Usar el bbox expandido para el recorte en GOES
            x_min, y_min = transformer_to_goes.transform(lon_min_exp, lat_min_exp)
            x_max, y_max = transformer_to_goes.transform(lon_max_exp, lat_max_exp)
        else:
            # Sin reproyección, usar el bbox exacto
            x_min, y_min = transformer_to_goes.transform(lon_min, lat_min)
            x_max, y_max = transformer_to_goes.transform(lon_max, lat_max)
        
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
        
        print(f"Índices de recorte: y[{y_idx_min}:{y_idx_max+1}], x[{x_idx_min}:{x_idx_max+1}]")
        print(f"Tamaño recortado: {len(y_coords)} x {len(x_coords)} píxeles")
    else:
        # Sin recorte, usar todo el dominio
        x_coords = x_coords_full
        y_coords = y_coords_full
        x_slice = slice(None)
        y_slice = slice(None)
    
   # Configurar geo_template con la información espacial
    geo_template = ds_c07['CMI']
    
    # Aseguramos que la altura sea float nativo
    goes_height = float(goes_proj.perspective_point_height)

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
            # IMPORTANTE: x_coords_full YA ESTÁN EN METROS (ver línea 538)
            # Por lo tanto, NO multiplicamos por goes_height aquí.
            x_res_meters = (x_coords_full[-1] - x_coords_full[0]) / (len(x_coords_full) - 1)
            y_res_meters = (y_coords_full[-1] - y_coords_full[0]) / (len(y_coords_full) - 1)
            
    except Exception as e:
        print(f"Advertencia: Usando resolución fallback para banda IR: {e}")
        # Fallback (Radianes -> Metros)
        x_res_meters = 0.000056 * goes_height
        y_res_meters = -0.000056 * goes_height

    # Debug para verificar que no sean valores astronómicos (debe ser ~2000.0)
    print(f"Resolución calculada (m): X={x_res_meters:.2f}, Y={y_res_meters:.2f}")

    # Normalizar signos y asignar
    x_res = abs(x_res_meters)
    y_res = -abs(y_res_meters) # Y negativo (Norte -> Sur)

    # 4. Coordenada de la esquina superior izquierda (Upper Left)
    # x_coords[0] es el CENTRO del píxel. Restamos medio píxel.
    x_ul = x_coords[0] - (x_res / 2.0)
    y_ul = y_coords[0] - (y_res / 2.0)
    
    geotransform = Affine(x_res, 0.0, x_ul, 0.0, y_res, y_ul)
    
    # Leemos las demás variables, aplicando el recorte si es necesario
    print("\nCargando datos de las bandas y productos...")
    
    # Cargar datos y cerrar datasets inmediatamente para liberar recursos
    with xr.open_dataset(file_paths["C04"]) as ds:
        c04 = ds['CMI'].data[y_slice, x_slice]
    
    c07 = ds_c07['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["C11"]) as ds:
        c11 = ds['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["C13"]) as ds:
        c13 = ds['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["C14"]) as ds:
        c14 = ds['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["C15"]) as ds:
        c15 = ds['CMI'].data[y_slice, x_slice]
    
    with xr.open_dataset(file_paths["ACTP"]) as ds:
        phase = ds['Phase'].data[y_slice, x_slice]
    
    print(f"Forma de los arrays cargados: {c07.shape}")
    
    # Crear máscara de datos válidos (píxeles que tienen datos en todas las bandas)
    # Si alguna banda tiene NaN, el píxel se marcará como sin datos
    valid_data_mask = (
        np.isfinite(c04) & np.isfinite(c07) & np.isfinite(c11) & 
        np.isfinite(c13) & np.isfinite(c14) & np.isfinite(c15) & 
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
    
    print(f"\n--- Coordenadas calculadas ---")
    print(f"Forma de lat/lon: {lat.shape}")
    print(f"Rango de latitud: [{np.nanmin(lat):.2f}, {np.nanmax(lat):.2f}]")
    print(f"Rango de longitud: [{np.nanmin(lon):.2f}, {np.nanmax(lon):.2f}]")

    # Obtenemos fecha y hora de los datos desde el atributo time_coverage_start
    # que está en formato ISO 8601
    time_coverage_start = ds_c07.attrs['time_coverage_start']
    
    # Cerrar el dataset C07 ya que no lo necesitamos más
    ds_c07.close()
    
    # Parsear el string ISO 8601 a datetime
    from dateutil.parser import parse
    image_time_dt = parse(time_coverage_start).replace(tzinfo=utc)

    # Diferencias de brillo y temperatura (BTD)
    delta1 = c13 - c15
    delta2 = c11 - c13
    delta3 = c07 - c13

    print("Fecha y hora ", image_time_dt.strftime("%Y-%m-%d %H:%M:%S UTC"))
    sza = get_sun_zenith_angle(lat, lon, image_time_dt, eph, ts)

    # --- Clasificación de ceniza ---
    # Máscaras de iluminación
    mask_noche = sza > 85
    mask_dia = sza < 70
    mask_crepusculo = (sza >= 70) & (sza <= 85)

    # Cálculo de textura
    media, dst = genera_media_dst(delta1, kernel_size=5)

    # Usando np.select para mayor claridad
    cond_nhood = [
        (delta1 < 0) & (delta1 - (media * dst) < -1),
        (delta1 < 1) & (delta1 - (media * dst) < -1)
    ]
    val_nhood = [1, 2]
    nhood = np.select(cond_nhood, val_nhood, default=0)

    # Clasificación inicial por iluminación
    # Noche
    cond_noche = [
        ((delta1 < 0) & (delta2 > 0) & (delta3 > 2)) | (nhood == 1),
        ((delta1 < 1) & (delta2 > -0.5) & (delta3 > 2)) | (nhood == 2)
    ]
    ceniza_noche = np.select(cond_noche, [1, 2], default=0)

    # Crepúsculo
    cond_crepusculo = [
        ((delta1 < 0) & (delta2 > 0) & (delta3 > 2)) | (nhood == 1),
        ((delta1 < 1) & (delta2 > -0.5) & (delta3 > 2) & (c04 > 0.002) & (c13 < 273.15)) | (nhood == 2)
    ]
    ceniza_crepusculo = np.select(cond_crepusculo, [1, 2], default=0)

    # Día
    cond_dia = [
        ((delta1 < 0) & (delta2 > 0) & (delta3 > 2)) | (nhood == 1),
        ((delta1 < 1) & (delta2 > -0.5) & (delta3 > 2) & (c04 > 0.002)) | (nhood == 2)
    ]
    ceniza_dia = np.select(cond_dia, [1, 2], default=0)

    # Combinar según la máscara de iluminación
    ceniza_tiempo = np.select(
        [mask_noche, mask_crepusculo, mask_dia],
        [ceniza_noche, ceniza_crepusculo, ceniza_dia],
        default=0
    )

    # Refinamiento de umbrales (usando np.select)
    cond_um1 = [
        ceniza_tiempo == 1,
        (ceniza_tiempo == 2) & (delta2 >= -1),
        (ceniza_tiempo == 2) & (delta2 >= -1.5)
    ]
    val_um1 = [1, 2, 3]
    ceniza_um1 = np.select(cond_um1, val_um1, default=ceniza_tiempo)

    cond_um2 = [
        (ceniza_um1 <= 2) & (delta3 <= 0),
        (ceniza_um1 >= 3) & (delta3 <= 1.5)
    ]
    ceniza_um2 = np.select(cond_um2, [0, 0], default=ceniza_um1)

    # Clasificación final basada en fase de la nube
    cond_final = [
        (ceniza_um2 == 2) & (phase == 1), # Nube de agua
        (ceniza_um2 == 2) & (phase == 4), # Hielo
        (ceniza_um2 == 3) & (phase == 1), # Nube de agua
        (ceniza_um2 == 3) & (phase >= 2)  # Superfría
    ]
    val_final = [3, 0, 0, 0]
    ceniza = np.select(cond_final, val_final, default=ceniza_um2)
    
    # Marcar píxeles sin datos válidos como 255 (nodata)
    ceniza = ceniza.astype(np.uint8)
    ceniza[~valid_data_mask] = 255

    print("\n--- Clasificación Final de Ceniza ---")
    print(f"Forma del array final: {ceniza.shape}")
    print(f"Valores únicos en la clasificación: {np.unique(ceniza)}")
    print(f"Píxeles sin datos (nodata=255): {np.sum(~valid_data_mask)} de {ceniza.size} ({100*np.sum(~valid_data_mask)/ceniza.size:.2f}%)")

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

    # Reproyectar a coordenadas geográficas si se especificó
    if bbox and reproject_to_geo:
        print("\nReproyectando a coordenadas geográficas (EPSG:4326)...")
        
        # Definir los límites EXACTOS en coordenadas geográficas (bbox original, sin expansión)
        # bbox = [lon_min, lat_max, lon_max, lat_min]
        lon_min, lat_max, lon_max, lat_min = bbox
        
        print(f"Límites geográficos objetivo: lon[{lon_min}, {lon_max}], lat[{lat_min}, {lat_max}]")
        
        # Calcular resolución y dimensiones objetivo
        from rasterio.warp import Resampling
        from affine import Affine
        
        # Definir una resolución objetivo razonable (~0.02° ≈ 2km)
        # Esto es aproximadamente equivalente a la resolución GOES en esta latitud
        target_resolution_deg = 0.02
        
        # Calcular las dimensiones necesarias para cubrir el bbox con esta resolución
        lon_range = lon_max - lon_min
        lat_range = lat_max - lat_min
        
        dst_width = int(np.round(lon_range / target_resolution_deg))
        dst_height = int(np.round(lat_range / target_resolution_deg))
        
        # Ahora calcular la resolución EXACTA necesaria para que el bbox sea preciso
        exact_lon_res = lon_range / dst_width
        exact_lat_res = lat_range / dst_height
        
        # Crear transformación afín exacta
        dst_transform = Affine(
            exact_lon_res, 0.0, lon_min,
            0.0, -exact_lat_res, lat_max
        )
        
        print(f"Resolución objetivo: lon={exact_lon_res:.6f}°, lat={exact_lat_res:.6f}°")
        print(f"Dimensiones objetivo: {dst_height} x {dst_width} píxeles")
        
        # Reproyectar directamente con transformación y dimensiones exactas
        output_da = output_da.rio.reproject(
            dst_crs="EPSG:4326",
            shape=(dst_height, dst_width),
            transform=dst_transform,
            resampling=Resampling.nearest,
            nodata=255
        )
        
        print(f"Forma después de reproyección: {output_da.shape}")
        print(f"Límites después de reproyección: {output_da.rio.bounds()}")
        print(f"CRS final: EPSG:4326 (lat/lon)")

    print(f"\nGuardando resultado en: {output_path}")
    
    # Definir tabla de colores (hardcoded desde ash.cpt)
    color_table = {
        0: (0, 0, 0, 0),           # clear - transparente (sin ceniza detectada)
        1: (255, 0, 0, 255),       # ash - rojo
        2: (255, 165, 0, 255),     # probable - naranja
        3: (255, 255, 0, 255),     # less probable - amarillo
        4: (0, 255, 0, 255),       # cloud - verde
        5: (0, 0, 255, 255),       # noise - azul
        255: (0, 0, 0, 0)          # nodata - transparente (sin datos válidos)
    }
    
    # Convertir a RGBA para que QGIS respete la transparencia
    # Usar los datos del output_da (que pueden estar reproyectados)
    data_to_save = output_da.values
    height, width = data_to_save.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    
    for value, (r, g, b, a) in color_table.items():
        mask = (data_to_save == value)
        rgba[mask, 0] = r  # Red
        rgba[mask, 1] = g  # Green
        rgba[mask, 2] = b  # Blue
        rgba[mask, 3] = a  # Alpha
    
    # Guardar como GeoTIFF RGBA
    import rasterio
    from rasterio.transform import from_bounds
    
    # Obtener transform y CRS del DataArray original
    transform = output_da.rio.transform()
    crs = output_da.rio.crs
    
    with rasterio.open(
        output_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=4,  # 4 bandas: R, G, B, A
        dtype=rasterio.uint8,
        crs=crs,
        transform=transform,
        compress='LZW',
        photometric='RGB'
    ) as dst:
        dst.write(rgba[:, :, 0], 1)  # Red
        dst.write(rgba[:, :, 1], 2)  # Green
        dst.write(rgba[:, :, 2], 3)  # Blue
        dst.write(rgba[:, :, 3], 4)  # Alpha
        dst.colorinterp = [
            rasterio.enums.ColorInterp.red,
            rasterio.enums.ColorInterp.green,
            rasterio.enums.ColorInterp.blue,
            rasterio.enums.ColorInterp.alpha
        ]
    
    print("¡Archivo GeoTIFF guardado con éxito (formato RGBA con transparencia)!")
    
    # Crear imagen PNG a color si se solicita
    if create_png:
        # Determinar la ruta del archivo PNG
        png_path = Path(str(output_path).replace('.tif', '.png'))
        
        # Buscar el archivo ash.cpt en el directorio del script
        script_dir = Path(__file__).parent
        cpt_path = script_dir / 'ash.cpt'
        
        print("\n--- Generando imagen PNG a color ---")
        
        # Calcular los límites geográficos del DataArray
        # Si está reproyectado a EPSG:4326, usar las coordenadas directamente
        # Si está en proyección GOES, necesitamos convertir las esquinas
        png_bounds = None
        
        if output_da.rio.crs is not None:
            try:
                # Obtener los límites del raster
                bounds_array = output_da.rio.bounds()
                # bounds_array es (left, bottom, right, top)
                # Necesitamos convertirlo a (lon_min, lat_max, lon_max, lat_min)
                
                if output_da.rio.crs.to_string() == "EPSG:4326":
                    # Ya está en coordenadas geográficas
                    png_bounds = (bounds_array[0], bounds_array[3], bounds_array[2], bounds_array[1])
                else:
                    # Para otras proyecciones (ej: GOES), transformar las esquinas a EPSG:4326
                    # MapDrawer se encargará de manejar correctamente la proyección
                    from pyproj import Transformer
                    transformer = Transformer.from_crs(output_da.rio.crs, "EPSG:4326", always_xy=True)
                    
                    # Transformar las esquinas para obtener límites aproximados
                    lon_min, lat_min = transformer.transform(bounds_array[0], bounds_array[1])
                    lon_max, lat_max = transformer.transform(bounds_array[2], bounds_array[3])
                    
                    png_bounds = (lon_min, lat_max, lon_max, lat_min)
                
                print(f"Límites geográficos del PNG: lon [{png_bounds[0]:.2f}, {png_bounds[2]:.2f}], lat [{png_bounds[3]:.2f}, {png_bounds[1]:.2f}]")
                
            except Exception as e:
                print(f"Advertencia: No se pudieron calcular límites geográficos: {e}")
                print("  El PNG se generará sin mapa base.")
        
        create_color_png(
            output_da.data, 
            png_path, 
            cpt_path if cpt_path.exists() else None,
            bounds=png_bounds,
            timestamp=image_time_dt,
            crs=output_da.rio.crs
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detecta ceniza volcánica a partir de datos GOES L2.")
    parser.add_argument('--path', type=Path, default=l2_path, 
                        help=f"Ruta al directorio de datos L2. Por defecto: {l2_path}")
    parser.add_argument('--moment', type=str, default=None, 
                        help="Momento o rango a procesar. Formatos: 'YYYYjjjHHMM', 'YYYYMMDDHHMM', o 'YYYYMMDDHHmm-HHmm'. "
                             "Por defecto, se calcula el más reciente.")
    parser.add_argument('--output', type=str, default=None, 
                        help="Ruta de salida para el GeoTIFF. Puede ser un archivo (ej: 'resultado.tif') o un directorio (ej: '/data/salida/'). "
                             "Si es un directorio, se genera automáticamente el nombre 'ceniza_[momento].tif' (o con sufijo '_geo' si se reproyecta). "
                             "Por defecto: './ceniza_[momento].tif'")
    parser.add_argument('--clip', type=str, choices=list(CLIP_REGIONS_WITH_GEO.keys()), default=None, 
                        help=f"Región para recortar el resultado final. Agrega 'geo' al final para reproyectar a lat/lon. Opciones: {', '.join(CLIP_REGIONS.keys())} (o con sufijo 'geo')")
    parser.add_argument('--png', action='store_true', 
                        help="Genera también una imagen PNG a color con la misma resolución que el GeoTIFF")
    parser.add_argument('--date-tree', action='store_true', 
                        help="Usa estructura de directorios YYYY/MM/DD dentro de --path para localizar los archivos según el momento especificado")
    parser.add_argument('--dry-run', action='store_true',
                        help="Realiza una verificación de archivos para el momento o rango especificado sin procesar los datos. "
                             "Informa qué momentos tienen datos completos y cuáles no.")
    
    args = parser.parse_args()

    # --- 1. Determinar la lista de momentos a procesar ---
    if args.moment:
        try:
            moment_list = parse_moment_string(args.moment)
        except ValueError as e:
            print(f"Error: {e}")
            exit(1)
    else:
        # Obtiene el momento más reciente en formato 'YYYYjjjHHMM'
        moment_list = [get_moment()]

    # --- 2. Verificación de archivos (Pre-flight check) ---
    print("\n--- Verificando disponibilidad de archivos ---")
    productos_requeridos = ["ACTP", "C04", "C07", "C11", "C13", "C14", "C15"]
    momentos_validos = []
    momentos_fallidos = []

    for moment_info in moment_list:
        files = get_filelist_from_path(args.path, moment_info, productos_requeridos, use_date_tree=args.date_tree, verbose=False)
        if len(files) == len(productos_requeridos):
            momentos_validos.append(moment_info)
        else:
            momentos_fallidos.append(moment_info[0]) # Solo guardamos el string del momento para el reporte

    # --- 3. Reportar resultados de la verificación ---
    group_and_report_failures(momentos_fallidos)

    if momentos_validos:
        print(f"\nSe encontraron datos completos para {len(momentos_validos)} momentos.")
    
    if not momentos_validos:
        print("\nNo se encontraron datos completos para ningún momento en el rango especificado. Terminando.")
        exit(0)

    if args.dry_run:
        print("\nModo 'dry-run' activado. No se realizará ningún procesamiento. Terminando.")
        exit(0)

    # --- 4. Procesar momentos válidos ---
    print(f"\n--- Iniciando procesamiento para {len(momentos_validos)} momentos válidos ---")
    
    # Cargar recursos pesados una sola vez
    print("Cargando efemérides de Skyfield (una sola vez)...")
    eph_global = load('de421.bsp')
    ts_global = load.timescale()
    
    for i, moment_info in enumerate(momentos_validos):
        moment_a_procesar = moment_info[0]
        print(f"\n[{i+1}/{len(momentos_validos)}] Procesando momento: {moment_a_procesar}")
        
        # Generar nombre de archivo de salida para cada momento
        if args.output:
            outp = str(args.output)
            output_path = Path(outp)
            
            # Determinar si es un directorio o un archivo:
            # 1. Si termina en path separator -> directorio explícito
            # 2. Si existe y es directorio -> directorio
            # 3. Si no existe pero no tiene extensión .tif/.png -> asumimos directorio
            # 4. En otro caso -> archivo único
            
            is_directory = (
                outp.endswith(os.path.sep) or
                output_path.is_dir() or
                (not output_path.exists() and not outp.endswith('.tif') and not outp.endswith('.png'))
            )
            
            if is_directory:
                # Tratarlo como directorio
                output_dir = output_path
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    print(f"Error creando el directorio de salida '{output_dir}': {e}")
                    raise
                
                # Generar nombre de archivo según momento y región
                if args.clip and args.clip.endswith('geo'):
                    filename = f"ceniza_{moment_a_procesar}_geo.tif"
                else:
                    filename = f"ceniza_{moment_a_procesar}.tif"
                output_file = output_dir / filename
            else:
                # Tratarlo como archivo único
                if i > 0:
                    print("Advertencia: Se especificó un único archivo de salida para un rango. Solo se procesará el primer momento válido.")
                    break
                output_file = output_path
        else:
            if args.clip and args.clip.endswith('geo'):
                output_file = Path(f"./ceniza_{moment_a_procesar}_geo.tif")
            else:
                output_file = Path(f"./ceniza_{moment_a_procesar}.tif")

        try:
            main(
                data_path=args.path, 
                moment_info=moment_info, 
                output_path=output_file, 
                clip_region=args.clip, 
                create_png=args.png, 
                use_date_tree=args.date_tree,
                eph=eph_global,
                ts=ts_global
            )
        except Exception as e:
            print(f"\n*** Error procesando momento {moment_a_procesar}: {e}")
            print("Continuando con el siguiente momento...")
            import traceback
            traceback.print_exc()
            continue

    print("\n--- Procesamiento completado. ---")
