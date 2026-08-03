from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask, current_app, request
from flask_babel import Babel, get_locale
from packtools.sps import i18n as packtools_i18n

from spsvalidator.build_metadata import get_footer_build_label
from spsvalidator.db.repository import init_db
from spsvalidator.version import APP_DISPLAY_NAME
from spsvalidator.web import i18n
from spsvalidator.web.routes import web_blueprint

# Mapeia os codigos de idioma do spsvalidator (web/i18n.SUPPORTED_LANGUAGES)
# pros nomes de diretorio de catalogo do packtools (packtools/sps/locale/*).
# Nota: ate o packtools corrigir scieloorg/packtools#1267 (release nao inclui
# os .mo compilados quando instalado via git), set_locale() aqui fica sem
# efeito pratico - as mensagens de validacao continuam em ingles mesmo com o
# locale certo selecionado. O wiring fica pronto pra quando isso for corrigido
# no packtools.
_PACKTOOLS_LOCALE_MAP = {"pt": "pt_BR", "en": "en", "es": "es"}


def select_locale():
    if current_app.config["EXECUTION_MODE"] == "desktop":
        return i18n.normalize_language(current_app.config["SYSTEM_LANGUAGE"])

    return request.accept_languages.best_match(i18n.SUPPORTED_LANGUAGES)


def create_app(
    data_dir: str | None = None,
    execution_mode="browser",
    system_language=None,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.secret_key = "spsvalidator-local-secret"
    target_dir = Path(data_dir) if data_dir else Path.home() / ".spsvalidator"
    target_dir.mkdir(parents=True, exist_ok=True)
    db_path = target_dir / "spsvalidator.sqlite3"
    init_db(str(db_path))
    app.config["DB_PATH"] = str(db_path)
    app.config["HTML_PREVIEWS_DIR"] = str(target_dir / "html_previews")
    app.config["APP_DISPLAY_NAME"] = APP_DISPLAY_NAME
    app.config["BABEL_DEFAULT_LOCALE"] = "pt"
    app.config["EXECUTION_MODE"] = execution_mode
    app.config["SYSTEM_LANGUAGE"] = system_language
    # Protege a rota web.shutdown: só quem carregou a página (e recebeu o
    # token embutido no HTML) consegue encerrar o servidor via POST, o que
    # impede uma página externa de derrubar o app com um POST às cegas.
    app.config["SHUTDOWN_TOKEN"] = secrets.token_urlsafe(32)

    Babel(app, locale_selector=select_locale)

    @app.before_request
    def sync_packtools_locale():
        packtools_i18n.set_locale(_PACKTOOLS_LOCALE_MAP.get(str(get_locale()), "en"))

    @app.context_processor
    def inject_app_info():
        return {
            "app_display_name": app.config["APP_DISPLAY_NAME"],
            "current_locale": str(get_locale()).replace("_", "-"),
            "footer_build_label": get_footer_build_label(),
            "server_url": app.config.get("SERVER_URL"),
            "execution_mode": app.config["EXECUTION_MODE"],
            "shutdown_token": app.config["SHUTDOWN_TOKEN"],
        }

    app.register_blueprint(web_blueprint)
    return app
