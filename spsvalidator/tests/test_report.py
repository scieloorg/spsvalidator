from spsvalidator.domain.report import build_grouped_report


def _row(status, subject, message="msg", advise="advise", data=None):
    return {
        "package": "p",
        "status": status,
        "subject": subject,
        "message": message,
        "advise": advise,
        "data": data or {},
    }


def test_build_grouped_report_orders_severities_critical_first():
    rows = [
        _row("WARNING", "b"),
        _row("CRITICAL", "a"),
        _row("ERROR", "a"),
    ]
    report = build_grouped_report(rows)
    assert [group["severity"] for group in report] == ["CRITICAL", "ERROR", "WARNING"]


def test_build_grouped_report_orders_categories_alphabetically():
    rows = [
        _row("CRITICAL", "history"),
        _row("CRITICAL", "contrib-group"),
        _row("CRITICAL", "abstract"),
    ]
    report = build_grouped_report(rows)
    category_names = [category["name"] for category in report[0]["categories"]]
    assert category_names == ["abstract", "contrib-group", "history"]


def test_build_grouped_report_counts_occurrences():
    rows = [
        _row("CRITICAL", "history", message="m1"),
        _row("CRITICAL", "history", message="m2"),
        _row("ERROR", "history", message="m1"),
    ]
    report = build_grouped_report(rows)
    critical_group = next(g for g in report if g["severity"] == "CRITICAL")
    assert critical_group["count"] == 2
    assert critical_group["categories"][0]["count"] == 2


def test_build_grouped_report_groups_repeated_messages_within_category():
    rows = [
        _row("CRITICAL", "contrib", message="missing CRediT role", advise="fix author 1"),
        _row("CRITICAL", "contrib", message="missing CRediT role", advise="fix author 2"),
        _row("CRITICAL", "contrib", message="missing CRediT role", advise="fix author 3"),
        _row("CRITICAL", "contrib", message="duplicate role", advise="fix author 4"),
    ]
    report = build_grouped_report(rows)
    problems = report[0]["categories"][0]["problems"]
    assert len(problems) == 2
    assert problems[0]["message"] == "missing CRediT role"
    assert problems[0]["count"] == 3
    assert [o["advise"] for o in problems[0]["occurrences"]] == [
        "fix author 1",
        "fix author 2",
        "fix author 3",
    ]
    assert problems[1]["message"] == "duplicate role"
    assert problems[1]["count"] == 1


def test_build_grouped_report_orders_problems_by_frequency_then_message():
    rows = [
        _row("CRITICAL", "history", message="rare issue"),
        _row("CRITICAL", "history", message="common issue"),
        _row("CRITICAL", "history", message="common issue"),
    ]
    report = build_grouped_report(rows)
    problem_messages = [p["message"] for p in report[0]["categories"][0]["problems"]]
    assert problem_messages == ["common issue", "rare issue"]


def test_build_grouped_report_selects_technical_detail_fields_only():
    data = {
        "item": "history",
        "sub_item": "date[@date-type='rev-request']",
        "validation_type": "exist",
        "expected_value": "present",
        "got_value": "missing",
        "msg_text": "should not appear",
        "parent": "article",
    }
    rows = [_row("CRITICAL", "history", data=data)]
    report = build_grouped_report(rows)
    details = report[0]["categories"][0]["problems"][0]["occurrences"][0]["details"]
    assert details == {
        "item": "history",
        "sub_item": "date[@date-type='rev-request']",
        "validation_type": "exist",
        "expected_value": "present",
        "got_value": "missing",
    }


def test_build_grouped_report_omits_empty_detail_fields():
    data = {"item": "history", "sub_item": None, "expected_value": ""}
    rows = [_row("CRITICAL", "history", data=data)]
    report = build_grouped_report(rows)
    details = report[0]["categories"][0]["problems"][0]["occurrences"][0]["details"]
    assert details == {"item": "history"}


def test_build_grouped_report_handles_empty_rows():
    assert build_grouped_report([]) == []


def test_build_grouped_report_assigns_stable_unique_keys():
    rows = [
        _row("CRITICAL", "contrib", message="missing CRediT role", advise="fix author 1"),
        _row("CRITICAL", "contrib", message="missing CRediT role", advise="fix author 2"),
        _row("ERROR", "history", message="missing date"),
    ]
    first_run = build_grouped_report(rows)
    second_run = build_grouped_report(rows)

    def all_keys(report):
        return [
            occurrence["key"]
            for group in report
            for category in group["categories"]
            for problem in category["problems"]
            for occurrence in problem["occurrences"]
        ]

    keys_first = all_keys(first_run)
    keys_second = all_keys(second_run)
    assert len(keys_first) == len(set(keys_first)) == 3
    assert keys_first == keys_second