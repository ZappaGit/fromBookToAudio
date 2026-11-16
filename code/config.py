"""Settings for fromBookToAudio. All three steps read them from here.

Folder layout (one subfolder per book):
    input/<book>/    scanned or photographed pages, sorted by file name
    work/<book>/     intermediate results (OCR per page, book.txt, audio per paragraph)
    output/<book>/   final audiobook, one MP3 per chapter

Any setting can be overridden for one book in input/<book>/book.ini, one per line,
written as here, e.g.:
    ROTATE = 270
    DOUBLE_PAGES = True
"""
import ast
import pathlib
import sys

# So that accented characters print correctly in the Windows console.
sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent   # project root, one level above code/
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
MARKDOWN = False              # True: also write book.md, which keeps headings, lists and bold words
PER_IMAGE = False             # True: every image is a document of its own: one audio file per image,
                              # with its text (.txt, and .md if book.md exists) beside it in output/<book>/

# ---------- Step 3: audio ----------
VOICE_LANG = "e"              # Kokoro language code: 'e' Spanish (needs espeak-ng), 'a' US English
VOICE = "ef_dora"             # ef_dora, em_alex, em_santa; mixes allowed: "ef_dora,em_alex"
SPEED = 1.0                   # 0.8 slower, 1.2 faster
SAMPLE_RATE = 24000           # Hz; Kokoro's output sample rate
MAX_CHARS = 300               # max size of each chunk sent to the model (avoids cut-off audio)
PAUSE_PARAGRAPH = 0.6         # seconds of silence between paragraphs
PAUSE_TITLE = 1.2             # seconds of silence after a chapter title
OUTPUT_FORMAT = "MP3"         # "MP3", "FLAC" or "WAV"

# ---------- Step 4: validation (optional) ----------
WHISPER_MODEL = "openai/whisper-large-v3-turbo"   # speech-to-text model that listens to the audio
WHISPER_LANGUAGE = None       # None: taken from VOICE_LANG; or a Whisper name such as "spanish"
MIN_SIMILARITY = 0.90         # blocks whose heard text matches the written text less than this
                              # (0 to 1, by words) are flagged "review"


def folders(book: str):
    """Return (input, work, output) folders for the book; creates the last two."""
    source = INPUT_DIR / book
    work = WORK_DIR / book
    output = OUTPUT_DIR / book
    if not source.is_dir():
        sys.exit(f"Image folder not found: {source}")
    apply_book_settings(source / "book.ini")
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    return source, work, output


def apply_book_settings(path):
    """Override the settings in this file with the ones in the book's book.ini, if any."""
    if not path.is_file():
        return
    names = {n for n in globals() if n.isupper() and not n.endswith("_DIR")}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, equals, value = (part.strip() for part in line.partition("="))
        if not equals or name.upper() not in names:
            sys.exit(f"{path}, line {number}: unknown setting {name!r}")
        try:
            globals()[name.upper()] = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            sys.exit(f"{path}, line {number}: invalid value {value!r} (text needs quotes)")
    print(f"Book settings: {path}")


def book_from_args() -> str:
    """Book name: the first argument that does not start with '--'."""
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(names) != 1:
        sys.exit(f"Usage: python {pathlib.Path(sys.argv[0]).name} <book> [--force]")
    return names[0]
