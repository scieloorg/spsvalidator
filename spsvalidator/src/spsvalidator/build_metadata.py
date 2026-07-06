from __future__ import annotations

import platform
import sys
from pathlib import Path


def _linux_distro_name() -> str:
    os_release = Path("/etc/os-release")
    if not os_release.is_file():
        return "Linux"

    values: dict[str, str] = {}
    for line in os_release.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key] = value.strip().strip('"')

    return values.get("PRETTY_NAME") or values.get("NAME") or "Linux"


def _runtime_platform_label() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macOS"
    if system == "Windows":
        return "Windows"
    if system == "Linux":
        return "Linux"
    return system


def _runtime_version_label() -> str:
    system = platform.system()
    if system == "Darwin":
        mac_version = platform.mac_ver()[0]
        build_number = platform.mac_ver()[2]
        if build_number:
            return f"{mac_version} ({build_number})"
        return mac_version or "unknown"

    if system == "Windows":
        version, _, build, _ = platform.win32_ver()
        label = version or platform.release()
        if build:
            return f"{label} (build {build})"
        return label or "unknown"

    if system == "Linux":
        return f"{_linux_distro_name()} (kernel {platform.release()})"

    return platform.platform()


def get_footer_build_label(language: str, translations: dict[str, str]) -> str:
    platform_label = _runtime_platform_label()
    if getattr(sys, "frozen", False):
        return translations["footer_built_for"].format(
            platform=platform_label,
            version=_runtime_version_label(),
        )
    return translations["footer_dev_build"].format(platform=platform_label)
