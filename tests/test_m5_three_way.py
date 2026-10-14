"""M5：三方对账测试（FR-8.3 / D26）—— CLI stdout = 编排直调 = 报告章节。

同一个业务判断在项目里只能有一处实现：编排入口上收为 ``calc.pipeline``
公开函数组后，CLI 的 stdout 行、编排层直调的渲染行、报告章节里的
"逐项结论与计算过程"必须是**同一份输出**（行为等价，不是字面声明）。

对账对象（scan 通路，三方覆盖最全）：
  A. ``patfee scan`` CLI stdout（解析 --out 关闭时的打印）；
  B. 编排直调：``portfolio_lines(compute_full_portfolio(...), compare_rounds(...))``；
  C. 报告章节：``scan_report_sections`` 中 "二、逐项结论与计算过程" 的行。

另附 calc / reduction 两通路的 CLI = 编排直调两方对账。
"""

from __future__ import annotations

import json
import subprocess
import sys
import os
from pathlib import Path

import pytest

from conftest import repo_root, data_dir

CLI = [sys.executable, "-X", "utf8", "-m", "patfee.cli"]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root() / "src")
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(
        CLI + list(args), capture_output=True, text=True,
        encoding="utf-8", env=env, cwd=str(repo_root()),
    )


def _orchestrated_scan_lines():
    """编排直调：scan 结果渲染行（与 CLI 同输入同口径）。"""
    from decimal import Decimal
    from patfee.rules.loader import load_library
    from patfee.calc import pipeline
    from patfee.calc.portfolio import compare_rounds

    payload = json.loads(
        (repo_root() / "data" / "samples" / "portfolio-demo.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    lib = load_library(data_dir())
    request = pipeline.build_portfolio_request(payload, preview=False)
    result = pipeline.compute_full_portfolio(request, lib)
    baseline, current = pipeline.portfolio_rounds(request)
    reconciliation = compare_rounds(baseline, current)
    return pipeline.portfolio_lines(result, reconciliation), result


def test_three_way_reconciliation_scan_cli_vs_orchestration_vs_report(tmp_path):
    """scan 通路三方对账：CLI stdout == 编排直调 == 报告章节。"""
    sample = str(repo_root() / "data" / "samples" / "portfolio-demo.json")

    # ---- A: CLI stdout（不带 --out；尾部含"未启用章节"附加段，见下） ----
    proc = _run_cli("scan", sample)
    assert proc.returncode == 1  # 检出问题
    cli_all = proc.stdout.splitlines()
    # CLI 在编排渲染行之后附加"未启用章节"段（== 标题 + 空行 + 2 条），
    # 这 3 行对应报告的"三、未启用章节"——先剥离再对齐编排行。
    marker = "== 未启用章节（没查 ≠ 查了没问题）=="
    idx = cli_all.index(marker)
    cli_lines = cli_all[:idx]
    cli_extra = cli_all[idx + 1:]  # 跳过空行后为 2 条说明

    # ---- B: 编排直调 ----
    orch_lines, result = _orchestrated_scan_lines()

    # ---- C: 报告章节 ----
    from decimal import Decimal
    from patfee.rules.loader import load_library
    from patfee.calc import pipeline
    from patfee.calc.portfolio import compare_rounds
    from patfee.cli import _scan_not_enabled_sections
    from patfee.report import scan_report_sections

    payload = json.loads(
        (repo_root() / "data" / "samples" / "portfolio-demo.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    lib = load_library(data_dir())
    request = pipeline.build_portfolio_request(payload, preview=False)
    res2 = pipeline.compute_full_portfolio(request, lib)
    baseline, current = pipeline.portfolio_rounds(request)
    recon2 = compare_rounds(baseline, current)
    sections = scan_report_sections(
        res2, recon2, lib, False, _scan_not_enabled_sections(), pipeline.DISCLAIMER
    )
    body_section = [s for s in sections if s.title == "二、逐项结论与计算过程"][0]
    report_lines = list(body_section.lines)

    # ---- 三方对账（空行在段落边界上的差异不参与判定：剥两端空行）----
    def _norm(lines):
        body = list(lines)
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        return body

    assert _norm(cli_lines) == _norm(orch_lines), "CLI stdout 与编排直调不一致"
    assert _norm(report_lines) == _norm(orch_lines), "报告章节与编排直调不一致"
    # CLI 的"未启用章节"附加段与报告"三"节同源（同一 dict 驱动两格式）
    ne_section = [s for s in sections if s.title.startswith("三、未启用章节")][0]
    # 报告"三"节把 not_enabled 渲染为表格 rows；CLI 附加段渲染为 "  - 文本" 行
    report_ne_texts = [str(row[1]) for row in ne_section.table_rows()]
    cli_ne_texts = [ln.strip().lstrip("- ").strip() for ln in cli_extra if ln.strip()]
    assert report_ne_texts == cli_ne_texts
    # 金额事实抽查（防"两边同错"）：
    assert any("件数合计: 7" in ln for ln in orch_lines)


def test_three_way_calc_cli_matches_orchestration(tmp_path):
    """calc 通路两方对账：CLI stdout == 编排直调渲染行。"""
    sample = str(repo_root() / "data" / "samples" / "patent-demo.json")
    proc = _run_cli("calc", sample)
    assert proc.returncode == 0
    cli_lines = proc.stdout.splitlines()

    from decimal import Decimal
    from patfee.rules.loader import load_library
    from patfee.calc import pipeline

    payload = json.loads(
        Path(sample).read_text(encoding="utf-8"), parse_float=Decimal
    )
    lib = load_library(data_dir())
    request = pipeline.build_request(payload, preview=False)
    result = pipeline.compute_full_calc(request, lib)
    orch_lines = pipeline.result_lines(result, lib)
    assert cli_lines == orch_lines
    assert any("应缴年费:" in ln for ln in orch_lines)


def test_three_way_reduction_cli_matches_orchestration(tmp_path):
    """reduction 通路两方对账：CLI stdout == 编排直调渲染行。"""
    sample = str(repo_root() / "data" / "samples" / "applicants-demo.json")
    proc = _run_cli("reduction", sample)
    assert proc.returncode == 0
    cli_lines = proc.stdout.splitlines()

    from decimal import Decimal
    from patfee.rules.loader import load_library
    from patfee.calc import pipeline

    payload = json.loads(
        Path(sample).read_text(encoding="utf-8"), parse_float=Decimal
    )
    lib = load_library(data_dir())
    request = pipeline.build_reduction_request(payload, preview=False)
    result = pipeline.compute_full_reduction(request, lib)
    orch_lines = pipeline.reduction_lines(result)
    assert cli_lines == orch_lines
    assert any("资格结论:" in ln for ln in orch_lines)
