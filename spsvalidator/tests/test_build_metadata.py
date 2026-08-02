from spsvalidator import build_info, build_metadata


def test_footer_shows_macos_label_when_built_and_running_on_macos(monkeypatch):
    monkeypatch.setattr(build_metadata, "is_running_from_source", lambda: False)
    monkeypatch.setattr(build_info, "BUILD_PLATFORM", "macOS")
    monkeypatch.setattr(build_info, "BUILD_MACOS_VERSION", "15.0 (24A335)")
    monkeypatch.setattr(build_metadata.platform, "system", lambda: "Darwin")

    assert "macOS" in build_metadata.get_footer_build_label()


def test_footer_ignores_stale_macos_build_info_on_other_platforms(monkeypatch):
    """build_info.py desatualizado (ex.: gerado num build macOS anterior e
    reaproveitado sem regenerar) nao deve fazer o rodape mentir sobre a
    plataforma real de execucao."""
    monkeypatch.setattr(build_metadata, "is_running_from_source", lambda: False)
    monkeypatch.setattr(build_info, "BUILD_PLATFORM", "macOS")
    monkeypatch.setattr(build_info, "BUILD_MACOS_VERSION", "15.0 (24A335)")
    monkeypatch.setattr(build_metadata.platform, "system", lambda: "Windows")

    assert "macOS" not in build_metadata.get_footer_build_label()


def test_footer_shows_dev_label_when_running_from_source(monkeypatch):
    monkeypatch.setattr(build_metadata, "is_running_from_source", lambda: True)
    monkeypatch.setattr(build_metadata.platform, "system", lambda: "Windows")

    label = build_metadata.get_footer_build_label()

    assert "macOS" not in label
    assert "Windows" in label