"""Paso 1 · OCR: lee las imágenes de entrada/<libro>/ y guarda el texto de cada página.

Ejecutar desde la carpeta del repositorio con el venv:
    .\\.venv\\Scripts\\python.exe paso1_ocr.py <libro> [--forzar]

Por cada imagen escribe trabajo/<libro>/ocr/<imagen>.json con las líneas detectadas
(texto, posición y confianza). Las páginas ya procesadas se saltan; --forzar las repite.
Al final escribe trabajo/<libro>/ocr_informe.csv con la confianza media de cada página.
"""
import csv
import json
import sys
import time

import numpy as np
from PIL import Image, ImageOps

import config

FORZAR = "--forzar" in sys.argv


def cargar_paginas(ruta):
    """Abre la imagen, corrige la rotación de la cámara y devuelve una o dos páginas."""
    imagen = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    if config.PAGINAS_DOBLES:
        ancho, alto = imagen.size
        mitades = [imagen.crop((0, 0, ancho // 2, alto)), imagen.crop((ancho // 2, 0, ancho, alto))]
    else:
        mitades = [imagen]
    paginas = []
    for pagina in mitades:
        if max(pagina.size) > config.LADO_MAXIMO:
            pagina.thumbnail((config.LADO_MAXIMO, config.LADO_MAXIMO), Image.LANCZOS)
        paginas.append(pagina)
    return paginas


def agrupar_en_lineas(fragmentos):
    """Une los fragmentos del OCR que están a la misma altura en líneas de texto."""
    lineas = []
    for frag in sorted(fragmentos, key=lambda f: (f["y0"] + f["y1"]) / 2):
        centro = (frag["y0"] + frag["y1"]) / 2
        alto = frag["y1"] - frag["y0"]
        actual = lineas[-1] if lineas else None
        if actual and abs(centro - actual["centro"]) < 0.5 * min(alto, actual["alto"]):
            actual["fragmentos"].append(frag)
            n = len(actual["fragmentos"])
            actual["centro"] += (centro - actual["centro"]) / n
        else:
            lineas.append({"centro": centro, "alto": alto, "fragmentos": [frag]})

    resultado = []
    for linea in lineas:
        frags = sorted(linea["fragmentos"], key=lambda f: f["x0"])
        resultado.append({
            "texto": " ".join(f["texto"] for f in frags).strip(),
            "x0": min(f["x0"] for f in frags),
            "y0": min(f["y0"] for f in frags),
            "x1": max(f["x1"] for f in frags),
            "y1": max(f["y1"] for f in frags),
            "confianza": round(float(np.mean([f["confianza"] for f in frags])), 3),
        })
    return resultado


def leer_pagina(lector, pagina):
    """Pasa el OCR a una página y devuelve sus líneas en orden de lectura."""
    ancho, alto = pagina.size
    fragmentos = []
    leido = lector(np.array(pagina))
    if leido.boxes is None:          # página en blanco o sin texto
        return {"ancho": ancho, "alto": alto, "lineas": []}
    for caja, texto, confianza in zip(leido.boxes, leido.txts, leido.scores):
        xs = [p[0] for p in caja]
        ys = [p[1] for p in caja]
        frag = {"texto": texto.strip(), "x0": float(min(xs)), "y0": float(min(ys)),
                "x1": float(max(xs)), "y1": float(max(ys)), "confianza": float(confianza)}
        centro = (frag["y0"] + frag["y1"]) / 2
        if not frag["texto"] or frag["confianza"] < config.CONFIANZA_MINIMA:
            continue
        if centro < alto * config.MARGEN_SUPERIOR or centro > alto * (1 - config.MARGEN_INFERIOR):
            continue
        fragmentos.append(frag)
    return {"ancho": ancho, "alto": alto, "lineas": agrupar_en_lineas(fragmentos)}


def main():
    libro = config.libro_de_argumentos()
    entrada, trabajo, _ = config.carpetas(libro)
    carpeta_ocr = trabajo / "ocr"
    carpeta_ocr.mkdir(exist_ok=True)

    imagenes = sorted(p for p in entrada.iterdir() if p.suffix.lower() in config.EXTENSIONES)
    if not imagenes:
        sys.exit(f"No hay imágenes en {entrada}")
    print(f"{len(imagenes)} imágenes en {entrada}")

    lector = None
    t_total = time.perf_counter()
    for i, ruta in enumerate(imagenes, 1):
        destino = carpeta_ocr / f"{ruta.stem}.json"
        if destino.exists() and not FORZAR:
            print(f"[{i}/{len(imagenes)}] {ruta.name}: ya hecha, se salta")
            continue
        if lector is None:
            # Se importa aquí: tarda, y no hace falta si todo está hecho.
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
            t0 = time.perf_counter()
            lector = RapidOCR(params={
                "Global.log_level": "warning",
                "Rec.lang_type": LangRec[config.ALFABETO_OCR],
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
            })
            print(f"Modelo de OCR cargado en {time.perf_counter() - t0:.1f} s")
        t0 = time.perf_counter()
        paginas = [leer_pagina(lector, p) for p in cargar_paginas(ruta)]
        destino.write_text(json.dumps({"imagen": ruta.name, "paginas": paginas},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
        n_lineas = sum(len(p["lineas"]) for p in paginas)
        print(f"[{i}/{len(imagenes)}] {ruta.name}: {n_lineas} líneas en {time.perf_counter() - t0:.1f} s")
    print(f"OCR terminado en {time.perf_counter() - t_total:.1f} s")

    # Informe de confianza: indica qué páginas conviene revisar a mano.
    informe = trabajo / "ocr_informe.csv"
    a_revisar = 0
    with informe.open("w", newline="", encoding="utf-8-sig") as f:
        salida = csv.writer(f, delimiter=";")
        salida.writerow(["imagen", "lineas", "confianza_media", "estado"])
        for ruta in imagenes:
            datos = json.loads((carpeta_ocr / f"{ruta.stem}.json").read_text(encoding="utf-8"))
            lineas = [l for p in datos["paginas"] for l in p["lineas"]]
            media = float(np.mean([l["confianza"] for l in lineas])) if lineas else 0.0
            estado = "ok" if media >= config.CONFIANZA_AVISO else "revisar"
            a_revisar += estado == "revisar"
            salida.writerow([ruta.name, len(lineas), f"{media:.2f}", estado])
    print(f"Informe: {informe} ({a_revisar} páginas marcadas para revisar)")


if __name__ == "__main__":
    main()
