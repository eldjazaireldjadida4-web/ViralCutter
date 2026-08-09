@echo off
setlocal
title ViralCutter

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [!] Virtual environment not found.
    echo     Run install_dependencies.bat once first, then run.bat again.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

:: FFmpeg installed next to the app by install_dependencies.bat / packaging\install_ffmpeg_windows.bat
if exist "bin\ffmpeg.exe" set "PATH=%CD%\bin;%PATH%"

:: Pre-flight: check EVERYTHING and auto-install anything missing, so the
:: app starts with everything in place. --auto-fix installs missing core
:: dependencies automatically; --off skips the check.
echo.
echo [preflight] Checking environment and installing anything missing...
python -m scripts.preflight --auto-fix
if errorlevel 1 (
    echo.
    echo [!] Pre-flight found critical problems. Fix the items above, then run again.
    echo     (or set VIRALCUTTER_SKIP_PREFLIGHT=1 to force-start anyway)
    pause
    exit /b 1
)

python main_improved.py %*
pause
