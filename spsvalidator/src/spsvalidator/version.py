from __future__ import annotations

import tomllib
from pathlib import Path


def _pyproject_path() -> Path:
    return Path(__file__).resolve().parents[2] / "pyproject.toml"


def is_running_from_source() -> bool:
    """True quando rodando a partir do repositorio (pip install -e .).

    Nesse caso pyproject.toml esta presente ao lado do pacote; num build
    empacotado (PyInstaller) ele nao existe, e so ai os metadados
    gravados em build_info.py (gerados pra aquele build especifico) sao
    confiaveis.
    """
    return _pyproject_path().is_file()


def _load_version() -> str:
    if is_running_from_source():
        with _pyproject_path().open("rb") as file_pointer:
            data = tomllib.load(file_pointer)
        return str(data["project"]["version"])
    from spsvalidator import build_info

    return build_info.APP_VERSION


__version__ = _load_version()
APP_DISPLAY_NAME = f"SPSValidator-v{__version__}"
