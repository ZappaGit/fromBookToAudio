"""Paso 3 · Audio: convierte trabajo/<libro>/libro.txt en un audiolibro con Kokoro-82M.

Ejecutar desde la carpeta del repositorio con el venv:
    .\\.venv\\Scripts\\python.exe paso3_audio.py <libro>

Genera un archivo por capítulo en salida/<libro>/ (los capítulos son las líneas "# Título").
El audio de cada párrafo se guarda en trabajo/<libro>/audio/, de modo que si el proceso se
interrumpe o se corrige un párrafo, al repetirlo solo se sintetiza lo que falta o ha cambiado.
Español requiere espeak-ng instalado en el sistema (ver README.md).
"""
import hashlib
import re
import time
import unicodedata

import numpy as np
import soundfile as sf

import config


def leer_capitulos(ruta):
    """Devuelve [(título o None, [párrafos])] a partir de libro.txt."""
    capitulos = [(None, [])]
    for bloque in re.split(r"\n\s*\n", ruta.read_text(encoding="utf-8")):
        bloque = " ".join(bloque.split())
        if not bloque:
            continue
        if bloque.startswith("#"):
            capitulos.append((bloque.lstrip("# ").strip(), []))
        else:
            capitulos[-1][1].append(bloque)
    return [(t, p) for t, p in capitulos if t or p]


def trocear(texto, maximo):
    """Parte un párrafo en trozos de como mucho `maximo` caracteres, por frases si puede."""
    trozos, actual = [], ""
    for frase in re.split(r"(?<=[.!?…;:])\s+", texto):
        partes = [frase]
        if len(frase) > maximo:                       # frase muy larga: se parte por comas
            partes = re.split(r"(?<=,)\s+", frase)
        for parte in partes:
            while len(parte) > maximo:                # sin comas: se parte por espacios
                corte = parte.rfind(" ", 0, maximo)
                corte = corte if corte > 0 else maximo
                if actual:
                    trozos.append(actual)
                    actual = ""
                trozos.append(parte[:corte])
                parte = parte[corte:].strip()
            if actual and len(actual) + 1 + len(parte) > maximo:
                trozos.append(actual)
                actual = parte
            else:
                actual = f"{actual} {parte}".strip()
    if actual:
        trozos.append(actual)
    return trozos


def nombre_de_archivo(numero, titulo):
    base = unicodedata.normalize("NFKD", titulo or "inicio").encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:50] or "capitulo"
    return f"{numero:02d}-{base}.{config.FORMATO_SALIDA.lower()}"


class Narrador:
    """Sintetiza párrafos con Kokoro y guarda cada uno en disco para no repetirlo."""

    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.pipeline = None
        self.segundos_sintesis = 0.0
        self.segundos_audio_nuevo = 0.0

    def audio(self, texto):
        clave = f"{config.IDIOMA_VOZ}|{config.VOZ}|{config.VELOCIDAD}|{texto}"
        ruta = self.carpeta / f"{hashlib.sha1(clave.encode('utf-8')).hexdigest()}.flac"
        if ruta.exists():
            return sf.read(ruta, dtype="float32")[0]

        if self.pipeline is None:
            from kokoro import KPipeline  # se importa aquí: tarda, y no hace falta si todo está hecho
            t0 = time.perf_counter()
            self.pipeline = KPipeline(lang_code=config.IDIOMA_VOZ, repo_id="hexgrad/Kokoro-82M")
            print(f"Modelo de voz cargado en {time.perf_counter() - t0:.1f} s")

        t0 = time.perf_counter()
        partes = []
        for trozo in trocear(texto, config.MAX_CARACTERES):
            for resultado in self.pipeline(trozo, voice=config.VOZ, speed=config.VELOCIDAD):
                if resultado.audio is not None:
                    partes.append(np.asarray(resultado.audio.detach().cpu(), dtype=np.float32))
        audio = np.concatenate(partes) if partes else np.zeros(1, dtype=np.float32)
        self.segundos_sintesis += time.perf_counter() - t0
        self.segundos_audio_nuevo += len(audio) / config.FRECUENCIA

        temporal = ruta.with_suffix(".tmp")           # se renombra al final: nunca queda a medias
        sf.write(temporal, audio, config.FRECUENCIA, format="FLAC", subtype="PCM_16")
        temporal.replace(ruta)
        return audio


def silencio(segundos):
    return np.zeros(int(segundos * config.FRECUENCIA), dtype=np.float32)


def main():
    libro = config.libro_de_argumentos()
    _, trabajo, salida = config.carpetas(libro)
    texto = trabajo / "libro.txt"
    if not texto.exists():
        raise SystemExit(f"Falta {texto}. Ejecuta antes paso2_texto.py {libro}")
    carpeta_audio = trabajo / "audio"
    carpeta_audio.mkdir(exist_ok=True)

    capitulos = leer_capitulos(texto)
    total = sum(len(p) + bool(t) for t, p in capitulos)
    print(f"{len(capitulos)} capítulos, {total} bloques de texto. Voz: {config.VOZ}, velocidad {config.VELOCIDAD}")

    narrador = Narrador(carpeta_audio)
    hechos = 0
    duracion_total = 0.0
    for numero, (titulo, parrafos) in enumerate(capitulos, 1):
        destino = salida / nombre_de_archivo(numero, titulo)
        muestras = 0
        with sf.SoundFile(destino, "w", samplerate=config.FRECUENCIA, channels=1,
                          format=config.FORMATO_SALIDA) as archivo:
            bloques = ([(titulo, config.PAUSA_TITULO)] if titulo else []) + \
                      [(p, config.PAUSA_PARRAFO) for p in parrafos]
            for bloque, pausa in bloques:
                for trozo in (narrador.audio(bloque), silencio(pausa)):
                    archivo.write(trozo)
                    muestras += len(trozo)
                hechos += 1
                print(f"  [{hechos}/{total}] {bloque[:60]}")
        duracion = muestras / config.FRECUENCIA
        duracion_total += duracion
        print(f"{destino.name}: {duracion / 60:.1f} min")

    print(f"Audiolibro: {duracion_total / 60:.1f} min en {salida}")
    if narrador.segundos_audio_nuevo:
        rtf = narrador.segundos_sintesis / narrador.segundos_audio_nuevo
        print(f"Síntesis nueva: {narrador.segundos_sintesis:.1f} s para "
              f"{narrador.segundos_audio_nuevo:.1f} s de audio (RTF {rtf:.2f})")
    else:
        print("Todo el audio estaba ya generado; solo se han montado los archivos.")


if __name__ == "__main__":
    main()
