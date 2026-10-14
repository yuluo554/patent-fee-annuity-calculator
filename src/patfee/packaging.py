"""打包（PyInstaller）：datas 单一事实源 + spec + 构建后断言（M5）。

口径（plan/04 §十一）：

* ``build_datas()`` 是 spec 内 ``datas`` 的**唯一事实源**：白名单 =
  ``data/rules`` + ``data/truth`` + ``data/knowledge`` 索引（clauses.json）；
  ``data/knowledge/raw/`` 原文快照**不入包**（版权 + 体积）。
* 双 exe：GUI（``console=False``）+ CLI（``console=True``），同一 ``main``。
* 构建后断言：dist 全树无禁区成分（``plan/``、``tests/``、``_private/``、
  ``.git`` 出现在**任意层**即失败）+ 内嵌数据与仓库逐份 sha256 对账 +
  白名单外目录检测。
* ``patfee --selftest <输出json>`` 在冻结态跑数据落点 + 规则加载 +
  calc 全链路 + 基准 + GUI offscreen 冒烟。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

# 数据白名单（相对仓库根）：(源目录/文件, 打包内目标目录)
_DATA_WHITELIST: List[Tuple[str, str]] = [
    ("data/rules", "data/rules"),
    ("data/truth", "data/truth"),
    ("data/knowledge/clauses.json", "data/knowledge"),
]

# 禁区成分：dist 全树任意层出现即构建失败
FORBIDDEN_NAMES = {"plan", "tests", "_private", ".git", ".verify-out", "tools"}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def build_datas() -> List[Tuple[str, str]]:
    """spec 的 ``datas`` 唯一事实源（白名单逐项，raw 快照不入包）。"""
    root = repo_root()
    datas: List[Tuple[str, str]] = []
    for src_rel, dest in _DATA_WHITELIST:
        src = root / src_rel
        if src.is_dir():
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    datas.append((str(p), dest))
        elif src.is_file():
            datas.append((str(src), dest))
        else:
            raise FileNotFoundError("打包白名单缺失: %s" % src)
    return datas


def assert_dist_clean(dist_dir: Path) -> Dict[str, Any]:
    """构建后断言：禁区成分 / 白名单外顶层目录 / 内嵌数据 sha256 对账。

    返回报告 dict（供构建脚本落盘）；断言失败抛 ``AssertionError``。
    """
    dist_dir = Path(dist_dir)
    report: Dict[str, Any] = {"forbidden": [], "top_dirs": [], "data_files": {}}

    all_paths = list(dist_dir.rglob("*"))
    top_dirs = sorted(p.name for p in dist_dir.iterdir() if p.is_dir())
    report["top_dirs"] = top_dirs

    for p in all_paths:
        for part in p.relative_to(dist_dir).parts:
            if part in FORBIDDEN_NAMES:
                report["forbidden"].append(str(p.relative_to(dist_dir)))
    assert not report["forbidden"], "dist 含禁区成分: %s" % report["forbidden"]

    # 内嵌数据与仓库逐份 sha256 对账（PyInstaller 6 onedir：_internal/data/；
    # 兼容 PyInstaller 5 平铺布局 data/）
    root = repo_root()
    for src_rel, dest in _DATA_WHITELIST:
        src = root / src_rel
        sources = (
            sorted(p for p in src.rglob("*") if p.is_file())
            if src.is_dir() else [src]
        )
        for src_file in sources:
            rel_in_dest = src_file.relative_to(root)
            embedded = None
            for base in (dist_dir / "_internal", dist_dir):
                candidate = base / rel_in_dest
                if candidate.is_file():
                    embedded = candidate
                    break
            assert embedded is not None, "内嵌数据缺失: %s" % rel_in_dest
            h_repo = _sha256(src_file)
            h_emb = _sha256(embedded)
            assert h_repo == h_emb, "内嵌数据 sha256 不一致: %s" % rel_in_dest
            report["data_files"][str(rel_in_dest)] = h_repo

    # 白名单外目录检测：data/ 下只允许 rules/truth/knowledge（含 _internal 布局）
    for base in (dist_dir / "_internal", dist_dir):
        data_dir_in_dist = base / "data"
        if data_dir_in_dist.is_dir():
            allowed = {"rules", "truth", "knowledge"}
            extra = [p.name for p in data_dir_in_dist.iterdir() if p.name not in allowed]
            assert not extra, "data/ 出现白名单外目录: %s（%s）" % (extra, base)
            break

    return report


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_build_dirs(build_dir: Path, dist_dir: Path) -> None:
    """清理上次构建产物（确定性构建）。"""
    for d in (build_dir, dist_dir):
        if Path(d).exists():
            shutil.rmtree(d)
