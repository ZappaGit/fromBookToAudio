"""Step 3 · Audio: turns work/<book>/book.txt into an audiobook with Kokoro-82M.

Run from the repository folder with the virtual environment:
    .\\.venv\\Scripts\\python.exe step3_audio.py <book>

Writes one file per chapter to output/<book>/ (chapters are the lines starting with "# Title").
The audio of each paragraph is saved in work/<book>/audio/, so if the process is interrupted
or a paragraph is corrected, only what is missing or changed gets synthesized again.
Spanish needs espeak-ng installed on the system (see README.md).
"""
import hashlib
import re
import time
import unicodedata

import numpy as np
import soundfile as sf

import config


def read_chapters(path):
    """Return [(title or None, [paragraphs])] from book.txt."""
    chapters = [(None, [])]
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        block = " ".join(block.split())
        if not block:
            continue
        if block.startswith("#"):
            chapters.append((block.lstrip("# ").strip(), []))
        else:
            chapters[-1][1].append(block)
    return [(t, p) for t, p in chapters if t or p]


def split_text(text, maximum):
    """Split a paragraph into chunks of at most `maximum` characters, by sentence when possible."""
    chunks, current = [], ""
    for sentence in re.split(r"(?<=[.!?…;:])\s+", text):
        parts = [sentence]
        if len(sentence) > maximum:                   # very long sentence: split at commas
            parts = re.split(r"(?<=,)\s+", sentence)
        for part in parts:
            while len(part) > maximum:                # no commas: split at spaces
                cut = part.rfind(" ", 0, maximum)
                cut = cut if cut > 0 else maximum
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(part[:cut])
                part = part[cut:].strip()
            if current and len(current) + 1 + len(part) > maximum:
                chunks.append(current)
                current = part
            else:
                current = f"{current} {part}".strip()
    if current:
        chunks.append(current)
    return chunks


def file_name(number, title):
    base = unicodedata.normalize("NFKD", title or "intro").encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:50] or "chapter"
    return f"{number:02d}-{base}.{config.OUTPUT_FORMAT.lower()}"


class Narrator:
    """Synthesizes paragraphs with Kokoro and saves each one to disk so it is not repeated."""

    def __init__(self, folder):
        self.folder = folder
        self.pipeline = None
        self.synthesis_seconds = 0.0
        self.new_audio_seconds = 0.0

    def audio(self, text):
        key = f"{config.VOICE_LANG}|{config.VOICE}|{config.SPEED}|{text}"
        path = self.folder / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()}.flac"
        if path.exists():
            return sf.read(path, dtype="float32")[0]

        if self.pipeline is None:
            from kokoro import KPipeline  # imported here: it is slow, and not needed if everything is done
            t0 = time.perf_counter()
            self.pipeline = KPipeline(lang_code=config.VOICE_LANG, repo_id="hexgrad/Kokoro-82M")
            print(f"Voice model loaded in {time.perf_counter() - t0:.1f} s")

        t0 = time.perf_counter()
        parts = []
        for chunk in split_text(text, config.MAX_CHARS):
            for result in self.pipeline(chunk, voice=config.VOICE, speed=config.SPEED):
                if result.audio is not None:
                    parts.append(np.asarray(result.audio.detach().cpu(), dtype=np.float32))
        audio = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
        self.synthesis_seconds += time.perf_counter() - t0
        self.new_audio_seconds += len(audio) / config.SAMPLE_RATE

        temporary = path.with_suffix(".tmp")          # renamed at the end: never left half-written
        sf.write(temporary, audio, config.SAMPLE_RATE, format="FLAC", subtype="PCM_16")
        temporary.replace(path)
        return audio


def silence(seconds):
    return np.zeros(int(seconds * config.SAMPLE_RATE), dtype=np.float32)


def main():
    book = config.book_from_args()
    _, work, output = config.folders(book)
    text_file = work / "book.txt"
    if not text_file.exists():
        raise SystemExit(f"Missing {text_file}. Run step2_text.py {book} first.")
    audio_folder = work / "audio"
    audio_folder.mkdir(exist_ok=True)

    chapters = read_chapters(text_file)
    total = sum(len(p) + bool(t) for t, p in chapters)
    if not total:
        raise SystemExit(f"{text_file} has no text to read.")
    print(f"{len(chapters)} chapters, {total} text blocks. Voice: {config.VOICE}, speed {config.SPEED}")

    narrator = Narrator(audio_folder)
    done = 0
    total_duration = 0.0
    for number, (title, paragraphs) in enumerate(chapters, 1):
        target = output / file_name(number, title)
        samples = 0
        with sf.SoundFile(target, "w", samplerate=config.SAMPLE_RATE, channels=1,
                          format=config.OUTPUT_FORMAT) as archive:
            blocks = ([(title, config.PAUSE_TITLE)] if title else []) + \
                     [(p, config.PAUSE_PARAGRAPH) for p in paragraphs]
            for block, pause in blocks:
                for chunk in (narrator.audio(block), silence(pause)):
                    archive.write(chunk)
                    samples += len(chunk)
                done += 1
                print(f"  [{done}/{total}] {block[:60]}")
        duration = samples / config.SAMPLE_RATE
        total_duration += duration
        print(f"{target.name}: {duration / 60:.1f} min")

    print(f"Audiobook: {total_duration / 60:.1f} min in {output}")
    if narrator.new_audio_seconds:
        rtf = narrator.synthesis_seconds / narrator.new_audio_seconds
        print(f"New synthesis: {narrator.synthesis_seconds:.1f} s for "
              f"{narrator.new_audio_seconds:.1f} s of audio (RTF {rtf:.2f})")
    else:
        print("All audio was already generated; only the files were assembled.")


if __name__ == "__main__":
    main()
