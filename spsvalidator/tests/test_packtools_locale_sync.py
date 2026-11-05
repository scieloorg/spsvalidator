import pytest

from spsvalidator import app as app_module
from spsvalidator.app import create_app


@pytest.mark.parametrize(
    ("accept_language", "expected_packtools_locale"),
    [
        ("pt-BR,pt;q=0.9", "pt_BR"),
        ("en-US,en;q=0.9", "en"),
        ("es-AR,es;q=0.9", "es"),
    ],
)
def test_before_request_sets_packtools_locale_from_accept_language(
    tmp_path, monkeypatch, accept_language, expected_packtools_locale
):
    calls = []
    monkeypatch.setattr(app_module.packtools_i18n, "set_locale", calls.append)

    app = create_app(str(tmp_path), execution_mode="browser")
    app.test_client().get("/", headers={"Accept-Language": accept_language})

    assert calls == [expected_packtools_locale]


def test_before_request_sets_packtools_locale_from_system_language(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.packtools_i18n, "set_locale", calls.append)

    app = create_app(str(tmp_path), execution_mode="desktop", system_language="es_AR")
    app.test_client().get("/", headers={"Accept-Language": "en-US"})

    assert calls == ["es"]


def test_unsupported_locale_falls_back_to_packtools_portuguese(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.packtools_i18n, "set_locale", calls.append)

    app = create_app(str(tmp_path), execution_mode="browser")
    app.test_client().get("/", headers={"Accept-Language": "de-DE"})

    assert calls == ["pt_BR"]

_PACKTOOLS_MSGID = (
    "Missing <alt-text>. Provide a concise textual description of the visual element content."
)


@pytest.mark.parametrize(
    ("packtools_locale", "expected_prefix"),
    [
        ("pt_BR", "Falta o elemento <alt-text>."),
        ("es", "Falta <alt-text>."),
    ],
)
def test_installed_packtools_ships_compiled_catalogs(packtools_locale, expected_prefix):
    """Sem mock: o packtools instalado precisa trazer os .mo (packtools#1267)."""
    try:
        app_module.packtools_i18n.set_locale(packtools_locale)
        translated = app_module.packtools_i18n._(_PACKTOOLS_MSGID)
    finally:
        app_module.packtools_i18n.set_locale("en")

    assert translated.startswith(expected_prefix)
