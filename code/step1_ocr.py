"""Step 1 · OCR: reads the images in input/<book>/ and saves the text of each page.

Run from the repository folder with the virtual environment:
    .\\.venv\\Scripts\\python.exe step1_ocr.py <book> [--force]

For each image it writes work/<book>/ocr/<image>.json with the detected lines
(text, position and confidence). Pages already processed are skipped; --force redoes them.
Each line also records the layout that step 2 needs to keep the format of the page: the text
height, the block it belongs to (boxes side by side are read one after another, not across)
and which words look bold.
At the end it writes work/<book>/ocr_report.csv with the mean confidence of each page.
"""
import csv
import json
import sys
import time

import numpy as np
from PIL import Image, ImageOps

import config

FORCE = "--force" in sys.argv
BAND_GAP = 0.25        # x text height; a taller empty strip separates two horizontal bands of text
COLUMN_GAP = 0.7       # x text height; a wider empty strip separates two side-by-side columns
COLUMN_WIDTH = 2.0     # x text height; anything narrower (a bullet mark) is not a column
COLUMN_REACH = 1.5     # x text height; a band further below does not continue the columns above
BOLD_FACTOR = 1.35     # a word is bold when its strokes are this much thicker than the page's usual


def load_pages(path):
    """Open the image, fix its rotation, crop the edges, and return one or two pages."""
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if config.ROTATE:
        if config.ROTATE not in (90, 180, 270):
            sys.exit(f"ROTATE must be 0, 90, 180 or 270 (got {config.ROTATE})")
        image = image.rotate(-config.ROTATE, expand=True)   # PIL rotates counter-clockwise
    left, top, right, bottom = config.CROP
    if any(config.CROP):
        if min(config.CROP) < 0 or left + right >= 1 or top + bottom >= 1:
            sys.exit(f"CROP fractions must be >= 0 and leave some image (got {config.CROP})")
        width, height = image.size
        image = image.crop((round(width * left), round(height * top),
                            round(width * (1 - right)), round(height * (1 - bottom))))
    if config.DOUBLE_PAGES:
        width, height = image.size
        x = gutter_x(image)
        halves = [image.crop((0, 0, x, height)), image.crop((x, 0, width, height))]
    else:
        halves = [image]
    pages = []
    for page in halves:
        if max(page.size) > config.MAX_SIDE:
            page.thumbnail((config.MAX_SIDE, config.MAX_SIDE), Image.LANCZOS)
        pages.append(page)
    return pages


def gutter_x(image):
    """x of the gap between the two pages of an open book: the widest text-free band near the middle.

    Photos are rarely centred, so cutting at exactly half the width can slice a page's text.
    """
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    height = gray.shape[0]
    band = gray[int(height * 0.1):int(height * 0.9)]
    edges = np.convolve(np.abs(np.diff(band, axis=1)).sum(axis=0), np.ones(15) / 15, mode="same")
    lo, hi = int(len(edges) * 0.35), int(len(edges) * 0.75)
    quiet = edges[lo:hi] < np.median(edges[lo:hi]) * 0.35
    best, start = (0, 0), None
    for i, q in enumerate([*quiet, False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    if best == (0, 0):
        return gray.shape[1] // 2
    return lo + (best[0] + best[1]) // 2


def inside_text_column(fragments):
    """Drop fragments that lie beside the page's text column (other books, objects in the photo)."""
    if len(fragments) < 5:
        return fragments
    widest = max(f["x1"] - f["x0"] for f in fragments)
    body = [f for f in fragments if f["x1"] - f["x0"] >= 0.5 * widest]   # full text lines
    left = np.percentile([f["x0"] for f in body], 10)
    right = np.percentile([f["x1"] for f in body], 90)
    return [f for f in fragments if f["x0"] < right and f["x1"] > left]


def stroke_thickness(gray, x0, y0, x1, y1):
    """Mean thickness in pixels of the pen strokes inside the box (0.0 if it cannot be measured)."""
    crop = gray[max(int(y0), 0):int(y1) + 1, max(int(x0), 0):int(x1) + 1]
    if crop.size < 20:
        return 0.0
    paper, dark = np.percentile(crop, 90), np.percentile(crop, 2)
    if paper - dark < 40:                             # no clear ink in the box
        return 0.0
    cover = np.clip((paper - crop) / (paper - dark), 0, 1)
    ink = cover > 0.5
    widths = []
    for mask, soft in ((ink, cover), (ink.T, cover.T)):      # across and down; thin strokes win
        padded = np.pad(mask, ((0, 0), (1, 1)))
        runs = (padded[:, 1:] & ~padded[:, :-1]).sum()
        widths.append(float(soft[mask].sum()) / max(int(runs), 1))
    return min(widths)


def mark_bold(fragments):
    """Add to each fragment the character spans of its text that look bold ("bold": [[start, end]]).

    Each fragment brings "words": [(text, thickness relative to the text height)]. A word counts as
    bold when it is clearly thicker than the usual word of the page; short words are too noisy to
    decide alone, so they follow their neighbours.
    """
    usual = [t for f in fragments for w, t in f.get("words", []) if len(w) >= 4 and t]
    usual = float(np.median(usual)) if len(usual) >= 10 else 0.0
    for frag in fragments:
        words = frag.pop("words", [])
        if not usual:
            continue
        ratios = [t / usual for _, t in words]
        bold = [len(w) >= 4 and r >= BOLD_FACTOR for (w, _), r in zip(words, ratios)]
        for i, (word, _) in enumerate(words):
            if len(word) < 4 and ratios[i] >= 1.15:
                around = [bold[j] for j in (i - 1, i + 1) if 0 <= j < len(words) and len(words[j][0]) >= 4]
                bold[i] = bool(around) and all(around)
        spans, cursor = [], 0
        for (word, _), is_bold in zip(words, bold):
            start = frag["text"].find(word, cursor)
            if start < 0:
                continue
            cursor = start + len(word)
            if is_bold and spans and frag["text"][spans[-1][1]:start].strip() == "":
                spans[-1][1] = cursor                 # continues the previous bold word
            elif is_bold:
                spans.append([start, cursor])
        if spans:
            frag["bold"] = spans


def split_into_blocks(fragments):
    """Return the fragments as blocks in reading order: [(is_column, [fragments])].

    Text boxes that sit side by side are found as bands of text crossed by empty vertical strips;
    each column becomes its own block, read top to bottom, instead of being read across.
    A page with a single column of text comes back as one block.
    """
    if not fragments:
        return []
    unit = float(np.median([f.get("text_height", f["y1"] - f["y0"]) for f in fragments]))
    skew = float(np.median([f.get("slope", 0.0) for f in fragments]))

    def top(f):
        height = f.get("text_height", f["y1"] - f["y0"])
        return (f["y0"] + f["y1"]) / 2 - skew * (f["x0"] + f["x1"]) / 2 - height / 2

    bands = []                                        # horizontal bands separated by empty strips
    for frag in sorted(fragments, key=top):
        bottom = top(frag) + frag.get("text_height", frag["y1"] - frag["y0"])
        if bands and top(frag) - bands[-1]["bottom"] < BAND_GAP * unit:
            bands[-1]["fragments"].append(frag)
            bands[-1]["bottom"] = max(bands[-1]["bottom"], bottom)
        else:
            bands.append({"top": top(frag), "bottom": bottom, "fragments": [frag]})

    def columns_of(band):
        columns = []
        for frag in sorted(band["fragments"], key=lambda f: f["x0"]):
            if columns and frag["x0"] - columns[-1]["x1"] < COLUMN_GAP * unit:
                columns[-1]["fragments"].append(frag)
                columns[-1]["x1"] = max(columns[-1]["x1"], frag["x1"])
            else:
                columns.append({"x0": frag["x0"], "x1": frag["x1"], "fragments": [frag]})
        if any(c["x1"] - c["x0"] < COLUMN_WIDTH * unit for c in columns):
            return [{"x0": min(c["x0"] for c in columns), "x1": max(c["x1"] for c in columns),
                     "fragments": list(band["fragments"])}]
        return columns

    def matches(region, columns):
        """Index of the region column each new column falls under, or None if they do not line up."""
        found = []
        for column in columns:
            under = [i for i, r in enumerate(region) if column["x0"] < r["x1"] and column["x1"] > r["x0"]]
            if len(under) != 1 or under[0] in found:
                return None
            found.append(under[0])
        return found

    blocks, plain, region, region_bottom = [], [], None, 0.0

    def close_region():
        nonlocal region, plain
        if region is None:
            return
        if all(len(c["fragments"]) >= 2 for c in region):
            if plain:
                blocks.append((False, plain))
                plain = []
            blocks.extend((True, c["fragments"]) for c in region)
        else:                                         # a chance gap in one line, not real columns
            plain += [f for c in region for f in c["fragments"]]
        region = None

    for band in bands:
        columns = columns_of(band)
        found = None
        if region is not None and band["top"] - region_bottom <= COLUMN_REACH * unit:
            found = matches(region, columns)
        if found is not None:
            for index, column in zip(found, columns):
                region[index]["fragments"] += column["fragments"]
                region[index]["x0"] = min(region[index]["x0"], column["x0"])
                region[index]["x1"] = max(region[index]["x1"], column["x1"])
            region_bottom = band["bottom"]
            continue
        close_region()
        if len(columns) >= 2:
            region, region_bottom = columns, band["bottom"]
        else:
            plain += band["fragments"]
    close_region()
    if plain:
        blocks.append((False, plain))
    return blocks


def group_into_lines(fragments):
    """Join OCR fragments that sit at the same height into lines of text."""
    # Photographed pages are often tilted: measure the dominant slope and compare
    # heights as if the page were straight, using the text height, not the box height.
    skew = float(np.median([f.get("slope", 0.0) for f in fragments])) if fragments else 0.0

    def level(f):
        return (f["y0"] + f["y1"]) / 2 - skew * (f["x0"] + f["x1"]) / 2

    lines = []
    for frag in sorted(fragments, key=level):
        center = level(frag)
        height = frag.get("text_height", frag["y1"] - frag["y0"])
        current = lines[-1] if lines else None
        if current and abs(center - current["center"]) < 0.5 * min(height, current["height"]):
            current["fragments"].append(frag)
            n = len(current["fragments"])
            current["center"] += (center - current["center"]) / n
        else:
            lines.append({"center": center, "height": height, "fragments": [frag]})

    result = []
    for line in lines:
        frags = sorted(line["fragments"], key=lambda f: f["x0"])
        bold, offset = [], 0                          # bold spans, moved to their place in the line
        for f in frags:
            bold += [[offset + a, offset + b] for a, b in f.get("bold", [])]
            offset += len(f["text"]) + 1
        result.append({
            "text": " ".join(f["text"] for f in frags).strip(),
            "x0": min(f["x0"] for f in frags),
            "y0": min(f["y0"] for f in frags),
            "x1": max(f["x1"] for f in frags),
            "y1": max(f["y1"] for f in frags),
            "confidence": round(float(np.mean([f["confidence"] for f in frags])), 3),
            "height": round(float(np.median([f.get("text_height", f["y1"] - f["y0"]) for f in frags])), 1),
            "level": round(float(line["center"]), 1),      # height on the page as if it were straight
            **({"bold": bold} if bold else {}),
        })
    return result


def read_page(reader, page):
    """Run OCR on one page and return its lines in reading order."""
    width, height = page.size
    fragments = []
    result = reader(np.array(page), return_word_box=True)
    if result.boxes is None:         # blank page or no text
        return {"width": width, "height": height, "lines": []}
    gray = np.asarray(page.convert("L"), dtype=np.float32)
    word_groups = result.word_results or [()] * len(result.txts)
    for box, text, confidence, group in zip(result.boxes, result.txts, result.scores, word_groups):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = box
        frag = {"text": text.strip(), "x0": float(min(xs)), "y0": float(min(ys)),
                "x1": float(max(xs)), "y1": float(max(ys)), "confidence": float(confidence),
                "slope": float((try_ - tly) / (trx - tlx)) if trx > tlx else 0.0,
                "text_height": float((bly - tly + bry - try_) / 2)}
        center = (frag["y0"] + frag["y1"]) / 2
        if not frag["text"] or frag["confidence"] < config.MIN_CONFIDENCE:
            continue
        if center < height * config.MARGIN_TOP or center > height * (1 - config.MARGIN_BOTTOM):
            continue
        frag["words"] = []
        for word in group:                            # (text, confidence, four corners)
            wx, wy = [p[0] for p in word[2]], [p[1] for p in word[2]]
            thickness = stroke_thickness(gray, min(wx), min(wy), max(wx), max(wy))
            frag["words"].append((word[0], thickness / max(frag["text_height"], 1.0)))
        fragments.append(frag)
    fragments = inside_text_column(fragments)
    mark_bold(fragments)
    lines = []
    for number, (is_column, block) in enumerate(split_into_blocks(fragments)):
        for line in group_into_lines(block):
            lines.append({**line, "block": number, **({"column": True} if is_column else {})})
    return {"width": width, "height": height, "lines": lines}


def main():
    book = config.book_from_args()
    source, work, _ = config.folders(book)
    ocr_folder = work / "ocr"
    ocr_folder.mkdir(exist_ok=True)

    images = sorted(p for p in source.iterdir() if p.suffix.lower() in config.IMAGE_EXTENSIONS)
    if not images:
        sys.exit(f"No images in {source}")
    print(f"{len(images)} images in {source}")

    reader = None
    t_total = time.perf_counter()
    for i, path in enumerate(images, 1):
        target = ocr_folder / f"{path.stem}.json"
        if target.exists() and not FORCE:
            print(f"[{i}/{len(images)}] {path.name}: already done, skipped")
            continue
        if reader is None:
            # Imported here: it is slow, and not needed if everything is already done.
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
            t0 = time.perf_counter()
            reader = RapidOCR(params={
                "Global.log_level": "warning",
                "Rec.lang_type": LangRec[config.OCR_ALPHABET],
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
            })
            print(f"OCR model loaded in {time.perf_counter() - t0:.1f} s")
        t0 = time.perf_counter()
        pages = [read_page(reader, p) for p in load_pages(path)]
        target.write_text(json.dumps({"image": path.name, "pages": pages},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        n_lines = sum(len(p["lines"]) for p in pages)
        print(f"[{i}/{len(images)}] {path.name}: {n_lines} lines in {time.perf_counter() - t0:.1f} s")
    print(f"OCR finished in {time.perf_counter() - t_total:.1f} s")

    # Confidence report: shows which pages are worth checking by hand.
    report = work / "ocr_report.csv"
    to_review = 0
    with report.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["image", "lines", "mean_confidence", "status"])
        for path in images:
            data = json.loads((ocr_folder / f"{path.stem}.json").read_text(encoding="utf-8"))
            lines = [l for p in data["pages"] for l in p["lines"]]
            mean = float(np.mean([l["confidence"] for l in lines])) if lines else 0.0
            status = "ok" if mean >= config.REVIEW_CONFIDENCE else "review"
            to_review += status == "review"
            writer.writerow([path.name, len(lines), f"{mean:.2f}", status])
    print(f"Report: {report} ({to_review} pages flagged for review)")


if __name__ == "__main__":
    main()
