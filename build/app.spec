# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec. Run from the repository root:

    pyinstaller build/app.spec

Windows: two executables are produced from one analysis:
  dist/clear-pdf-properties.exe      windowed (GUI; double-click friendly)
  dist/clear-pdf-properties-cli.exe  console  (CLI output visible)
macOS / Linux: a single console executable that also opens the GUI when
run without arguments.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is injected by PyInstaller
SRC = ROOT / "src"

hiddenimports = collect_submodules("pikepdf") + ["tkinter", "tkinter.ttk"]
datas = collect_data_files("pikepdf")

a = Analysis(  # noqa: F821
    [str(ROOT / "build" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

common = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    disable_windowed_traceback=False,
    argv_emulation=sys.platform == "darwin",
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "win32":
    exe_gui = EXE(  # noqa: F821
        pyz, a.scripts, a.binaries, a.datas, [],
        name="clear-pdf-properties", console=False, **common,
    )
    exe_cli = EXE(  # noqa: F821
        pyz, a.scripts, a.binaries, a.datas, [],
        name="clear-pdf-properties-cli", console=True, **common,
    )
else:
    exe = EXE(  # noqa: F821
        pyz, a.scripts, a.binaries, a.datas, [],
        name="clear-pdf-properties", console=True, **common,
    )
