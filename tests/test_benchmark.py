"""基准套件测试：可证伪（注入缺陷必报未达标）、退出码、未实装语义。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import data_dir
from patfee.benchmark import suites
from patfee.errors import RulesetError
from patfee.rules.loader import STATUS_VERIFIED, Entry, RuleLibrary, Ruleset, load_library


@pytest.fixture(scope="module")
def lib():
    return load_library(data_dir())


def _library_with_ladder(ladder, status=STATUS_VERIFIED):
    """构造只含一条阶梯的最小规则库，用于变异验证。"""
    raw_rs = {
        "schema": "patfee.ruleset/v1",
        "id": "probe",
        "version": "v1",
        "title": "probe",
        "doc_no": "probe",
        "entries": [
            {
                "key": "annuity.invention",
                "label": "probe",
                "kind": "ladder",
                "status": status,
                "scopes": ["calc"],
                "ladder": ladder,
                "basis": {"doc_no": "d", "clause": "c", "url": "http://x", "retrieved": "2026-10-14"},
            }
        ],
    }
    rs = Ruleset(raw_rs)
    manifest = {
        "schema": "patfee.rules.manifest/v1",
        "rulesets": [],
        "scopes": ["calc"],
        "benchmarks": {
            "b1_ladder": {"min_pass_rate": "1.0", "max_fail": 0, "max_seconds": "1.0"},
        },
        "exemptions": {
            "small_int_abs_limit": 100, "exempt_integers": [],
            "exempt_decimals": ["0.01", "0.1", "0.5", "1.0", "2.0"], "inline_allow_mark": "literal-ok",
        },
        "banned_tokens": {"integers": [], "decimals": []},
    }
    from pathlib import Path

    return RuleLibrary(manifest, [rs], Path("."))


def test_b1_passes_on_real_ruleset(lib):
    result = suites.suite_b1_ladder(lib)
    assert result.total > 0, "B1 的分母不能为 0（否则 100% 达标是假的）"
    assert not result.failures, "\n".join(result.failures)
    assert result.pass_rate == Decimal("1.0000")


def test_b1_detects_gap_between_tiers():
    """变异验证：区间留空洞 → B1 必须报未达标。"""
    bad = [
        {"from_year": 1, "to_year": 3, "amount": 900, "label": "1-3"},
        {"from_year": 5, "to_year": 6, "amount": 1200, "label": "5-6"},  # 缺第 4 年
    ]
    result = suites.suite_b1_ladder(_library_with_ladder(bad))
    assert result.failures, "留空洞后 B1 仍全绿 —— 基准失效"
    assert any("不连续" in f or "命中 0 个区间" in f for f in result.failures)


def test_b1_detects_overlapping_tiers():
    """变异验证：区间重叠 → 某年命中两个区间，必须报未达标。"""
    bad = [
        {"from_year": 1, "to_year": 4, "amount": 900, "label": "1-4"},
        {"from_year": 4, "to_year": 6, "amount": 1200, "label": "4-6"},  # 第 4 年重叠
    ]
    result = suites.suite_b1_ladder(_library_with_ladder(bad))
    assert result.failures, "区间重叠后 B1 仍全绿 —— 基准失效"
    assert any("应为恰好 1 个" in f for f in result.failures)


def test_b1_marks_not_implemented_when_no_ladder_entries():
    """没有任何可校验条目时，必须显式声明"未实装"，不许把自己算成 100% 达标。"""
    manifest = {
        "schema": "patfee.rules.manifest/v1", "rulesets": [], "scopes": ["calc"],
        "benchmarks": {}, "exemptions": {}, "banned_tokens": {},
    }
    from pathlib import Path

    empty = RuleLibrary(manifest, [], Path("."))
    result = suites.suite_b1_ladder(empty)
    assert result.implemented is False
    assert result.total == 0


def test_unknown_suite_raises_usage_error(lib):
    with pytest.raises(RulesetError, match="未知基准套件"):
        suites.run_suites(lib, only=["nope"])


def test_all_suites_implemented_and_judged(lib):
    """M3 起 B1–B4 全部实装并参与达标判定；未实装语义由空库路径守护
    （B1 无条目 → implemented=False 显式标出，不静默算达标）。"""
    results, verdicts, implemented = suites.run_suites(lib)
    assert set(implemented) == {"b1_ladder", "b2_late", "b3_reduction", "b4_portfolio"}
    assert all(v.endswith("=达标") for v in verdicts)


def test_threshold_must_come_from_manifest(lib):
    """门槛缺失即报配置错误，不得回落代码默认值。"""
    from pathlib import Path

    manifest = {
        "schema": "patfee.rules.manifest/v1", "rulesets": [], "scopes": ["calc"],
        "benchmarks": {}, "exemptions": {}, "banned_tokens": {},
    }
    bare = RuleLibrary(manifest, [], Path("."))
    with pytest.raises(RulesetError, match="门槛"):
        bare.benchmark_threshold("b1_ladder")


def test_all_suite_names_registered():
    assert set(suites.suite_names()) == {"b1_ladder", "b2_late", "b3_reduction", "b4_portfolio"}


# ------------------------------------------------------------ M4：计时门槛与指标固化

def test_threshold_problems_executes_max_seconds(lib):
    """计时门槛 max_seconds 随 manifest 下发后必须实际执行（M4）：
    构造"超时结果"直接喂判定函数，必须判未达标并给出原因。"""
    from patfee.benchmark.suites import CheckResult, _threshold_problems

    threshold = {"min_pass_rate": "1.0", "max_fail": 0, "max_seconds": "2.0"}
    slow = CheckResult(suite="b4_portfolio", total=10, passed=10, elapsed_seconds=Decimal("2.001"))
    problems = _threshold_problems(slow, threshold)
    assert problems, "超时结果未被计时门槛拦截 —— max_seconds 是摆设"
    assert any("max_seconds" in p for p in problems)

    fast = CheckResult(suite="b4_portfolio", total=10, passed=10, elapsed_seconds=Decimal("0.008"))
    assert _threshold_problems(fast, threshold) == []


def test_run_suites_records_elapsed_and_all_verdicts_pass(lib):
    """run_suites 必须记录每套件实测耗时；现行规则包四套件全达标（含计时）。"""
    results, verdicts, implemented = suites.run_suites(lib)
    for name, res in results.items():
        assert res.elapsed_seconds is not None, "%s 未记录耗时" % name
        assert res.elapsed_seconds >= 0
    assert all(v.endswith("=达标") for v in verdicts)
    # M4 指标固化复核：B1 99 / B2 18 / B3 20 / B4 48（M4 起 B4 补两条对账语义断言）
    counts = {name: (res.passed, res.total) for name, res in results.items()}
    assert counts == {
        "b1_ladder": (99, 99),
        "b2_late": (18, 18),
        "b3_reduction": (20, 20),
        "b4_portfolio": (48, 48),
    }


def test_max_seconds_gate_is_falsifiable_via_run_suites(lib, monkeypatch):
    """探活（可证伪）：把计时函数桩成超时值后，run_suites 必须报未达标。"""
    import time as time_mod

    class _FakePerf:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            return 0.0 if self.calls == 1 else 10.0  # 首读 0，末读 10s

    fake = _FakePerf()
    monkeypatch.setattr(time_mod, "perf_counter", fake)
    results, verdicts, _ = suites.run_suites(lib)
    assert any("未达标" in v and "max_seconds" in v for v in verdicts), verdicts
    monkeypatch.undo()
    # 桩撤掉后必须回到全达标（防桩残留导致假红）
    _, verdicts2, _ = suites.run_suites(lib)
    assert all(v.endswith("=达标") for v in verdicts2)
