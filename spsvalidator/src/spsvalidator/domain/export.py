from __future__ import annotations

import csv
import io

VALIDATION_CSV_COLUMNS = [
    "package",
    "status",
    "subject",
    "message",
    "advise",
]

DEFAULT_CSV_HEADERS = {column: column for column in VALIDATION_CSV_COLUMNS}


def build_validation_csv(rows: list[dict], headers: dict[str, str] | None = None) -> str:
    column_headers = {**DEFAULT_CSV_HEADERS, **(headers or {})}
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=VALIDATION_CSV_COLUMNS,
        extrasaction="ignore",
    )
    writer.writerow(column_headers)
    writer.writerows(rows)
    return buffer.getvalue()
