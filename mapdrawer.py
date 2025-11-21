#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
from PIL import Image
import aggdraw
import shapefile as shp

# Intentamos importar pyproj. Si no existe, el programa sigue funcionando en modo lineal.
try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

class MapDrawer:
    def __init__(self, lanot_dir='/usr/local/share/lanot', target_crs=None):
        """
        Inicializa el dibujante de mapas.
        
        Args:
            lanot_dir (str): Ruta base de los recursos (shapefiles/logos).
            target_crs (str, opcional): Código EPSG (ej. 'epsg:3857' para Web Mercator).
                                        Si es None, usa proyección lineal (Plate Carrée).
        """
        self.lanot_dir = lanot_dir
        self.image = None
        self._shp_cache = {} # Caché para no re-leer shapefiles del disco

        # Configuración de proyección
        self.use_proj = False
        self.transformer = None
        
        if target_crs:
            if HAS_PYPROJ:
                # 'always_xy=True' asegura el orden (lon, lat)
                self.transformer = Transformer.from_crs("epsg:4326", target_crs, always_xy=True)
                self.use_proj = True
                print(f"Info: Usando proyección {target_crs} vía pyproj.")
            else:
                print("Advertencia: pyproj no está instalado. Se usará proyección lineal simple.")

        # Coordenadas (se inicializan en 0)
        self.bounds = {'ulx': 0., 'uly': 0., 'lrx': 0., 'lry': 0.}
        
    def set_image(self, pil_image):
        self.image = pil_image

    def set_bounds(self, ulx, uly, lrx, lry):
        """
        Define los límites geográficos (Lon/Lat WGS84) de la imagen.
        Si se usa pyproj, calcula también los límites en el plano proyectado.
        """
        self.bounds['ulx'] = ulx
        self.bounds['uly'] = uly
        self.bounds['lrx'] = lrx
        self.bounds['lry'] = lry

        if self.use_proj:
            # Proyectamos las esquinas para saber cuánto mide la imagen en metros/unidades
            # Asumimos que la imagen está alineada al norte (no rotada)
            x_min, y_max = self.transformer.transform(ulx, uly)
            x_max, y_min = self.transformer.transform(lrx, lry)
            
            self.proj_bounds = {
                'min_x': x_min, 'max_y': y_max,
                'width': x_max - x_min,
                'height': y_min - y_max  # Note: y_min suele ser menor que y_max
            }

    def load_bounds_from_csv(self, recorte_name, csv_path=None):
        if csv_path is None:
            csv_path = os.path.join(self.lanot_dir, "docs/recortes_coordenadas.csv")
        
        try:
            # Optimización: Podríamos cargar todo el CSV a memoria si se hacen muchas consultas,
            # pero para uso normal línea por línea está bien.
            with open(csv_path, newline='') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    if row[0] == recorte_name:
                        # Convertir a float y desempaquetar
                        vals = [float(i) for i in row[2:]]
                        self.set_bounds(*vals)
                        return True
            print(f"Advertencia: Recorte '{recorte_name}' no encontrado en CSV.")
            return False
        except FileNotFoundError:
            print(f"Error: No se encontró el archivo {csv_path}")
            return False

    def _geo2pixel(self, lon, lat):
        """Convierte lon/lat a u/v (píxeles) usando la estrategia activa."""
        w = self.image.width
        h = self.image.height
        
        if self.use_proj:
            # 1. Proyectar punto (Lat/Lon -> Metros)
            x_p, y_p = self.transformer.transform(lon, lat)
            
            # 2. Interpolar en el plano proyectado
            pb = self.proj_bounds
            if pb['width'] == 0 or pb['height'] == 0: return 0, 0
            
            u = int(w * (x_p - pb['min_x']) / pb['width'])
            # Coordenada Y de imagen crece hacia abajo, coordenadas geográficas/proyectadas crecen hacia arriba
            v = int(h * (y_p - pb['max_y']) / pb['height']) 
            return u, v
            
        else:
            # Estrategia Original (Lineal / Plate Carrée)
            b = self.bounds
            width_span = b['lrx'] - b['ulx']
            height_span = b['uly'] - b['lry'] # uly suele ser mayor que lry
            
            if width_span == 0 or height_span == 0: return 0, 0
            
            u = int(w * (lon - b['ulx']) / width_span)
            v = int(h * (b['uly'] - lat) / height_span)
            return u, v

    def draw_shapefile(self, shp_rel_path, color='yellow', width=0.5):
        if self.image is None: return

        full_path = os.path.join(self.lanot_dir, shp_rel_path)
        
        # Cache del lector de shapefiles para no reabrir el archivo si se usa en bucle
        if full_path not in self._shp_cache:
            try:
                self._shp_cache[full_path] = shp.Reader(full_path)
            except Exception as e:
                print(f"Error leyendo shapefile {full_path}: {e}")
                return

        sf = self._shp_cache[full_path]
        draw = aggdraw.Draw(self.image)
        pen = aggdraw.Pen(color, width)

        b = self.bounds
        # Buffer simple para decidir si dibujar o no el shape
        margin = 5.0 

        for shape in sf.shapeRecords():
            # Optimización rápida: Bounding box del shape vs Bounding box de la imagen
            # shape.shape.bbox es [minx, miny, maxx, maxy]
            s_bbox = shape.shape.bbox
            if (s_bbox[2] < b['ulx'] - margin or s_bbox[0] > b['lrx'] + margin or
                s_bbox[3] < b['lry'] - margin or s_bbox[1] > b['uly'] + margin):
                continue

            parts = shape.shape.parts
            points = shape.shape.points
            parts_idx = list(parts) + [len(points)]

            for k in range(len(parts)):
                segment = points[parts_idx[k]:parts_idx[k+1]]
                if not segment: continue

                # Transformar todos los puntos del segmento
                # Usamos una lista plana para aggdraw.line: [x1, y1, x2, y2, ...]
                pixel_coords = []
                
                # Convertimos punto a punto
                # NOTA: En C++ haríamos esto vectorizado, aquí el bucle es lo más costoso.
                # Si la precisión extrema no es vital en los bordes, el clipping manual
                # dentro del bucle ayuda a no dibujar líneas fuera de imagen.
                
                for lon, lat in segment:
                    # Clipping suave para evitar coordenadas locas fuera de imagen
                    if (b['ulx'] - margin < lon < b['lrx'] + margin and 
                        b['lry'] - margin < lat < b['uly'] + margin):
                        u, v = self._geo2pixel(lon, lat)
                        pixel_coords.extend((u, v))
                    else:
                        # Si el segmento se sale, dibujamos lo que llevamos y reiniciamos
                        if len(pixel_coords) >= 4:
                            draw.line(pixel_coords, pen)
                        pixel_coords = []
                
                # Dibujar remanente
                if len(pixel_coords) >= 4:
                    draw.line(pixel_coords, pen)

        draw.flush()

    def draw_logo(self, logosize=128, position=3):
        """
        position: bitmask (0=Left, 1=Right) | (0=Top, 2=Bottom) 
        Ej: 0=UL, 1=UR, 2=LL, 3=LR
        """
        try:
            logo_path = os.path.join(self.lanot_dir, 'logos/lanot_negro_sn-128.png')
            logo = Image.open(logo_path)
        except FileNotFoundError:
            print("Logo no encontrado.")
            return

        # Mantener aspecto
        aspect = logo.height / logo.width
        new_h = int(logosize * aspect)
        logo = logo.resize((logosize, new_h), Image.Resampling.LANCZOS)

        pos_x = position & 1
        pos_y = position >> 1

        x = self.image.width - logosize - 10 if pos_x else 10
        y = self.image.height - new_h - 10 if pos_y else 10

        self.image.paste(logo, (x, y), logo)

    def draw_fecha(self, timestamp, position=2, fontsize=15, format="%Y/%m/%d %H:%MZ", color='white'):
        """
        Dibuja la fecha/hora en la imagen.
        
        Args:
            timestamp (datetime): Objeto datetime con la fecha/hora a dibujar
            position (int): Posición en la imagen (0=UL, 1=UR, 2=LL, 3=LR)
            fontsize (int): Tamaño de la fuente
            format (str): Formato de fecha usando códigos strftime (por defecto: "%Y/%m/%d %H:%MZ")
            color (str): Color del texto
        """
        if self.image is None:
            return
        
        try:
            from datetime import datetime
            
            # Convertir timestamp a string usando el formato especificado
            if isinstance(timestamp, datetime):
                fecha_str = timestamp.strftime(format)
            else:
                # Si es un string, usarlo directamente
                fecha_str = str(timestamp)
            
            # Usar aggdraw para dibujar texto
            draw = aggdraw.Draw(self.image)
            
            # Crear fuente (aggdraw usa fuentes truetype)
            try:
                # Intentar usar una fuente del sistema
                font = aggdraw.Font(color, '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', fontsize)
            except:
                # Si falla, usar fuente por defecto (puede ser más pequeña)
                font = aggdraw.Font(color, size=fontsize)
            
            # Calcular posición del texto
            # Aproximación del ancho del texto (8 píxeles por carácter es razonable)
            text_width = len(fecha_str) * int(fontsize * 0.6)
            text_height = fontsize + 4
            
            pos_x = position & 1
            pos_y = position >> 1
            
            margin = 10
            
            if pos_x:  # Right
                x = self.image.width - text_width - margin
            else:  # Left
                x = margin
            
            if pos_y:  # Bottom
                y = self.image.height - text_height - margin
            else:  # Top
                y = margin
            
            # Dibujar el texto
            draw.text((x, y), fecha_str, font)
            draw.flush()
            
        except Exception as e:
            print(f"Error dibujando fecha: {e}")

# --- Bloque Principal para pruebas ---
if __name__ == "__main__":
    # Ejemplo de uso
    print("Prueba de MapDrawer Modernizado")
    
    # 1. Instancia (opcionalmente pasas target_crs='epsg:3857' para probar pyproj)
    # Si no pasas nada, funciona como tu script original.
    mapper = MapDrawer(lanot_dir='./lanot_fake', target_crs=None)
    
    # 2. Crear imagen dummy
    img = Image.new('RGB', (800, 600), 'black')
    mapper.set_image(img)
    
    # 3. Definir límites (Ejemplo: México)
    # mapper.load_bounds_from_csv("Mexico") o manual:
    mapper.set_bounds(-118.0, 33.0, -86.0, 14.0)
    
    # 4. Dibujar (asumiendo que existen los archivos en las rutas relativas)
    # mapper.draw_shapefile('shapefiles/ne_10m_coastline.shp', color='cyan')
    
    # 5. Logo
    # mapper.draw_logo()
    
    # img.save("test_output.png")
    print("Proceso finalizado (sin guardar imagen en demo).")