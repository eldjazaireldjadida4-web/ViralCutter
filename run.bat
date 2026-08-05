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

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [!] Warning: ffmpeg not found. Transcription/editing will fail.
    echo     Run install_dependencies.bat and choose the ffmpeg download option.
)

python main_improved.py %*
pause
