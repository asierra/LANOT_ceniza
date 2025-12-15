#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import matplotlib
matplotlib.use('Agg') # Modo sin ventana (servidores)

import argparse
import xarray as xr
import rioxarray
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import matplotlib.patches as mpatches
from pathlib import Path
import sys
import re

def extract_timestamp(filename):
    """Intenta extraer YYYYjjjHHmm (11 dígitos) del nombre del archivo."""
    match = re.search(r'(\d{11})', filename)
    if match:
        return match.group(1)
    return "Desconocido"

def analizar_y_visualizar(ref_path, test_path, output_png):
    # Obtener nombres y timestamps para el reporte
    ref_name = Path(ref_path).name
    test_name = Path(test_path).name
    ts_ref = extract_timestamp(ref_name)
    ts_test = extract_timestamp(test_name)

    print(f"\n" + "="*60)
    print(f"      COMPARACIÓN DE ALGORITMOS: TeraScan vs Python")
    print(f"="*60)
    print(f"TeraScan (Ref): {ref_name} | TS: {ts_ref}")
    print(f"Python (Test):  {test_name}            | TS: {ts_test}")
    
    if ts_ref != "Desconocido" and ts_test != "Desconocido" and ts_ref != ts_test:
        print(f"⚠️  ADVERTENCIA: Los Timestamps parecen diferentes ({ts_ref} vs {ts_test}).")
        print("    Asegúrate de estar comparando la misma imagen.")

    # 1. Cargar Archivos
    try:
        da_ref = rioxarray.open_rasterio(ref_path, masked=True).squeeze()
        da_test = rioxarray.open_rasterio(test_path, masked=True).squeeze()
    except Exception as e:
        print(f"Error crítico al abrir archivos: {e}")
        sys.exit(1)

    # 2. Limpieza de Datos TeraScan (Float32 -> Categorías)
    print("\nProcesando matriz de TeraScan...")
    # Eliminar valores negativos gigantes (NoData)
    da_ref = da_ref.where(da_ref > -100) 
    # Asegurar que nans sean 0
    ref_raw = np.nan_to_num(da_ref.values, nan=0).astype(int)

    # 3. Alineación Espacial
    print("Alineando rejilla de Python a la geometría de TeraScan...")
    try:
        da_test_matched = da_test.rio.reproject_match(da_ref, resampling=0)
    except Exception as e:
        print(f"Error en reproyección: {e}")
        sys.exit(1)

    test_data = np.nan_to_num(da_test_matched.values, nan=0).astype(int)
    ref_data = ref_raw # Ya lo convertimos arriba

    # 4. Lógica de Comparación y Máscaras
    # ---------------------------------------------------------
    # Categorías de Interés:
    # 0: Match (Fondo/Nada)
    # 1: Python FP (TeraScan=0, Python=Ash)
    # 2: Python FN (TeraScan=Ash, Python=0)
    # 3: Diferencia Clase (TeraScan=Ash, Python=Ash, valor distinto)
    # 4: Zona Nube/Ruido (TeraScan=4/5) -> Nueva categoría visual
    
    diff_map = np.zeros_like(ref_data, dtype=int)

    # A. Zona Nube/Ruido (Prioridad visual baja, pero informativa)
    mask_cloud_noise = (ref_data >= 4)
    
    # B. Zonas de Ceniza en TeraScan (1, 2, 3)
    mask_ref_ash = (ref_data >= 1) & (ref_data <= 3)
    
    # C. Zonas de Ceniza en Python (1, 2, 3)
    mask_test_ash = (test_data >= 1) & (test_data <= 3)

    # Definir valores para el mapa visual
    # Fondo por defecto es 0
    
    # 1. Marcar nubes de TeraScan primero (Púrpura)
    diff_map[mask_cloud_noise] = 4 

    # 2. Errores Graves y Aciertos (Sobrescriben nubes si fuera necesario, 
    # pero aquí respetaremos que si TeraScan dice Nube, visualmente sea Nube 
    # para entender por qué falló la comparación, O podemos resaltar si Python vio ceniza ahí).
    
    # Vamos a dejar 4 como "Zona excluida de estadísticas de ceniza pura"
    
    # Coincidencia exacta de Ceniza
    mask_match_ash = mask_ref_ash & mask_test_ash & (ref_data == test_data)
    # (No pintamos match en el mapa de diferencias, se queda en 0 o transparente, 
    # pero si quieres verlo, podríamos darle otro valor. Lo dejaremos como 0 para limpiar).

    # Diferencia Leve (Ambos ceniza, distinta clase)
    mask_diff_class = mask_ref_ash & mask_test_ash & (ref_data != test_data)
    diff_map[mask_diff_class] = 3

    # Falso Positivo Python (TeraScan=0, Python=Ash)
    mask_fp = (ref_data == 0) & mask_test_ash
    diff_map[mask_fp] = 1

    # Falso Negativo Python (TeraScan=Ash, Python=0)
    mask_fn = mask_ref_ash & (test_data == 0)
    diff_map[mask_fn] = 2

    # --- SUB-ANÁLISIS: ¿Qué vio Python dentro de las nubes de TeraScan? ---
    # Esto no se pinta en el mapa principal para no saturar, pero se reporta.
    mask_ash_in_cloud = mask_cloud_noise & mask_test_ash
    n_ash_in_cloud = np.sum(mask_ash_in_cloud)


    # 5. Estadísticas
    total_pixels = ref_data.size
    n_fp = np.sum(mask_fp)
    n_fn = np.sum(mask_fn)
    n_diff = np.sum(mask_diff_class)
    n_match_ash = np.sum(mask_match_ash)
    n_clouds = np.sum(mask_cloud_noise)
    
    # Área de interés para porcentajes: Donde ALGUIEN vio ceniza O TeraScan vio nubes
    # (Excluye el fondo puro 0 vs 0)
    n_active = n_fp + n_fn + n_diff + n_match_ash + n_clouds
    
    if n_active == 0: n_active = 1 # Evitar div/0

    # --- REPORTE DE TEXTO ---
    print("\n" + "-"*35 + " REPORTE ESTADÍSTICO " + "-"*35)
    print(f"{'CONDICIÓN':<45} | {'PÍXELES':>10} | {'% ÁREA ACTIVA':>15}")
    print("-" * 75)
    
    # Bloque Ceniza vs Ceniza
    p_match = (n_match_ash / n_active * 100)
    p_diff = (n_diff / n_active * 100)
    print(f"{'Acierto (Ceniza Exacta)':<45} | {n_match_ash:>10,} | {p_match:>14.2f}%")
    print(f"{'Diferencia Leve (Clase distinta)':<45} | {n_diff:>10,} | {p_diff:>14.2f}%")
    
    # Bloque Errores
    p_fp = (n_fp / n_active * 100)
    p_fn = (n_fn / n_active * 100)
    print(f"{'Python FP (TeraScan=0, Python=Ceniza)':<45} | {n_fp:>10,} | {p_fp:>14.2f}%")
    print(f"{'Python FN (TeraScan=Ceniza, Python=0)':<45} | {n_fn:>10,} | {p_fn:>14.2f}%")
    
    # Bloque Nubes/Ruido
    p_clouds = (n_clouds / n_active * 100)
    print("-" * 75)
    print(f"{'Zona Nube/Ruido (TeraScan=4 o 5)':<45} | {n_clouds:>10,} | {p_clouds:>14.2f}%")
    
    # Dato curioso
    if n_ash_in_cloud > 0:
        print(f"  ↳ De estas nubes, Python detectó ceniza en:     {n_ash_in_cloud:>10,} px")
    
    print("=" * 75)

    # 6. Mapa Visual
    print(f"Generando mapa visual en: {output_png}")
    
    # Colores:
    # 0: Match/Fondo (Gris Claro)
    # 1: Python FP (Rojo)
    # 2: Python FN (Azul)
    # 3: Diferencia Clase (Naranja)
    # 4: TeraScan Nube/Ruido (Púrpura/Lila)
    
    colors = [
        '#f0f0f0',  # 0
        '#d62728',  # 1 Rojo
        '#1f77b4',  # 2 Azul
        '#ff7f0e',  # 3 Naranja
        '#9467bd'   # 4 Púrpura (Muted Purple)
    ]
    cmap = ListedColormap(colors)

    plt.figure(figsize=(12, 10))
    # Interpolación nearest para ver píxeles exactos
    im = plt.imshow(diff_map, cmap=cmap, vmin=0, vmax=4, interpolation='nearest')
    
    plt.title(f"Comparación: TeraScan vs Python\nTimestamp Ref: {ts_ref}", fontsize=14)
    plt.axis('off')
    
    # Leyenda Personalizada
    patches = [
        mpatches.Patch(color=colors[0], label="Fondo / Coincidencia"),
        mpatches.Patch(color=colors[1], label=f"Python FP (Sobra): {n_fp}"),
        mpatches.Patch(color=colors[2], label=f"Python FN (Falta): {n_fn}"),
        mpatches.Patch(color=colors[3], label=f"Diferencia Clase: {n_diff}"),
        mpatches.Patch(color=colors[4], label=f"TeraScan Nube/Ruido: {n_clouds}")
    ]
    plt.legend(handles=patches, loc='lower right', frameon=True, fontsize=11)
    
    plt.tight_layout()
    plt.savefig(output_png, dpi=150)
    print("¡Proceso finalizado con éxito!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compara resultados de detección de ceniza: TeraScan (Legacy) vs Python (New).")
    parser.add_argument('ref', type=Path, help="Archivo TeraScan (Referencia)")
    parser.add_argument('test', type=Path, help="Archivo Python (Test)")
    parser.add_argument('--output', '-o', type=Path, default=None, help="Nombre imagen salida")
    
    args = parser.parse_args()

    if not args.ref.exists() or not args.test.exists():
        print("Error: No se encuentran los archivos de entrada.")
        sys.exit(1)

    out_name = args.output if args.output else Path(f"comp_{args.test.stem}.png")
    analizar_y_visualizar(args.ref, args.test, out_name)
    
