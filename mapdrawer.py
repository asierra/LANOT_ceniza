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
        # Mapeo interno de capas simbólicas -> rutas relativas de shapefiles
        # Se puede extender con add_layer(). Las claves se manejan en mayúsculas.
        self._layers = {
            'COASTLINE': 'shapefiles/ne_10m_coastline.shp',
            'COUNTRIES': 'shapefiles/ne_10m_admin_0_countries.shp',
            #'MEXSTATES': 'shapefiles/dest_2015gwLines.shp'
            'MEXSTATES': 'shapefiles/mexico_estados_2023_wgs84_lines.shp'
        }

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

    # --- Nueva API basada en nombres de capa ---
    def add_layer(self, key, rel_path):
        """Agrega o actualiza una capa simbólica.

        Args:
            key (str): Nombre simbólico (ej: 'RIVERS'). Se normaliza a mayúsculas.
            rel_path (str): Ruta relativa al directorio lanot_dir.
        """
        self._layers[key.upper()] = rel_path

    def list_layers(self):
        """Devuelve lista de claves de capas disponibles."""
        return sorted(self._layers.keys())

    def draw_layer(self, key, color='yellow', width=0.5):
        """Dibuja una capa referenciada por nombre simbólico.

        Args:
            key (str): Clave de la capa (ej: 'COASTLINE'). No sensible a mayúsculas.
            color (str): Color de la línea.
            width (float): Grosor de línea.
        """
        if self.image is None:
            return
        layer_key = key.upper()
        if layer_key not in self._layers:
            print(f"Advertencia: capa '{key}' no registrada. Capas disponibles: {self.list_layers()}")
            return
        rel_path = self._layers[layer_key]
        self.draw_shapefile(rel_path, color=color, width=width)

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
            # Intentar múltiples rutas para compatibilidad Debian/Rocky
            font_paths = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',  # Debian/Ubuntu
                '/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf',  # Rocky/RHEL
            ]
            font = None
            for font_path in font_paths:
                try:
                    font = aggdraw.Font(color, font_path, fontsize)
                    break
                except:
                    continue
            if font is None:
                # Si todas fallan, usar fuente por defecto
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
    def draw_legend(self, items, position=2, fontsize=15, box_size=None, 
                    padding=10, gap=6, margin=10, vertical_offset=0,
                    bg_color='white', text_color='black', border_color=None, border_width=1):
        """Dibuja una leyenda con recuadros de color y etiquetas.

        Args:
            items (list[tuple[str, tuple|str]]): Lista de (etiqueta, color).
            position (int): 0=UL, 1=UR, 2=LL, 3=LR.
            fontsize (int): Tamaño de fuente.
            box_size (int, opcional): Tamaño del cuadro de color. Por defecto = fontsize.
            padding (int): Relleno interno del fondo.
            gap (int): Espacio entre cuadro de color y texto.
            margin (int): Margen desde el borde de la imagen.
            vertical_offset (int): Desplazamiento vertical en píxeles desde el borde
                (positivo aleja del borde: hacia arriba si Bottom, hacia abajo si Top).
            bg_color (str|tuple): Color de fondo de la leyenda.
            text_color (str|tuple): Color del texto.
            border_color (str|tuple, opcional): Color del borde. None para sin borde.
            border_width (int): Grosor del borde si border_color no es None.
        """
        if self.image is None or not items:
            return

        box_size = box_size or fontsize
        draw = aggdraw.Draw(self.image)
        
        # Intentar múltiples rutas para compatibilidad Debian/Rocky
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',  # Debian/Ubuntu
            '/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf',  # Rocky/RHEL
        ]
        font = None
        for font_path in font_paths:
            try:
                font = aggdraw.Font(text_color, font_path, fontsize)
                break
            except:
                continue
        if font is None:
            # Si todas fallan, usar fuente por defecto
            font = aggdraw.Font(text_color, size=fontsize)

        # Calcular dimensiones
        text_width = lambda s: int(len(str(s)) * fontsize * 0.6)
        line_heights = [max(fontsize + 4, box_size) for _, _ in items]
        line_widths = [padding + box_size + gap + text_width(label) + padding for label, _ in items]
        
        legend_width = max(line_widths)
        legend_height = padding + sum(line_heights) + padding

        # Calcular posición
        pos_x = position & 1
        pos_y = position >> 1

        x0 = self.image.width - legend_width - margin if pos_x else margin
        y0 = (self.image.height - legend_height - margin - vertical_offset) if pos_y else (margin + vertical_offset)
        x1 = x0 + legend_width
        y1 = y0 + legend_height

        # Dibujar fondo
        brush_bg = aggdraw.Brush(bg_color)
        if border_color:
            pen_border = aggdraw.Pen(border_color, border_width)
            draw.rectangle((x0, y0, x1, y1), pen_border, brush_bg)
        else:
            draw.rectangle((x0, y0, x1, y1), None, brush_bg)

        # Dibujar filas (cuadro de color + etiqueta)
        cy = y0 + padding
        for label, color in items:
            lh = max(fontsize + 4, box_size)
            
            # Cuadro de color
            bx0 = x0 + padding
            by0 = cy + (lh - box_size) // 2
            bx1 = bx0 + box_size
            by1 = by0 + box_size
            draw.rectangle((bx0, by0, bx1, by1), aggdraw.Pen(color, 1), aggdraw.Brush(color))

            # Texto de etiqueta
            tx = bx1 + gap
            ty = cy + (lh - fontsize) // 2
            draw.text((tx, ty), str(label), font)

            cy += lh

        draw.flush()

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