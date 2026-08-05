#!/usr/bin/env bash
# ViralCutter installer — macOS (Roadmap 1.3). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

echo "== ViralCutter installer (macOS) =="
echo "[1/4] Homebrew check..."
if ! command -v brew >/dev/null 2>&1; then
    echo "Installing Homebrew (https://brew.sh)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
echo "[2/4] ffmpeg + python..."
brew install ffmpeg python@3.11 || brew upgrade ffmpeg python@3.11
echo "[3/4] Virtual environment + deps..."
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install -r requirements-dev.txt --quiet || true
echo "[4/4] Sanity check..."
python -c "import sys; sys.path.insert(0,'.'); import scripts.risk_scorecard; print('✅ import ok')"
echo ""
echo "✅ Done. Run:  ./run.sh"
