"""数据目录与规则包定位（源码态 / 冻结态分支）。

优先级（改动属"动了会打挂测试"的口径变更，测试锁死）：

    1. 显式参数 / ``PATFEE_DATA_DIR`` 环境变量
    2. 冻结态：``sys._MEIPASS/data``（PyInstaller 6 onedir 下即 ``_internal/data``）
       兼容 PyInstaller 5 平铺布局 ``<exe目录>/data``
    3. 源码态：``<仓库根>/data``
    4. CWD 上溯查找 ``data/rules/manifest.json``

冻结态自检必须再断言"数据目录落在 exe 目录内"（见 :func:`data_dir_within_exe`）——
打包最常见的失效模式是"数据没随包走、exe 回头读了开发机仓库"，本地看着能跑、换台机器就废。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

ENV_DATA_DIR = "PATFEE_DATA_DIR"
MANIFEST_REL = os.path.join("rules", "manifest.json")


def _candidate_roots() -> List[Path]:
    """按优先级返回候选 data 目录。"""
    roots: List[Path] = []

    explicit = os.environ.get(ENV_DATA_DIR)
    if explicit:
        roots.append(Path(explicit))

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "data")
        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir / "data")              # PyInstaller 5 平铺
        roots.append(exe_dir / "_internal" / "data")  # PyInstaller 6 onedir

    here = Path(__file__).resolve()
    # src/patfee/data_paths.py -> src/patfee -> src -> <仓库根>
    roots.append(here.parent.parent.parent / "data")

    cwd = Path.cwd().resolve()
    for base in (cwd, *cwd.parents):
        roots.append(base / "data")

    return roots


def find_data_dir(explicit: Optional[str] = None) -> Path:
    """返回第一个含 ``rules/manifest.json`` 的候选目录；找不到则抛 FileNotFoundError。"""
    if explicit:
        p = Path(explicit)
        if (p / MANIFEST_REL).is_file():
            return p
        raise FileNotFoundError("data 目录缺少 %s: %s" % (MANIFEST_REL, p))

    tried: List[str] = []
    for root in _candidate_roots():
        tried.append(str(root))
        if (root / MANIFEST_REL).is_file():
            return root
    raise FileNotFoundError(
        "未找到含 %s 的数据目录；已尝试:\n  %s" % (MANIFEST_REL, "\n  ".join(tried))
    )


def data_dir_within_exe(data_dir: Path) -> Optional[bool]:
    """冻结态：数据目录是否落在 exe 目录内。非冻结态返回 None（不报 FAIL）。"""
    if not getattr(sys, "frozen", False):
        return None
    exe_dir = Path(sys.executable).resolve().parent
    try:
        return os.path.commonpath([str(exe_dir), str(Path(data_dir).resolve())]) == str(exe_dir)
    except ValueError:
        # 跨盘符时 commonpath 抛 ValueError —— 跨盘即必然不在 exe 目录内
        return False


def is_within_exe(path: Path) -> Optional[bool]:
    return data_dir_within_exe(path)
