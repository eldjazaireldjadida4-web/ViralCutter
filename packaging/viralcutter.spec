# -*- mode: python ; coding: utf-8 -*-
# ViralCutter PyInstaller spec — single-file executable build (Roadmap 1.1).
#
# Build (run from the repo root):
#   Windows:   pyinstaller packaging/viralcutter.spec --noconfirm
#   Linux:     pyinstaller packaging/viralcutter.spec --noconfirm
#   macOS:     pyinstaller packaging/viralcutter.spec --noconfirm
#
# The result is dist/ViralCutter(.exe). FFmpeg is NOT bundled into the
# binary by default because the licenses/platforms differ per OS; instead:
#   - Windows: run scripts/install_ffmpeg_windows.bat once (downloads static
#     ffmpeg next to the exe) — or uncomment the `binaries` line below after
#     placing ffmpeg.exe/ffprobe.exe in packaging/ffmpeg-win/.
#   - Linux/macOS: the install script installs ffmpeg via the package manager.
#
# CUDA is optional and detected at runtime (WhisperX uses whatever torch
# brings); nothing extra is needed in the bundle.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # packaging/ → repo root

datas = [
    (str(ROOT / "i18n"), "i18n"),
    (str(ROOT / "models"), "models"),
    (str(ROOT / "fonts"), "fonts"),
    (str(ROOT / "prompt.txt"), "."),
    (str(ROOT / "api_config.json"), "."),
    (str(ROOT / "safety_blocklist.json"), "."),
    (str(ROOT / "safety_terms.example.json"), "."),
]

# Third-party binaries bundled automatically from packaging/third_party/.
# The Windows CI build (build-exe.yml) drops fpcalc.exe (and its runtime
# DLLs) there; at runtime they appear next to the exe (onefile →
# sys._MEIPASS), where scripts/music_fingerprint.py finds them. This makes
# the music check work out of the box — no manual downloads for the user.
binaries = []
_tp = ROOT / "packaging" / "third_party"
if _tp.is_dir():
    for p in sorted(_tp.iterdir()):
        if p.is_file():
            binaries.append((str(p), "."))

a = Analysis(
    [str(ROOT / "main_improved.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # whisperx + deps that PyInstaller's static analysis misses
        "whisperx",
        "whisperx.transcribe",
        "whisperx.alignment",
        "whisperx.diarize",
        "pyannote.audio",
        "omegaconf",
        "torchaudio",
        "onnxruntime",
        "google.generativeai",
        "g4f",
        "llama_cpp",
        "mediapipe",
        "insightface",
        "acoustid",  # optional music fingerprint check (2.3)
        "gradio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ViralCutter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # CLI + WebUI launcher share the console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
