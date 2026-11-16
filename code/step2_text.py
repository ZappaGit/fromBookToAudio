"""Step 2 · Text: joins the OCR of all pages into a single book.txt that can be edited.

Run from the repository folder with the virtual environment:
    .\\.venv\\Scripts\\python.exe code\\step2_text.py <book> [--force] [--markdown] [--per-image]

What it does:
  - removes page numbers (lines with only digits at the top or bottom of the page);
  - rebuilds paragraphs (indent, vertical gap, or a short line ending a sentence);
  - joins words hyphenated at the end of a line;
  - joins a paragraph that continues from one page to the next;
  - marks chapter headings with "# " (each one becomes its own audio file).

The result, work/<book>/book.txt, can be corrected by hand before step 3.
Format: paragraphs separated by a blank line; headings on lines starting with "# ".
If book.txt already exists it is not overwritten (so corrections are kept), unless --force is given.

With --markdown (or MARKDOWN = True in book.ini) it also writes work/<book>/book.md, which keeps
the format of the page: headings, bullet lists and bold words. It is built from the OCR, not from
book.txt, so corrections made in one file are not in the other. The audio is always made from book.txt.

With --per-image (or PER_IMAGE = True in book.ini) every image is a document of its own: it becomes a
chapter of book.txt, titled with the headings it starts with, so step 3 makes one audio file per image.
"""
import json
import re
import statistics
import sys

import config

FORCE = "--force" in sys.argv
END_OF_SENTENCE = tuple(".!?…:»\"”)")
IS_TITLE = re.compile(config.CHAPTER_PATTERN, re.IGNORECASE)
IS_PAGE_NUMBER = re.compile(r"^[\W_]*\d{1,4}[\W_]*$")
BULLET = re.compile(r"^\s*[•·▪◦●○■□‣⁃]\s*")
NOT_A_HEADING_START = ("—", "–", "-", "«", "\"", "“")
NOT_A_HEADING_END = (".", ",", ";", ":", "…")
TALLER = 1.15          # x usual text height; a line this tall is a heading
MUCH_TALLER = 1.5      # x usual text height; a line this tall is the main title
DOCUMENT_MARK = "<!-- document: {} -->"   # starts each document in book.md with PER_IMAGE


def is_title(text):
    return len(text) <= config.MAX_TITLE_LENGTH and bool(IS_TITLE.match(text))


def join(previous, following):
    """Join two pieces of text; if the first ends with a hyphen, glue the word back together."""
    cut = re.search(r"(?<=\w)\s*[-¬](\*\*)?$", previous)       # "**" closes a bold word in book.md
    start = following.lstrip("*")
    if cut and start[:1].islower():
        if cut.group(1) and following.startswith("**"):
            return previous[:cut.start()] + start                # the bold word goes on
        return previous[:cut.start()] + (cut.group(1) or "") + following
    return f"{previous} {following}"


def clean(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?»)])", r"\1", text)   # no space before closing punctuation
    text = re.sub(r"([«(¿¡])\s+", r"\1", text)       # no space after opening punctuation
    return text


def tidy_bold(text):
    """Join bold words that follow each other and leave the punctuation after them outside."""
    text = re.sub(r"\*\*(\s*)\*\*", r"\1", text)
    return re.sub(r"\*\*([^*]*?)([.,;:!?»)]*)\*\*",
                  lambda m: f"**{m[1].strip()}**{m[2]}" if m[1].strip() else m[2], text)


def plain_and_marked(line):
    """Return (is bullet, text of the line, the same text with **bold** marks)."""
    text, spans = line["text"], line.get("bold", [])
    bullet = BULLET.match(text)
    if bullet:
        cut = bullet.end()
        text = text[cut:]
        spans = [[max(a - cut, 0), b - cut] for a, b in spans if b > cut]
    marked = text
    for a, b in reversed(spans):
        marked = f"{marked[:a]}**{marked[a:b]}**{marked[b:]}"
    return bool(bullet), text, marked


def blocks_of_page(page):
    """Return the paragraphs of one page, based on the position of its lines.

    Each one is a dict: "text", "marked" (the text with **bold** marks), "bullet" (list item),
    "column" (it sits in a box beside others) and "level" (0, or 1 to 3 if it looks like a heading).
    """
    height = page["height"]
    lines = []
    for line in page["lines"]:
        center = (line["y0"] + line["y1"]) / 2
        at_edge = center < height * 0.12 or center > height * 0.88
        if at_edge and IS_PAGE_NUMBER.match(line["text"]):
            continue
        lines.append(line)
    if not lines:
        return []

    # Lines are grouped in blocks by step 1 (boxes side by side); older OCR files have a single block.
    groups = []
    for line in lines:
        if groups and groups[-1][0].get("block", 0) == line.get("block", 0):
            groups[-1].append(line)
        else:
            groups.append([line])

    def tall(line):
        return line.get("height", line["y1"] - line["y0"])

    def level(line):                                  # height on the page, corrected for tilted photos
        return line.get("level", line["y0"])

    line_height = statistics.median(l["y1"] - l["y0"] for l in lines)
    usual_height = statistics.median(tall(l) for l in lines)
    steps = [level(b) - level(a) for group in groups for a, b in zip(group, group[1:])]
    step = statistics.median(steps) if steps else line_height

    paragraphs = []
    for group in groups:
        left_margin = statistics.median(l["x0"] for l in group)
        right_margin = max(l["x1"] for l in group)
        text_width = max(right_margin - left_margin, 1)
        previous, bullet_x = None, None
        for line in group:
            bullet, text, marked = plain_and_marked(line)
            # The heading of a box sits closer to its text than a paragraph gap: ask for less there.
            box_heading = line.get("column") and previous is group[0]
            gap = previous is not None and (level(line) - level(previous)) > (1.2 if box_heading else 1.5) * step
            if previous is None or bullet:
                new = True
            elif bullet_x is not None and not gap and line["x0"] > bullet_x + 0.3 * line_height:
                new = False                           # the list item goes on in the next line
            else:
                indent = line["x0"] > left_margin + 0.8 * line_height
                previous_short = previous["x1"] < right_margin - 0.15 * text_width
                previous_closed = previous_short and previous["text"].endswith(END_OF_SENTENCE)
                # A line that stops well before the margin, followed by a capital: a heading or a new start.
                previous_stub = (previous["x1"] < left_margin + 0.6 * text_width
                                 and not previous["text"].endswith(",")
                                 and (text[:1].isupper() or text[:1] in "¿¡"))
                new = (indent or gap or previous_closed or previous_stub
                       or is_title(previous["text"]) or is_title(line["text"]))
            if new:
                bullet_x = line["x0"] if bullet else None
                stub = line["x1"] < left_margin + 0.6 * text_width
                paragraphs.append({"text": text, "marked": marked, "bullet": bullet, "lines": 1,
                                   "apart": previous is None or gap or stub, "height": tall(line),
                                   "column": bool(line.get("column"))})
            else:
                last = paragraphs[-1]
                last["text"], last["marked"] = join(last["text"], text), join(last["marked"], marked)
                last["lines"] += 1
            previous = line

    for p in paragraphs:
        text = clean(p["text"])
        heading = (p["lines"] == 1 and not p["bullet"] and len(text) <= config.MAX_TITLE_LENGTH
                   and re.search(r"[^\W\d_]", text) and not text.endswith(NOT_A_HEADING_END)
                   and not text.startswith(NOT_A_HEADING_START)
                   and (p["apart"] or p["height"] >= TALLER * usual_height))
        if is_title(text) or (heading and p["height"] >= MUCH_TALLER * usual_height):
            p["level"] = 1
        elif heading:
            p["level"] = 3 if p["column"] else 2
        else:
            p["level"] = 0
    return paragraphs


def paragraphs_of_page(page):
    """Return the text of the paragraphs of one page."""
    return [p["text"] for p in blocks_of_page(page)]


def as_markdown(paragraphs):
    """Return the paragraphs as Markdown: # headings, - list items and **bold** words."""
    parts, previous_bullet = [], False
    for p in paragraphs:
        text = clean(p["text"])
        if not text:
            continue
        if p["level"]:
            piece = f"{'#' * p['level']} {text}"
        else:
            piece = ("- " if p["bullet"] else "") + tidy_bold(clean(p["marked"]))
        parts.append(("\n" if p["bullet"] and previous_bullet else "\n\n") + piece)
        previous_bullet = p["bullet"]
    return "".join(parts).strip() + "\n"


def continue_with(paragraphs, new):
    """Add the paragraphs of a new page; its first one continues the last one if that was left open."""
    if (new and paragraphs and not paragraphs[-1]["text"].endswith(END_OF_SENTENCE)
            and not is_title(paragraphs[-1]["text"]) and not is_title(new[0]["text"])
            and not new[0]["bullet"] and not new[0]["level"] and not paragraphs[-1]["level"]):
        first, last = new.pop(0), paragraphs[-1]
        last["text"], last["marked"] = join(last["text"], first["text"]), join(last["marked"], first["marked"])
    paragraphs.extend(new)


def document_title(name, paragraphs):
    """Return (title, remaining paragraphs) for a document made from one image.

    The headings it starts with become the title ("EL CICLO DEL AGUA. LA EVAPORACIÓN"); a document that
    starts with plain text is titled after its image file.
    """
    headings = []
    for p in paragraphs[:2]:
        if not p["level"] or not clean(p["text"]):
            break
        headings.append(clean(p["text"]).rstrip(".:"))
    if headings:
        return ". ".join(headings), paragraphs[len(headings):]
    return re.sub(r"[_-]+", " ", name).strip(), paragraphs


def main():
    book = config.book_from_args()
    source, work, _ = config.folders(book)
    target, markdown = work / "book.txt", work / "book.md"
    per_image = "--per-image" in sys.argv or config.PER_IMAGE
    write_text = FORCE or not target.exists()
    write_markdown = ("--markdown" in sys.argv or config.MARKDOWN) and (FORCE or not markdown.exists())
    if not write_text and not write_markdown:
        sys.exit(f"{target} already exists and may contain corrections. Use --force to regenerate it.")

    images = sorted(p for p in source.iterdir() if p.suffix.lower() in config.IMAGE_EXTENSIONS)
    documents = []                                    # [(image, paragraphs)]
    for path in images:
        ocr_file = work / "ocr" / f"{path.stem}.json"
        if not ocr_file.exists():
            sys.exit(f"Missing OCR for {path.name}. Run step1_ocr.py {book} first.")
        if per_image or not documents:
            documents.append((path, []))
        for page in json.loads(ocr_file.read_text(encoding="utf-8"))["pages"]:
            continue_with(documents[-1][1], blocks_of_page(page))

    if write_text:
        blocks = []
        for path, paragraphs in documents:
            if per_image:                             # each image is a chapter: its own audio file
                title, paragraphs = document_title(path.stem, paragraphs)
                blocks.append(f"# {title}")
                blocks += [text for text in (clean(p["text"]) for p in paragraphs) if text]
            else:
                for text in (clean(p["text"]) for p in paragraphs):
                    if text:
                        blocks.append(f"# {text}" if is_title(text) else text)
        target.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
        titles = sum(b.startswith("# ") for b in blocks)
        characters = sum(len(b) for b in blocks)
        print(f"{target}: {len(blocks) - titles} paragraphs, {titles} titles, {characters} characters")
        print("Review and correct the text before generating the audio (step3_audio.py).")
    else:
        print(f"Kept the existing {target} (use --force to rebuild it).")

    if write_markdown:
        if per_image:                                 # step 3 splits book.md at these marks
            text = "\n".join(f"{DOCUMENT_MARK.format(path.name)}\n\n{as_markdown(paragraphs)}"
                             for path, paragraphs in documents)
        else:
            text = as_markdown(documents[0][1] if documents else [])
        markdown.write_text(text, encoding="utf-8")
        every = [p for _, paragraphs in documents for p in paragraphs]
        headings = sum(bool(p["level"]) for p in every)
        items = sum(p["bullet"] for p in every)
        print(f"{markdown}: {headings} headings, {items} list items. Bold words are a guess: check them.")


if __name__ == "__main__":
    main()
