from spsvalidator.db.repository import (
    count_articles,
    init_db,
    insert_validation_result,
    list_articles,
)


def _insert(db_path, package_name, articles):
    return insert_validation_result(
        db_path,
        package_name=package_name,
        package_sha256=f"sha-{package_name}",
        rows=[],
        exceptions=[],
        articles=articles,
        status="valid",
    )


def _seed(db_path):
    history_a = _insert(
        db_path,
        "1676-0611-bn-rpass-11-26-1",
        [
            {
                "xml_path": "art01.xml",
                "title": "Artigo A",
                "authors_text": "Autor A",
                "doi": "10.1590/aaa",
                "pid": "S1676-06112026000100001",
                "article_status": "ok",
                "issue_count": 0,
            }
        ],
    )
    history_b = _insert(
        db_path,
        "1234-5678-ean-outro-pacote",
        [
            {
                "xml_path": "art02.xml",
                "title": "Artigo B",
                "authors_text": "Autor B",
                "doi": "10.1590/bbb",
                "pid": "S1234-56782026000200002",
                "article_status": "issue",
                "issue_count": 3,
            }
        ],
    )
    return history_a, history_b


def test_list_articles_joins_package_name_and_validated_at(tmp_path):
    db_path = str(tmp_path / "test.sqlite3")
    init_db(db_path)
    _seed(db_path)

    articles = list_articles(db_path)

    assert len(articles) == 2
    assert {a["package_name"] for a in articles} == {
        "1676-0611-bn-rpass-11-26-1",
        "1234-5678-ean-outro-pacote",
    }
    assert all(a["validated_at"] for a in articles)


def test_list_articles_filters_by_history_id(tmp_path):
    db_path = str(tmp_path / "test.sqlite3")
    init_db(db_path)
    history_a, history_b = _seed(db_path)

    articles = list_articles(db_path, history_id=history_a)

    assert len(articles) == 1
    assert articles[0]["doi"] == "10.1590/aaa"


def test_list_articles_filters_by_package_name(tmp_path):
    db_path = str(tmp_path / "test.sqlite3")
    init_db(db_path)
    _seed(db_path)

    articles = list_articles(db_path, name_query="ean")

    assert len(articles) == 1
    assert articles[0]["package_name"] == "1234-5678-ean-outro-pacote"


def test_list_articles_filters_by_doi_pid_and_status(tmp_path):
    db_path = str(tmp_path / "test.sqlite3")
    init_db(db_path)
    _seed(db_path)

    assert len(list_articles(db_path, doi_query="bbb")) == 1
    assert len(list_articles(db_path, pid_query="S1676")) == 1
    assert len(list_articles(db_path, status="issue")) == 1
    assert len(list_articles(db_path, status="ok")) == 1


def test_list_articles_respects_limit_and_offset(tmp_path):
    db_path = str(tmp_path / "test.sqlite3")
    init_db(db_path)
    _seed(db_path)

    first_page = list_articles(db_path, limit=1, offset=0)
    second_page = list_articles(db_path, limit=1, offset=1)

    assert len(first_page) == 1
    assert len(second_page) == 1
    assert first_page[0]["id"] != second_page[0]["id"]


def test_count_articles_matches_filters(tmp_path):
    db_path = str(tmp_path / "test.sqlite3")
    init_db(db_path)
    _seed(db_path)

    assert count_articles(db_path) == 2
    assert count_articles(db_path, status="issue") == 1
    assert count_articles(db_path, name_query="nao-existe") == 0