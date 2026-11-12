"""Step 2 · Text: joins the OCR of all pages into a single book.txt that can be edited.

Run from the repository folder with the virtual environment:
    .\\.venv\\Scripts\\python.exe step2_text.py <book> [--force]

What it does:
  - removes page numbers (lines with only digits at the top or bottom of the page);
  - rebuilds paragraphs (indent, vertical gap, or a short line ending a sentence);
  - joins words hyphenated at the end of a line;
  - joins a paragraph that continues from one page to the next;
  - marks chapter headings with "# " (each one becomes its own audio file).

The result, work/<book>/book.txt, can be corrected by hand before step 3.
Format: paragraphs separated by a blank line; headings on lines starting with "# ".
If book.txt already exists it is not overwritten (so corrections are kept), unless --force is given.
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


def is_title(text):
    return len(text) <= config.MAX_TITLE_LENGTH and bool(IS_TITLE.match(text))


def join(previous, following):
    """Join two pieces of text; if the first ends with a hyphen, glue the word back together."""
    cut = re.search(r"(?<=\w)\s*[-¬]$", previous)
    if cut and following[:1].islower():
        return previous[:cut.start()] + following
    return f"{previous} {following}"


def clean(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?»)])", r"\1", text)   # no space before closing punctuation
    text = re.sub(r"([«(¿¡])\s+", r"\1", text)       # no space after opening punctuation
    return text


def paragraphs_of_page(page):
    """Return the paragraphs of one page, based on the position of its lines."""
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

    line_height = statistics.median(l["y1"] - l["y0"] for l in lines)
    left_margin = statistics.median(l["x0"] for l in lines)
    right_margin = max(l["x1"] for l in lines)
    text_width = max(right_margin - left_margin, 1)
    steps = [b["y0"] - a["y0"] for a, b in zip(lines, lines[1:])]
    step = statistics.median(steps) if steps else line_height

    paragraphs = [lines[0]["text"]]
    for previous, line in zip(lines, lines[1:]):
        indent = line["x0"] > left_margin + 0.8 * line_height
        gap = (line["y0"] - previous["y0"]) > 1.5 * step
        previous_short = previous["x1"] < right_margin - 0.15 * text_width
        previous_closed = previous_short and previous["text"].endswith(END_OF_SENTENCE)
        if indent or gap or previous_closed or is_title(previous["text"]) or is_title(line["text"]):
            paragraphs.append(line["text"])
        else:
            paragraphs[-1] = join(paragraphs[-1], line["text"])
    return paragraphs


def main():
    book = config.book_from_args()
    source, work, _ = config.folders(book)
    target = work / "book.txt"
    if target.exists() and not FORCE:
        sys.exit(f"{target} already exists and may contain corrections. Use --force to regenerate it.")

    images = sorted(p for p in source.iterdir() if p.suffix.lower() in config.IMAGE_EXTENSIONS)
    paragraphs = []
    for path in images:
        ocr_file = work / "ocr" / f"{path.stem}.json"
        if not ocr_file.exists():
            sys.exit(f"Missing OCR for {path.name}. Run step1_ocr.py {book} first.")
        for page in json.loads(ocr_file.read_text(encoding="utf-8"))["pages"]:
            new = paragraphs_of_page(page)
            # The first paragraph of the page continues the previous one if that one was left open.
            if (new and paragraphs and not paragraphs[-1].endswith(END_OF_SENTENCE)
                    and not is_title(paragraphs[-1]) and not is_title(new[0])):
                paragraphs[-1] = join(paragraphs[-1], new.pop(0))
            paragraphs.extend(new)

    blocks = []
    for text in map(clean, paragraphs):
        if text:
            blocks.append(f"# {text}" if is_title(text) else text)
    target.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

    titles = sum(b.startswith("# ") for b in blocks)
    characters = sum(len(b) for b in blocks)
    print(f"{target}: {len(blocks) - titles} paragraphs, {titles} titles, {characters} characters")
    print("Review and correct the text before generating the audio (step3_audio.py).")


if __name__ == "__main__":
    main()
