@echo off
rem Opens the fromBookToAudio launcher window. Double-click it, or make a shortcut to it.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment not found. Install it first, see README.md "Quick start".
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "code\launcher.py"
