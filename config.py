"""Settings for fromBookToAudio. All three steps read them from here.

Folder layout (one subfolder per book):
    input/<book>/    scanned or photographed pages, sorted by file name
    work/<book>/     intermediate results (OCR per page, book.txt, audio per paragraph)
    output/<book>/   final audiobook, one MP3 per chapter
"""
import pathlib
import sys

# So that accented characters print correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = pathlib.Path(__file__).parent
INPUT_DIR = ROOT_DIR / "input"
WORK_DIR = ROOT_DIR / "work"
OUTPUT_DIR = ROOT_DIR / "output"

# ---------- Step 1: OCR ----------
OCR_ALPHABET = "LATIN"        # RapidOCR model: LATIN covers Spanish, English, French, etc.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
MAX_SIDE = 2400               # px; larger photos are downscaled (faster, same text)
ROTATE = 0                    # degrees clockwise (0, 90, 180, 270) for images that come out sideways;
                              # applied after the automatic EXIF correction
CROP = (0.0, 0.0, 0.0, 0.0)   # fraction to cut off each edge (left, top, right, bottom) after rotating,
                              # e.g. (0.05, 0.0, 0.05, 0.10) to remove fingers, desk or scanner borders
DOUBLE_PAGES = False         # True if each image holds two pages (open book)
MARGIN_TOP = 0.0              # fraction of the height to ignore at the top (headers), e.g. 0.07
MARGIN_BOTTOM = 0.0           # fraction of the height to ignore at the bottom (footers)
MIN_CONFIDENCE = 0.30         # text fragments below this confidence are dropped (stains, noise)
REVIEW_CONFIDENCE = 0.90      # pages whose mean confidence is below this are flagged "review"

# ---------- Step 2: text ----------
# A short line starting with one of these is treated as a chapter heading.
# Spanish and English headings are both included.
CHAPTER_PATTERN = (
    r"^(cap[ií]tulo|parte|pr[oó]logo|ep[ií]logo|introducci[oó]n|prefacio"
    r"|chapter|part|prologue|epilogue|introduction|preface)\b"
)
MAX_TITLE_LENGTH = 60

# ---------- Step 3: audio ----------
VOICE_LANG = "e"              # Kokoro language code: 'e' Spanish (needs espeak-ng), 'a' US English
VOICE = "ef_dora"             # ef_dora, em_alex, em_santa; mixes allowed: "ef_dora,em_alex"
SPEED = 1.0                   # 0.8 slower, 1.2 faster
SAMPLE_RATE = 24000           # Hz; Kokoro's output sample rate
MAX_CHARS = 300               # max size of each chunk sent to the model (avoids cut-off audio)
PAUSE_PARAGRAPH = 0.6         # seconds of silence between paragraphs
PAUSE_TITLE = 1.2             # seconds of silence after a chapter title
OUTPUT_FORMAT = "MP3"         # "MP3", "FLAC" or "WAV"


def folders(book: str):
    """Return (input, work, output) folders for the book; creates the last two."""
    source = INPUT_DIR / book
    work = WORK_DIR / book
    output = OUTPUT_DIR / book
    if not source.is_dir():
        sys.exit(f"Image folder not found: {source}")
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    return source, work, output


def book_from_args() -> str:
    """Book name: the first argument that does not start with '--'."""
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(names) != 1:
        sys.exit(f"Usage: python {pathlib.Path(sys.argv[0]).name} <book> [--force]")
    return names[0]
