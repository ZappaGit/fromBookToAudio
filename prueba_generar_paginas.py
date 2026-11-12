"""Genera dos páginas de prueba en entrada/prueba/ para comprobar el proceso completo.

Ejecutar desde la carpeta del repositorio con el venv:
    .\\.venv\\Scripts\\python.exe prueba_generar_paginas.py

El texto es inventado para la prueba. Incluye los casos que debe resolver el paso 2:
título de capítulo, sangrías, palabras partidas con guion, número de página y un párrafo
que continúa de una página a la siguiente. La segunda página imita una foto (girada, con
fondo gris). También escribe trabajo/prueba/esperado.txt con el texto correcto.
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

import config

FUENTE = r"C:\Windows\Fonts\georgia.ttf"
ANCHO, ALTO = 1500, 2200
MARGEN = 190
CUERPO = 42
INTERLINEA = 66
SANGRIA = 70

# Cada párrafo es una lista de líneas, tal como se imprimen. "#" marca un título centrado.
PAGINA_1 = [
    ["#Capítulo 1"],
    ["Aquella mañana el faro amaneció envuelto en una niebla",
     "tan espesa que Marta no distinguía la barandilla desde la",
     "ventana. Preparó café, encendió la radio y esperó, como ca-",
     "da día, el parte del tiempo de las siete."],
    ["—Hoy no sale ningún barco —dijo el locutor—. Viento",
     "del noroeste y mar gruesa hasta la tarde."],
    ["Ella sonrió. Llevaba doce años cuidando la linterna y",
     "había aprendido que los días sin barcos eran los mejores",
     "para subir a limpiar los cristales, engrasar el mecanis-",
     "mo y escribir en el cuaderno. Subió los ciento cuarenta",
     "escalones despacio, contando en voz baja, y al llegar"],
]
PAGINA_2 = [
    ["arriba encontró algo que no esperaba: una gaviota dormida",
     "junto a la lámpara, tranquila como si la torre fuera suya."],
    ["¿Qué podía hacer? No quiso despertarla. Se sentó en el",
     "último escalón, abrió el cuaderno y anotó la fecha, la hora",
     "y una sola frase: «Hoy tenemos visita»."],
]
NUMEROS = ["7", "8"]

ESPERADO = """# Capítulo 1

Aquella mañana el faro amaneció envuelto en una niebla tan espesa que Marta no distinguía la barandilla desde la ventana. Preparó café, encendió la radio y esperó, como cada día, el parte del tiempo de las siete.

—Hoy no sale ningún barco —dijo el locutor—. Viento del noroeste y mar gruesa hasta la tarde.

Ella sonrió. Llevaba doce años cuidando la linterna y había aprendido que los días sin barcos eran los mejores para subir a limpiar los cristales, engrasar el mecanismo y escribir en el cuaderno. Subió los ciento cuarenta escalones despacio, contando en voz baja, y al llegar arriba encontró algo que no esperaba: una gaviota dormida junto a la lámpara, tranquila como si la torre fuera suya.

¿Qué podía hacer? No quiso despertarla. Se sentó en el último escalón, abrió el cuaderno y anotó la fecha, la hora y una sola frase: «Hoy tenemos visita».
"""


def dibujar(parrafos, numero, continua):
    """`continua` indica que el primer párrafo viene de la página anterior (sin sangría)."""
    imagen = Image.new("RGB", (ANCHO, ALTO), "white")
    lapiz = ImageDraw.Draw(imagen)
    fuente = ImageFont.truetype(FUENTE, CUERPO)
    fuente_titulo = ImageFont.truetype(FUENTE, 60)
    y = MARGEN
    for n, parrafo in enumerate(parrafos):
        if parrafo[0].startswith("#"):
            titulo = parrafo[0][1:]
            ancho = lapiz.textlength(titulo, font=fuente_titulo)
            lapiz.text(((ANCHO - ancho) / 2, y + 60), titulo, font=fuente_titulo, fill="black")
            y += 260
            continue
        for i, linea in enumerate(parrafo):
            sangrar = i == 0 and not (n == 0 and continua)
            lapiz.text((MARGEN + (SANGRIA if sangrar else 0), y), linea, font=fuente, fill="black")
            y += INTERLINEA
    ancho = lapiz.textlength(numero, font=fuente)
    lapiz.text(((ANCHO - ancho) / 2, ALTO - 150), numero, font=fuente, fill="black")
    return imagen


def main():
    entrada = config.ENTRADA / "prueba"
    trabajo = config.TRABAJO / "prueba"
    entrada.mkdir(parents=True, exist_ok=True)
    trabajo.mkdir(parents=True, exist_ok=True)

    dibujar(PAGINA_1, NUMEROS[0], continua=False).save(entrada / "pagina_001.png")

    # La segunda imita una foto: fondo gris, giro leve y compresión JPEG.
    pagina = dibujar(PAGINA_2, NUMEROS[1], continua=True)
    foto = Image.blend(pagina, Image.new("RGB", pagina.size, (150, 145, 135)), 0.25)
    foto = foto.rotate(1.2, expand=True, fillcolor=(90, 85, 80), resample=Image.BICUBIC)
    foto.save(entrada / "pagina_002.jpg", quality=70)

    (trabajo / "esperado.txt").write_text(ESPERADO, encoding="utf-8")
    print(f"Páginas de prueba en {entrada}")
    print(f"Texto esperado en {trabajo / 'esperado.txt'}")


if __name__ == "__main__":
    main()
