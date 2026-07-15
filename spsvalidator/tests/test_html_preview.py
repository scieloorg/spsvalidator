from __future__ import annotations

import io
import zipfile
from textwrap import dedent

from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
from PIL import Image

from spsvalidator.domain.html_preview import generate_html_previews


def _tif_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), color="red").save(buffer, "TIFF")
    return buffer.getvalue()


def _article_xml_with_figure() -> str:
    return dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <article xmlns:xlink="http://www.w3.org/1999/xlink"
                 article-type="research-article" xml:lang="en" dtd-version="1.1">
        <front>
        <journal-meta>
        <journal-id journal-id-type="nlm-ta">Rev Test</journal-id>
        <journal-title-group><journal-title>Revista de Teste</journal-title>
        <abbrev-journal-title abbrev-type="publisher">Rev. Teste</abbrev-journal-title>
        </journal-title-group>
        <issn pub-type="epub">1234-5678</issn>
        <publisher><publisher-name>Publisher</publisher-name></publisher>
        </journal-meta>
        <article-meta>
        <article-id pub-id-type="doi">10.1234/test.2023.001</article-id>
        <title-group><article-title>Test Article Title</article-title></title-group>
        <contrib-group><contrib contrib-type="author">
        <name><surname>Silva</surname><given-names>João</given-names></name>
        </contrib></contrib-group>
        <pub-date publication-format="electronic" date-type="pub">
        <year>2023</year><month>01</month><day>01</day></pub-date>
        <volume>1</volume>
        <elocation-id>e001</elocation-id>
        </article-meta>
        </front>
        <body>
        <sec><title>Introduction</title><p>Text.</p>
        <fig id="f01"><label>Fig. 1</label><caption><title>t</title></caption>
        <graphic xlink:href="article-gf1.tif"/></fig>
        </sec>
        </body>
        <back></back>
        </article>
        """)


def _make_zip(tmp_path) -> str:
    zip_path = tmp_path / "package.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("package/article.xml", _article_xml_with_figure())
        zf.writestr("package/article-gf1.tif", _tif_bytes())
    return str(zip_path)


def test_generate_html_previews_optimises_and_extracts_assets(tmp_path):
    zip_path = _make_zip(tmp_path)
    html_dir = tmp_path / "html_previews"

    xml_with_pre = next(XMLWithPre.create(path=zip_path))
    langs = generate_html_previews(xml_with_pre, str(html_dir))

    assert langs == ["en"]
    article_dir = html_dir / "article"
    html_path = article_dir / "en.html"
    assert html_path.is_file()

    assets_dir = article_dir / "assets"
    asset_names = {p.name for p in assets_dir.iterdir()}
    assert "article-gf1.tif" in asset_names
    assert "article-gf1.png" in asset_names
    assert "article-gf1.thumbnail.jpg" in asset_names

    html_text = html_path.read_text(encoding="utf-8")
    assert "assets/article-gf1.tif" in html_text
    assert "assets/article-gf1.png" in html_text
    assert "assets/article-gf1.thumbnail.jpg" in html_text


def test_generate_html_previews_does_not_mutate_validation_tree(tmp_path):
    zip_path = _make_zip(tmp_path)
    html_dir = tmp_path / "html_previews"

    xml_with_pre = next(XMLWithPre.create(path=zip_path))
    href_before = xml_with_pre.xmltree.xpath(
        "//graphic/@xlink:href",
        namespaces={"xlink": "http://www.w3.org/1999/xlink"},
    )[0]

    generate_html_previews(xml_with_pre, str(html_dir))

    href_after = xml_with_pre.xmltree.xpath(
        "//graphic/@xlink:href",
        namespaces={"xlink": "http://www.w3.org/1999/xlink"},
    )[0]
    assert href_before == href_after == "article-gf1.tif"
