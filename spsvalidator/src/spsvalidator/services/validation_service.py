from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from spsvalidator.db.repository import insert_validation_result
from spsvalidator.domain.html_preview import generate_html_previews
from spsvalidator.domain.validation import validate_sps_xml_with_pre


def _sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_pointer:
        for chunk in iter(lambda: file_pointer.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compute_status(rows: list[dict], exceptions: list[dict]) -> str:
    if rows:
        return "invalid"
    if exceptions:
        return "error"
    return "valid"


def run_validation(
    db_path: str,
    uploaded_file,
    zip_only_message: str | None = None,
    html_base_dir: str | None = None,
    html_asset_urls: dict | None = None,
) -> dict:
    from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre

    filename = uploaded_file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise ValueError(zip_only_message or "Only SPS .zip files are supported.")
    with tempfile.TemporaryDirectory(prefix="spsvalidator-") as temp_dir:
        zip_path = os.path.join(temp_dir, Path(filename).name)
        uploaded_file.save(zip_path)
        package_sha256 = _sha256_of_file(zip_path)
        html_dir = (
            os.path.join(html_base_dir, package_sha256) if html_base_dir else None
        )

        rows = []
        exceptions = []
        articles = []
        # Um único parse do zip (XMLWithPre.create), compartilhado entre a
        # validação e a geração da prévia HTML de cada artigo.
        for xml_with_pre in XMLWithPre.create(path=zip_path):
            result = validate_sps_xml_with_pre(xml_with_pre)
            rows.extend(result["rows"])
            exceptions.extend(result["exceptions"])
            articles.append(result["article"])
            if html_dir:
                generate_html_previews(xml_with_pre, html_dir, html_asset_urls)

        status = _compute_status(rows, exceptions)
        history_id = insert_validation_result(
            db_path=db_path,
            package_name=Path(filename).name,
            package_sha256=package_sha256,
            rows=rows,
            exceptions=exceptions,
            articles=articles,
            status=status,
        )
    return {
        "history_id": history_id,
        "status": status,
        "rows": rows,
        "exceptions": exceptions,
        "articles": articles,
        "issues_count": len(rows),
        "exceptions_count": len(exceptions),
        "xml_count": len(articles),
    }
