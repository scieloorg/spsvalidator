# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

project_root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
main_script = os.path.join(project_root, "src", "spsvalidator", "main.py")
src_path = os.path.join(project_root, "src")
icon_path = os.path.join(
    project_root, "src", "spsvalidator", "web", "static", "img", "icon.png"
)

datas = []
binaries = []
hiddenimports = [
    "pkg_resources",
    "requests",
    "tenacity",
    "langdetect",
    "gi",
    "gi.repository",
    "gi.repository.Gtk",
    "gi.repository.WebKit2",
    "webview.platforms.gtk",
    "webview.platforms.qt",
]
datas += collect_data_files("packtools")
datas += collect_data_files("spsvalidator")
datas += copy_metadata("setuptools")
tmp_ret = collect_all("webview")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    [main_script],
    pathex=[src_path],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        "gi": {
            "icons": ["hicolor"],
            "themes": [],
        }
    },
    runtime_hooks=[],
    excludes=[
        "webview.platforms.android",
        "webview.platforms.cocoa",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "black",
        "pytest",
        "isort",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="spsvalidator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[icon_path],
)
