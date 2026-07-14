from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import PurePosixPath

from lxml import etree
from packtools.domain import HTMLGenerator
from packtools.sps.models.article_assets import ArticleAssets
from packtools.utils import XMLWebOptimiser


def generate_html_previews(
    xml_with_pre, html_dir: str, html_asset_urls: dict | None = None
) -> list[str]:
    """Gera uma prévia HTML por idioma disponível para o artigo de ``xml_with_pre``.

    ``html_asset_urls`` são as URLs do CSS/JS do design system do packtools
    (repassadas como kwargs pro HTMLGenerator, ex.: css/print_css/js) — nunca
    URLs de imagem: as imagens do artigo ficam em caminho relativo
    ``assets/...``, resolvido a partir da própria página de prévia.

    Imagens tif/sem-extensão são otimizadas via packtools.utils.XMLWebOptimiser
    (mesma classe usada pela pipeline real de publicação do SciELO), que gera
    as variantes .png (ampliação) e .thumbnail.jpg (miniatura) a partir do
    conteúdo real da imagem — sem depender de já existir um arquivo de mesmo
    nome-base no pacote.
    """
    package = PurePosixPath(xml_with_pre.filename).stem
    article_dir = os.path.join(html_dir, package)
    assets_dir = os.path.join(article_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    with zipfile.ZipFile(xml_with_pre.zip_file_path) as zip_archive:
        optimised_root = _optimise_and_write_assets(xml_with_pre, zip_archive, assets_dir)

    generator = HTMLGenerator(
        etree.ElementTree(optimised_root), **(html_asset_urls or {})
    )
    generated_langs = []
    for lang in generator.languages:
        try:
            html_output = generator.generate(lang)
        except Exception:
            # XSLT pode falhar para um idioma isolado (XML malformado); os demais seguem.
            continue
        out_path = os.path.join(article_dir, f"{lang}.html")
        with open(out_path, "wb") as fp:
            fp.write(etree.tostring(
                html_output, pretty_print=True, encoding="utf-8",
                method="html", doctype="<!DOCTYPE html>",
            ))
        generated_langs.append(lang)
    return generated_langs


def _optimise_and_write_assets(xml_with_pre, zip_archive, assets_dir: str):
    member_by_basename = {
        os.path.basename(name): name
        for name in zip_archive.namelist()
        if not name.endswith("/")
    }
    image_filenames = [
        name for name in member_by_basename
        if os.path.splitext(name)[-1].lower() != ".pdf"
    ]

    def read_file(filename):
        member = member_by_basename[os.path.basename(filename)]
        return zip_archive.read(member)

    optimiser = XMLWebOptimiser(
        filename=xml_with_pre.filename,
        image_filenames=image_filenames,
        read_file=read_file,
        work_dir=assets_dir,
        stop_if_error=False,
    )
    optimised_root = etree.fromstring(optimiser.get_xml_file())

    from_to = {}
    for filename, content in optimiser.get_optimised_assets():
        if content is None:
            continue
        _write_bytes(assets_dir, filename, content)
        from_to[filename] = f"assets/{filename}"
    for filename, content in optimiser.get_assets_thumbnails():
        if content is None:
            continue
        _write_bytes(assets_dir, filename, content)
        from_to[filename] = f"assets/{filename}"

    for asset in ArticleAssets(optimised_root).article_assets:
        name = asset.name
        if name in from_to:
            continue
        member = member_by_basename.get(os.path.basename(name))
        if member is None:
            continue
        with zip_archive.open(member) as source, open(
            os.path.join(assets_dir, os.path.basename(name)), "wb"
        ) as dest:
            shutil.copyfileobj(source, dest)
        from_to[name] = f"assets/{name}"

    ArticleAssets(optimised_root).replace_names(from_to)
    return optimised_root


def _write_bytes(assets_dir: str, filename: str, content: bytes) -> None:
    with open(os.path.join(assets_dir, filename), "wb") as fp:
        fp.write(content)