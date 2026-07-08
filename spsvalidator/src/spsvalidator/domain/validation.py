from __future__ import annotations

import os
import zipfile
from pathlib import Path, PurePosixPath

from spsvalidator.domain.metadata import extract_article_snapshot


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


# tag -> atributo que pode referenciar um arquivo do pacote (figura, imagem
# original em TIFF, SVG) no HTML gerado pelo packtools.HTMLGenerator.
_PACKAGE_ASSET_TAG_ATTRS = {"img": "src", "a": "href", "object": "data"}


def _is_package_asset_reference(value: str | None) -> bool:
    if not value:
        return False
    if "://" in value:
        return False
    return not value.startswith(("/", "#", "mailto:", "javascript:"))


def _extract_html_preview_assets(root, zip_archive: zipfile.ZipFile, assets_dir: Path) -> None:
    """Copia pro disco os arquivos do pacote referenciados no HTML (figuras,
    imagem original em TIFF etc.) e reescreve os links pra apontar pro
    subdiretório 'assets/', servido pela rota de prévia HTML.

    O HTMLGenerator do packtools emite esses links como o nome de arquivo cru
    do XML, sem nenhum caminho (o zip original é descartado logo após a
    validação, então sem isso os links ficam quebrados na prévia).
    """
    basenames_in_zip = {}
    for name in zip_archive.namelist():
        basenames_in_zip.setdefault(PurePosixPath(name).name, name)

    extracted = set()
    for tag, attr in _PACKAGE_ASSET_TAG_ATTRS.items():
        for element in root.iter(tag):
            value = element.get(attr)
            if not _is_package_asset_reference(value):
                continue
            basename = PurePosixPath(value).name
            member_name = basenames_in_zip.get(basename)
            if member_name is None:
                continue
            if basename not in extracted:
                assets_dir.mkdir(parents=True, exist_ok=True)
                (assets_dir / basename).write_bytes(zip_archive.read(member_name))
                extracted.add(basename)
            element.set(attr, f"assets/{basename}")


def _write_html_previews(
    xmltree, html_dir: str, asset_urls: dict | None, zip_archive: zipfile.ZipFile
) -> list[str]:
    from lxml import etree
    from packtools import HTMLGenerator

    tree = etree.ElementTree(xmltree)
    generator = HTMLGenerator(tree, **(asset_urls or {}))
    generated_langs = []
    for lang in generator.languages:
        try:
            html_output = generator.generate(lang)
        except Exception:
            # XSLT pode falhar para um idioma isolado (XML malformado); os demais seguem.
            continue
        _extract_html_preview_assets(
            html_output.getroot(), zip_archive, Path(html_dir) / "assets"
        )
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
    zip_archive = zipfile.ZipFile(zip_path) if html_dir else None
    try:
        for xml_with_pre in XMLWithPre.create(path=zip_path):
            package = PurePosixPath(xml_with_pre.filename).stem
            files_in_zip = set(xml_with_pre.files or [])

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

            for asset in xml_with_pre.assets:
                if asset["name"] not in files_in_zip:
                    name = asset["name"]
                    rows.append({
                        "package": package,
                        "status": "CRITICAL",
                        "subject": name,
                        "message": f"{name} file is mentioned in the XML but not present in the package.",
                        "data": {**asset, "xml_path": xml_with_pre.filename},
                    })

            xmltree = xml_with_pre.xmltree

            if html_dir:
                _write_html_previews(
                    xmltree, os.path.join(html_dir, package), asset_urls, zip_archive
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
    finally:
        if zip_archive is not None:
            zip_archive.close()
    articles = list(_iter_zip_xml_metadata(zip_path))
    for article in articles:
        path_key = article.get("xml_path", "")
        article["issue_count"] = issues_by_parent.get(path_key, 0)
        article["article_status"] = "issue" if article["issue_count"] else "ok"
    return {"rows": rows, "exceptions": exceptions, "articles": articles}
