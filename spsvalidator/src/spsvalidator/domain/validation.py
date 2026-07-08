from __future__ import annotations

import copy
import os
import zipfile
from pathlib import Path, PurePosixPath

from spsvalidator.domain.metadata import extract_article_snapshot

_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _extract_journal_data(xmltree):
    from packtools.sps.models.article_license import ArticleLicense
    from packtools.sps.pid_provider.models.journal_meta import (
        JournalID,
        Publisher,
        Title,
    )

    try:
        license_code = None
        for license_item in ArticleLicense(xmltree).licenses:
            code = license_item.get("code")
            if code:
                license_code = code
                break
        return {
            "abbrev_journal_title": Title(xmltree).abbreviated_journal_title,
            "publisher_name_list": Publisher(xmltree).publishers_names,
            "nlm_journal_title": JournalID(xmltree).nlm_ta,
            "license_code": license_code,
        }
    except Exception:
        return {}


def _fix_graphic_extension(basename: str) -> str:
    """Replica fix_extension (article-text-graphic.xsl do packtools): o XSLT
    exibe .tif/.tiff e nomes sem extensão como .jpg. Usado só pra saber qual
    arquivo extrair do zip pro disco também sob esse nome — quem decide o
    valor final do @xlink:href renderizado continua sendo o próprio XSLT.
    """
    last_six = basename[-6:]
    ext = last_six.rsplit(".", 1)[-1] if "." in last_six else ""
    if ext == "":
        return f"{basename}.jpg"
    if "tif" in ext:
        return f"{basename.rsplit('.', 1)[0]}.jpg"
    return basename


def _extract_and_relink_assets(
    tree_root, zip_archive: zipfile.ZipFile, asset_names: list[str], assets_dir: Path
) -> None:
    """Extrai pro disco os arquivos do pacote referenciados como assets do
    artigo (figuras, imagem original em TIFF etc.) e reescreve o @xlink:href
    da árvore pra apontar pro subdiretório 'assets/', servido pela rota de
    prévia HTML.

    A reescrita acontece no XML de entrada, antes do XSLT rodar — não no HTML
    de saída — pra não depender de adivinhar em qual tag/atributo (img/src,
    a/href, object/data...) o XSLT vai renderizar cada tipo de asset. O
    próprio XSLT aplica sua lógica de extensão (tif -> jpg) em cima do valor
    reescrito aqui, então extraímos preventivamente também a variante com
    extensão corrigida, quando ela existe no zip.
    """
    basenames_in_zip = {}
    for name in zip_archive.namelist():
        basenames_in_zip.setdefault(PurePosixPath(name).name, name)

    extracted = set()

    def extract(basename: str) -> None:
        if basename in extracted:
            return
        member_name = basenames_in_zip.get(basename)
        if member_name is None:
            return
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / basename).write_bytes(zip_archive.read(member_name))
        extracted.add(basename)

    asset_name_set = set(asset_names)
    for href in asset_name_set:
        basename = PurePosixPath(href).name
        extract(basename)
        extract(_fix_graphic_extension(basename))

    for element in tree_root.iter():
        href = element.get(_XLINK_HREF)
        if href in asset_name_set:
            element.set(_XLINK_HREF, f"assets/{PurePosixPath(href).name}")


def _write_html_previews(
    xmltree,
    html_dir: str,
    asset_urls: dict | None,
    zip_archive: zipfile.ZipFile | None,
    asset_names: list[str],
) -> list[str]:
    from lxml import etree
    from packtools import HTMLGenerator

    if asset_names and zip_archive is not None:
        # Copia a árvore antes de reescrever @xlink:href: xmltree é a mesma
        # instância usada logo depois por get_validation_results(), mutar o
        # original contaminaria a validação SPS com hrefs que não existem
        # no XML real.
        tree_root = copy.deepcopy(xmltree)
        _extract_and_relink_assets(
            tree_root, zip_archive, asset_names, Path(html_dir) / "assets"
        )
    else:
        tree_root = xmltree

    tree = etree.ElementTree(tree_root)
    generator = HTMLGenerator(tree, **(asset_urls or {}))
    generated_langs = []
    for lang in generator.languages:
        try:
            html_output = generator.generate(lang)
        except Exception:
            # XSLT pode falhar para um idioma isolado (XML malformado); os demais seguem.
            continue
        out_path = Path(html_dir) / f"{lang}.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(etree.tostring(
            html_output, pretty_print=True, encoding="utf-8",
            method="html", doctype="<!DOCTYPE html>",
        ))
        generated_langs.append(lang)
    return generated_langs


def _iter_zip_xml_metadata(zip_path: str):
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            suffix = PurePosixPath(member.filename).suffix.lower()
            if suffix != ".xml":
                continue
            yield extract_article_snapshot(archive.read(member), member.filename)


def validate_sps_zip(
    zip_path: str, html_dir: str | None = None, asset_urls: dict | None = None
) -> dict:
    from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
    from packtools.sps.validation.xml_validator import get_validation_results

    if not os.path.isfile(zip_path):
        raise FileNotFoundError(zip_path)
    rows = []
    exceptions = []
    issues_by_parent = {}
    for xml_with_pre in XMLWithPre.create(path=zip_path):
        package = PurePosixPath(xml_with_pre.filename).stem
        # xml_with_pre.files traz o caminho completo dentro do zip (pacotes
        # reais sempre têm os arquivos numa subpasta); rendition["name"] e
        # asset["name"] são só o nome do arquivo, então a comparação precisa
        # ser por nome-base, senão nunca bate.
        files_in_zip = {PurePosixPath(f).name for f in (xml_with_pre.files or [])}

        for rendition in xml_with_pre.renditions:
            if rendition["name"] not in files_in_zip:
                lang = rendition["lang"]
                rows.append({
                    "package": package,
                    "status": "ERROR",
                    "subject": f"Renditions {lang}",
                    "message": f"{lang} language is mentioned in the XML but its PDF file not present in the package.",
                    "data": rendition,
                })

        available_asset_names = []
        for asset in xml_with_pre.assets:
            name = asset["name"]
            if name not in files_in_zip:
                rows.append({
                    "package": package,
                    "status": "CRITICAL",
                    "subject": name,
                    "message": f"{name} file is mentioned in the XML but not present in the package.",
                    "data": {**asset, "xml_path": xml_with_pre.filename},
                })
                continue
            available_asset_names.append(name)

        xmltree = xml_with_pre.xmltree

        if html_dir:
            with zipfile.ZipFile(zip_path) as zip_archive:
                _write_html_previews(
                    xmltree,
                    os.path.join(html_dir, package),
                    asset_urls,
                    zip_archive,
                    available_asset_names,
                )

        rules = {"journal_data": _extract_journal_data(xmltree)}
        for result in get_validation_results(xmltree, rules):
            if not result:
                continue
            if result.get("response") == "exception":
                exceptions.append(result)
                continue
            if result.get("response") == "OK":
                continue
            row = {
                "package": package,
                "status": result.get("response"),
                "subject": result.get("group"),
                "message": result.get("advice"),
                "data": dict(result),
            }
            rows.append(row)
            parent_key = result.get("parent") or result.get("parent_id") or ""
            if parent_key:
                issues_by_parent[parent_key] = issues_by_parent.get(parent_key, 0) + 1
    articles = list(_iter_zip_xml_metadata(zip_path))
    for article in articles:
        path_key = article.get("xml_path", "")
        article["issue_count"] = issues_by_parent.get(path_key, 0)
        article["article_status"] = "issue" if article["issue_count"] else "ok"
    return {"rows": rows, "exceptions": exceptions, "articles": articles}
