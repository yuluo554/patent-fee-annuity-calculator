"""M5：打包守门（不真构建——构建由 CI/发布流程实跑，此处锁不变式）。

锁死的口径（plan/04 §十一 / HANDOFF-M5 §二.2）：

* ``build_datas()`` 白名单：rules + truth + knowledge 索引；raw 快照不入包；
* spec 双 exe：GUI console=False + CLI console=True，同一 main（入口启动器）；
* spec 由 ``patfee.packaging.build_datas()`` 产生 datas（单一事实源，不是
  手写清单）；
* ``--selftest`` 判定链：源码态六项检查全绿（数据/规则/calc/基准/GUI 冒烟）；
* dist 断言函数可对现存 dist 目录运行（构建后才存在，缺失则 skip 语义）。
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import os
from pathlib import Path

import pytest

from conftest import repo_root

SPEC = repo_root() / "packaging" / "patfee.spec"


def test_build_datas_whitelist_excludes_raw_snapshots():
    from patfee.packaging import build_datas

    datas = build_datas()
    assert datas, "build_datas 产出为空"
    src_all = [src.replace("\\", "/") for src, _ in datas]
    # 白名单内：规则包 + 真值库 + 依据索引
    assert any("data/rules" in s for s in src_all)
    assert any("data/truth" in s for s in src_all)
    assert any("clauses.json" in s for s in src_all)
    # 原文快照不入包（版权 + 体积）
    for s in src_all:
        assert "/raw/" not in s.replace("\\", "/"), "原文快照不得入包: %s" % s


def test_spec_uses_build_datas_and_dual_exe():
    text = SPEC.read_text(encoding="utf-8")
    assert "from patfee.packaging import build_datas" in text
    assert "datas = build_datas()" in text
    # 双 exe + console 语义
    assert 'name="patfee-gui"' in text and "console=False" in text
    assert 'name="patfee-cli"' in text and "console=True" in text
    # 同一 main：入口是共享启动器
    assert "run_patfee.py" in text
    # PyInstaller >= 6 语义（exclude_binaries + COLLECT onedir）
    assert "exclude_binaries=True" in text and "COLLECT" in text
    # CLI 包排除 GUI 重件（CLI-only 体积纪律）
    assert 'excludes=["PySide6", "openpyxl"]' in text


def test_spec_has_no_duplicate_kwargs_and_compiles():
    """spec 语法错误会让 PyInstaller 静默产出空壳——直接编译检查。"""
    text = SPEC.read_text(encoding="utf-8")
    tree = ast.parse(text)  # 语法错误在此抛出
    for node in ast.walk(tree):
        if isinstance(node, (ast.Call, ast.Dict)):
            if isinstance(node, ast.Call):
                kws = [kw.arg for kw in node.keywords if kw.arg]
                dupes = {k for k in kws if kws.count(k) > 1}
                assert not dupes, "spec 关键字参数重复: %s" % dupes


def test_launcher_invokes_patfee_cli_main():
    launcher = repo_root() / "packaging" / "run_patfee.py"
    text = launcher.read_text(encoding="utf-8")
    assert "from patfee.cli import main" in text
    assert "sys.exit(main())" in text


def test_selftest_checks_cover_six_gates():
    """--selftest 判定链必须覆盖六项检查（缺一项即出口判据不完整）。"""
    from patfee.cli import _frozen_selftest
    import inspect

    source = inspect.getsource(_frozen_selftest)
    for gate in (
        "data_dir_found",
        "data_dir_within_exe",
        "rules_loaded",
        "calc_pipeline",
        "benchmark_suites",
        "gui_offscreen_smoke",
    ):
        assert '"%s"' % gate in source, "自检缺少判定项: %s" % gate


def test_selftest_source_mode_all_green(tmp_path):
    """源码态跑一次 --selftest 主链（六项全绿），冻结语义由 exe 实测背书。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root() / "src")
    env.setdefault("PYTHONUTF8", "1")
    out_json = tmp_path / "selftest.json"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "patfee.cli", "--selftest", str(out_json)],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=str(repo_root()), timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    import json

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    names = {c["name"] for c in payload["checks"]}
    assert {"data_dir_found", "rules_loaded", "calc_pipeline", "benchmark_suites"} <= names
