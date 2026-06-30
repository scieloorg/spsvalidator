from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime


def _json_safe(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS package_validation_history (
                id TEXT PRIMARY KEY,
                validated_at TEXT NOT NULL,
                package_name TEXT NOT NULL,
                package_sha256 TEXT NOT NULL,
                xml_count INTEGER NOT NULL,
                issues_count INTEGER NOT NULL,
                exceptions_count INTEGER NOT NULL,
                status TEXT NOT NULL,
                report_json TEXT NOT NULL,
                exceptions_json TEXT NOT NULL,
                critical_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                warning_count INTEGER NOT NULL DEFAULT 0
            )
            """)
        for col in ("critical_count", "error_count", "warning_count"):
            try:
                connection.execute(
                    f"ALTER TABLE package_validation_history ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass
        connection.execute("""
            CREATE TABLE IF NOT EXISTS package_article_snapshot (
                id TEXT PRIMARY KEY,
                history_id TEXT NOT NULL,
                xml_path TEXT NOT NULL,
                title TEXT NOT NULL,
                authors_text TEXT NOT NULL,
                doi TEXT NOT NULL,
                pid TEXT NOT NULL,
                article_status TEXT NOT NULL,
                issue_count INTEGER NOT NULL,
                FOREIGN KEY(history_id) REFERENCES package_validation_history(id)
            )
            """)
        connection.commit()


def insert_validation_result(
    db_path: str,
    package_name: str,
    package_sha256: str,
    rows: list[dict],
    exceptions: list[dict],
    articles: list[dict],
    status: str,
) -> str:
    history_id = str(uuid.uuid4())
    validated_at = datetime.now(UTC).isoformat()
    status_counts = {"CRITICAL": 0, "ERROR": 0, "WARNING": 0}
    for row in rows:
        s = row.get("status", "")
        if s in status_counts:
            status_counts[s] += 1
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO package_validation_history (
                id, validated_at, package_name, package_sha256, xml_count,
                issues_count, exceptions_count, status, report_json, exceptions_json,
                critical_count, error_count, warning_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id,
                validated_at,
                package_name,
                package_sha256,
                len(articles),
                len(rows),
                len(exceptions),
                status,
                json.dumps(rows, ensure_ascii=False),
                json.dumps(exceptions, ensure_ascii=False),
                status_counts["CRITICAL"],
                status_counts["ERROR"],
                status_counts["WARNING"],
            ),
        )
        for article in articles:
            connection.execute(
                """
                INSERT INTO package_article_snapshot (
                    id, history_id, xml_path, title, authors_text, doi, pid,
                    article_status, issue_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    history_id,
                    article.get("xml_path", ""),
                    article.get("title", ""),
                    article.get("authors_text", ""),
                    article.get("doi", ""),
                    article.get("pid", ""),
                    article.get("article_status", "ok"),
                    int(article.get("issue_count", 0)),
                ),
            )
        connection.commit()
    return history_id


def list_validations(db_path: str) -> list[dict]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""
            SELECT id, validated_at, package_name, xml_count, issues_count,
                   exceptions_count, critical_count, error_count, warning_count
            FROM package_validation_history
            ORDER BY datetime(validated_at) DESC
            """).fetchall()
    return [dict(row) for row in rows]


def get_validation_details(db_path: str, history_id: str) -> dict | None:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        history = connection.execute(
            "SELECT * FROM package_validation_history WHERE id = ?",
            (history_id,),
        ).fetchone()
        if history is None:
            return None
        articles = connection.execute(
            """
            SELECT xml_path, title, authors_text, doi, pid, article_status, issue_count
            FROM package_article_snapshot
            WHERE history_id = ?
            ORDER BY xml_path
            """,
            (history_id,),
        ).fetchall()
    history_dict = dict(history)
    history_dict["rows"] = json.loads(history_dict["report_json"])
    history_dict["exceptions"] = json.loads(history_dict["exceptions_json"])
    history_dict["articles"] = [dict(row) for row in articles]
    return history_dict
