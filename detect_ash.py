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


# Ruta al directorio de datos L2
l2_path = Path("/data/ceniza/2019/spring")

# Regiones predefinidas para recorte [lon_min, lat_max, lon_max, lat_min]
CLIP_REGIONS = {
    'centromex': [-107.2319400, 22.7180385, -93.8363933, 14.9386282],
    'popocatepetl': [-100.2622042, 20.5800993, -96.8495200, 18.2893953]
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


def get_filelist_from_path(data_path, moment, products):
    """
    Busca archivos en un directorio que coincidan con un momento 'YYYYjjjhhmm" 
    y que contengan uno de los identificadores de 'products' en su nombre.
    """
    
    patron_base = f"*s{moment}*.nc"

    print(f"Buscando archivos en: {data_path}")
    print(f"Usando patrón base: {patron_base}")
    print(f"Filtrando por productos: {products}")

    lista_archivos = [] 

    # Comprobar si el directorio existe antes de buscar
    if not data_path.is_dir():
        print(f"Error: El directorio '{data_path}' no existe. Por favor, comprueba la ruta.")
        # Se devolverá la lista vacía
    else:
        # Obtenemos *todos* los archivos que coinciden con el tiempo (patrón base)
        archivos_por_tiempo = data_path.glob(patron_base)
        
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


def main(data_path, moment, output_path, nav_file=None, clip_region=None):
    """Función principal para ejecutar el proceso de detección de cenizas."""
    print(f"Iniciando detección para el momento: {moment}")
    
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
    if nav_file:
        productos = ["ACTP", "C04", "C07", "C11", "C13", "C14", "C15"]
        print(f"Usando archivo NAV especificado: {nav_file}")
    else:
        productos = ["ACTP", "C04", "C07", "C11", "C13", "C14", "C15", "NAV"]
    
    archivos = get_filelist_from_path(data_path, moment, productos)
    if not archivos:
        print(f"Error: No se encontró ningún archivo con este momento {moment}.")
        return
    if len(archivos) != len(productos):
        print(f"Error: Se encontraron {len(archivos)} archivos, pero se esperaban {len(productos)}.")
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
    
    # Si se especificó un archivo NAV, lo agregamos al diccionario
    if nav_file:
        file_paths["NAV"] = str(nav_file)
        print(f"Asociando NAV con: {nav_file}")
    
    print("\n¡Éxito! Todos los productos requeridos fueron encontrados.")

    # Usamos xarray para abrir los archivos NetCDF
    print("\nLeyendo datos con xarray...")
    ds_c07 = xr.open_dataset(file_paths["C07"])
    
    # Obtener parámetros de proyección GOES desde el NetCDF
    goes_proj = ds_c07['goes_imager_projection']
    
    # Construir el CRS usando el string Proj4 de GOES-16
    from pyproj import CRS
    from affine import Affine
    proj_string = (f"+proj=geos +h={goes_proj.perspective_point_height} "
                   f"+lon_0={goes_proj.longitude_of_projection_origin} "
                   f"+sweep={goes_proj.sweep_angle_axis} "
                   f"+a={goes_proj.semi_major_axis} "
                   f"+b={goes_proj.semi_minor_axis} "
                   f"+units=m +no_defs")
    
    crs_goes = CRS.from_proj4(proj_string)
    
    # Configurar geo_template con la información espacial
    geo_template = ds_c07['CMI']
    
    # Obtener las coordenadas x e y para el geotransform
    x_coords = ds_c07['x'].values * goes_proj.perspective_point_height
    y_coords = ds_c07['y'].values * goes_proj.perspective_point_height
    
    # --- Construir la geotransformación manualmente ---
    # La geotransformación define cómo los píxeles se mapean a coordenadas espaciales.
    # Formato: (x_res, rot_y, x_ul, rot_x, y_res, y_ul)
    # 1. Calcular resolución (tamaño del píxel) en metros
    x_res = x_coords[1] - x_coords[0]
    y_res = y_coords[1] - y_coords[0] # Será negativo porque el origen es arriba-izquierda
    # 2. Coordenada de la esquina superior izquierda (Upper Left)
    x_ul = x_coords[0] - x_res / 2.0
    y_ul = y_coords[0] - y_res / 2.0
    # 3. Crear la matriz de transformación afín
    geotransform = Affine(x_res, 0.0, x_ul, 0.0, y_res, y_ul)
    
    # Leemos las demás variables
    c04 = xr.open_dataset(file_paths["C04"])['CMI'].data
    c07 = ds_c07['CMI'].data
    c11 = xr.open_dataset(file_paths["C11"])['CMI'].data
    c13 = xr.open_dataset(file_paths["C13"])['CMI'].data
    c14 = xr.open_dataset(file_paths["C14"])['CMI'].data
    c15 = xr.open_dataset(file_paths["C15"])['CMI'].data
    phase = xr.open_dataset(file_paths["ACTP"])['Phase'].data
    
    # Extraemos lat/lon para el cálculo del ángulo cenital solar
    lat = xr.open_dataset(file_paths["NAV"])['Latitude'].data
    lon = xr.open_dataset(file_paths["NAV"])['Longitude'].data

    # Obtenemos fecha y hora de los datos desde el atributo time_coverage_start
    # que está en formato ISO 8601
    time_coverage_start = ds_c07.attrs['time_coverage_start']
    # Parsear el string ISO 8601 a datetime
    from dateutil.parser import parse
    image_time_dt = parse(time_coverage_start).replace(tzinfo=utc)

    # Diferencias de brillo y temperatura (BTD)
    delta1 = c13 - c15
    delta2 = c11 - c13
    delta3 = c07 - c13

    print("Fecha y hora ", image_time_dt.strftime("%Y-%m-%d %H:%M:%S UTC"))
    sza = get_sun_zenith_angle(lat, lon, image_time_dt)

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
        (ceniza_tiempo == 2) & (delta2 >= -1.5),
        (ceniza_tiempo == 2) & (delta2 < -1.5)
    ]
    val_um1 = [3, 0]
    ceniza_um1 = np.select(cond_um1, val_um1, default=ceniza_tiempo)

    cond_um2 = [
        (ceniza_um1 <= 2) & (delta3 <= 0),
        (ceniza_um1 >= 3) & (delta3 <= 1.5)
    ]
    ceniza_um2 = np.select(cond_um2, [0, 0], default=ceniza_um1)

    # Clasificación final basada en fase de la nube
    cond_final = [
        (ceniza_um2 == 2) & (phase == 1), # Nube de agua
        (ceniza_um2 == 2) & (phase == 4), # Polvo
        (ceniza_um2 == 3) & (phase == 1), # Nube de agua
        (ceniza_um2 == 3) & (phase >= 2)  # Hielo, etc.
    ]
    val_final = [4, 0, 5, 0]
    ceniza = np.select(cond_final, val_final, default=ceniza_um2)

    print("\n--- Clasificación Final de Ceniza ---")
    print(f"Forma del array final: {ceniza.shape}")
    print(f"Valores únicos en la clasificación: {np.unique(ceniza)}")

    # --- Guardado en GeoTIFF ---
    # Creamos un DataArray de xarray con el resultado, usando la plantilla geoespacial
    output_da = xr.DataArray(
        data=ceniza.astype(np.uint8), # Los datos de la clasificación
        coords={
            'y': y_coords, # Las coordenadas Y en metros que calculamos
            'x': x_coords  # Las coordenadas X en metros que calculamos
        },
        dims=geo_template.dims,
        name="ash_detection",
        attrs={"long_name": "Ash Detection Classification", "units": "category"}
    )
    # Asignamos la información de proyección (CRS) y la geotransformación
    output_da.rio.write_crs(crs_goes, inplace=True)
    output_da.rio.write_transform(geotransform, inplace=True)

    # Aplicar recorte si se especificó una región
    if bbox:
        print(f"\nRecortando a región: {bbox}")
        # bbox en formato [lon_min, lat_max, lon_max, lat_min]
        # rio.clip_box espera (minx, miny, maxx, maxy) en el CRS del DataArray
        # Como nuestro bbox está en coordenadas geográficas (lon/lat), 
        # debemos transformar las coordenadas del bbox a la proyección GOES
        from pyproj import Transformer
        
        # Crear transformador de lat/lon (EPSG:4326) a la proyección GOES
        transformer = Transformer.from_crs("EPSG:4326", crs_goes, always_xy=True)
        
        # Transformar las esquinas del bbox
        # bbox = [lon_min, lat_max, lon_max, lat_min]
        lon_min, lat_max, lon_max, lat_min = bbox
        
        # Transformar esquina inferior izquierda (lon_min, lat_min)
        x_min, y_min = transformer.transform(lon_min, lat_min)
        # Transformar esquina superior derecha (lon_max, lat_max)
        x_max, y_max = transformer.transform(lon_max, lat_max)
        
        print(f"Límites en coordenadas GOES: x=[{x_min:.2f}, {x_max:.2f}], y=[{y_min:.2f}, {y_max:.2f}]")
        
        # Aplicar el recorte usando las coordenadas transformadas
        output_da = output_da.rio.clip_box(
            minx=x_min,
            miny=y_min,
            maxx=x_max,
            maxy=y_max
        )
        print(f"Forma del array recortado: {output_da.shape}")
        
        # Reproyectar a coordenadas geográficas si se especificó
        if reproject_to_geo:
            print("\nReproyectando a coordenadas geográficas (EPSG:4326)...")
            
            # Definir los límites en coordenadas geográficas
            # bbox = [lon_min, lat_max, lon_max, lat_min]
            # Calcular una resolución apropiada basada en el tamaño del recorte original
            # Usamos aproximadamente el mismo número de píxeles
            height, width = output_da.shape
            
            # Calcular resolución en grados
            lon_range = lon_max - lon_min
            lat_range = lat_max - lat_min
            lon_res = lon_range / width
            lat_res = lat_range / height
            
            print(f"Resolución objetivo: {lon_res:.6f}° (lon) x {lat_res:.6f}° (lat)")
            
            # Reproyectar usando rioxarray
            output_da = output_da.rio.reproject(
                dst_crs="EPSG:4326",
                shape=(height, width),  # Mantener aproximadamente el mismo número de píxeles
                resampling=0  # Nearest neighbor para datos categóricos
            )
            print(f"Forma después de reproyección: {output_da.shape}")
            print(f"CRS final: EPSG:4326 (lat/lon)")

    print(f"\nGuardando resultado en: {output_path}")
    output_da.rio.to_raster(output_path, driver="GTiff", dtype="uint8", compress='LZW')
    print("¡Archivo GeoTIFF guardado con éxito!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detecta ceniza volcánica a partir de datos GOES L2.")
    parser.add_argument('--path', type=Path, default=l2_path, help=f"Ruta al directorio de datos L2. Por defecto: {l2_path}")
    parser.add_argument('--moment', type=str, default=None, help="Momento a procesar en formato 'YYYYjjjHHMM'. Por defecto, se calcula el más reciente.")
    parser.add_argument('--output', type=Path, default=None, help="Ruta del archivo GeoTIFF de salida. Por defecto, se genera un nombre basado en el momento.")
    parser.add_argument('--nav', type=Path, default=None, help="Ruta a un archivo NAV específico. Si se especifica, no se buscará en el directorio de datos.")
    parser.add_argument('--clip', type=str, choices=list(CLIP_REGIONS_WITH_GEO.keys()), default=None, 
                        help=f"Región para recortar el resultado final. Agrega 'geo' al final para reproyectar a lat/lon. Opciones: {', '.join(CLIP_REGIONS.keys())} (o con sufijo 'geo')")
    
    args = parser.parse_args()

    if args.moment:
        moment_a_procesar = args.moment
    else:
        # Esta función obtiene el momento más reciente en formato 'YYYYjjjhhmm'
        moment_a_procesar = get_moment()

    if args.output:
        output_file = args.output
    else:
        # Genera un nombre de archivo de salida por defecto
        output_file = Path(f"./ceniza_{moment_a_procesar}.tif")

    # Descomentar para pruebas con datos específicos
    # moment_a_procesar = "20191001731"

    main(args.path, moment_a_procesar, output_file, nav_file=args.nav, clip_region=args.clip)
