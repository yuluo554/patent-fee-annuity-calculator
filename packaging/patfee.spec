# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec（M5）：onedir 双 exe —— GUI(console=False) + CLI(console=True)。

datas 由 patfee.packaging.build_datas() 单一事实源产生（plan/04 §十一）：
data/rules + data/truth + data/knowledge/clauses.json；raw 原文快照不入包。
构建：pyinstaller --clean -y packaging/patfee.spec （PyInstaller >= 6）
"""

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from patfee.packaging import build_datas  # noqa: E402

datas = build_datas()
hiddenimports = [
    "patfee.gui",
    "patfee.gui.main_window",
    "patfee.report",
    "patfee.report.markdown_render",
    "patfee.report.xlsx_render",
    "patfee.packaging",
]

gui = Analysis(
    [str(ROOT / "packaging" / "run_patfee.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports + ["PySide6"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz_gui = PYZ(gui.pure)

exe_gui = EXE(
    pyz_gui,
    gui.scripts,
    [],
    name="patfee-gui",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    exclude_binaries=True,
)
coll_gui = COLLECT(
    exe_gui,
    gui.binaries,
    gui.zipfiles,
    gui.datas,
    strip=False,
    upx=False,
    name="patfee-gui",
)

cli = Analysis(
    [str(ROOT / "packaging" / "run_patfee.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6", "openpyxl"],
    noarchive=False,
)
pyz_cli = PYZ(cli.pure)

exe_cli = EXE(
    pyz_cli,
    cli.scripts,
    [],
    name="patfee-cli",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    exclude_binaries=True,
)
coll_cli = COLLECT(
    exe_cli,
    cli.binaries,
    cli.zipfiles,
    cli.datas,
    strip=False,
    upx=False,
    name="patfee-cli",
)
