"""Paso 2 · Texto: une el OCR de todas las páginas en un único libro.txt revisable.

Ejecutar desde la carpeta del repositorio con el venv:
    .\\.venv\\Scripts\\python.exe paso2_texto.py <libro> [--forzar]

Qué hace:
  - quita los números de página (líneas solo con cifras arriba o abajo de la página);
  - reconstruye los párrafos (sangría, salto vertical o línea anterior corta y cerrada);
  - une las palabras partidas con guion a final de línea;
  - une el párrafo que continúa de una página a la siguiente;
  - marca los títulos de capítulo con "# " (cada uno será un archivo de audio).

El resultado, trabajo/<libro>/libro.txt, se puede corregir a mano antes del paso 3.
Formato: párrafos separados por una línea en blanco; títulos en líneas que empiezan por "# ".
Si libro.txt ya existe no se sobrescribe (para no perder correcciones), salvo con --forzar.
"""
import json
import re
import statistics
import sys

import config

FORZAR = "--forzar" in sys.argv
FIN_DE_FRASE = tuple(".!?…:»\"”)")
ES_TITULO = re.compile(config.PATRON_CAPITULO, re.IGNORECASE)
ES_NUMERO_DE_PAGINA = re.compile(r"^[\W_]*\d{1,4}[\W_]*$")


def es_titulo(texto):
    return len(texto) <= config.LONGITUD_MAXIMA_TITULO and bool(ES_TITULO.match(texto))


def unir(anterior, siguiente):
    """Une dos trozos de texto; si el primero acaba en guion de corte, pega la palabra."""
    corte = re.search(r"(?<=\w)\s*[-¬]$", anterior)
    if corte and siguiente[:1].islower():
        return anterior[:corte.start()] + siguiente
    return f"{anterior} {siguiente}"


def limpiar(texto):
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"\s+([,.;:!?»)])", r"\1", texto)   # sin espacio antes de puntuación de cierre
    texto = re.sub(r"([«(¿¡])\s+", r"\1", texto)       # sin espacio después de la de apertura
    return texto


def parrafos_de_pagina(pagina):
    """Devuelve los párrafos de una página a partir de la posición de sus líneas."""
    alto = pagina["alto"]
    lineas = []
    for linea in pagina["lineas"]:
        centro = (linea["y0"] + linea["y1"]) / 2
        en_borde = centro < alto * 0.12 or centro > alto * 0.88
        if en_borde and ES_NUMERO_DE_PAGINA.match(linea["texto"]):
            continue
        lineas.append(linea)
    if not lineas:
        return []

    alto_linea = statistics.median(l["y1"] - l["y0"] for l in lineas)
    margen_izq = statistics.median(l["x0"] for l in lineas)
    margen_der = max(l["x1"] for l in lineas)
    ancho_texto = max(margen_der - margen_izq, 1)
    pasos = [b["y0"] - a["y0"] for a, b in zip(lineas, lineas[1:])]
    paso = statistics.median(pasos) if pasos else alto_linea

    parrafos = [lineas[0]["texto"]]
    for anterior, linea in zip(lineas, lineas[1:]):
        sangria = linea["x0"] > margen_izq + 0.8 * alto_linea
        salto = (linea["y0"] - anterior["y0"]) > 1.5 * paso
        anterior_corta = anterior["x1"] < margen_der - 0.15 * ancho_texto
        anterior_cerrada = anterior_corta and anterior["texto"].endswith(FIN_DE_FRASE)
        if sangria or salto or anterior_cerrada or es_titulo(anterior["texto"]) or es_titulo(linea["texto"]):
            parrafos.append(linea["texto"])
        else:
            parrafos[-1] = unir(parrafos[-1], linea["texto"])
    return parrafos


def main():
    libro = config.libro_de_argumentos()
    entrada, trabajo, _ = config.carpetas(libro)
    destino = trabajo / "libro.txt"
    if destino.exists() and not FORZAR:
        sys.exit(f"{destino} ya existe y puede tener correcciones. Usa --forzar para regenerarlo.")

    imagenes = sorted(p for p in entrada.iterdir() if p.suffix.lower() in config.EXTENSIONES)
    parrafos = []
    for ruta in imagenes:
        archivo = trabajo / "ocr" / f"{ruta.stem}.json"
        if not archivo.exists():
            sys.exit(f"Falta el OCR de {ruta.name}. Ejecuta antes paso1_ocr.py {libro}")
        for pagina in json.loads(archivo.read_text(encoding="utf-8"))["paginas"]:
            nuevos = parrafos_de_pagina(pagina)
            # El primer párrafo de la página continúa el anterior si este quedó sin cerrar.
            if (nuevos and parrafos and not parrafos[-1].endswith(FIN_DE_FRASE)
                    and not es_titulo(parrafos[-1]) and not es_titulo(nuevos[0])):
                parrafos[-1] = unir(parrafos[-1], nuevos.pop(0))
            parrafos.extend(nuevos)

    bloques = []
    for texto in map(limpiar, parrafos):
        if texto:
            bloques.append(f"# {texto}" if es_titulo(texto) else texto)
    destino.write_text("\n\n".join(bloques) + "\n", encoding="utf-8")

    titulos = sum(b.startswith("# ") for b in bloques)
    caracteres = sum(len(b) for b in bloques)
    print(f"{destino}: {len(bloques) - titulos} párrafos, {titulos} títulos, {caracteres} caracteres")
    print("Revisa y corrige el texto antes de generar el audio (paso3_audio.py).")


if __name__ == "__main__":
    main()
