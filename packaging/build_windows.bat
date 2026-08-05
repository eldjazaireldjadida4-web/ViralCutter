@echo off
REM Build the ViralCutter single-file executable on Windows (Roadmap 1.1).
cd /d "%~dp0\.."
echo [1/3] Installing build deps...
pip install --quiet pyinstaller
echo [2/3] Building (onefile, console)...
pyinstaller packaging\viralcutter.spec --noconfirm --clean
echo [3/3] Done -^> dist\ViralCutter.exe
dir dist
