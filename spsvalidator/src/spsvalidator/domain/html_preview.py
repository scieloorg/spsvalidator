from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import PurePosixPath

from lxml import etree
from packtools.domain import HTMLGenerator
from packtools.sps.models.article_assets import ArticleAssets
from packtools.utils import SPPackage


def generate_html_previews(
    xml_with_pre, html_dir: str, html_asset_urls: dict | None = None
) -> list[str]:
    """Gera uma prévia HTML por idioma disponível para o artigo de ``xml_with_pre``.

    ``html_asset_urls`` são as URLs do CSS/JS do design system do packtools
    (repassadas como kwargs pro HTMLGenerator, ex.: css/print_css/js) — nunca
    URLs de imagem: as imagens do artigo ficam em caminho relativo
    ``assets/...``, resolvido a partir da própria página de prévia.

    Imagens tif/sem-extensão são otimizadas via packtools.utils.SPPackage
    (mesma classe usada pela pipeline real de publicação do SciELO), que gera
    as variantes .png (ampliação) e .thumbnail.jpg (miniatura) a partir do
    conteúdo real da imagem, e grava os arquivos otimizados direto em
    ``assets_dir``.
    """
    package = PurePosixPath(xml_with_pre.filename).stem
    article_dir = os.path.join(html_dir, package)
    assets_dir = os.path.join(article_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as work_dir:
        flat_zip_path = os.path.join(work_dir, "flat.zip")
        _flatten_zip(xml_with_pre.zip_file_path, flat_zip_path)
        optimised_root = _optimise_package(flat_zip_path, work_dir, assets_dir)

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


def _flatten_zip(source_zip_path: str, dest_zip_path: str) -> None:
    """Copia ``source_zip_path`` para ``dest_zip_path`` sem subpasta interna.

    A especificação de pacote de entrega não exige nenhuma estrutura de
    subpasta, e pacotes reais aparecem das duas formas (com e sem). O
    packtools.utils.SPPackage monta a lista de imagens a otimizar direto do
    namelist do zip de entrada: se houver subpasta, o xlink:href (sempre
    nome-base) nunca bate com esse caminho completo, e a otimização falha
    silenciosamente. Achatar antes elimina essa causa.
    """
    with zipfile.ZipFile(source_zip_path) as source, zipfile.ZipFile(
        dest_zip_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as dest:
        for name in source.namelist():
            if name.endswith("/"):
                continue
            dest.writestr(os.path.basename(name), source.read(name))


def _optimise_package(flat_zip_path: str, work_dir: str, assets_dir: str):
    optimised_zip_path = os.path.join(work_dir, "optimised.zip")
    package = SPPackage.from_file(
        flat_zip_path, extracted_package=assets_dir, stop_if_error=False
    )
    package.optimise(new_package_file_path=optimised_zip_path, preserve_files=True)

    with zipfile.ZipFile(optimised_zip_path) as optimised_zip:
        names = optimised_zip.namelist()
        from_to = {}
        xml_name = None
        for name in names:
            if name.endswith(".xml"):
                xml_name = name
            from_to[name] = f"assets/{name}"
        optimised_root = etree.fromstring(optimised_zip.read(xml_name))

    ArticleAssets(optimised_root).replace_names(from_to)
    return optimised_root
