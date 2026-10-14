"""M2 交付物测试：滞纳金引擎、费减判定、基准 B2/B3、CLI 扩展。

M2 出口判据（plan/05 §三之二）：

* 算例回归 100% —— truth 库 late/reduction 全部对上（test_b2/b3 真值层）；
* 阶梯/滞纳金/费减均走门控（scope 隔离测试）；
* B1/B2/B3 全达标，且 B2/B3 各配探活（可证伪）测试；
* 口径纪律：month_basis / grace / 阈值 / 比例全部从规则包读（变异验证）。
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import data_dir, repo_root
from patfee.benchmark import suites
from patfee.calc import late as late_mod
from patfee.calc import reduction as reduction_mod
from patfee.domain.models import PatentType, parse_patent_type
from patfee.rules.loader import RuleLibrary, Ruleset, load_library


@pytest.fixture(scope="module")
def lib():
    return load_library(data_dir())


@pytest.fixture(scope="module")
def truth_cases():
    path = repo_root() / "data" / "truth" / "truth.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {c["id"]: c for c in doc["cases"]}


def _late_request(case):
    inputs = case["inputs"]
    return late_mod.LateRequest(
        patent_type=parse_patent_type(case["patent_type"]),
        year=int(case["year"]),
        due_on=date.fromisoformat(inputs["due_on"]),
        paid_on=date.fromisoformat(inputs["paid_on"]),
    )


# ------------------------------------------------------------ 滞纳金引擎

def test_late_surcharge_accumulates_monthly(lib, truth_cases):
    """逐月累加：1/2 个月 = 全额 × 费率 × 月数（真值对账）。"""
    for cid in ("late.invention.y05.m1", "late.invention.y05.m2"):
        case = truth_cases[cid]
        res = late_mod.compute_late(lib, _late_request(case))
        assert res.computed
        assert str(res.surcharge) == case["expect"]["surcharge"]
        assert str(res.full_annuity) == case["expect"]["full_annuity"]
        assert str(res.payable) == str(
            Decimal(case["expect"]["full_annuity"]) + Decimal(case["expect"]["surcharge"])
        )


def test_late_six_months_at_cap_not_exceeded(lib, truth_cases):
    """K25：恰好上限（grace）不超限、grace+1 超限且 reason=late_exceeds_cap。"""
    grace = int(lib.ruleset("fee_schedule").get("late.grace_months").decimal())
    at_cap = late_mod.compute_late(lib, _late_request(truth_cases["late.invention.y05.m%d" % grace]))
    over_cap = late_mod.compute_late(lib, _late_request(truth_cases["late.invention.y05.m%d" % (grace + 1)]))
    assert at_cap.exceeds_cap is False
    assert at_cap.reasons == ()
    assert over_cap.exceeds_cap is True
    assert "late_exceeds_cap" in over_cap.reasons
    # 超上限仍给出金额：风险提示 ≠ 法律判定（金额照算，warning 不拦截）
    assert over_cap.computed and over_cap.surcharge is not None
    assert any("风险测算" in w for w in over_cap.warnings)


def test_late_month_basis_read_from_rules(lib):
    """K21：month_basis 从规则包读，引擎不写死 —— 同输入换口径月数变化。"""
    due, paid = date(2026, 1, 31), date(2026, 4, 15)
    months_cal, _ = late_mod.overdue_months_between(due, paid, "calendar_month")
    months_30, _ = late_mod.overdue_months_between(due, paid, "thirty_day")
    assert months_cal == 2  # 1-31 → 3-31 是第 2 个整月，4-15 不足第 3 个
    assert months_30 == 2   # 74 天 ÷ 30 = 2
    with pytest.raises(Exception, match="month_basis"):
        late_mod.overdue_months_between(due, paid, "fortnight")


def test_late_partial_month_not_counted(lib, truth_cases):
    """自然月零头不计：due+grace 月的"相应日"之前不满整月。"""
    months, _ = late_mod.overdue_months_between(
        date.fromisoformat(truth_cases["late.invention.y05.m1"]["inputs"]["due_on"]),
        date(2019, 11, 3),  # 恰在 6 个月相应日（11-04）的前一天
        "calendar_month",
    )
    assert months == 5


def test_late_related_fees_from_fee_schedule(lib, truth_cases):
    """恢复权利请求费/评价报告费按费率表条目列出（不编造、不计入滞纳金）。"""
    case = truth_cases["late.invention.y05.m7"]
    res = late_mod.compute_late(lib, _late_request(case))
    keys = {f.entry_key for f in res.related_fees}
    assert "check.fee.ruc" in keys and "check.fee.evaluation_report" in keys
    for fee in res.related_fees:
        assert fee.amount is not None
    assert res.payable == res.full_annuity + res.surcharge, "应缴合计不含关联费用"


def test_late_not_computed_when_input_inverted(lib):
    """paid_on <= due_on → 0 月，滞纳金为 0（不是错误）。"""
    res = late_mod.compute_late(lib, late_mod.LateRequest(
        PatentType.INVENTION, 5, date(2026, 5, 4), date(2026, 5, 4)))
    assert res.computed
    assert res.overdue_months == 0
    assert res.surcharge == Decimal("0.00")


# ------------------------------------------------------------ 费减引擎

def _red_request(case):
    return reduction_mod.ReductionRequest(
        patent_type=parse_patent_type(case["patent_type"]),
        year=int(case["year"]),
        as_of_year=int(case["as_of_year"]),
        applicants=reduction_mod.parse_applicants(case["applicants"]),
        open_license=bool(case.get("open_license")),
    )


def test_reduction_strictly_below_threshold(lib, truth_cases):
    """K25：恰好等于阈值 → 不合格；略低 → 合格。"""
    at = reduction_mod.compute_reduction(lib, _red_request(truth_cases["reduction.sole.individual.at_threshold"]))
    below = reduction_mod.compute_reduction(lib, _red_request(truth_cases["reduction.sole.individual.below"]))
    assert at.eligible is False and at.payable is None
    assert below.eligible is True and str(below.payable) == "180.00"


def test_reduction_combined_requires_all_eligible(lib, truth_cases):
    """共同主体须逐个合格；比例取 combined 条目。"""
    both = reduction_mod.compute_reduction(lib, _red_request(truth_cases["reduction.combined.both_below"]))
    one_at = reduction_mod.compute_reduction(lib, _red_request(truth_cases["reduction.combined.one_at_threshold"]))
    assert both.eligible is True and str(both.reduction_rate) == "0.70"
    assert one_at.eligible is False


def test_reduction_threshold_anchor_by_year(lib, truth_cases):
    """as_of_year 锚点前用 .prev 历史阈值。"""
    old = reduction_mod.compute_reduction(
        lib, _red_request(truth_cases["reduction.anchor.2018.below_old_threshold"]))
    assert old.eligible is True
    assert old.thresholds["individual_monthly_income"] == Decimal("3500")
    assert old.thresholds["entity_taxable_income"] == Decimal("300000")


def test_reduction_multi_policy_picks_min_payable(lib, truth_cases):
    """多政策择实缴最小者；candidates 全留痕；不叠加。"""
    case = truth_cases["multi_policy.sole_eligible_and_open_license"]
    res = reduction_mod.compute_reduction(lib, _red_request(case))
    assert res.no_double_benefit_applied is True
    assert len(res.candidates) == 2
    amounts = [c.amount for c in res.candidates]
    assert res.chosen.amount == min(amounts)
    assert str(res.payable) == case["expect"]["payable"]
    # rate 字段始终是费减比例（eligible 时），即使选中的是开放许可
    assert str(res.reduction_rate) == "0.85"


def test_reduction_open_license_alone_when_ineligible(lib, truth_cases):
    """不合格 + 开放许可：候选集只有 15% 一项，证明择一按候选集而非固定费减。"""
    case = truth_cases["multi_policy.ineligible_but_open_license"]
    res = reduction_mod.compute_reduction(lib, _red_request(case))
    assert res.eligible is False
    assert len(res.candidates) == 1
    assert res.candidates[0].policy == "开放许可年费减免"
    assert str(res.payable) == "1020.00"


def test_reduction_rejects_float_incomes(lib):
    """金额字段拒收 float（Decimal 纪律贯穿费减路径）。"""
    with pytest.raises(Exception):
        reduction_mod.parse_applicants([{"kind": "individual", "monthly_avg_income": 4999.99}])


# ------------------------------------------------------------ scope 门控隔离

def _library_with_status(status: str, annuity_verified: bool = False) -> RuleLibrary:
    """构造指定 status 的最小规则库（费减条目 + 年费条目），供门控路径测试。

    ``annuity_verified=True`` 时仅年费条目置 verified、其余保持给定 status ——
    用于验证 scope 隔离（calc 路径不被其他 scope 的 pending 连坐）。
    """
    def _entry(key, kind, value=None, ladder=None, scopes=None):
        entry_status = "verified" if (annuity_verified and key.startswith("annuity.")) else status
        return {
            "key": key, "label": key, "kind": kind, "status": entry_status,
            "scopes": scopes or (["reduction"] if key.startswith("reduction.") else ["calc"]),
            **({"value": value} if value is not None else {}),
            **({"ladder": ladder} if ladder else {}),
            "basis": {"doc_no": "d", "clause": "c", "url": "http://x", "retrieved": "2026-10-14"},
        }

    entries = [
        _entry("annuity.invention", "ladder", ladder=[
            {"from_year": 1, "to_year": 6, "amount": 1200, "label": "1-6"},
        ]),
        _entry("reduction.threshold.individual_monthly_income", "scalar", value="5000"),
        _entry("reduction.threshold.individual_annual_income", "scalar", value="60000"),
        _entry("reduction.threshold.entity_taxable_income", "scalar", value="1000000"),
        _entry("reduction.threshold.effective_from", "scalar", value="2019-07-01"),
        _entry("reduction.rate.sole", "scalar", value="0.85"),
        _entry("reduction.rate.combined", "scalar", value="0.70"),
        _entry("reduction.open_license_discount", "scalar", value="0.15"),
        _entry("reduction.no_double_benefit", "scalar", value="choose_most_favorable"),
        _entry("late.monthly_rate", "scalar", value="0.05", scopes=["late"]),
        _entry("late.grace_months", "scalar", value="6", scopes=["late"]),
        _entry("late.month_basis", "scalar", value="calendar_month", scopes=["late"]),
    ]
    rs = Ruleset({"schema": "patfee.ruleset/v1", "id": "probe", "version": "v1",
                  "title": "probe", "doc_no": "probe", "entries": entries})
    manifest = {
        "schema": "patfee.rules.manifest/v1", "rulesets": [],
        "scopes": ["calc", "late", "reduction", "check"],
        "benchmarks": {}, "exemptions": {}, "banned_tokens": {},
    }
    return RuleLibrary(manifest, [rs], Path("."))


def test_reduction_gated_pending_is_uncomputed():
    """scope 隔离：费减条目 pending → reduction scope 拒绝 → 未判定（不崩、不假成功）。"""
    probe = _library_with_status("pending")
    res = reduction_mod.compute_reduction(probe, reduction_mod.ReductionRequest(
        PatentType.INVENTION, 5, 2026,
        reduction_mod.parse_applicants([{"kind": "entity", "taxable_income": "1"}]),
    ))
    assert res.computed is False
    assert "gated_pending" in res.reasons


def test_late_gated_pending_is_uncomputed():
    """scope 隔离：late 条目 pending → 滞纳金路径拒绝 → 未判定。"""
    probe = _library_with_status("pending")
    res = late_mod.compute_late(probe, late_mod.LateRequest(
        PatentType.INVENTION, 5, date(2026, 5, 4), date(2026, 6, 4)))
    assert res.computed is False
    assert "gated_pending" in res.reasons


def test_scope_isolation_pending_reduction_does_not_block_calc():
    """reduction 条目 pending 时年费路径照常（calc scope 不受别的 scope 条目连坐）。"""
    probe = _library_with_status("pending", annuity_verified=True)
    from patfee.calc import annuity as annuity_mod

    res = annuity_mod.compute_annuity(probe, PatentType.INVENTION, 5)
    assert res.computed, "calc scope 不应被 reduction/late 条目的 pending 连坐"
    assert str(res.amount) == "1200.00"


# ------------------------------------------------------------ 基准 B2/B3

def test_b2_passes_on_real_ruleset(lib):
    result = suites.suite_b2_late(lib)
    assert result.implemented is True
    assert result.total > 0, "B2 分母不能为 0"
    assert not result.failures, "\n".join(result.failures)
    assert result.pass_rate == Decimal("1.0000")


def test_b3_passes_on_real_ruleset(lib):
    result = suites.suite_b3_reduction(lib)
    assert result.implemented is True
    assert result.total > 0, "B3 分母不能为 0"
    assert not result.failures, "\n".join(result.failures)
    assert result.pass_rate == Decimal("1.0000")


def test_b2_truth_layer_actually_reconciles(lib):
    """真值层必须真的读了 truth 库（防"分母悄悄做小"）：late 算例数计入 total。"""
    truth = json.loads((repo_root() / "data" / "truth" / "truth.json").read_text(encoding="utf-8"))
    n_late = sum(1 for c in truth["cases"] if c.get("kind") == "late")
    result = suites.suite_b2_late(lib)
    assert result.total >= n_late, "B2 total 应至少覆盖真值库 late 算例数"


def test_b3_truth_layer_actually_reconciles(lib):
    truth = json.loads((repo_root() / "data" / "truth" / "truth.json").read_text(encoding="utf-8"))
    n_red = sum(1 for c in truth["cases"] if c.get("kind") == "reduction")
    result = suites.suite_b3_reduction(lib)
    assert result.total >= n_red, "B3 total 应至少覆盖真值库 reduction 算例数"


def test_b2_detects_rate_defect():
    """探活（可证伪）：费率翻倍后 B2 必须报未达标。"""
    probe = _library_with_status("verified")
    for rs in probe.rulesets.values():
        entry = rs.get("late.monthly_rate")
        entry.value = Decimal("0.10")  # 注入缺陷：费率错一倍
    result = suites.suite_b2_late(probe)
    assert result.failures, "费率注入缺陷后 B2 仍全绿 —— 基准失效"


def test_b3_detects_threshold_defect():
    """探活（可证伪）：阈值抬高后 B3 的边界枚举必须报未达标。"""
    probe = _library_with_status("verified")
    for rs in probe.rulesets.values():
        entry = rs.get("reduction.threshold.entity_taxable_income")
        entry.value = Decimal("1000001")  # 注入缺陷：阈值 +1 元
    result = suites.suite_b3_reduction(probe)
    assert result.failures, "阈值注入缺陷后 B3 仍全绿 —— 基准失效"


def test_bench_full_run_all_implemented_pass(lib):
    """基准全量运行：B1–B4 全实装（M3 起 B4 实装）、全达标。"""
    results, verdicts, implemented = suites.run_suites(lib)
    assert {"b1_ladder", "b2_late", "b3_reduction", "b4_portfolio"} <= set(implemented)
    assert all(v.endswith("=达标") for v in verdicts)
