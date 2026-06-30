#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${ROOT_DIR}/.venv"
_ensure_build_venv() {
  if [[ -d "$VENV_DIR" ]] && ! "$VENV_DIR/bin/python" -c "import gi" >/dev/null 2>&1; then
    rm -rf "$VENV_DIR"
  fi
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
  fi
}

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  _ensure_build_venv
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
fi

if ! python -c "import gi" >/dev/null 2>&1; then
  echo "Missing GTK bindings (gi). Install system packages and rebuild:" >&2
  echo "  sudo apt install python3-gi python3-gi-cairo gir1.2-webkit-6.0" >&2
  exit 1
fi

python -m pip install -e .
python -m pip install pyinstaller

# Remove old onedir output so the onefile binary can use dist/spsvalidator.
rm -rf build/spsvalidator dist/spsvalidator spsvalidator.spec

pyinstaller --noconfirm --clean --onefile --windowed \
  --name spsvalidator \
  --icon src/spsvalidator/web/static/img/icon.png \
  --paths src \
  --collect-data packtools \
  --collect-data spsvalidator \
  --hidden-import pkg_resources \
  --hidden-import requests \
  --hidden-import tenacity \
  --hidden-import langdetect \
  --hidden-import gi \
  --hidden-import gi.repository \
  --hidden-import gi.repository.Gtk \
  --hidden-import gi.repository.WebKit2 \
  --hidden-import webview.platforms.gtk \
  --exclude-module webview.platforms.qt \
  --exclude-module webview.platforms.android \
  --exclude-module webview.platforms.cocoa \
  --exclude-module webview.platforms.winforms \
  --exclude-module webview.platforms.edgechromium \
  --exclude-module qtpy \
  --exclude-module PyQt6 \
  --exclude-module PySide6 \
  --exclude-module black \
  --exclude-module pytest \
  --exclude-module isort \
  --copy-metadata setuptools \
  src/spsvalidator/main.py

echo "Linux executable generated at dist/spsvalidator."
echo "Use linuxdeploy/appimagetool to convert it into AppImage."
