#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SPEC_FILE="${ROOT_DIR}/src/spsvalidator/spsvalidator_linux.spec"

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
  echo "  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit-6.0" >&2
  exit 1
fi

python -m pip install -e .
python -m pip install "pywebview[qt]" pyinstaller

if ! python -c "import webview.platforms.qt" >/dev/null 2>&1; then
  echo "Missing Qt backend for pywebview. Install system packages and rebuild:" >&2
  echo "  sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine" >&2
  exit 1
fi

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "Spec file not found: $SPEC_FILE" >&2
  exit 1
fi

# Remove old output so the binary can use dist/spsvalidator.
rm -rf build/spsvalidator dist/spsvalidator

pyinstaller --noconfirm --clean "$SPEC_FILE"

echo "Linux executable generated at dist/spsvalidator."
echo "GTK and Qt backends are bundled; runtime still needs system GTK or Qt libraries."
echo "Use linuxdeploy/appimagetool to convert it into AppImage."
