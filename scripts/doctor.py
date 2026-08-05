"""ViralCutter system check.

Verifies runtime requirements BEFORE processing so users get a clear
report instead of a crash mid-pipeline.

Usage:  python scripts/doctor.py
Exit code 0 = all critical checks pass, 1 = something critical failed.
"""
import importlib
import os
import shutil
import sys

OK, WARN, FAIL = "ok", "warn", "fail"

ICONS = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}

MIN_PYTHON = (3, 9)

# (module, critical?) — critical failures break the core pipeline
DEPENDENCIES = [
    ("numpy", True),
    ("yt_dlp", True),
    ("gradio", False),
    ("psutil", False),
    ("fastapi", False),
    ("uvicorn", False),
    ("cv2", False),
    ("mediapipe", False),
    ("insightface", False),
    ("torch", False),
    ("google.genai", False),
    ("deep_translator", False),
    ("g4f", False),
    ("tqdm", False),
    # v6 features (Roadmap 2.1 / 4.4) — optional but strongly recommended:
    # onnxruntime = local visual classifier, cryptography = real key encryption.
    ("onnxruntime", False),
    ("cryptography", False),
    # Full transcription stack (Roadmap "ready to run"): whisperx + torch make
    # the complete YouTube→shorts pipeline work; without them only the
    # editing/safety/polish features run.
    ("whisperx", False),
    ("torch", False),
]


def check_python():
    if sys.version_info >= MIN_PYTHON:
        return {"name": "Python", "status": OK,
                "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"}
    return {"name": "Python", "status": FAIL,
            "detail": f"{sys.version_info.major}.{sys.version_info.minor} — required >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"}


def check_binary(name, critical=True):
    path = shutil.which(name)
    if path:
        return {"name": name, "status": OK, "detail": path}
    return {"name": name, "status": FAIL if critical else WARN,
            "detail": "not found on PATH"}


def check_dependency(module, critical):
    try:
        importlib.import_module(module)
        return {"name": module, "status": OK, "detail": "installed"}
    except Exception:
        return {"name": module, "status": FAIL if critical else WARN,
                "detail": "missing"}


def check_gpu():
    try:
        import torch
        if torch.cuda.is_available():
            return {"name": "GPU (CUDA)", "status": OK,
                    "detail": torch.cuda.get_device_name(0)}
        return {"name": "GPU (CUDA)", "status": WARN,
                "detail": "no CUDA device — CPU mode will be slow"}
    except Exception:
        return {"name": "GPU (CUDA)", "status": WARN,
                "detail": "torch not installed — cannot detect GPU"}


def check_writable(path="."):
    try:
        test_path = os.path.join(path, ".vc_write_test")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        return {"name": "Working dir writable", "status": OK, "detail": os.path.abspath(path)}
    except Exception as e:
        return {"name": "Working dir writable", "status": FAIL, "detail": str(e)}


def run_checks():
    checks = [
        check_python(),
        check_binary("ffmpeg", critical=True),
        check_binary("ffprobe", critical=True),
        check_writable(),
        check_gpu(),
    ]
    checks.extend(check_dependency(mod, crit) for mod, crit in DEPENDENCIES)
    return checks


def main():
    print("\n=== ViralCutter Doctor ===\n")
    checks = run_checks()
    critical_failed = 0
    for c in checks:
        print(f"{ICONS[c['status']]} {c['name']:<24} {c['detail']}")
        if c["status"] == FAIL:
            critical_failed += 1

    print()
    if critical_failed:
        print(f"❌ {critical_failed} critical check(s) failed. Fix them before running ViralCutter.")
        return 1
    warns = sum(1 for c in checks if c["status"] == WARN)
    print(f"✅ System ready. ({warns} optional warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
