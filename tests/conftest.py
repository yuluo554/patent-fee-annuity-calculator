"""测试共享夹具。

要点：
* ``patfee`` 的 import 路径：优先已安装包，未安装时回落到 ``src/``（便于 CI core-only job）。
* **数据库定位**：一律用仓库内 ``data/`` 显式路径，不依赖 CWD 上溯——
  否则在临时目录里跑测试会静默取错数据。
* ``QT_QPA_PLATFORM=offscreen`` 必须在首次 import PySide6 前设置（M5 用）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 未安装包时（如 core-only job 只装 pytest）回落到 src/
_SRC = REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    try:
        import patfee  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(_SRC))

# GUI 测试用：必须在任何 PySide6 导入之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DATA_DIR = REPO_ROOT / "data"


def repo_root() -> Path:
    return REPO_ROOT


def data_dir() -> Path:
    assert (DATA_DIR / "rules" / "manifest.json").is_file(), "规则包缺失: %s" % DATA_DIR
    return DATA_DIR
