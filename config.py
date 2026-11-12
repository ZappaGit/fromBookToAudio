"""Parámetros del lab de audiolibros. Los tres pasos leen de aquí.

Estructura de carpetas (una subcarpeta por libro):
    entrada/<libro>/   imágenes escaneadas o fotografiadas, ordenadas por nombre
    trabajo/<libro>/   resultados intermedios (OCR por página, libro.txt, audio por bloque)
    salida/<libro>/    audiolibro final, un MP3 por capítulo
"""
import pathlib
import sys

# Para que los acentos se impriman bien en la consola de Windows.
sys.stdout.reconfigure(encoding="utf-8")

RAIZ = pathlib.Path(__file__).parent
ENTRADA = RAIZ / "entrada"
TRABAJO = RAIZ / "trabajo"
SALIDA = RAIZ / "salida"

# ---------- Paso 1: OCR ----------
ALFABETO_OCR = "LATIN"        # modelo de RapidOCR: LATIN cubre español, inglés, francés…
EXTENSIONES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
LADO_MAXIMO = 2400            # px; las fotos más grandes se reducen (más rápido, misma lectura)
PAGINAS_DOBLES = False        # True si cada imagen contiene dos páginas (libro abierto)
MARGEN_SUPERIOR = 0.0         # fracción de la altura que se ignora arriba (cabeceras), p. ej. 0.07
MARGEN_INFERIOR = 0.0         # fracción de la altura que se ignora abajo (pies de página)
CONFIANZA_MINIMA = 0.30       # fragmentos por debajo se descartan (manchas, ruido)
CONFIANZA_AVISO = 0.90       # páginas con media inferior se marcan "revisar" en el informe

# ---------- Paso 2: texto ----------
# Una línea corta que empiece así se toma como título de capítulo.
PATRON_CAPITULO = r"^(cap[ií]tulo|parte|pr[oó]logo|ep[ií]logo|introducci[oó]n|prefacio)\b"
LONGITUD_MAXIMA_TITULO = 60

# ---------- Paso 3: audio ----------
IDIOMA_VOZ = "e"              # código de Kokoro: 'e' español (requiere espeak-ng), 'a' inglés EE. UU.
VOZ = "ef_dora"               # ef_dora, em_alex, em_santa; admite mezclas: "ef_dora,em_alex"
VELOCIDAD = 1.0               # 0.8 más lento, 1.2 más rápido
FRECUENCIA = 24000            # Hz; es la frecuencia de salida de Kokoro
MAX_CARACTERES = 300          # tamaño máximo de cada trozo enviado al modelo (evita recortes)
PAUSA_PARRAFO = 0.6           # segundos de silencio entre párrafos
PAUSA_TITULO = 1.2            # segundos de silencio después de un título
FORMATO_SALIDA = "MP3"        # "MP3", "FLAC" o "WAV"


def carpetas(libro: str):
    """Devuelve (entrada, trabajo, salida) del libro y crea las dos últimas."""
    entrada = ENTRADA / libro
    trabajo = TRABAJO / libro
    salida = SALIDA / libro
    if not entrada.is_dir():
        sys.exit(f"No existe la carpeta de imágenes: {entrada}")
    trabajo.mkdir(parents=True, exist_ok=True)
    salida.mkdir(parents=True, exist_ok=True)
    return entrada, trabajo, salida


def libro_de_argumentos() -> str:
    """Nombre del libro: primer argumento que no empieza por '--'."""
    nombres = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(nombres) != 1:
        sys.exit(f"Uso: python {pathlib.Path(sys.argv[0]).name} <libro> [--forzar]")
    return nombres[0]
