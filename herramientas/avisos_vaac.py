#!/usr/bin/env python3
"""Baja y resume los avisos de ceniza (VAA) del VAAC de Washington para el Popocatépetl.

    herramientas/avisos_vaac.py --carpeta /data/ceniza/vaac 2025 2026

Para cada año lee el archivo de avisos de NOAA (ospo.noaa.gov/products/atmosphere/vaac/AAAA.html),
baja el texto de cada aviso del Popocatépetl a CARPETA/avisos/ (los que ya estén no se vuelven
a bajar) y escribe CARPETA/avisos_popocatepetl.csv, una fila por aviso:

    emision        DTG del aviso (UTC)
    observacion    OBS VA DTG o, si no hay, EST VA DTG: hora de la observación (UTC)
    ceniza_sat     sí: OBS VA CLD trae un área con niveles (SFC/FL...), el satélite la vio;
                   estimada: EST VA CLD trae el área, pero el satélite no la vio (casi siempre
                   por nubes; la vio una cámara o la reportó alguien);
                   no: ni observada ni estimada ("VA NOT IDENTIFIABLE...")
    nubes          el aviso menciona nubes meteorológicas en la zona (WX CLD, MET CLDS,
                   OBSCURED...), salvo "MINIMAL" o "NO" antes
    fuentes        INFO SOURCE (GOES-19, WEBCAM, NWP MODELS, VOLCAT...)
    detalles       ERUPTION DETAILS
    va_cld         OBS VA CLD o EST VA CLD (sin coordenadas)
    rmk            RMK

Los analistas del VAAC usan las mismas imágenes de GOES: no es una referencia del todo
independiente, pero da horas en UTC y cita cámaras, pilotos y CENAPRED.
"""
import argparse
import csv
import datetime
import html
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://www.ospo.noaa.gov"
AGENTE = "lanot-ceniza"


def baja(url, intentos=4):
    """Texto de la página; reintenta si el servidor corta la conexión."""
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if i == intentos - 1:
                raise
            time.sleep(5 * 2 ** i)


def texto(pagina):
    t = html.unescape(re.sub(r"<[^>]*>", "", pagina))
    return "\n".join(linea.rstrip() for linea in t.splitlines() if linea.strip())


def lista_avisos(anio):
    """URLs de los avisos del Popocatépetl de un año, del archivo de NOAA."""
    pagina = baja(f"{BASE}/products/atmosphere/vaac/{anio}.html")
    i = pagina.index('<a name="POPO">')
    j = pagina.index("<a name=", i + 10)
    return re.findall(r'<a href="(/VAAC/ARCH\d\d/POPO/[^"]+\.html)">\d{4} UTC</a>', pagina[i:j])


def campos(t):
    """Campos 'CLAVE: valor' del aviso; un valor sigue en las líneas que no empiezan con clave."""
    d, clave = {}, None
    for linea in t.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9 +]*?):\s*(.*)$", linea)
        if m and m.group(1) in ("DTG", "INFO SOURCE", "ERUPTION DETAILS", "OBS VA DTG", "OBS VA CLD", "RMK",
                                "FCST VA CLD +6HR", "FCST VA CLD +12HR", "FCST VA CLD +18HR", "NXT ADVISORY",
                                "ADVISORY NR", "VOLCANO", "PSN", "AREA", "SOURCE ELEV", "VAAC",
                                "EST VA DTG", "EST VA CLD"):
            clave = m.group(1)
            d[clave] = m.group(2)
        elif clave and not linea.startswith("..."):
            d[clave] += " " + linea.strip()
    return d


def hora_obs(dtg_emision, obs):
    """OBS VA DTG 'dd/hhmmZ' a datetime, con el mes y año de la emisión."""
    m = re.match(r"(\d{2})/(\d{2})(\d{2})Z", obs or "")
    if not m:
        return None
    dia, h, mi = map(int, m.groups())
    t = dtg_emision.replace(day=1, hour=h, minute=mi)
    if dia > dtg_emision.day:  # la observación es del mes anterior
        t = (t - datetime.timedelta(days=1)).replace(day=1)
    return t.replace(day=dia)


def resume(t):
    d = campos(t)
    emision = datetime.datetime.strptime(d["DTG"].strip(), "%Y%m%d/%H%MZ")
    estimada = "OBS VA CLD" not in d and "EST VA CLD" in d
    obs = hora_obs(emision, d.get("EST VA DTG" if estimada else "OBS VA DTG"))
    cld = d.get("EST VA CLD" if estimada else "OBS VA CLD", "")
    cld_sin_coord = re.sub(r"(N\d{4} W\d{5}\s*-?\s*)+", "<área> ", cld).strip()
    todo = " ".join([cld, d.get("RMK", ""), d.get("ERUPTION DETAILS", "")])
    con_area = bool(re.search(r"(SFC|FL\d{3})/FL\d{3}", cld))
    return {
        "emision": emision.strftime("%Y-%m-%d %H:%M"),
        "observacion": obs.strftime("%Y-%m-%d %H:%M") if obs else "",
        "ceniza_sat": ("estimada" if estimada else "sí") if con_area else "no",
        "nubes": "sí" if re.search(r"(?<!MINIMAL )(?<!NO )\b(WX|MET|METEOROLOGICAL) (CLD|CLDS|CLOUDS?)\b|OBSC", todo)
                 else "no",
        "fuentes": d.get("INFO SOURCE", "").strip(),
        "detalles": d.get("ERUPTION DETAILS", "").strip(),
        "va_cld": cld_sin_coord,
        "rmk": re.sub(r"\s+", " ", d.get("RMK", "")).strip(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta", type=Path, required=True)
    ap.add_argument("--pausa", type=float, default=0.3, help="segundos entre descargas")
    ap.add_argument("anios", nargs="+", type=int)
    args = ap.parse_args()

    destino = args.carpeta / "avisos"
    destino.mkdir(parents=True, exist_ok=True)
    filas = []
    for anio in args.anios:
        urls = lista_avisos(anio)
        print(f"{anio}: {len(urls)} avisos")
        for n, url in enumerate(urls, 1):
            f = destino / (Path(url).stem + ".txt")
            if not (f.exists() and f.stat().st_size > 200):
                f.write_text(texto(baja(BASE + url)))
                time.sleep(args.pausa)
                if n % 100 == 0:
                    print(f"  {n}/{len(urls)}")
            try:
                filas.append(resume(f.read_text()) | {"archivo": f.name})
            except (KeyError, ValueError) as e:
                print(f"  {f.name}: no se pudo leer ({e})")
    filas.sort(key=lambda r: r["emision"])
    with open(args.carpeta / "avisos_popocatepetl.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    print(f"{len(filas)} avisos en {args.carpeta / 'avisos_popocatepetl.csv'}")


if __name__ == "__main__":
    main()
