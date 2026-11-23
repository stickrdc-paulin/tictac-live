# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH)
UI = ROOT / "ui"

a = Analysis(
    ["studio_regie.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(UI / "index.html"), "ui"),
        (str(UI / "styles.css"), "ui"),
        (str(UI / "app.js"), "ui"),
        (str(UI / "radio.js"), "ui"),
        (str(UI / "tt-direct.js"), "ui"),
    ],
    hiddenimports=[
        "auth_session",
        "local_server",
        "radio_store",
        "radio_engine",
        "browser_cookie3",
        "requests",
        "webview",
        "clr",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="TICTAC-Studio-Regie",
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
)
