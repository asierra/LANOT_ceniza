# LANOT_ceniza

Sistema de detección de ceniza volcánica del Popocatépetl utilizando datos del satélite GOES-16 (ABI).

## Descripción

Este proyecto procesa datos de nivel 2 (L2) del instrumento ABI (Advanced Baseline Imager) del satélite GOES-16 para detectar y analizar ceniza volcánica emitida por el volcán Popocatépetl. 

El sistema utiliza múltiples canales infrarrojos y productos derivados para:
- Calcular diferencias de temperatura de brillo (BTD - Brightness Temperature Difference)
- Determinar el ángulo cenital solar (SZA) usando geometría esférica y efemérides precisas
- Analizar la fase de las nubes (Phase) para distinguir entre ceniza y otros tipos de nubes
- Generar productos de detección de ceniza volcánica

### Productos ABI utilizados

- **ACTP**: Cloud Top Phase (Fase de la cima de nube)
- **C04**: Canal 4 (1.38 μm) - Cirrus
- **C07**: Canal 7 (3.9 μm) - Infrarrojo de onda corta
- **C11**: Canal 11 (8.4 μm) - Infrarrojo de onda larga
- **C13**: Canal 13 (10.3 μm) - Infrarrojo limpio
- **C14**: Canal 14 (11.2 μm) - Infrarrojo de onda larga
- **C15**: Canal 15 (12.3 μm) - Infrarrojo sucio
- **NAV**: Navegación (Latitud/Longitud)

## Instalación

### Requisitos previos

- Python 3.8 o superior
- pip (gestor de paquetes de Python)

### Configuración del ambiente

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/asierra/LANOT_ceniza.git
   cd LANOT_ceniza
   ```

2. **Crear un ambiente virtual:**
   ```bash
   python3 -m venv .venv
   ```

3. **Activar el ambiente virtual:**
   
   En Linux/Mac:
   ```bash
   source .venv/bin/activate
   ```
   
   En Windows:
   ```bash
   .venv\Scripts\activate
   ```

4. **Instalar las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

### Dependencias principales

- **netCDF4**: Lectura de archivos NetCDF (formato de datos satelitales)
- **numpy**: Operaciones numéricas y manejo de arrays
- **skyfield**: Cálculos astronómicos precisos (posición del Sol)

## Uso

### Ejecución básica

```bash
python detect_ash.py
```

El script automáticamente:
1. Determina el momento más reciente según la cadencia del dominio (CONUS: minutos terminados en 1 o 6)
2. Busca los archivos NetCDF correspondientes en el directorio configurado
3. Extrae las variables necesarias de cada producto
4. Calcula el ángulo cenital solar para cada píxel
5. Genera los productos de diferencia de temperatura de brillo
6. En desarrollo ...

### Configuración

Por defecto, el script busca datos en `/data/output/abi/l2/conus`. Para cambiar esta ruta, editar la variable `l2_path` en `detect_ash.py`:

```python
l2_path = Path("/tu/ruta/personalizada")
```

## Estructura del proyecto

```
LANOT_ceniza/
├── detect_ash.py       # Script principal
├── requirements.txt    # Dependencias del proyecto
├── de421.bsp          # Efemérides planetarias (descargado automáticamente)
├── README.md          # Este archivo
└── LICENSE            # Licencia del proyecto
```

## Metodología

### Cálculo del ángulo cenital solar

El script utiliza un método optimizado para calcular el ángulo cenital solar (SZA) en cada píxel:

1. Obtiene la posición del Sol (RA/Dec) usando efemérides precisas de JPL (DE421)
2. Calcula el tiempo sideral de Greenwich (GST)
3. Determina el ángulo horario local (LHA) para cada punto
4. Aplica geometría esférica: `cos(SZA) = sin(lat) × sin(dec) + cos(lat) × cos(dec) × cos(LHA)`

Este enfoque es más eficiente que la vectorización directa con Skyfield para arrays grande.

### Diferencias de temperatura de brillo

El script calcula tres diferencias importantes:
- **delta1** = C13 - C15 (BTD 10.3-12.3 μm)
- **delta2** = C11 - C13 (BTD 8.4-10.3 μm)
- **delta3** = C07 - C13 (BTD 3.9-10.3 μm)

Estas diferencias son indicadores clave para la detección de ceniza volcánica.

## Notas técnicas

- El script maneja correctamente `MaskedArrays` de NetCDF, rellenando valores enmascarados con NaN
- Los archivos de efemérides (de421.bsp) se descargan automáticamente la primera vez que se ejecuta
- El formato de tiempo esperado en los nombres de archivo es `YYYYjjjhhmm` (año, día juliano y hora)

## Licencia

Ver archivo [LICENSE](LICENSE) para más detalles.

## Contacto

Alejandro Aguilar Sierra, asierra@unam.mx
Víctor Manuel Jiménez Escudero, ...
Laboratorio Nacional de Observación de la Tierra (LANOT)
