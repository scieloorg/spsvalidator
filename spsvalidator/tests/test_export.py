import csv
import io

from spsvalidator.domain.export import build_validation_csv


def test_build_validation_csv_uses_default_headers():
    rows = [
        {
            "package": "10.1590-example",
            "status": "ERROR",
            "subject": "history",
            "message": "Got missing, expected present",
            "advise": "Add <date> to <history>",
            "data": {"got_value": "missing"},
        }
    ]
    content = build_validation_csv(rows)
    parsed = list(csv.DictReader(io.StringIO(content)))
    assert len(parsed) == 1
    assert parsed[0]["package"] == "10.1590-example"
    assert parsed[0]["status"] == "ERROR"
    assert parsed[0]["message"] == "Got missing, expected present"
    assert parsed[0]["advise"] == "Add <date> to <history>"
    assert "data" not in parsed[0]


def test_build_validation_csv_accepts_custom_headers():
    rows = [
        {
            "package": "p",
            "status": "ERROR",
            "subject": "history",
            "message": "m",
            "advise": "a",
        }
    ]
    content = build_validation_csv(
        rows,
        headers={"message": "Problema", "advise": "Ação de correção"},
    )
    header_line = content.splitlines()[0]
    assert "Problema" in header_line
    assert "Ação de correção" in header_line
