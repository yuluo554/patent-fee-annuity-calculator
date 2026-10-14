"""M3 交付物测试：组合批量排期、失败隔离、到期预警、跨轮对账、基准 B4、CLI scan。

M3 出口判据（plan/05 里程碑表 + HANDOFF-M3 §二）：

* B1–B4 全达标（B4 见 test_benchmark.py 与本文件探活）；
* 组合批量排期 + 到期预警 + 跨轮对账可用；
* 失败隔离与退出码语义有测试守门（失败件不改变退出码）。
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import data_dir, repo_root
from patfee.benchmark import suites
from patfee.calc import pipeline
from patfee.calc.portfolio import (
    KIND_FAILED,
    KIND_NOT_DUE,
    KIND_SETTLED,
    KIND_UNPAID,
    PortfolioRequest,
    compare_rounds,
    content_fingerprint,
    scan_portfolio,
)

TODAY = date(2026, 10, 14)


@pytest.fixture(scope="module")
def lib():
    return load_library(data_dir())


from patfee.rules.loader import load_library  # noqa: E402


def _entry(no, ptype, year, due, paid=""):
    return {
        "patent_no": no, "patent_type": ptype, "year": year,
        "due_on": due, "paid_on": paid,
    }


def _scan(items, window_months=3, library=None):
    sources = [("item[%d]" % i, item) for i, item in enumerate(items)]
    return scan_portfolio(
        PortfolioRequest(sources=tuple(sources), today=TODAY, window_months=window_months),
        library,
    )


# ------------------------------------------------------------ 批量排期与分类

def test_scan_classifies_settled_unpaid_not_due(lib):
    result = _scan([
        _entry("990000000001SYN", "invention", 3, "2026-11-01", "2026-10-01"),  # 已缴
        _entry("990000000002SYN", "utility_model", 2, "2026-09-01"),            # 已到期未缴
        _entry("990000000003SYN", "design", 3, "2027-02-20"),                   # 未到期（窗口外）
    ], library=lib)
    kinds = {e.id: e.kind for e in result.entries}
    assert kinds["990000000001SYN#y3"] == KIND_SETTLED
    assert kinds["990000000002SYN#y2"] == KIND_UNPAID
    assert kinds["990000000003SYN#y3"] == KIND_NOT_DUE
    assert result.due_soon == (), "窗口 3 个月内无到期件（2-20 距基准日 > 3 个月）"


def test_scan_due_soon_sorted_by_days(lib):
    """到期预警：窗口内按剩余天数升序（FR-4.4）。"""
    result = _scan([
        _entry("990000000004SYN", "invention", 3, "2026-12-20"),
        _entry("990000000005SYN", "utility_model", 2, "2026-10-20"),
        _entry("990000000006SYN", "design", 2, "2026-11-15"),
    ], window_months=3, library=lib)
    days = [e.days_until_due for e in result.due_soon]
    assert days == sorted(days)
    assert len(result.due_soon) == 3
    # 窗口外的到期件（>3 个月）不进预警清单
    result2 = _scan([_entry("990000000004SYN", "invention", 3, "2027-06-01")],
                    window_months=3, library=lib)
    assert result2.due_soon == ()
    assert result2.entries[0].kind == KIND_NOT_DUE


def test_scan_amounts_computed_from_rules(lib):
    """金额随排期输出（取自年费阶梯引擎，Decimal 两位）。"""
    result = _scan([_entry("990000000001SYN", "invention", 3, "2026-11-01")], library=lib)
    assert result.entries[0].amount == Decimal("900.00")


# ------------------------------------------------------------ 失败隔离

def test_scan_failure_isolation_keeps_batch_going(lib):
    """坏格式件单列 failed，其余件照常排期（FR-4.2）。"""
    result = _scan([
        _entry("990000000001SYN", "invention", 3, "2026-11-01", "2026-10-01"),
        {"patent_type": "invention", "year": 5, "due_on": "2026-11-01"},        # 缺 patent_no
        {"patent_no": "990000000002SYN", "patent_type": "unicorn",
         "year": 2, "due_on": "2026-11-01"},                                     # 类型不识别
        None,                                                                     # 载荷缺失
    ], library=lib)
    assert len(result.failed) == 3
    assert all(e.kind == KIND_FAILED for e in result.failed)
    assert {e.reason for e in result.failed} == {"bad_format"}
    # 正常件不受影响
    live = [e for e in result.entries if e.kind != KIND_FAILED]
    assert len(live) == 1 and live[0].kind == KIND_SETTLED


def test_scan_failed_items_do_not_change_exit_code(lib):
    """失败件不改变退出码语义：退出码由"是否检出问题"决定（plan/03 §七）。

    * 有失败件 + 有未缴清 → 1（检出问题）；
    * 有失败件 + 其余全缴清且无到期 → 1（失败件本身是记录在案的问题）；
    * 无失败件 + 全缴清无到期 → 0。
    """
    dirty = _scan([
        _entry("990000000001SYN", "invention", 3, "2026-11-01", "2026-10-01"),
        {"patent_type": "invention", "year": 5, "due_on": "2026-11-01"},
    ], library=lib)
    assert pipeline.portfolio_exit_code_for(dirty) == 1

    clean = _scan([
        _entry("990000000001SYN", "invention", 3, "2026-11-01", "2026-10-01"),
    ], library=lib)
    assert pipeline.portfolio_exit_code_for(clean) == 0

    with_failed_only = _scan([
        _entry("990000000001SYN", "invention", 3, "2026-11-01", "2026-10-01"),
        {"patent_no": "990000000002SYN", "patent_type": "invention",
         "year": 3, "due_on": "2026-11-01", "paid_on": "2026-10-01"},
        {"patent_type": "invention", "year": 5, "due_on": "2026-11-01"},
    ], library=lib)
    assert len(with_failed_only.failed) == 1
    assert pipeline.portfolio_exit_code_for(with_failed_only) == 1


def test_scan_is_deterministic(lib):
    """同输入两次扫描结果一致（无 set 迭代序 / 无时钟依赖）。"""
    items = [
        _entry("990000000002SYN", "utility_model", 2, "2026-10-20"),
        _entry("990000000001SYN", "invention", 3, "2026-11-01"),
        {"patent_type": "invention", "year": 5, "due_on": "2026-11-01"},
    ]
    a = _scan(items, library=lib).as_dict()
    b = _scan(items, library=lib).as_dict()
    assert a == b


# ------------------------------------------------------------ 跨轮对账

def test_compare_rounds_three_sets_and_aux():
    """三集合（new_due/settled/still_unpaid）+ 辅助集（content_changed/vanished）。"""
    prev = [
        _entry("990000000001SYN", "invention", 3, "2026-01-01"),
        _entry("990000000002SYN", "utility_model", 2, "2026-01-01"),
        _entry("990000000003SYN", "design", 3, "2026-01-01", "2025-12-01"),
        _entry("990000000004SYN", "invention", 3, "2026-01-01"),
    ]
    curr = [
        _entry("990000000001SYN", "invention", 3, "2026-01-01", "2026-01-05"),  # → settled
        _entry("990000000002SYN", "utility_model", 2, "2026-01-01"),            # → still_unpaid
        # 003 期限变化（仍配得上）→ content_changed + settled（D13/FR-4.5）
        _entry("990000000003SYN", "design", 3, "2026-02-01", "2025-12-01"),
        _entry("990000000005SYN", "utility_model", 2, "2026-03-01"),            # → new_due
        # 004 本轮无 → vanished
    ]
    rec = compare_rounds(prev, curr)
    assert rec.settled == ("990000000001SYN#y3", "990000000003SYN#y3")
    assert rec.still_unpaid == ("990000000002SYN#y2",)
    assert rec.new_due == ("990000000005SYN#y2",)
    assert rec.content_changed == ("990000000003SYN#y3",)
    assert rec.vanished == ("990000000004SYN#y3",)


def test_compare_rounds_content_change_does_not_degrade_to_add_remove():
    """金额/期限变了仍按 patent_no 配对（不是"新增+移除"）。"""
    prev = [_entry("990000000001SYN", "invention", 3, "2026-01-01")]
    curr = [_entry("990000000001SYN", "invention", 3, "2027-01-01")]
    rec = compare_rounds(prev, curr)
    assert rec.content_changed == ("990000000001SYN#y3",)
    assert rec.new_due == () and rec.vanished == ()


def test_compare_rounds_paid_on_change_is_not_content_change():
    """缴清与否由 settled/still_unpaid 承载，不得同时再报 content_changed。"""
    prev = [_entry("990000000001SYN", "invention", 3, "2026-01-01")]
    curr = [_entry("990000000001SYN", "invention", 3, "2026-01-01", "2026-01-05")]
    rec = compare_rounds(prev, curr)
    assert rec.settled == ("990000000001SYN#y3",)
    assert rec.content_changed == ()


def test_content_fingerprint_ignores_paid_on():
    assert (content_fingerprint({"patent_no": "A", "year": 1, "due_on": "2026-01-01",
                                 "paid_on": ""})
            == content_fingerprint({"patent_no": "A", "year": 1, "due_on": "2026-01-01",
                                    "paid_on": "2026-01-05"}))
    assert content_fingerprint({"patent_no": "A", "year": 1, "due_on": "2026-01-01"}) != \
        content_fingerprint({"patent_no": "A", "year": 1, "due_on": "2026-02-01"})


def test_compare_rounds_deterministic():
    prev = [_entry("99000000000%dSYN" % i, "invention", 1, "2026-01-0%d" % i) for i in (1, 2, 3)]
    curr = [_entry("99000000000%dSYN" % i, "invention", 1, "2026-01-0%d" % i, "2026-01-05")
            for i in (1, 2, 3)]
    assert compare_rounds(prev, curr).as_dict() == compare_rounds(prev, curr).as_dict()


# ------------------------------------------------------------ pipeline 编排

def test_pipeline_build_request_two_rounds_and_items():
    payload = {
        "today": "2026-10-14", "window_months": 2,
        "baseline": [_entry("990000000001SYN", "invention", 3, "2026-01-01")],
        "current": [_entry("990000000001SYN", "invention", 3, "2026-01-01", "2026-01-05")],
    }
    req = pipeline.build_portfolio_request(payload)
    assert req.today == TODAY
    assert req.window_months == 2
    base, curr = pipeline.portfolio_rounds(req)
    assert len(base) == 1 and len(curr) == 1

    single = pipeline.build_portfolio_request({
        "today": "2026-10-14",
        "items": [_entry("990000000001SYN", "invention", 3, "2026-11-01")],
    })
    base2, curr2 = pipeline.portfolio_rounds(single)
    assert base2 == [] and len(curr2) == 1


def test_pipeline_request_bad_today_or_window_is_usage_error():
    with pytest.raises(Exception, match="today"):
        pipeline.build_portfolio_request({"today": "2026/10/14", "items": []})
    with pytest.raises(Exception, match="window_months"):
        pipeline.build_portfolio_request({"today": "2026-10-14", "window_months": 0, "items": []})
    with pytest.raises(Exception):
        pipeline.build_portfolio_request({"today": "2026-10-14"})


def test_pipeline_full_run_and_lines(lib):
    payload = json.loads(
        (repo_root() / "data" / "samples" / "portfolio-demo.json").read_text(encoding="utf-8"))
    req = pipeline.build_portfolio_request(payload)
    result = pipeline.compute_full_portfolio(req, lib)
    assert len(result.entries) == 7 and len(result.failed) == 1
    base, curr = pipeline.portfolio_rounds(req)
    rec = compare_rounds(base, curr)
    lines = pipeline.portfolio_lines(result, rec)
    assert any("组合批量排期" in l for l in lines)
    assert any("跨轮对账" in l for l in lines)
    assert any("bad_format" in l for l in lines)


# ------------------------------------------------------------ 基准 B4

def test_b4_passes_on_real_truth(lib):
    result = suites.suite_b4_portfolio(lib)
    assert result.implemented is True
    assert result.total > 0, "B4 分母不能为 0"
    assert not result.failures, "\n".join(result.failures)
    assert result.pass_rate == Decimal("1.0000")


def test_b4_truth_layer_actually_reconciles(lib):
    """真值层必须真的读了组合库（防分母做小）：total ≥ 缴费记录数 + clean 对照数。"""
    truth = json.loads((repo_root() / "data" / "truth" / "truth.json").read_text(encoding="utf-8"))
    portfolio = json.loads(
        (repo_root() / "data" / "truth" / "portfolio.json").read_text(encoding="utf-8"))
    n_clean = sum(1 for cid in truth["controls"]["clean"] if cid.startswith("payment."))
    result = suites.suite_b4_portfolio(lib)
    assert result.total >= len(portfolio["payments"]) + n_clean


def _probe_library():
    """构造探活库：现行条目全部复制并置 verified，由 caller 注入缺陷。

    库坐标仍指 data/（真值库可寻），manifest benchmarks 留空——
    探活直接调 suite 函数不走 run_suites 判定。
    """
    from patfee.rules.loader import RuleLibrary, Ruleset

    entries = []
    real = load_library(data_dir())
    for rs in real.rulesets.values():
        for entry in rs.entries.values():
            raw = entry.as_dict()
            raw["status"] = "verified"
            entries.append(raw)
    rs = Ruleset({"schema": "patfee.ruleset/v1", "id": "probe", "version": "vX",
                  "title": "probe", "doc_no": "probe", "entries": entries})
    manifest = {
        "schema": "patfee.rules.manifest/v1", "rulesets": [],
        "scopes": ["calc", "late", "reduction", "check"],
        "benchmarks": {}, "exemptions": {}, "banned_tokens": {},
    }
    return RuleLibrary(manifest, [rs], data_dir())


def test_b4_detects_amount_defect():
    """探活（可证伪）：阶梯金额篡改后 B4 的组合重算必须报未达标。"""
    probe = _probe_library()
    for rs in probe.rulesets.values():
        entry = rs.get("annuity.invention")
        if entry is not None:
            ladder = entry.ladder
            ladder[0]["amount"] = ladder[0]["amount"] + 1  # 注入缺陷：第 1 档 +1 元
    result = suites.suite_b4_portfolio(probe)
    assert result.failures, "金额注入缺陷后 B4 仍全绿 —— 基准失效"


def test_b4_detects_degrade_control_failure():
    """探活（可证伪）：把补缴上限 6 抬成 7 个月后，degrade 对照件（第 7 个月
    超上限算例）不再触发 late_exceeds_cap —— controls 层必须报未达标。

    防"controls 对照集永远绿"：若该层停止真实核对（例如只数数不断言），
    这条注入会与 clean 层一起全绿。
    """
    probe = _probe_library()
    for rs in probe.rulesets.values():
        entry = rs.get("late.grace_months")
        if entry is not None:
            entry.value = 7  # 注入缺陷：上限 6 → 7（degrade 件 = 第 7 整月算例）
    result = suites.suite_b4_portfolio(probe)
    assert result.failures, "抬上限后 degrade 对照仍绿 —— controls 层失效"
    assert any("degrade" in f for f in result.failures), result.failures


def test_b4_detects_reconciliation_omission():
    """探活（可证伪）：对账口径层漏报 vanished —— 上轮件本轮缺失不进
    vanished 集合的缺陷必须被 B4 检出（否则"消失的未缴件"在对账里隐身）。
    """
    from patfee.calc import portfolio as portfolio_mod

    probe = _probe_library()
    real_impl = portfolio_mod.compare_rounds

    def _swallow_vanished(previous, current):
        rec = real_impl(previous, current)
        return rec.__class__(new_due=rec.new_due, settled=rec.settled,
                             still_unpaid=rec.still_unpaid,
                             content_changed=rec.content_changed, vanished=())

    portfolio_mod.compare_rounds = _swallow_vanished
    try:
        result = suites.suite_b4_portfolio(probe)
    finally:
        portfolio_mod.compare_rounds = real_impl
    assert result.failures, "漏报 vanished 后 B4 仍全绿 —— 对账口径层失效"
    assert any("vanished" in f for f in result.failures), result.failures


# ------------------------------------------------------------ CLI scan

def _run(argv):
    from patfee import cli
    return cli.main(list(argv))


def test_cli_scan_stdout_exit_1_when_issues_found(capsys):
    sample = str(repo_root() / "data" / "samples" / "portfolio-demo.json")
    code = _run(["scan", sample])
    out = capsys.readouterr().out
    assert code == 1, "样例含未缴清件与失败件 → 检出问题 → 1"
    assert "组合批量排期" in out
    assert "跨轮对账" in out
    assert "未启用章节" in out, "未启用能力必须显式写出（没查 ≠ 查了没问题）"
    assert "不构成法律或代理意见" in out, "免责声明为强制输出"


def test_cli_scan_exit_0_when_all_settled(tmp_path, capsys):
    p = tmp_path / "clean.json"
    p.write_text(json.dumps({
        "today": "2026-10-14", "window_months": 3,
        "items": [_entry("990000000001SYN", "invention", 3, "2026-11-01", "2026-10-01")],
    }, ensure_ascii=False), encoding="utf-8")
    assert _run(["scan", str(p)]) == 0
    out = capsys.readouterr().out
    assert "已缴清: 1 件" in out


def test_cli_scan_preview_exit_1(tmp_path, capsys):
    p = tmp_path / "clean.json"
    p.write_text(json.dumps({
        "today": "2026-10-14",
        "items": [_entry("990000000001SYN", "invention", 3, "2026-11-01", "2026-10-01")],
    }, ensure_ascii=False), encoding="utf-8")
    assert _run(["scan", str(p), "--preview"]) == 1
    assert "不得作为缴费依据" in capsys.readouterr().out


def test_cli_scan_json_machine_readable(tmp_path, capsys):
    p = tmp_path / "two.json"
    p.write_text(json.dumps({
        "today": "2026-10-14",
        "baseline": [_entry("990000000001SYN", "invention", 3, "2026-01-01")],
        "current": [_entry("990000000001SYN", "invention", 3, "2026-01-01", "2026-01-05"),
                    _entry("990000000005SYN", "utility_model", 2, "2026-10-20")],
    }, ensure_ascii=False), encoding="utf-8")
    assert _run(["scan", str(p), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["counts"]["settled"] == 1
    assert payload["result"]["counts"]["due_soon"] == 1
    assert payload["reconciliation"]["settled"] == ["990000000001SYN#y3"]
    assert set(payload["not_enabled_sections"]) == {"late", "reduction"}


def test_cli_scan_writes_report_and_evidence(tmp_path, capsys):
    sample = str(repo_root() / "data" / "samples" / "portfolio-demo.json")
    out_dir = tmp_path / "report"
    code = _run(["scan", sample, "--out", str(out_dir)])
    assert code == 1
    md = out_dir / "scan-report.md"
    ev = out_dir / "evidence.json"
    assert md.is_file() and ev.is_file()
    import hashlib

    evidence = json.loads(ev.read_text(encoding="utf-8"))
    actual = hashlib.sha256(md.read_bytes()).hexdigest()
    assert evidence["report"]["sha256"] == actual, "evidence 必须携带报告的 sha256 指纹"
    text = md.read_text(encoding="utf-8")
    assert "未启用章节" in text
    assert "## 四、适用依据与免责声明" in text


def test_cli_scan_report_markdown_has_no_external_links(tmp_path, capsys):
    """无外链纪律自 M3 起守（plan/04 §七）：报告正文不写 URL。"""
    sample = str(repo_root() / "data" / "samples" / "portfolio-demo.json")
    out_dir = tmp_path / "report"
    _run(["scan", sample, "--out", str(out_dir)])
    text = (out_dir / "scan-report.md").read_text(encoding="utf-8")
    assert "http://" not in text and "https://" not in text, "报告正文不得含外链"


def test_cli_scan_missing_file_exit_2(tmp_path, capsys):
    assert _run(["scan", str(tmp_path / "nope.json")]) == 2
    assert "bad_format" in capsys.readouterr().err


def test_cli_scan_window_months_override(tmp_path, capsys):
    p = tmp_path / "far.json"
    p.write_text(json.dumps({
        "today": "2026-10-14",
        "items": [_entry("990000000004SYN", "invention", 3, "2027-02-20")],  # 129 天，3 月窗外
    }, ensure_ascii=False), encoding="utf-8")
    # 默认 3 个月窗口：2-20 在窗口外 → 全清 exit 0
    assert _run(["scan", str(p)]) == 0
    # 拉长到 5 个月（上界 155 天）：进入窗口 → 检出到期 → exit 1
    assert _run(["scan", str(p), "--window-months", "5"]) == 1
    out = capsys.readouterr().out
    assert "未来 5 个月内到期清单" in out
