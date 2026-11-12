"""Creates two test pages in input/test/ to check the whole pipeline.

Run from the repository folder with the virtual environment:
    .\\.venv\\Scripts\\python.exe test_generate_pages.py

The text is invented (in Spanish, because the voice is Spanish). It covers the cases step 2 must
handle: chapter heading, indents, words hyphenated at line ends, a page number, and a paragraph
that continues from one page to the next. The second page imitates a photo (rotated, grey
background). It also writes work/test/expected.txt with the correct text.
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

import config

FONT = r"C:\Windows\Fonts\georgia.ttf"
WIDTH, HEIGHT = 1500, 2200
MARGIN = 190
BODY_SIZE = 42
LINE_SPACING = 66
INDENT = 70

# Each paragraph is a list of lines, as printed. "#" marks a centred heading.
PAGE_1 = [
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
PAGE_2 = [
    ["arriba encontró algo que no esperaba: una gaviota dormida",
     "junto a la lámpara, tranquila como si la torre fuera suya."],
    ["¿Qué podía hacer? No quiso despertarla. Se sentó en el",
     "último escalón, abrió el cuaderno y anotó la fecha, la hora",
     "y una sola frase: «Hoy tenemos visita»."],
]
PAGE_NUMBERS = ["7", "8"]

EXPECTED = """# Capítulo 1

Aquella mañana el faro amaneció envuelto en una niebla tan espesa que Marta no distinguía la barandilla desde la ventana. Preparó café, encendió la radio y esperó, como cada día, el parte del tiempo de las siete.

—Hoy no sale ningún barco —dijo el locutor—. Viento del noroeste y mar gruesa hasta la tarde.

Ella sonrió. Llevaba doce años cuidando la linterna y había aprendido que los días sin barcos eran los mejores para subir a limpiar los cristales, engrasar el mecanismo y escribir en el cuaderno. Subió los ciento cuarenta escalones despacio, contando en voz baja, y al llegar arriba encontró algo que no esperaba: una gaviota dormida junto a la lámpara, tranquila como si la torre fuera suya.

¿Qué podía hacer? No quiso despertarla. Se sentó en el último escalón, abrió el cuaderno y anotó la fecha, la hora y una sola frase: «Hoy tenemos visita».
"""


def draw_page(paragraphs, number, continued):
    """`continued` means the first paragraph comes from the previous page (no indent)."""
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    pen = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, BODY_SIZE)
    title_font = ImageFont.truetype(FONT, 60)
    y = MARGIN
    for n, paragraph in enumerate(paragraphs):
        if paragraph[0].startswith("#"):
            title = paragraph[0][1:]
            width = pen.textlength(title, font=title_font)
            pen.text(((WIDTH - width) / 2, y + 60), title, font=title_font, fill="black")
            y += 260
            continue
        for i, line in enumerate(paragraph):
            indent = i == 0 and not (n == 0 and continued)
            pen.text((MARGIN + (INDENT if indent else 0), y), line, font=font, fill="black")
            y += LINE_SPACING
    width = pen.textlength(number, font=font)
    pen.text(((WIDTH - width) / 2, HEIGHT - 150), number, font=font, fill="black")
    return image


def main():
    source = config.INPUT_DIR / "test"
    work = config.WORK_DIR / "test"
    source.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    draw_page(PAGE_1, PAGE_NUMBERS[0], continued=False).save(source / "pagina_001.png")

    # The second page imitates a photo: grey background, slight rotation and JPEG compression.
    page = draw_page(PAGE_2, PAGE_NUMBERS[1], continued=True)
    photo = Image.blend(page, Image.new("RGB", page.size, (150, 145, 135)), 0.25)
    photo = photo.rotate(1.2, expand=True, fillcolor=(90, 85, 80), resample=Image.BICUBIC)
    photo.save(source / "pagina_002.jpg", quality=70)

    (work / "expected.txt").write_text(EXPECTED, encoding="utf-8")
    print(f"Test pages in {source}")
    print(f"Expected text in {work / 'expected.txt'}")


if __name__ == "__main__":
    main()
