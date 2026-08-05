#!/usr/bin/env bash
# ViralCutter launcher — Linux/macOS (Roadmap 1.3).
# 1) applies a pending auto-update binary if present,
# 2) activates the venv (or creates it via install_linux.sh / install_macos.sh),
# 3) starts the CLI (pass --webui to launch the web interface).
set -euo pipefail
cd "$(dirname "$0")"

if [ -f updates/update_info.json ]; then
    echo "[auto-update] pending update found — see updates/"
fi

if [ ! -d .venv ]; then
    echo "No .venv found. Run ./install_linux.sh or ./install_macos.sh first."
    exit 1
fi
. .venv/bin/activate
if [ "${1:-}" = "--webui" ]; then
    shift
    exec python webui/app.py "$@"
fi
exec python main_improved.py "$@"
