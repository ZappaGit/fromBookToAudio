"""Run the whole pipeline (OCR -> text -> audio) for one book with a single command.

    python run.py <book> [--force]

Each step reports clearly if it fails and the pipeline stops there; the exit code is the
number of the failed step (1, 2 or 3). Steps are idempotent, so re-running after fixing the
problem continues where it stopped. An existing book.txt is kept (it may hold your
corrections) unless --force is given, which also redoes the OCR of every page.
"""
import sys
import time
import traceback

import config

FORCE = "--force" in sys.argv

HINTS = {
    1: "Check that input/<book>/ holds images and that rapidocr is installed (pip install -r requirements.txt).",
    2: "Check that step 1 produced work/<book>/ocr/*.json for every image.",
    3: "Check book.txt is not empty, that kokoro is installed and, for the Spanish voice, that espeak-ng is installed.",
}


def run_step(number, name, module_name):
    print(f"\n=== Step {number}/3: {name} ===", flush=True)
    t0 = time.perf_counter()
    try:
        module = __import__(module_name)
        module.main()
    except ImportError as error:
        fail(number, name, f"missing dependency: {error}")
    except SystemExit as error:
        if error.code not in (None, 0):
            fail(number, name, str(error.code))
    except KeyboardInterrupt:
        fail(number, name, "interrupted by the user")
    except Exception as error:
        traceback.print_exc()
        fail(number, name, f"{type(error).__name__}: {error}")
    print(f"--- Step {number} ({name}) OK in {time.perf_counter() - t0:.1f} s", flush=True)


def fail(number, name, reason):
    print(f"\n*** Step {number}/3 ({name}) FAILED: {reason}", file=sys.stderr)
    print(f"    Hint: {HINTS[number]}", file=sys.stderr)
    print("    Fix the problem and run the same command again; finished work is kept.", file=sys.stderr)
    sys.exit(number)


def main():
    book = config.book_from_args()
    work, output = config.WORK_DIR / book, config.OUTPUT_DIR / book
    t0 = time.perf_counter()

    run_step(1, "OCR", "step1_ocr")
    if (work / "book.txt").exists() and not FORCE:
        print(f"\n=== Step 2/3: text === skipped, keeping existing {work / 'book.txt'} (use --force to rebuild)")
    else:
        run_step(2, "text", "step2_text")
    run_step(3, "audio", "step3_audio")

    print(f"\nDone in {time.perf_counter() - t0:.1f} s. Audiobook in {output}")


if __name__ == "__main__":
    main()
