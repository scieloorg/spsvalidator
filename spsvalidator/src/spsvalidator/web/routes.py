from __future__ import annotations

from datetime import datetime
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
    count_articles,
    count_validations,
    get_package_name,
    get_validation_details,
    list_articles,
    list_validations,
)
from spsvalidator.domain.export import build_validation_csv
from spsvalidator.domain.report import build_grouped_report
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


def _short_pdf_label(xml_stem: str, filename: str) -> str:
    """Rótulo curto pra diferenciar PDFs de um mesmo artigo na listagem.

    Os nomes de arquivo compartilham o prefixo `xml_stem` (ex.:
    "artigo.pdf", "artigo-suppl1.pdf"), o que faz uma lista inteira de
    nomes completos parecer repetitiva; aqui extraímos só a parte que
    diferencia cada arquivo.
    """
    stem = filename[:-4] if filename.lower().endswith(".pdf") else filename
    if stem == xml_stem:
        return gettext("PDF principal")
    if stem.startswith(xml_stem) and stem[len(xml_stem):len(xml_stem) + 1] in ("-", "_"):
        suffix = stem[len(xml_stem):].lstrip("-_")
        if suffix:
            return suffix
    return filename


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
        xml_stem = article_dir.name
        pdf_names = sorted(p.name for p in (article_dir / "assets").glob("*.pdf"))
        if pdf_names:
            pdfs = [
                {"filename": name, "label": _short_pdf_label(xml_stem, name)}
                for name in pdf_names
            ]
            groups.append({"xml_stem": xml_stem, "pdfs": pdfs})
    return groups


def _format_validated_at(value: str) -> str:
    """Formata "validated_at" como "AAAA-MM-DD HH:MM:SS" pra exibicao na tabela.

    O valor e gravado com datetime.now(UTC).isoformat(), que inclui
    microssegundos e o offset "+00:00"; ambos sao ruido pra quem esta
    lendo a lista de historico.
    """
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def _parse_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_range(page: int, total_pages: int, window: int = 2) -> list[int]:
    """Janela de numeros de pagina ao redor da pagina atual, tipo Django."""
    start = max(1, page - window)
    end = min(total_pages, page + window)
    return list(range(start, end + 1))


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
        item["validated_at"] = _format_validated_at(item["validated_at"])
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
        "page_range": _page_range(page, total_pages),
    }


def _paginated_articles() -> dict:
    db_path = current_app.config["DB_PATH"]
    name_query = request.args.get("article_q", "").strip()
    doi_query = request.args.get("article_doi", "").strip()
    pid_query = request.args.get("article_pid", "").strip()
    status_query = request.args.get("article_status", "").strip()
    history_id = request.args.get("history_id", "").strip()
    page_size = _parse_int(request.args.get("article_page_size"), DEFAULT_PAGE_SIZE)
    page_size = min(MAX_PAGE_SIZE, max(1, page_size))
    page = max(1, _parse_int(request.args.get("article_page"), 1))

    total = count_articles(
        db_path, name_query, doi_query, pid_query, status_query, history_id or None
    )
    total_pages = max(1, -(-total // page_size))  # ceil division
    page = min(page, total_pages)

    articles = list_articles(
        db_path,
        name_query,
        doi_query,
        pid_query,
        status_query,
        history_id or None,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    for article in articles:
        article["validated_at"] = _format_validated_at(article["validated_at"])

    return {
        "articles": articles,
        "article_name_query": name_query,
        "article_doi_query": doi_query,
        "article_pid_query": pid_query,
        "article_status_query": status_query,
        "article_history_id": history_id,
        "article_page": page,
        "article_page_size": page_size,
        "article_total": total,
        "article_total_pages": total_pages,
        "article_page_range": _page_range(page, total_pages),
        "selected_package_name": (
            get_package_name(db_path, history_id) if history_id else None
        ),
    }


def _render_index(**context):
    context.setdefault("error_message", None)
    context.setdefault("default_tab", "history")
    return render_template(
        "index.html", **_paginated_history(), **_paginated_articles(), **context
    )


@web_blueprint.get("/history-list")
def history_list():
    return render_template("_history_list.html", **_paginated_history())


@web_blueprint.get("/articles-list")
def articles_list():
    return render_template("_articles_list.html", **_paginated_articles())


@web_blueprint.get("/")
def index():
    selected_id = request.args.get("history_id", "").strip()
    return _render_index(default_tab="articles" if selected_id else "history")


@web_blueprint.post("/validate")
def validate():
    uploaded_file = request.files.get("package_zip")

    if uploaded_file is None or not uploaded_file.filename:
        return _render_index(
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
        return _render_index(error_message=str(exc))

    return redirect(
        url_for(
            "web.index",
            history_id=result["history_id"],
            q=request.args.get("q") or None,
            status=request.args.get("status") or None,
            page_size=request.args.get("page_size") or None,
            page=request.args.get("page") or None,
            article_q=request.args.get("article_q") or None,
            article_doi=request.args.get("article_doi") or None,
            article_pid=request.args.get("article_pid") or None,
            article_status=request.args.get("article_status") or None,
            article_page_size=request.args.get("article_page_size") or None,
            article_page=request.args.get("article_page") or None,
        )
    )


@web_blueprint.get("/validation/<history_id>/report.csv")
def download_csv(history_id: str):
    details = get_validation_details(current_app.config["DB_PATH"], history_id)
    if details is None:
        abort(404)
    csv_headers = {
        "package": gettext("Pacote"),
        "status": gettext("Gravidade"),
        "subject": gettext("Categoria"),
        "message": gettext("Problema"),
        "advise": gettext("Ação de correção"),
    }
    csv_content = build_validation_csv(details["rows"], headers=csv_headers)
    response = make_response(csv_content.encode("utf-8"))
    response.headers["Content-Type"] = "application/octet-stream"
    package_stem = details["package_name"].rsplit(".", 1)[0]
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{package_stem}.validation.csv"'
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@web_blueprint.get("/validation/<history_id>/report.html")
def view_report(history_id: str):
    details = get_validation_details(current_app.config["DB_PATH"], history_id)
    if details is None:
        abort(404)
    return render_template(
        "report.html",
        history_id=history_id,
        package_name=details["package_name"],
        grouped_report=build_grouped_report(details["rows"]),
    )


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
