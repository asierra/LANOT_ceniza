#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import numpy as np
from scipy import ndimage
from pathlib import Path
from netCDF4 import Dataset
from skyfield.api import utc
from skyfield.api import Topos, load
from netCDF4 import num2date 


# Ruta al directorio de datos L2
l2_path = Path("/data/output/abi/l2/conus")

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


def get_filelist_from_path(moment, products):
    """
    Busca archivos en un directorio que coincidan con un momento 'YYYYjjjhhmm" 
    y que contengan uno de los identificadores de 'products' en su nombre.
    """
    
    patron_base = f"*s{moment}*.nc"

    print(f"Buscando archivos en: {l2_path}")
    print(f"Usando patrón base: {patron_base}")
    print(f"Filtrando por productos: {products}")

    lista_archivos = [] 

    # Comprobar si el directorio existe antes de buscar
    if not l2_path.is_dir():
        print(f"Error: El directorio '{l2_path}' no existe. Por favor, comprueba la ruta.")
        # Se devolverá la lista vacía
    else:
        # Obtenemos *todos* los archivos que coinciden con el tiempo (patrón base)
        archivos_por_tiempo = l2_path.glob(patron_base)
        
        # Filtramos la lista
        lista_archivos = [
            str(p) for p in archivos_por_tiempo 
            if any(
                # Si el producto es una banda (ej. "C07"), busca también "CMIP" en el nombre.
                (prod in p.name and "CMIP" in p.name) if prod.startswith("C") 
                # Para otros productos (ej. "ACTP"), solo busca el producto.
                else (prod in p.name) 
                for prod in products
            )
        ]
    return lista_archivos
    

def get_sun_zenith_angle(lat_array, lon_array, image_time_dt):
    """
    Calcula el ángulo cenital solar para cada punto de un arreglo lat/lon.
    
    Skyfield no maneja bien arrays grandes, así que calculamos la posición
    del Sol (RA/Dec) una sola vez y luego usamos geometría esférica para
    calcular el ángulo cenital en cada píxel.
    """
    # --- 1. Cargar las efemérides y la escala de tiempo ---
    eph = load('de421.bsp')
    ts = load.timescale()
    
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


def genera_media_dst(arreglo, kernel_size=5):
    """
    Calcula la media y la desviación estándar local (kernel) de un arreglo, ignorando NaNs.

    Para la media, utiliza un método optimizado con uniform_filter para mayor rendimiento.
    Para la desviación estándar, utiliza generic_filter con np.nanstd.

    Args:
        arreglo (np.ndarray): El arreglo de entrada, puede contener NaNs.
        kernel_size (int): El tamaño de la ventana cuadrada para el cálculo.

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

    # --- Desviación Estándar (usando generic_filter) ---
    kernel_std = ndimage.generic_filter(
        arreglo, 
        np.nanstd, 
        size=kernel_size,
        mode='constant',
        cval=np.nan
    )

    print(f"\n--- Resultados del Kernel ({kernel_size}x{kernel_size}) ---")
    print(f"Forma del array de Media: {kernel_media.shape}")
    print(f"Forma del array de Desv. Estándar: {kernel_std.shape}")

    return kernel_media, kernel_std


if __name__ == "__main__":
    # Esta función obtiene el momento más reciente en formato 'YYYYjjjhhmm'
    ahora = get_moment();
    print(f"Momento: {ahora}")
    ahora = "20253161601"  # Mis datos de prueba
    productos = ["ACTP", "C04", "C07", "C11", "C13", "C14", "C15", "NAV"]
    archivos = get_filelist_from_path(ahora, productos)
    if not archivos:
        print(f"Error: No se encontró ningún archivo con este momento {ahora}.")
        exit(-1)
    if len(archivos) != len(productos):
        print(f"Error: Se encontraron {len(archivos)} archivos, pero se esperaban {len(productos)}.")
        exit(-1)

    print(f"Se encontraron los {len(archivos)} archivos requeridos.")
    
    # Creamos un diccionario para almacenar los datasets abiertos.
    datasets = {}
    for archivo_path in archivos:
        # Identificamos a qué producto pertenece cada archivo
        for prod in productos:
            # La lógica debe coincidir con la de get_filelist_from_path
            is_band_product = prod.startswith("C") and "CMIP" in archivo_path
            is_other_product = not prod.startswith("C")

            if (is_band_product or is_other_product) and prod in archivo_path:
                print(f"Abriendo {prod} desde: {archivo_path}")
                datasets[prod] = Dataset(archivo_path, 'r')
                break # Pasamos al siguiente archivo una vez que encontramos su producto
    print("\n¡Éxito! Todos los productos requeridos fueron encontrados y abiertos.")
   
    # Asignamos los datasets a variables individuales para un acceso directo.
    print("\nExtrayendo los arrays de datos de cada producto...")
    # Tanto fd como conus tienen huecos, los llenamos con NaN para evitar problemas.
    phase = datasets["ACTP"].variables['Phase'][:]
    c04 = datasets["C04"].variables['CMI'][:].filled(np.nan)
    c07 = datasets["C07"].variables['CMI'][:].filled(np.nan)
    c11 = datasets["C11"].variables['CMI'][:].filled(np.nan)
    c13 = datasets["C13"].variables['CMI'][:].filled(np.nan)
    c14 = datasets["C14"].variables['CMI'][:].filled(np.nan)
    c15 = datasets["C15"].variables['CMI'][:].filled(np.nan)
    lat = datasets["NAV"].variables['Latitude'][:].filled(np.nan)
    lon = datasets["NAV"].variables['Longitude'][:].filled(np.nan)
    
    # Obtenemos fecha y hora de estos datos
    time_var = datasets["C07"].variables['t']
    image_time_cft = num2date(time_var[0], time_var.units)
    # Convertimos el objeto cftime a un datetime estándar de Python.
    image_time_naive = datetime.datetime(image_time_cft.year, image_time_cft.month, image_time_cft.day, 
                                      image_time_cft.hour, image_time_cft.minute, image_time_cft.second)
    # Skyfield requiere un datetime "aware". Le asignamos la zona horaria UTC.
    image_time_dt = image_time_naive.replace(tzinfo=utc)

    # Transmisividad
    delta1 = c13 - c15
    delta2 = c11 - c13
    delta3 = c07 - c13

    print("Fecha y hora ", image_time_dt.strftime("%Y-%m-%d %H:%M:%S UTC"))
    sza = get_sun_zenith_angle(lat, lon, image_time_dt)

    mask_noche = sza > 85
    print("\nMáscara SZA > 85 (Sol Bajo):\n", mask_noche)
    mask_dia = sza < 70
    print("\nMáscara SZA < 70 (Sol Alto):\n", mask_dia)
    mask_crepusculo = (sza >= 70) & (sza <= 85)
    print("\nMáscara 70 <= SZA <= 85 (Intermedio):\n", mask_crepusculo)

    media, dst = genera_media_dst(delta1, kernel_size=5)

    ceniza = np.zeros_like(delta1, dtype=np.int8)
    ceniza_dia = np.zeros_like(delta1, dtype=np.int8)
    ceniza_noche = np.zeros_like(delta1, dtype=np.int8)
    ceniza_crepusculo = np.zeros_like(delta1, dtype=np.int8)

    ceniza = np.where((delta1 < 0) & (delta1 - (media*dst) < -1), 1,
                   np.where((delta1 < 1) & (delta1 - (media*dst) < -1), 2, 0))

    ceniza_dia = np.where(mask_dia, np.nan, ceniza)

