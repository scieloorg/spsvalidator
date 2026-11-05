from __future__ import annotations

import os
from pathlib import PurePosixPath

from lxml import etree
from packtools.sps.models.article_license import ArticleLicense
from packtools.sps.pid_provider.models.article_renditions import ArticleRenditions
from packtools.sps.pid_provider.models.journal_meta import JournalID, Publisher, Title
from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
from packtools.sps.validation.xml_validator import get_validation_results

from spsvalidator.domain.metadata import extract_article_snapshot


def _localized_field(result: dict, template_key: str, params_key: str, legacy_key: str) -> str | None:
    """Formata o texto internacionalizavel do packtools (``msg_text``/``adv_text`` +
    seus ``_params``), caindo para o campo legado (``message``/``advice``) quando o
    template nao vier preenchido ou nao puder ser formatado com os parametros dados.

    O fallback nao e um caso raro: ate a packtools#1257 ser concluida, a maioria dos
    validadores ainda nao preenche esses campos (packtools#1257 documenta que so uma
    fracao deles passa ``advice_text``/``advice_params`` para ``build_response``).
    """
    template = result.get(template_key)
    if not template:
        return result.get(legacy_key)
    try:
        return template.format(**(result.get(params_key) or {}))
    except (KeyError, IndexError, ValueError):
        return result.get(legacy_key)


def _extract_journal_data(xmltree):
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


def _expected_renditions(xml_with_pre) -> list[dict]:
    """PDFs que o XML declara, com o nome que o pacote deve ter.

    O packtools 4.18.3 devolve ``renditions == []`` quando ``zip_namelist`` está
    vazia, e o carregador do zip não põe os XMLs nessa lista. Num pacote só com
    o XML, a ausência dos PDFs deixaria de ser verificada. Nesse caso os nomes
    são montados aqui, com a mesma regra do packtools.
    """
    if xml_with_pre.zip_namelist:
        return list(xml_with_pre.renditions)
    items = []
    for rendition in ArticleRenditions(xml_with_pre.xmltree).article_renditions:
        suffix = ".pdf" if rendition.is_main_language else f"-{rendition.language}.pdf"
        items.append({
            "name": f"{xml_with_pre.xml_name}{suffix}",
            "lang": rendition.language,
            "component_type": "rendition",
            "main": rendition.is_main_language,
        })
    return items


def validate_sps_xml_with_pre(xml_with_pre) -> dict:
    """Valida um único artigo já parseado (``xml_with_pre``).

    Recebe uma instância de ``packtools.sps.pid_provider.xml_sps_lib.XMLWithPre``
    em vez de um caminho de zip, para permitir que quem já tenha parseado o
    pacote (ex.: para também gerar a prévia HTML) não precise reabri-lo.
    """
    package = PurePosixPath(xml_with_pre.filename).stem
    files_in_zip = set(xml_with_pre.filenames or [])

    rows = []
    exceptions = []

    for rendition in _expected_renditions(xml_with_pre):
        if rendition["name"] not in files_in_zip:
            lang = rendition["lang"]
            rows.append({
                "package": package,
                "status": "ERROR",
                "subject": "Renditions",
                "message": f"{lang} language is mentioned in the XML but its PDF file not present in the package.",
                "advise": f"Add the {lang} PDF file to the package or remove the {lang} rendition reference from the XML.",
                "data": rendition,
            })

    for asset in xml_with_pre.assets:
        if asset["name"] not in files_in_zip:
            name = asset["name"]
            rows.append({
                "package": package,
                "status": "CRITICAL",
                "subject": "Assets",
                "message": f"{name} file is mentioned in the XML but not present in the package.",
                "advise": f"Add the {name} file to the package or remove its reference from the XML.",
                "data": {**asset, "xml_path": xml_with_pre.filename},
            })

    xmltree = xml_with_pre.xmltree
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
            "message": _localized_field(result, "msg_text", "msg_params", "message"),
            "advise": _localized_field(result, "adv_text", "adv_params", "advice"),
            "data": dict(result),
        }
        rows.append(row)

    article = extract_article_snapshot(etree.tostring(xmltree), xml_with_pre.filename)
    # Todas as linhas vêm deste XML. O ``parent`` dos resultados é o elemento
    # (article, sub-article), não o arquivo, e não serve para associá-los ao artigo.
    issue_count = len(rows)
    article["issue_count"] = issue_count
    article["article_status"] = "issue" if issue_count else "ok"

    return {"rows": rows, "exceptions": exceptions, "article": article}


def validate_sps_zip(zip_path: str) -> dict:
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(zip_path)

    rows = []
    exceptions = []
    articles = []
    for xml_with_pre in XMLWithPre.create(path=zip_path):
        result = validate_sps_xml_with_pre(xml_with_pre)
        rows.extend(result["rows"])
        exceptions.extend(result["exceptions"])
        articles.append(result["article"])
    return {"rows": rows, "exceptions": exceptions, "articles": articles}