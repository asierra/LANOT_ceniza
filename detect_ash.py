#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
from pathlib import Path
from netCDF4 import Dataset
import numpy as np


def get_moment():
    # Obtener la hora actual en UTC (Tiempo Universal Coordinado)
    ahora_utc = datetime.datetime.now(datetime.timezone.utc)

    # Calcular los minutos redondeados al múltiplo de 10 más reciente (hacia abajo)
    # Usamos división entera (//) para truncar.
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
    l2_path = Path("/data/output/abi/l2/fd")
    
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

    # 4. Devolvemos la lista final, ya filtrada.
    return lista_archivos
    
    
if __name__ == "__main__":
    ahora = get_moment();
    ahora = "20253141600"
    productos = ["ACTP", "C04", "C07", "C11", "C13", "C14", "C15"]
    archivos = get_filelist_from_path(ahora, productos)
    if not archivos:
        print("Error: No se encontró ningún archivo.")
        exit(-1)

    if len(archivos) != len(productos):
        print(f"Error: Se encontraron {len(archivos)} archivos, pero se esperaban {len(productos)}.")
        exit(-1)

    print(f"Se encontraron {len(archivos)} archivos:")
    for f in archivos:
        print(f)

    # Creamos un diccionario para almacenar los datasets abiertos.
    # Esto es más robusto que depender del orden de la lista 'archivos'.
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
    for producto, ds in datasets.items():
        print(f"  - {producto}: {ds.filepath()}")

    # Asignando los datasets a variables individuales para un acceso más directo.
    print("\nExtrayendo los arrays de datos de cada producto...")
    phase = datasets["ACTP"].variables['Phase'][:]
    c04 = datasets["C04"].variables['CMI'][:]
    c07 = datasets["C07"].variables['CMI'][:]
    c11 = datasets["C11"].variables['CMI'][:]
    c13 = datasets["C13"].variables['CMI'][:]
    c14 = datasets["C14"].variables['CMI'][:]
    c15 = datasets["C15"].variables['CMI'][:]
    

