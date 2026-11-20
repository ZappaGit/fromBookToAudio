# Contributing

Thanks for your interest in fromBookToAudio. Bug reports, suggestions and pull requests are welcome.

## Reporting bugs and asking for features

Open an [issue](../../issues/new/choose) and use the template. For bugs, include the command you ran, the step that failed, the full console output, and your Python and Windows versions. **Do not attach book pages or audio**; a small synthetic image that reproduces the problem is enough.

Security problems must be reported privately, see [SECURITY.md](SECURITY.md).

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe code\test_generate_pages.py
```

The end-to-end check is described in the [README](README.md#test-results). Heavy model imports are kept inside functions so that unit-testable logic can run without loading models; please keep it that way.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Keep the change focused on one thing.
3. Make sure the pipeline still runs on the synthetic test (`code\run.py test --force`) and that existing `book.txt` files are still never overwritten without `--force`.
4. If behaviour or layout changes, update the README.
5. Fill in the pull request template.

## Guidelines

- Code, comments and documentation are in English.
- Do not commit book content, images, audio, model files or secrets. `input/`, `work/` and `output/` are git-ignored; keep it that way.
- Do not add dependencies without explaining why and checking that their license is compatible with GPLv3.
- Do not add an LLM-based OCR correction step (see the README, "Technical decisions").

## License

By contributing, you agree that your contributions are licensed under the [GNU GPL v3.0](LICENSE).
