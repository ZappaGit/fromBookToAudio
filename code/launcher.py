"""Windows launcher: a small window to pick a book, adjust its settings and run the pipeline.

    pythonw launcher.py        (or double-click fromBookToAudio.bat in the project root)

It is only a front end for the command line: it writes the book's settings to
input/<book>/book.ini and runs run.py or the step scripts as separate processes, showing
their output. Everything it does can also be done from the console, and the other way round.
Uses tkinter (part of Python), so it needs no extra packages.
"""
import ast
import os
import pathlib
import queue
import shutil
import subprocess
import sys
import threading

import config

CODE_DIR = pathlib.Path(__file__).resolve().parent

# Settings shown in the window: (name, label, kind, choices). Each kind is edited and
# parsed differently; all others in book.ini are kept untouched.
FIELDS = [
    ("VOICE_LANG", "Language", "choice", ["e", "a", "b", "f", "i", "p"]),
    ("VOICE", "Voice", "choice", ["ef_dora", "em_alex", "em_santa", "af_heart", "af_bella",
                                  "am_michael", "bf_emma", "bm_george", "ff_siwis",
                                  "if_sara", "im_nicola", "pf_dora", "pm_alex"]),
    ("SPEED", "Speed", "float", None),
    ("OUTPUT_FORMAT", "Audio format", "choice", ["MP3", "FLAC", "WAV"]),
    ("ROTATE", "Rotate (degrees)", "choice", ["0", "90", "180", "270"]),
    ("CROP", "Crop (left, top, right, bottom)", "floats", None),
    ("MARGIN_TOP", "Ignore top (fraction)", "float", None),
    ("MARGIN_BOTTOM", "Ignore bottom (fraction)", "float", None),
    ("DOUBLE_PAGES", "Two pages per image", "bool", None),
    ("MARKDOWN", "Also write book.md", "bool", None),
    ("PER_IMAGE", "One document per image", "bool", None),
]
LANGUAGES = "e Spanish · a US English · b UK English · f French · i Italian · p Portuguese"


# ---------- book.ini (pure logic, no window) ----------

def read_ini(path):
    """Return {NAME: value} from a book.ini; lines that do not parse are ignored."""
    values = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, equals, value = (part.strip() for part in line.partition("="))
        if equals:
            try:
                values[name.upper()] = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                pass
    return values


def write_ini(path, values, defaults):
    """Update the settings in `values` in book.ini, keeping every other line.

    A setting equal to its default is removed, so book.ini only holds what is special
    about the book. The file is deleted if nothing is left in it.
    """
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
    kept, done = [], set()
    for raw in lines:
        name = raw.partition("=")[0].strip().upper()
        if "=" in raw and not raw.strip().startswith("#") and name in values:
            if name not in done and values[name] != defaults[name]:
                kept.append(f"{name} = {values[name]!r}")
            done.add(name)
        else:
            kept.append(raw)
    kept += [f"{n} = {v!r}" for n, v in values.items() if n not in done and v != defaults[n]]
    if any(line.strip() for line in kept):
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    elif path.is_file():
        path.unlink()


def parse_field(kind, text):
    """Turn the text typed in a field into a setting value; raises ValueError if invalid."""
    text = text.strip()
    if kind == "float":
        return float(text.replace(",", "."))
    if kind == "floats":
        parts = [float(p) for p in text.replace("(", "").replace(")", "").split(",")]
        if len(parts) != 4:
            raise ValueError("four numbers are needed")
        return tuple(parts)
    if kind == "choice" and text.lstrip("-").isdigit():
        return int(text)
    return text


def show_field(kind, value):
    if kind == "floats":
        return ", ".join(f"{v:g}" for v in value)
    return str(value)


def books():
    """Names of the book folders in input/."""
    if not config.INPUT_DIR.is_dir():
        return []
    return sorted(p.name for p in config.INPUT_DIR.iterdir() if p.is_dir())


def images_in(folder):
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in config.IMAGE_EXTENSIONS)


def command(script, book, flags):
    """Command line that runs one of the scripts with the console Python of this venv."""
    python = pathlib.Path(sys.executable)
    if python.stem.lower() == "pythonw":
        python = python.with_name("python" + python.suffix)
    return [str(python), "-u", str(CODE_DIR / script), book, *flags]


def open_path(path):
    if hasattr(os, "startfile"):
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ---------- window ----------

class Launcher:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root = tk.Tk()
        self.root.title("fromBookToAudio")
        self.root.minsize(760, 560)
        self.process = None
        self.lines = queue.Queue()
        self.defaults = {name: getattr(config, name) for name, *_ in FIELDS}

        self.book = tk.StringVar()
        self.force = tk.BooleanVar()
        self.validate = tk.BooleanVar()
        self.vars = {name: tk.BooleanVar() if kind == "bool" else tk.StringVar()
                     for name, _, kind, _ in FIELDS}
        self.build()
        self.refresh_books()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.pump)

    def build(self):
        tk, ttk = self.tk, self.ttk
        pad = {"padx": 6, "pady": 3}

        top = ttk.LabelFrame(self.root, text="Book")
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Book (folder in input/):").pack(side="left", **pad)
        self.book_box = ttk.Combobox(top, textvariable=self.book, state="readonly", width=30)
        self.book_box.pack(side="left", **pad)
        self.book_box.bind("<<ComboboxSelected>>", lambda _: self.load_settings())
        ttk.Button(top, text="Add images from a folder…", command=self.add_folder).pack(side="left", **pad)
        self.count = ttk.Label(top, text="")
        self.count.pack(side="left", **pad)

        settings = ttk.LabelFrame(self.root, text="Settings for this book (saved in input/<book>/book.ini)")
        settings.pack(fill="x", **pad)
        for i, (name, label, kind, choices) in enumerate(FIELDS):
            row, col = divmod(i, 2)
            if kind == "bool":
                widget = ttk.Checkbutton(settings, text=label, variable=self.vars[name])
                widget.grid(row=row, column=col * 2, columnspan=2, sticky="w", **pad)
                continue
            ttk.Label(settings, text=label + ":").grid(row=row, column=col * 2, sticky="e", **pad)
            if kind == "choice":
                widget = ttk.Combobox(settings, textvariable=self.vars[name], values=choices, width=18)
            else:
                widget = ttk.Entry(settings, textvariable=self.vars[name], width=21)
            widget.grid(row=row, column=col * 2 + 1, sticky="w", **pad)
        ttk.Label(settings, text="Languages: " + LANGUAGES, foreground="gray").grid(
            row=len(FIELDS) // 2 + 1, column=0, columnspan=4, sticky="w", **pad)

        run = ttk.LabelFrame(self.root, text="Run")
        run.pack(fill="x", **pad)
        ttk.Checkbutton(run, text="Force (redo OCR and rebuild book.txt)", variable=self.force).grid(
            row=0, column=0, columnspan=3, sticky="w", **pad)
        ttk.Checkbutton(run, text="Validate with Whisper (step 4, slow)", variable=self.validate).grid(
            row=0, column=3, columnspan=3, sticky="w", **pad)
        buttons = [
            ("▶ Run all", self.run_all), ("1 OCR", lambda: self.run_step(1)),
            ("2 Text", lambda: self.run_step(2)), ("3 Audio", lambda: self.run_step(3)),
            ("4 Validate", lambda: self.run_step(4)), ("Apply corrections", self.apply),
        ]
        self.run_buttons = []
        for i, (text, action) in enumerate(buttons):
            button = ttk.Button(run, text=text, command=action)
            button.grid(row=1, column=i, sticky="ew", **pad)
            self.run_buttons.append(button)
        self.stop_button = ttk.Button(run, text="■ Stop", command=self.stop, state="disabled")
        self.stop_button.grid(row=1, column=6, sticky="ew", **pad)
        opens = [
            ("Open book.txt", lambda: self.open_work("book.txt")),
            ("Open corrections.txt", lambda: self.open_work("corrections.txt")),
            ("Open input folder", lambda: self.open_folder(config.INPUT_DIR)),
            ("Open work folder", lambda: self.open_folder(config.WORK_DIR)),
            ("Open audiobook folder", lambda: self.open_folder(config.OUTPUT_DIR)),
        ]
        for i, (text, action) in enumerate(opens):
            ttk.Button(run, text=text, command=action).grid(row=2, column=i, sticky="ew", **pad)

        log = ttk.Frame(self.root)
        log.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(log, height=14, wrap="word", font=("Consolas", 9), state="disabled")
        scroll = ttk.Scrollbar(log, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_configure("error", foreground="red")
        self.log.tag_configure("info", foreground="blue")

    # --- books and settings ---

    def refresh_books(self, select=None):
        names = books()
        self.book_box["values"] = names
        if select or (names and self.book.get() not in names):
            self.book.set(select or names[0])
        self.load_settings()

    def load_settings(self):
        book = self.book.get()
        values = dict(self.defaults)
        if book:
            values.update({k: v for k, v in read_ini(config.INPUT_DIR / book / "book.ini").items()
                           if k in values})
            self.count.configure(text=f"{len(images_in(config.INPUT_DIR / book))} images")
        for name, _, kind, _ in FIELDS:
            self.vars[name].set(values[name] if kind == "bool" else show_field(kind, values[name]))

    def save_settings(self):
        """Write the window's settings to book.ini; False (with a message) if a value is wrong."""
        from tkinter import messagebox
        values = {}
        for name, label, kind, _ in FIELDS:
            try:
                values[name] = self.vars[name].get() if kind == "bool" else parse_field(kind, self.vars[name].get())
            except ValueError as error:
                messagebox.showerror("Invalid setting", f"{label}: {error}")
                return False
        write_ini(config.INPUT_DIR / self.book.get() / "book.ini", values, self.defaults)
        return True

    def add_folder(self):
        """Copy the images of any folder into input/<name>, the folder the pipeline reads."""
        from tkinter import filedialog, messagebox, simpledialog
        chosen = filedialog.askdirectory(title="Folder with the photos or scans of the book")
        if not chosen:
            return
        folder = pathlib.Path(chosen).resolve()
        if folder.parent == config.INPUT_DIR.resolve():
            self.refresh_books(folder.name)
            return
        images = images_in(folder)
        if not images:
            messagebox.showerror("No images", f"No images ({', '.join(sorted(config.IMAGE_EXTENSIONS))}) in {folder}")
            return
        name = simpledialog.askstring("Book name", "Name for this book (folder in input/):",
                                      initialvalue=folder.name, parent=self.root)
        if not name or not name.strip():
            return
        target = config.INPUT_DIR / name.strip()
        if target.exists() and any(target.iterdir()):
            messagebox.showerror("Book exists", f"{target} already exists and is not empty. Choose another name.")
            return
        target.mkdir(parents=True, exist_ok=True)
        for image in images:
            shutil.copy2(image, target / image.name)
        self.write(f"Copied {len(images)} images to {target}\n", "info")
        self.refresh_books(target.name)

    # --- running ---

    def run_all(self):
        flags = ["--force"] * self.force.get() + ["--validate"] * self.validate.get()
        self.start("run.py", flags)

    def run_step(self, number):
        force = ["--force"] * self.force.get()
        script, flags = {
            1: ("step1_ocr.py", force),
            2: ("step2_text.py", force),
            3: ("step3_audio.py", []),
            4: ("step4_validate.py", force),
        }[number]
        self.start(script, flags)

    def apply(self):
        from tkinter import messagebox
        if messagebox.askyesno("Apply corrections",
                               "Write the lines of corrections.txt into book.txt?\n\n"
                               "Review corrections.txt first: Whisper's suggestions are not always right. "
                               "The current text is kept as book.before_corrections.txt."):
            self.start("step4_validate.py", ["--apply"])

    def start(self, script, flags):
        from tkinter import messagebox
        book = self.book.get()
        if not book:
            messagebox.showinfo("No book", "Add a folder of images first.")
            return
        if self.process or not self.save_settings():
            return
        flags = flags + ["--markdown"] * self.vars["MARKDOWN"].get() + ["--per-image"] * self.vars["PER_IMAGE"].get()
        cmd = command(script, book, flags)
        self.write("\n> " + " ".join([pathlib.Path(cmd[0]).name, *cmd[2:]]) + "\n", "info")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.process = subprocess.Popen(
            cmd, cwd=config.ROOT_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self.read_output, args=(self.process,), daemon=True).start()
        self.set_running(True)

    def read_output(self, process):
        for line in process.stdout:
            self.lines.put((line, None))
        self.lines.put((None, process.wait()))

    def pump(self):
        """Move the output of the running process into the log (tkinter is not thread-safe)."""
        try:
            while True:
                line, code = self.lines.get_nowait()
                if line is not None:
                    error = "FAILED" in line or "Error" in line or "Traceback" in line
                    self.write(line, "error" if error else None)
                    continue
                self.process = None
                self.set_running(False)
                if code == 0:
                    self.write("Finished.\n", "info")
                else:
                    self.write(f"Stopped with exit code {code}.\n", "error")
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def stop(self):
        if self.process:
            self.write("Stopping… (finished work is kept)\n", "info")
            self.process.terminate()

    def set_running(self, running):
        for button in self.run_buttons:
            button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def write(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    # --- opening files ---

    def open_work(self, name):
        from tkinter import messagebox
        path = config.WORK_DIR / self.book.get() / name
        if path.is_file():
            open_path(path)
        else:
            messagebox.showinfo("Not found", f"{path} does not exist yet.")

    def open_folder(self, base):
        book = self.book.get()
        folder = base / book if book and (base / book).is_dir() else base
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def close(self):
        if self.process:
            from tkinter import messagebox
            if not messagebox.askyesno("Running", "A step is still running. Stop it and close?"):
                return
            self.process.terminate()
        self.root.destroy()

    def mainloop(self):
        self.root.mainloop()


def main():
    Launcher().mainloop()


if __name__ == "__main__":
    main()
