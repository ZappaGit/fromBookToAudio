"""Step 1 · OCR: reads the images in input/<book>/ and saves the text of each page.

Run from the repository folder with the virtual environment:
    .\\.venv\\Scripts\\python.exe step1_ocr.py <book> [--force]

For each image it writes work/<book>/ocr/<image>.json with the detected lines
(text, position and confidence). Pages already processed are skipped; --force redoes them.
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
        halves = [image.crop((0, 0, width // 2, height)), image.crop((width // 2, 0, width, height))]
    else:
        halves = [image]
    pages = []
    for page in halves:
        if max(page.size) > config.MAX_SIDE:
            page.thumbnail((config.MAX_SIDE, config.MAX_SIDE), Image.LANCZOS)
        pages.append(page)
    return pages


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
        result.append({
            "text": " ".join(f["text"] for f in frags).strip(),
            "x0": min(f["x0"] for f in frags),
            "y0": min(f["y0"] for f in frags),
            "x1": max(f["x1"] for f in frags),
            "y1": max(f["y1"] for f in frags),
            "confidence": round(float(np.mean([f["confidence"] for f in frags])), 3),
        })
    return result


def read_page(reader, page):
    """Run OCR on one page and return its lines in reading order."""
    width, height = page.size
    fragments = []
    result = reader(np.array(page))
    if result.boxes is None:         # blank page or no text
        return {"width": width, "height": height, "lines": []}
    for box, text, confidence in zip(result.boxes, result.txts, result.scores):
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
        fragments.append(frag)
    return {"width": width, "height": height, "lines": group_into_lines(fragments)}


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
