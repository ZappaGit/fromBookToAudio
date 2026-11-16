"""Step 4 · Validation (optional): listens to the audiobook and compares it with book.txt.

Run from the repository folder with the virtual environment:
    .\\.venv\\Scripts\\python.exe code\\step4_validate.py <book> [--force]
    .\\.venv\\Scripts\\python.exe code\\step4_validate.py <book> --apply

Whisper transcribes the audio of every text block that step 3 saved in work/<book>/audio/ and
the result is compared, word by word, with the text that was meant to be read. Blocks that
differ too much (cut-off audio, skipped or garbled words) are flagged "review" in
work/<book>/validation_report.csv.

What Whisper heard is saved per block in work/<book>/heard/, so an interrupted run continues
where it stopped and a corrected paragraph is the only one listened to again. Use --force to
listen to everything again. On a CPU, listening takes about twice the length of the audio.

The differences are also written to work/<book>/corrections.txt as "written => heard" lines.
They are suggestions, not facts: Whisper mishears too. Delete the wrong lines, fix the right-hand
side where needed and run this step with --apply to write them into book.txt (a copy of the old
text is kept). Then run step 3 again: only the changed paragraphs get new audio.
"""
import csv
import difflib
import re
import sys
import time
import unicodedata

import soundfile as sf

import config
import step3_audio

FORCE = "--force" in sys.argv
APPLY = "--apply" in sys.argv
CORRECTION = re.compile(r"^\[(\d+)\] (.+?) => (.*)$")
CORRECTIONS_HEADER = """\
# Suggested corrections for book.txt, taken from what Whisper heard in the audio.
# Each line is:  [block] text in book.txt => text Whisper heard
# Whisper also mishears, so review them: delete the lines that are wrong, edit the right-hand
# side where needed, then run  step4_validate.py <book> --apply  and step 3 again.
# This file is rebuilt every time the validation runs.
"""
WHISPER_RATE = 16000              # Hz; the sample rate Whisper expects
LANGUAGES = {                     # Kokoro language code -> Whisper language name
    "a": "english", "b": "english", "e": "spanish", "f": "french", "h": "hindi",
    "i": "italian", "j": "japanese", "p": "portuguese", "z": "chinese",
}


def words(text):
    """Lower-case words without accents or punctuation, so only real differences count."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"\w+", text)


def compare(written, heard):
    """Return (similarity from 0 to 1, differences as 'written -> heard' separated by ' | ')."""
    a, b = words(written), words(heard)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    differences = [
        f"{' '.join(a[i1:i2]) or '∅'} -> {' '.join(b[j1:j2]) or '∅'}"
        for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"
    ]
    similarity = matcher.ratio() if a or b else 1.0
    return similarity, " | ".join(differences)


def tokens(text):
    """Return [(normalized word, start, end)] for every word, with its position in the text."""
    found = []
    for match in re.finditer(r"\w+", text):
        word = "".join(words(match.group()))
        if word:
            found.append((word, match.start(), match.end()))
    return found


def suggestions(written, heard):
    """Return [(text as written, text as heard)] for every difference, in their original spelling."""
    a, b = tokens(written), tokens(heard)
    matcher = difflib.SequenceMatcher(None, [t[0] for t in a], [t[0] for t in b], autojunk=False)
    pairs = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i1 == i2 or j1 == j2:          # a word on one side only: add a neighbour to locate it
            if i1 and j1:
                i1, j1 = i1 - 1, j1 - 1
            elif i2 < len(a) and j2 < len(b):
                i2, j2 = i2 + 1, j2 + 1
            else:
                continue
        old = written[a[i1][1]:a[i2 - 1][2]]
        new = heard[b[j1][1]:b[j2 - 1][2]]
        if re.search(r"\d", new) and not re.search(r"\d", old):
            continue                      # Whisper writes numbers as digits; the book is right
        if old[0].isupper() and new[0].islower():
            new = new[0].upper() + new[1:]        # keep the capital letter the book had
        pairs.append((old, new))
    return pairs


def loose(text, whole_words=False):
    """Pattern that finds the text whatever its line breaks and spacing are."""
    pattern = r"\s+".join(re.escape(word) for word in text.split())
    return rf"(?<!\w){pattern}(?!\w)" if whole_words else pattern


def apply_corrections(text, blocks, corrections):
    """Replace, inside each block of the book text, what was written by its correction.

    blocks is [(chapter, block text)] and corrections is [(block number, old, new)].
    Returns (new text, [corrections that could not be found]).
    """
    spans, cursor = {}, 0
    for number, (_, block) in enumerate(blocks, 1):
        match = re.compile(loose(block)).search(text, cursor)
        if match:
            spans[number] = match.span()
            cursor = match.end()
    by_block, missing = {}, []
    for number, old, new in corrections:
        by_block.setdefault(number, []).append((old, new))
    for number in sorted(by_block, reverse=True):     # from the end, so earlier positions stay valid
        if number not in spans:
            missing += [(number, old, new) for old, new in by_block[number]]
            continue
        start, end = spans[number]
        piece, cursor = text[start:end], 0
        for old, new in by_block[number]:
            match = re.compile(loose(old, whole_words=True)).search(piece, cursor)
            if not match:
                missing.append((number, old, new))
                continue
            piece = piece[:match.start()] + new + piece[match.end():]
            cursor = match.start() + len(new)
        text = text[:start] + piece + text[end:]
    return text, missing


def apply_file(work, text_file):
    """Write the reviewed corrections.txt into book.txt, keeping a copy of the previous text."""
    corrections_file = work / "corrections.txt"
    if not corrections_file.exists():
        raise SystemExit(f"Missing {corrections_file}. Run the validation first (without --apply).")
    corrections = []
    for line in corrections_file.read_text(encoding="utf-8-sig").splitlines():
        match = CORRECTION.match(line.strip())
        if match:
            corrections.append((int(match[1]), match[2], match[3].strip()))
    original = text_file.read_text(encoding="utf-8")
    text, missing = apply_corrections(original, blocks_of(step3_audio.read_chapters(text_file)), corrections)
    for number, old, new in missing:
        print(f"  not found, skipped: [{number}] {old} => {new}")
    if text != original:
        backup = work / "book.before_corrections.txt"
        backup.write_text(original, encoding="utf-8")
        temporary = text_file.with_suffix(".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(text_file)
        print(f"Previous text kept in {backup}")
    corrections_file.replace(work / "corrections.applied.txt")
    print(f"{len(corrections) - len(missing)} of {len(corrections)} corrections written to {text_file}. "
          f"Run step3_audio.py and then this step again: only the changed paragraphs are redone.")


def blocks_of(chapters):
    """Flatten the chapters into [(chapter number, text block)], titles included, as step 3 reads them."""
    blocks = []
    for number, (title, paragraphs) in enumerate(chapters, 1):
        blocks += [(number, text) for text in ([title] if title else []) + paragraphs]
    return blocks


class Listener:
    """Transcribes audio files with Whisper and saves each result to disk so it is not repeated."""

    def __init__(self, folder):
        self.folder = folder
        self.pipeline = None
        self.listening_seconds = 0.0
        self.audio_seconds = 0.0

    def heard(self, audio_path):
        path = self.folder / f"{audio_path.stem}.txt"
        if path.exists() and not FORCE:
            return path.read_text(encoding="utf-8")

        if self.pipeline is None:
            import torch                       # imported here: they are slow, and not needed if everything is done
            from transformers import logging, pipeline
            logging.set_verbosity_error()      # no progress bars or deprecation notices in the output
            logging.disable_progress_bar()
            t0 = time.perf_counter()
            # float32 on purpose: the weights are stored as float16, which is very slow on a CPU.
            self.pipeline = pipeline("automatic-speech-recognition", model=config.WHISPER_MODEL,
                                     dtype=torch.float32, device="cpu")
            print(f"Listening model loaded in {time.perf_counter() - t0:.1f} s")

        from scipy.signal import resample_poly
        audio, rate = sf.read(audio_path, dtype="float32")
        if rate != WHISPER_RATE:
            audio = resample_poly(audio, WHISPER_RATE, rate).astype("float32")
        language = config.WHISPER_LANGUAGE or LANGUAGES.get(config.VOICE_LANG)
        options = {"task": "transcribe", "condition_on_prev_tokens": False}
        if language:
            options["language"] = language

        t0 = time.perf_counter()
        # return_timestamps makes Whisper handle audio longer than its 30-second window.
        result = self.pipeline({"raw": audio, "sampling_rate": WHISPER_RATE},
                               return_timestamps=True, generate_kwargs=options)
        self.listening_seconds += time.perf_counter() - t0
        self.audio_seconds += len(audio) / WHISPER_RATE
        text = " ".join(result["text"].split())

        temporary = path.with_suffix(".tmp")          # renamed at the end: never left half-written
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
        return text


def main():
    book = config.book_from_args()
    _, work, _ = config.folders(book)
    text_file = work / "book.txt"
    audio_folder = work / "audio"
    if not text_file.exists():
        raise SystemExit(f"Missing {text_file}. Run step2_text.py {book} first.")
    if APPLY:
        return apply_file(work, text_file)
    blocks = blocks_of(step3_audio.read_chapters(text_file))
    missing = [text for _, text in blocks if not step3_audio.cache_path(audio_folder, text).exists()]
    if not blocks or missing:
        raise SystemExit(f"{len(missing)} of {len(blocks)} text blocks have no audio in {audio_folder}. "
                         f"Run step3_audio.py {book} first.")
    heard_folder = work / "heard"
    heard_folder.mkdir(exist_ok=True)
    print(f"{len(blocks)} text blocks to check with {config.WHISPER_MODEL}")

    listener = Listener(heard_folder)
    rows, to_review, suggested = [], 0, []
    for index, (chapter, text) in enumerate(blocks, 1):
        heard = listener.heard(step3_audio.cache_path(audio_folder, text))
        similarity, differences = compare(text, heard)
        status = "ok" if similarity >= config.MIN_SIMILARITY else "review"
        to_review += status == "review"
        rows.append([index, chapter, f"{similarity:.3f}", status, differences, text, heard])
        suggested += [f"[{index}] {old} => {new}" for old, new in suggestions(text, heard)]
        print(f"  [{index}/{len(blocks)}] {similarity:.2f} {status:6} {text[:50]}")

    report = work / "validation_report.csv"
    with report.open("w", newline="", encoding="utf-8-sig") as archive:
        writer = csv.writer(archive, delimiter=";")
        writer.writerow(["block", "chapter", "similarity", "status", "differences", "written", "heard"])
        writer.writerows(rows)

    corrections_file = work / "corrections.txt"
    corrections_file.write_text(CORRECTIONS_HEADER + "\n".join(suggested) + "\n", encoding="utf-8")
    print(f"{len(suggested)} suggested corrections to review in {corrections_file}")

    mean = sum(float(r[2]) for r in rows) / len(rows)
    print(f"Mean similarity {mean:.3f}; {to_review} of {len(rows)} blocks to review. Report: {report}")
    if listener.audio_seconds:
        rtf = listener.listening_seconds / listener.audio_seconds
        print(f"Listened to {listener.audio_seconds:.1f} s of audio in "
              f"{listener.listening_seconds:.1f} s (RTF {rtf:.2f})")
    else:
        print("Everything had already been listened to; only the report was rebuilt.")


if __name__ == "__main__":
    main()
