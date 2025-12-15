"""
lanot_ceniza: paquete mínimo para instalar y usar funciones principales del repo.
"""
from ._bridge_detect_ash import detect_ash_main
from ._bridge_mapdrawer import draw_map_main

__all__ = ['detect_ash_main', 'draw_map_main']
