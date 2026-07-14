from __future__ import annotations

from pathlib import Path

from flask import Flask, g, request

from spsvalidator.build_metadata import get_footer_build_label
from spsvalidator.db.repository import get_setting, init_db
from spsvalidator.version import APP_DISPLAY_NAME
from spsvalidator.web.i18n import (
    LANGUAGE_OPTIONS,
    detect_request_language,
    get_translations,
)
from spsvalidator.web.routes import web_blueprint


def create_app(data_dir=None, execution_mode="browser", system_language=None):
    app = Flask(__name__, static_folder=None)
    app.secret_key = "spsvalidator-local-secret"
    target_dir = Path(data_dir) if data_dir else Path.home() / ".spsvalidator"
    target_dir.mkdir(parents=True, exist_ok=True)
    db_path = target_dir / "spsvalidator.sqlite3"
    init_db(str(db_path))
    app.config["DB_PATH"] = str(db_path)
    app.config["APP_DISPLAY_NAME"] = APP_DISPLAY_NAME
    app.config["EXECUTION_MODE"] = execution_mode
    app.config["SYSTEM_LANGUAGE"] = system_language

    @app.before_request
    def set_request_language():
        g.language = detect_request_language(
            request,
            execution_mode=app.config["EXECUTION_MODE"],
            system_language=app.config["SYSTEM_LANGUAGE"],
            preferred_language=get_setting(app.config["DB_PATH"], "language"),
        )

    @app.context_processor
    def inject_app_info():
        language = g.language
        translations = get_translations(language)
        return {
            "app_display_name": app.config["APP_DISPLAY_NAME"],
            "current_language": language,
            "language_options": LANGUAGE_OPTIONS,
            "t": translations,
            "footer_build_label": get_footer_build_label(language, translations),
        }

    app.register_blueprint(web_blueprint)
    return app
