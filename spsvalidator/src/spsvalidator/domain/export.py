from __future__ import annotations

import csv
import io

VALIDATION_CSV_COLUMNS = [
    "package",
    "status",
    "subject",
    "message",
    "data",
]


def build_validation_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=VALIDATION_CSV_COLUMNS,
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
