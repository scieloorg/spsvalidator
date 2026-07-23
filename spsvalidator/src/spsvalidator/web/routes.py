from __future__ import annotations

from pathlib import Path

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
from flask_babel import gettext
from packtools import catalogs

from spsvalidator.db.repository import (
    count_validations,
    get_validation_details,
    list_validations,
)
from spsvalidator.domain.export import build_validation_csv
from spsvalidator.services.validation_service import run_validation

web_blueprint = Blueprint(
    "web",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


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


def _pdf_previews_by_article(package_sha256: str) -> list[dict]:
    """PDFs extraídos para um pacote, agrupados por artigo (xml_stem).

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
        pdf_names = sorted(p.name for p in (article_dir / "assets").glob("*.pdf"))
        if pdf_names:
            groups.append({"xml_stem": article_dir.name, "pdf_names": pdf_names})
    return groups


def _parse_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _paginated_history() -> dict:
    db_path = current_app.config["DB_PATH"]
    name_query = request.args.get("q", "").strip()
    status_query = request.args.get("status", "").strip()
    page_size = _parse_int(request.args.get("page_size"), DEFAULT_PAGE_SIZE)
    page_size = min(MAX_PAGE_SIZE, max(1, page_size))
    page = max(1, _parse_int(request.args.get("page"), 1))

    total = count_validations(db_path, name_query, status_query)
    total_pages = max(1, -(-total // page_size))  # ceil division
    page = min(page, total_pages)

    history_items = list_validations(
        db_path,
        name_query,
        status_query,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    for item in history_items:
        item["html_previews"] = _html_previews_by_article(item["package_sha256"])
        item["pdf_previews"] = _pdf_previews_by_article(item["package_sha256"])

    return {
        "history_items": history_items,
        "name_query": name_query,
        "status_query": status_query,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _render_index(**context):
    context.setdefault("error_message", None)
    return render_template("index.html", **_paginated_history(), **context)


@web_blueprint.get("/history-list")
def history_list():
    return render_template("_history_list.html", **_paginated_history())


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
    uploaded_file = request.files.get("package_zip")

    if uploaded_file is None or not uploaded_file.filename:
        return _render_index(
            latest_result=None,
            error_message=gettext("Selecione um arquivo .zip para validar."),
        )

    try:
        result = run_validation(
            current_app.config["DB_PATH"],
            uploaded_file,
            zip_only_message=gettext("Apenas arquivos .zip SPS são suportados."),
            html_base_dir=current_app.config["HTML_PREVIEWS_DIR"],
            html_asset_urls=_html_preview_asset_urls(),
        )
    except Exception as exc:
        return _render_index(latest_result=None, error_message=str(exc))

    return redirect(url_for("web.index", history_id=result["history_id"]))


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


@web_blueprint.get("/favicon.ico")
def favicon():
    static_dir = Path(__file__).resolve().parent / "static" / "img"
    return send_from_directory(static_dir, "icon.png", mimetype="image/png")
