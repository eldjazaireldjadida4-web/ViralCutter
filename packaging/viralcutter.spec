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

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent  # packaging/ → repo root

datas = [
    (str(ROOT / "i18n"), "i18n"),
    (str(ROOT / "models"), "models"),
    (str(ROOT / "fonts"), "fonts"),
    (str(ROOT / "prompt.txt"), "."),
    (str(ROOT / "api_config.json"), "."),
    (str(ROOT / "safety_blocklist.json"), "."),
    (str(ROOT / "safety_terms.example.json"), "."),
    # webui/preview.json is read via the module's __file__-relative dir
    # (webui/subtitle_handler.py) → must sit at the bundle root.
    (str(ROOT / "webui" / "preview.json"), "."),
]
# Several small packages in the gradio dependency chain (safehttpx, groovy,
# …) read a version.txt from their package dir at import time. PyInstaller
# has no hooks for them, so a frozen exe crashed on WebUI startup with
# FileNotFoundError: .../<pkg>/version.txt. Fix it GENERICALLY: collect data
# files for every installed package that ships such a version file at its
# root — catches this whole class at once, not one package per release.
import site as _site
import os as _os

def _packages_with_version_file():
    pkgs = []
    for _sp in _site.getsitepackages():
        if not _os.path.isdir(_sp):
            continue
        for _name in _os.listdir(_sp):
            _d = _os.path.join(_sp, _name)
            if not _os.path.isdir(_d) or _name.endswith((".dist-info", ".egg-info")):
                continue
            if any(_os.path.isfile(_os.path.join(_d, _f))
                   for _f in ("version.txt", "VERSION", "version")):
                pkgs.append(_name)
    return sorted(set(pkgs))

for _pkg in _packages_with_version_file():
    datas += collect_data_files(_pkg)
# gradio also reads bundled frontend/template files at runtime — and on top
# of that it reads its OWN .py SOURCE files at startup (component_meta.py →
# create_or_modify_pyi reads gradio/blocks_events.py to generate type stubs).
# PyInstaller excludes .py from data by default → frozen WebUI crashed with
# FileNotFoundError .../gradio/blocks_events.py. include_py_files=True fixes
# the whole class of "reads its own source at runtime".
datas += collect_data_files("gradio", include_py_files=True)

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
    pathex=[str(ROOT), str(ROOT / "webui")],
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
        # WebUI (launched by default when the exe is double-clicked)
        "app", "library", "subtitle_handler", "subtitle_editor",
        "segments_review", "publish_panel", "batch_queue",
        "settings_store", "header", "utils", "pipeline", "runtime",
        # Premiere XML export (called in-process by the WebUI)
        "scripts.export_xml_lib",
        "scripts.export_xml_lib.exporter",
        "scripts.export_xml_lib.face_detection",
        "scripts.export_xml_lib.rendering",
        "scripts.export_xml_lib.xml_generator",
        "scripts.export_xml_lib.utils",
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
