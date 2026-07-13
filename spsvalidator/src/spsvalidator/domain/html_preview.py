from __future__ import annotations

import copy
import os
import zipfile
from pathlib import Path, PurePosixPath

from spsvalidator.domain.zip_parser import parse_zip_packages

_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


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
        # instância usada pela validação SPS; mutar o original contaminaria
        # o resultado da validação com hrefs que não existem no XML real.
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


def generate_html_previews(
    zip_path: str, html_dir: str, asset_urls: dict | None = None
) -> dict[str, list[str]]:
    """Gera, para cada XML do pacote, a prévia HTML por idioma via
    packtools.HTMLGenerator, extraindo e relinkando os assets (figuras etc.)
    referenciados no XML. Devolve {package: [langs gerados]}."""
    generated_by_package: dict[str, list[str]] = {}
    with zipfile.ZipFile(zip_path) as zip_archive:
        for pkg in parse_zip_packages(zip_path):
            available_asset_names = [
                asset["name"]
                for asset in pkg.xml_with_pre.assets
                if asset["name"] in pkg.files_in_zip
            ]
            generated_by_package[pkg.package] = _write_html_previews(
                pkg.xmltree,
                os.path.join(html_dir, pkg.package),
                asset_urls,
                zip_archive,
                available_asset_names,
            )
    return generated_by_package