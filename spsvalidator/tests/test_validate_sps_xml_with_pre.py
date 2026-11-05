from __future__ import annotations

import zipfile
from textwrap import dedent

import pytest

from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre

from spsvalidator.domain.validation import validate_sps_xml_with_pre, validate_sps_zip


def _article_xml(*, graphic_href: str | None = None) -> str:
    graphic = (
        f'<fig id="f01"><graphic xlink:href="{graphic_href}"/></fig>'
        if graphic_href
        else ""
    )
    return dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <article xmlns:xlink="http://www.w3.org/1999/xlink"
                 article-type="research-article" xml:lang="pt" dtd-version="1.1">
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
        <article-id pub-id-type="publisher-id">S1234-56782023000100001</article-id>
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
        <body><sec><title>Introduction</title><p>Text.</p>{graphic}</sec></body>
        <back></back>
        </article>
        """)


def _make_zip(tmp_path, xml_content: str, extra_files: dict[str, bytes] | None = None) -> str:
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("package/article.xml", xml_content)
        for name, content in (extra_files or {}).items():
            zf.writestr(f"package/{name}", content)
    return str(zip_path)


def test_validate_sps_xml_with_pre_flags_missing_asset(tmp_path):
    zip_path = _make_zip(tmp_path, _article_xml(graphic_href="fig1.jpg"))

    xml_with_pre = next(XMLWithPre.create(path=zip_path))
    result = validate_sps_xml_with_pre(xml_with_pre)

    critical_rows = [r for r in result["rows"] if r["status"] == "CRITICAL"]
    assert any(
        r["subject"] == "Assets" and "fig1.jpg" in r["message"]
        for r in critical_rows
    )
    assert result["article"]["title"] == "Test Article Title"


def test_validate_sps_xml_with_pre_does_not_flag_present_asset(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        _article_xml(graphic_href="fig1.jpg"),
        extra_files={"fig1.jpg": b"fake-bytes"},
    )

    xml_with_pre = next(XMLWithPre.create(path=zip_path))
    result = validate_sps_xml_with_pre(xml_with_pre)

    critical_rows = [r for r in result["rows"] if r["status"] == "CRITICAL"]
    assert not any(
        r["subject"] == "Assets" and "fig1.jpg" in r["message"]
        for r in critical_rows
    )


def test_validate_sps_zip_matches_validate_sps_xml_with_pre(tmp_path):
    zip_path = _make_zip(tmp_path, _article_xml())

    xml_with_pre = next(XMLWithPre.create(path=zip_path))
    single = validate_sps_xml_with_pre(xml_with_pre)
    aggregate = validate_sps_zip(zip_path)

    assert aggregate["rows"] == single["rows"]
    assert aggregate["exceptions"] == single["exceptions"]
    assert aggregate["articles"] == [single["article"]]


@pytest.mark.parametrize("xml_name", ["article.xml", "package/article.xml", "package/0034-8910-rsp-1-e001.xml"])
def test_validate_sps_xml_with_pre_counts_every_row_as_article_issue(tmp_path, xml_name):
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(xml_name, _article_xml(graphic_href="fig1.jpg"))

    xml_with_pre = next(XMLWithPre.create(path=str(zip_path)))
    result = validate_sps_xml_with_pre(xml_with_pre)

    assert result["rows"]
    assert result["article"]["issue_count"] == len(result["rows"])
    assert result["article"]["article_status"] == "issue"


@pytest.mark.parametrize("extra_files", [{}, {"readme.txt": b"x"}])
def test_validate_sps_xml_with_pre_flags_missing_pdf_regardless_of_other_files(tmp_path, extra_files):
    zip_path = _make_zip(tmp_path, _article_xml(), extra_files=extra_files)

    xml_with_pre = next(XMLWithPre.create(path=zip_path))
    result = validate_sps_xml_with_pre(xml_with_pre)

    rendition_rows = [r for r in result["rows"] if r["subject"] == "Renditions"]
    assert [r["data"]["name"] for r in rendition_rows] == ["article.pdf"]


def test_validate_sps_xml_with_pre_does_not_flag_present_pdf(tmp_path):
    zip_path = _make_zip(tmp_path, _article_xml(), extra_files={"article.pdf": b"%PDF"})

    xml_with_pre = next(XMLWithPre.create(path=zip_path))
    result = validate_sps_xml_with_pre(xml_with_pre)

    assert not any(r["subject"] == "Renditions" for r in result["rows"])
