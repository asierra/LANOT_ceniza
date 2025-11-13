#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
from pathlib import Path
from netCDF4 import Dataset
import numpy as np
from skyfield.api import utc
from skyfield.api import Topos, load
from netCDF4 import num2date # Utilidad para convertir el tiempo de netCDF


def get_moment(is_conus=True):
    """
    Calcula la hora más reciente con minutos en múltiplos de 10
    o que terminen en 1 o 6
    """
    # Obtener la hora actual en UTC 
    ahora_utc = datetime.datetime.now(datetime.timezone.utc)

    # Calcular los minutos redondeados al múltiplo de 10 más reciente (hacia abajo)
    minuto_redondeado = (ahora_utc.minute // 10) * 10

    # Crear el nuevo objeto datetime con los minutos ajustados
    # También reiniciamos segundos y microsegundos para estar exactamente en esa marca
    dt_ajustado = ahora_utc.replace(minute=minuto_redondeado, second=0, microsecond=0)  

    # Formatear la fecha al formato deseado: "YYYYjjjhhmm"
    moment = dt_ajustado.strftime("%Y%j%H%M")
    return moment


def get_filelist_from_path(moment, products):
    """
    Busca archivos en un directorio que coincidan con un momento='YYYYjjjhhmm" 
    y que contengan uno de los identificadores de 'products' en su nombre.
    """
    l2_path = Path("/data/output/abi/l2/conus")
    
    # 1. Modificamos el patrón para que use un comodín (wildcard) *.
    #    Ahora buscará cualquier archivo que *comience* con "s{moment}".
    patron_base = f"*s{moment}*.nc"

    print(f"Buscando archivos en: {l2_path}")
    print(f"Usando patrón base: {patron_base}")
    print(f"Filtrando por productos: {products}")

    lista_archivos = [] # Inicializar como lista vacía

    # Comprobar si el directorio existe antes de buscar
    if not l2_path.is_dir():
        print(f"Error: El directorio '{l2_path}' no existe. Por favor, comprueba la ruta.")
        # Se devolverá la lista vacía definida arriba
    else:
        # 2. Obtenemos *todos* los archivos que coinciden con el tiempo (patrón base)
        archivos_por_tiempo = l2_path.glob(patron_base)
        
        # 3. Filtramos la lista
        # Iteramos sobre cada archivo encontrado (objeto Path 'p')
        # y nos quedamos solo con aquellos cuyo nombre (p.name)
        # contenga *alguno* de los strings en la lista 'products' con una lógica especial.
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
    Calcula el ángulo cenital solar para cada punto de una grilla lat/lon.
    
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


if __name__ == "__main__":
    ahora = get_moment();
    ahora = "20253161601"
    productos = ["ACTP", "C04", "C07", "C11", "C13", "C14", "C15", "NAV"]
    archivos = get_filelist_from_path(ahora, productos)
    if not archivos:
        print("Error: No se encontró ningún archivo.")
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
   
    # Asignando los datasets a variables individuales para un acceso más directo.
    print("\nExtrayendo los arrays de datos de cada producto...")
    phase = datasets["ACTP"].variables['Phase'][:]
    c04 = datasets["C04"].variables['CMI'][:]
    c07 = datasets["C07"].variables['CMI'][:]
    c11 = datasets["C11"].variables['CMI'][:]
    c13 = datasets["C13"].variables['CMI'][:]
    c14 = datasets["C14"].variables['CMI'][:]
    c15 = datasets["C15"].variables['CMI'][:]
    # --- Solución al problema de Broadcasting en Skyfield ---
    # Los arrays de lat/lon de los archivos NetCDF son MaskedArrays.
    # Skyfield no puede manejar la máscara, causando el ValueError.
    # La solución es convertir los MaskedArrays a arrays de NumPy estándar,
    # reemplazando los valores enmascarados con NaN (Not a Number).
    lat = datasets["NAV"].variables['Latitude'][:].filled(np.nan)
    lon = datasets["NAV"].variables['Longitude'][:].filled(np.nan)
    
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