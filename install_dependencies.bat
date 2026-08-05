@echo off
setlocal enabledelayedexpansion
echo ==========================================
echo ViralCutter - Windows Setup (v6.2)
echo ==========================================
echo.
echo [1/6] Installing uv (fast Python package manager)...
where uv >nul 2>nul
if %errorlevel%==0 (
    echo      uv already installed.
) else (
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)

echo.
echo [2/6] Creating virtual environment (.venv)...
if exist ".venv\Scripts\activate.bat" (
    echo      .venv already exists - reusing it.
) else (
    uv venv
)

echo.
echo [3/6] GPU selection (Whisper transcription speed)...
echo      [1] NVIDIA (CUDA - fastest)
echo      [2] AMD / Intel / no GPU (CPU - works but slower)
set /p gpu_choice="     Choose (1/2): "

if "%gpu_choice%"=="1" (
    echo      Installing PyTorch + torchaudio (CUDA 12.4)...
    uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
    echo      Installing onnxruntime-gpu...
    uv pip install onnxruntime-gpu==1.20.1
) else (
    echo      Installing PyTorch + torchaudio (CPU)...
    uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
    echo      Installing onnxruntime (CPU)...
    uv pip install onnxruntime==1.20.1
)

echo.
echo [4/6] Installing core dependencies (requirements.txt)...
uv pip install -r requirements.txt

echo.
echo [5/6] Installing transcription stack (whisperx - REQUIRED for the full pipeline)...
uv pip install whisperx

echo.
echo [6/6] FFmpeg check...
where ffmpeg >nul 2>nul
if %errorlevel%==0 (
    echo      FFmpeg found on PATH: OK
) else (
    echo      FFmpeg NOT found on PATH.
    echo      [1] Auto-download ffmpeg next to ViralCutter (recommended)
    echo      [2] Skip - I will install it myself
    set /p ff_choice="     Choose (1/2): "
    if "!ff_choice!"=="1" (
        call packaging\install_ffmpeg_windows.bat
    )
)

echo.
echo ==========================================
echo Optional: direct upload (YouTube OAuth)?
echo ==========================================
set /p up_choice="Install upload stack (requirements-upload.txt)? [y/N]: "
if /i "%up_choice%"=="y" uv pip install -r requirements-upload.txt

echo.
echo ==========================================
echo Done!
echo ==========================================
echo.
echo Next steps:
echo   1. Put your Gemini key:   setx GEMINI_API_KEY "your-key-here"
echo      (or edit api_config.json / use scripts.secure_config)
echo   2. Run the app:           run.bat
echo      Web interface:         run_webui.bat
echo.
pause
