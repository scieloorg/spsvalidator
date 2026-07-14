from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from spsvalidator.db.repository import get_validation_details, list_validations
from spsvalidator.domain.export import build_validation_csv
from spsvalidator.services.validation_service import run_validation
from spsvalidator.web.i18n import get_translations, normalize_language

web_blueprint = Blueprint(
    "web",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


def _current_translations():
    return get_translations(normalize_language(request.cookies.get("lang")))


def _html_preview_asset_urls() -> dict:
    return {
        "css": url_for(
            "web.html_preview_assets", filename="scielo-article-standalone.css"
        ),
        "print_css": url_for(
            "web.html_preview_assets", filename="scielo-bundle-print.css"
        ),
        "js": url_for(
            "web.html_preview_assets", filename="scielo-article-standalone-min.js"
        ),
    }


def _html_previews_by_article(package_sha256: str) -> list[dict]:
    """Idiomas com HTML gerado para um pacote, agrupados por artigo (xml_stem).

    Um pacote SPS válido tem 1 XML, mas o agrupamento evita ambiguidade caso um
    pacote atípico contenha mais de um.
    """
    base_dir = Path(current_app.config["HTML_PREVIEWS_DIR"]) / package_sha256
    if not base_dir.is_dir():
        return []
    groups = []
    for article_dir in sorted(base_dir.iterdir()):
        if not article_dir.is_dir():
            continue
        langs = sorted(p.stem for p in article_dir.glob("*.html"))
        if langs:
            groups.append({"xml_stem": article_dir.name, "langs": langs})
    return groups


def _render_index(**context):
    context.setdefault("error_message", None)
    history_items = list_validations(current_app.config["DB_PATH"])
    for item in history_items:
        item["html_previews"] = _html_previews_by_article(item["package_sha256"])
    return render_template(
        "index.html",
        history_items=history_items,
        **context,
    )


def _safe_redirect_target(next_url: str | None) -> str:
    if not next_url:
        return url_for("web.index")
    parsed_url = urlparse(next_url)
    if not parsed_url.netloc and parsed_url.path.startswith("/"):
        return next_url
    return url_for("web.index")


def _redirect_with_lang(endpoint: str, **values):
    response = make_response(redirect(url_for(endpoint, **values)))
    language = normalize_language(request.cookies.get("lang"))
    response.set_cookie("lang", language, max_age=60 * 60 * 24 * 365)
    return response


@web_blueprint.get("/")
def index():
    selected_id = request.args.get("history_id")
    details = (
        get_validation_details(current_app.config["DB_PATH"], selected_id)
        if selected_id
        else None
    )
    return _render_index(latest_result=details)


@web_blueprint.post("/validate")
def validate():
    translations = _current_translations()
    uploaded_file = request.files.get("package_zip")
    if uploaded_file is None or not uploaded_file.filename:
        return _render_index(
            latest_result=None,
            error_message=translations["select_zip"],
        )
    try:
        result = run_validation(
            current_app.config["DB_PATH"],
            uploaded_file,
            zip_only_message=translations["zip_only"],
            html_base_dir=current_app.config["HTML_PREVIEWS_DIR"],
            html_asset_urls=_html_preview_asset_urls(),
        )
    except Exception as exc:
        return _render_index(latest_result=None, error_message=str(exc))
    return _redirect_with_lang("web.index", history_id=result["history_id"])


@web_blueprint.get("/validation/<history_id>/report.csv")
def download_csv(history_id: str):
    details = get_validation_details(current_app.config["DB_PATH"], history_id)
    if details is None:
        abort(404)
    csv_content = build_validation_csv(details["rows"])
    response = make_response(csv_content.encode("utf-8"))
    response.headers["Content-Type"] = "application/octet-stream"
    package_stem = details["package_name"].rsplit(".", 1)[0]
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{package_stem}.validation.csv"'
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@web_blueprint.get("/html-preview-assets/<path:filename>")
def html_preview_assets(filename: str):
    from packtools import catalogs

    # `catalogs` substitui a si mesmo em sys.modules por um objeto sem __file__
    # (ver packtools/catalogs/__init__.py); usamos um path já resolvido por ele
    # para descobrir o diretório real dos assets estáticos.
    static_dir = Path(catalogs.HTML_GEN_DEFAULT_CSS_PATH).resolve().parent
    return send_from_directory(static_dir, filename)


@web_blueprint.get("/validation/<history_id>/html/<xml_stem>/<lang>")
def view_html_preview(history_id: str, xml_stem: str, lang: str):
    details = get_validation_details(current_app.config["DB_PATH"], history_id)
    if details is None:
        abort(404)
    preview_dir = (
        Path(current_app.config["HTML_PREVIEWS_DIR"])
        / details["package_sha256"]
        / xml_stem
    )
    return send_from_directory(preview_dir, f"{lang}.html")


@web_blueprint.get("/validation/<history_id>/html/<xml_stem>/assets/<path:filename>")
def html_preview_asset(history_id: str, xml_stem: str, filename: str):
    details = get_validation_details(current_app.config["DB_PATH"], history_id)
    if details is None:
        abort(404)
    assets_dir = (
        Path(current_app.config["HTML_PREVIEWS_DIR"])
        / details["package_sha256"]
        / xml_stem
        / "assets"
    )
    return send_from_directory(assets_dir, filename)


@web_blueprint.get("/language/<language_code>")
def set_language(language_code: str):
    language = normalize_language(language_code)
    redirect_target = _safe_redirect_target(request.args.get("next"))
    response = make_response(redirect(redirect_target))
    response.set_cookie("lang", language, max_age=60 * 60 * 24 * 365)
    return response


@web_blueprint.get("/favicon.ico")
def favicon():
    static_dir = Path(__file__).resolve().parent / "static" / "img"
    return send_from_directory(static_dir, "icon.png", mimetype="image/png")
