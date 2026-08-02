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