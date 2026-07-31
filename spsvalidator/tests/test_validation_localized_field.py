from __future__ import annotations

from spsvalidator.domain.validation import _localized_field


def test_localized_field_formats_template_with_params():
    result = {
        "message": "Got None, expected article title in pt",
        "msg_text": "Got {obtained}, expected {expected}",
        "msg_params": {"obtained": "None", "expected": "article title in pt"},
    }

    assert (
        _localized_field(result, "msg_text", "msg_params", "message")
        == "Got None, expected article title in pt"
    )


def test_localized_field_falls_back_to_legacy_when_template_missing():
    result = {"advice": "Mark article title for pt language", "adv_text": None, "adv_params": None}

    assert (
        _localized_field(result, "adv_text", "adv_params", "advice")
        == "Mark article title for pt language"
    )


def test_localized_field_falls_back_to_legacy_when_params_do_not_match_template():
    result = {
        "advice": "Mark article title for pt language",
        "adv_text": "Mark {element} for {language} language",
        "adv_params": {"element": "article title"},
    }

    assert (
        _localized_field(result, "adv_text", "adv_params", "advice")
        == "Mark article title for pt language"
    )


def test_localized_field_falls_back_when_legacy_key_and_template_are_absent():
    result = {}

    assert _localized_field(result, "adv_text", "adv_params", "advice") is None
