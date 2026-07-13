from __future__ import annotations

import zipfile
from pathlib import PurePosixPath
from typing import Iterator

from spsvalidator.domain.metadata import extract_article_snapshot


def parse_zip_packages(zip_path: str) -> list[tuple[object, set[str]]]:
    """Le o .zip via XMLWithPre.create() e devolve, para cada XML do pacote,
    o par (xml_with_pre, files_in_zip) com o nome dos arquivos do zip ja
    normalizado para nome-base (xml_with_pre.files traz o caminho completo
    dentro do zip, incluindo a subpasta que todo pacote SPS real tem)."""
    from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre

    packages = []
    for xml_with_pre in XMLWithPre.create(path=zip_path):
        files_in_zip = {
            PurePosixPath(f).name for f in (xml_with_pre.files or [])
        }
        packages.append((xml_with_pre, files_in_zip))
    return packages


def iter_zip_article_snapshots(zip_path: str) -> Iterator[dict]:
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            suffix = PurePosixPath(member.filename).suffix.lower()
            if suffix != ".xml":
                continue
            yield extract_article_snapshot(archive.read(member), member.filename)