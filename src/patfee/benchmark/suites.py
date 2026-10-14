"""基准套件实现。

新增套件必须同时注册进 :data:`SUITES`，未知名走 exit 2（不许静默跳过）。
每套件配探活（可证伪）测试：注入缺陷后必须报未达标。

M2 起 B2/B3 为**两层**：

1. **真值层** —— 读 ``data/truth/truth.json`` 冻结算例，引擎重算逐项对账；
   真值库不可得（非仓库环境）时显式留 note，不冒充分母；
2. **规则驱动层** —— 从规则包参数独立推导端点期望（套件内自算，不经引擎），
   引擎结果与期望逐项断言。分母不许悄悄做小。
"""

from __future__ import annotations

import calendar as _calendar
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..domain.models import PatentType, parse_patent_type, quantize_amount
from ..errors import RulesetError
from ..rules.loader import RuleLibrary, STATUS_PENDING, STATUS_VERIFIED, load_library


@dataclass
class CheckResult:
    suite: str
    total: int = 0
    passed: int = 0
    failures: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    implemented: bool = True

    @property
    def pass_rate(self) -> Decimal:
        if self.total == 0:
            return Decimal("0")
        return (Decimal(self.passed) / Decimal(self.total)).quantize(Decimal("0.0001"))

    def as_dict(self) -> dict:
        return {
            "suite": self.suite,
            "implemented": self.implemented,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": str(self.pass_rate),
            "failures": list(self.failures[:20]),
            "notes": list(self.notes),
        }


def _entry(library: RuleLibrary, key: str):
    for rs in library.rulesets.values():
        entry = rs.get(key)
        if entry is not None:
            return entry
    return None


def suite_b1_ladder(library: RuleLibrary) -> CheckResult:
    """B1 阶梯边界（规则驱动）。

    不读真值库：直接从规则表**枚举全部切换端点**做断言。

    断言两类：
    1. 覆盖完整性 —— 从最早年度到最末年度**每一个整年度**都必须命中唯一区间
       （不留空洞、不重叠）；
    2. 端点归属 —— 每个区间的首年必须命中该区间，末年必须命中该区间，
       且"上一区间末年"的下一整年必须命中**新**区间（恰好跳档年归新档）。
    """
    result = CheckResult(suite="b1_ladder")
    checked_types = 0

    for patent_type in PatentType:
        key = "annuity." + patent_type.value
        entry = _entry(library, key)
        if entry is None:
            result.notes.append("%s 未在规则包中建条目（该类用例未生成）" % key)
            continue
        if not entry.has_value:
            result.notes.append("%s 阶梯值为空，本套件跳过该类" % key)
            continue

        checked_types += 1
        from ..calc.annuity import tiers_from_entry

        tiers = tiers_from_entry(entry)

        # 断言 1：区间连续且恰好首尾相接（无缝无叠）
        ordered = sorted(tiers, key=lambda t: t.from_year)
        for prev, cur in zip(ordered, ordered[1:]):
            result.total += 1
            if cur.from_year != prev.to_year + 1:
                result.failures.append(
                    "%s 区间不连续: %d-%d 之后是 %d-%d"
                    % (key, prev.from_year, prev.to_year, cur.from_year, cur.to_year)
                )
            else:
                result.passed += 1

        # 断言 2：逐年覆盖 + 端点归属
        lo = ordered[0].from_year
        hi = ordered[-1].to_year
        for year in range(lo, hi + 1):
            result.total += 1
            matches = [t for t in ordered if t.contains(year)]
            if len(matches) != 1:
                result.failures.append(
                    "%s 第 %d 年命中 %d 个区间（应为恰好 1 个）" % (key, year, len(matches))
                )
            else:
                result.passed += 1

        for tier in ordered:
            for probe_year, expect_same in ((tier.from_year, True), (tier.to_year, True)):
                result.total += 1
                matches = [t for t in ordered if t.contains(probe_year)]
                if len(matches) == 1 and matches[0].from_year == tier.from_year:
                    result.passed += 1
                else:
                    result.failures.append(
                        "%s 第 %d 年归属错误（应属 %d-%d）"
                        % (key, probe_year, tier.from_year, tier.to_year)
                    )

        # 断言 3：恰好跳档年归新档（上一档末年的下一年）
        for prev, cur in zip(ordered, ordered[1:]):
            probe_year = prev.to_year + 1
            result.total += 1
            matches = [t for t in ordered if t.contains(probe_year)]
            if len(matches) == 1 and matches[0].from_year == cur.from_year:
                result.passed += 1
            else:
                result.failures.append(
                    "%s 第 %d 年应归新档 %d-%d" % (key, probe_year, cur.from_year, cur.to_year)
                )

    if checked_types == 0:
        result.implemented = False
        result.notes.append("无任何可校验的阶梯条目（分母为 0）—— 本套件无可判定内容")
    return result


# ---------------------------------------------------------------- 真值库装载

def _find_truth_dir(library: RuleLibrary):
    from pathlib import Path

    for base in (library.data_dir, Path(__file__).resolve().parent.parent.parent.parent / "data"):
        candidate = Path(base) / "truth"
        if (candidate / "truth.json").is_file():
            return candidate
    return None


def _load_truth_cases(library: RuleLibrary) -> Optional[List[dict]]:
    truth_dir = _find_truth_dir(library)
    if truth_dir is None:
        return None
    try:
        doc = json.loads((truth_dir / "truth.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return list(doc.get("cases") or [])


def _scalar_entry(library: RuleLibrary, key: str) -> Optional[Decimal]:
    for rs in library.rulesets.values():
        entry = rs.get(key)
        if entry is not None:
            return entry.decimal()
    return None


def _text_entry(library: RuleLibrary, key: str) -> str:
    for rs in library.rulesets.values():
        entry = rs.get(key)
        if entry is not None and entry.value is not None:
            return str(entry.value).strip()
    return ""


def _add_months(d: date, months: int) -> date:
    """自然月推进（细则第 5 条口径；与引擎/生成器同语义，独立落在这里供对账）。"""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, _calendar.monthrange(y, m)[1])
    return date(y, m, day)


def suite_b2_late(library: RuleLibrary) -> CheckResult:
    """B2 滞纳金：真值对账 + 规则驱动端点枚举（跨月累加、上限边界、不足整月零头）。

    规则驱动层从规则包独立推导期望（费率 × 月数、上限边界 1/2/…/grace/grace+1、
    月末日不足取月末的自然月推进），引擎结果与期望逐项断言——
    期望不经引擎产出，防"用被测物校验被测物"。
    """
    result = CheckResult(suite="b2_late")

    rate = _scalar_entry(library, "late.monthly_rate")
    grace_raw = _scalar_entry(library, "late.grace_months")
    month_basis = _text_entry(library, "late.month_basis")
    if rate is None or grace_raw is None or not month_basis:
        result.implemented = False
        result.notes.append("规则包缺 late.monthly_rate / late.grace_months / late.month_basis —— 无可判定内容")
        return result
    grace = int(grace_raw)

    from ..calc.late import LateRequest, compute_late, overdue_months_between

    # ---- 第一层：真值对账 ----
    cases = _load_truth_cases(library)
    if cases is None:
        result.notes.append("真值库不可得（非仓库环境）—— 本轮只跑规则驱动层")
    else:
        late_cases = [c for c in cases if c.get("kind") == "late"]
        if not late_cases:
            result.notes.append("真值库无 late 算例（该类用例未生成）")
        for case in late_cases:
            result.total += 1
            try:
                inputs = case["inputs"]
                expect = case["expect"]
                req = LateRequest(
                    patent_type=parse_patent_type(case["patent_type"]),
                    year=int(case["year"]),
                    due_on=date.fromisoformat(inputs["due_on"]),
                    paid_on=date.fromisoformat(inputs["paid_on"]),
                )
                res = compute_late(library, req)
            except Exception as exc:  # 坏算例按失败计，不中断
                result.failures.append("%s 计算异常: %s" % (case.get("id"), exc))
                continue
            problems = []
            if str(res.surcharge) != expect.get("surcharge"):
                problems.append("surcharge=%s 期望 %s" % (res.surcharge, expect.get("surcharge")))
            if str(res.full_annuity) != expect.get("full_annuity"):
                problems.append("full=%s 期望 %s" % (res.full_annuity, expect.get("full_annuity")))
            if res.overdue_months != inputs.get("overdue_months"):
                problems.append("months=%s 期望 %s" % (res.overdue_months, inputs.get("overdue_months")))
            if res.exceeds_cap != bool(expect.get("exceeds_cap")):
                problems.append("exceeds_cap=%s 期望 %s" % (res.exceeds_cap, expect.get("exceeds_cap")))
            if ("late_exceeds_cap" in res.reasons) != (expect.get("reason_code") == "late_exceeds_cap"):
                problems.append("reason_code 不符: %s" % (res.reasons,))
            if res.month_basis != expect.get("month_basis"):
                problems.append("month_basis=%s 期望 %s" % (res.month_basis, expect.get("month_basis")))
            if res.grace_months != expect.get("grace_months"):
                problems.append("grace=%s 期望 %s" % (res.grace_months, expect.get("grace_months")))
            if problems:
                result.failures.append("%s: %s" % (case.get("id"), "; ".join(problems)))
            else:
                result.passed += 1

    # ---- 第二层：规则驱动端点枚举 ----
    entry = None
    for rs in library.rulesets.values():
        entry = rs.get("annuity.invention")
        if entry is not None:
            break
    if entry is None:
        result.notes.append("规则包无 annuity.invention 条目 —— 规则驱动层该类用例未生成")
        return result

    from ..calc.annuity import tiers_from_entry

    tiers = tiers_from_entry(entry)
    if not tiers:
        result.notes.append("annuity.invention 阶梯为空 —— 规则驱动层该类用例未生成")
        return result

    tier = tiers[0]  # 第 1 档年度做枚举基底（端点行为与档位无关）
    year = tier.from_year
    full = tier.amount

    def _run(due: date, paid: date) -> "object":
        return compute_late(library, LateRequest(PatentType.INVENTION, year, due, paid))

    for months in list(range(1, grace + 2)) + [0]:
        result.total += 1
        expect_surcharge = quantize_amount(full * rate * Decimal(months))
        expect_exceeds = months > grace
        due = date(2026, 1, 31)
        paid = _add_months(due, months) if months else due
        res = _run(due, paid)
        if (str(res.surcharge) == str(expect_surcharge)
                and res.exceeds_cap is expect_exceeds
                and res.overdue_months == months
                and ("late_exceeds_cap" in res.reasons) is expect_exceeds
                and res.computed is True):
            result.passed += 1
        else:
            result.failures.append(
                "端点枚举 %d 月: surcharge=%s 期望 %s, exceeds=%s 期望 %s, months=%s"
                % (months, res.surcharge, expect_surcharge, res.exceeds_cap, expect_exceeds, res.overdue_months)
            )

    # 月数口径独立对账（含月末零头语义）：31 日 + N 自然月的"相应日"为 N 月 31 日，
    # 月末不足时取月末（细则第 5 条）—— 故 1-31 → 8-01 仍是 6 个整月（8-31 才是第 7 个）
    for (due_iso, paid_iso, expect_months) in (
        ("2026-01-31", "2026-02-28", 1),   # 月末日不足取月末 → 恰 1 整月
        ("2026-01-31", "2026-02-27", 0),   # 差一天 → 零头不计
        ("2026-01-31", "2026-07-31", 6),   # 恰好上限
        ("2026-01-31", "2026-08-01", 6),   # 第 7 个整月要到 8-31，此前零头不计
        ("2026-01-31", "2026-08-31", 7),   # 相应日 = 8-31 → 第 7 个整月
        ("2026-05-04", "2019-05-04", 0),   # 同日不算逾期（paid<=due 已由引擎另行短路）
    ):
        result.total += 1
        months, _ = overdue_months_between(date.fromisoformat(due_iso), date.fromisoformat(paid_iso), month_basis)
        if months == expect_months:
            result.passed += 1
        else:
            result.failures.append(
                "月数口径 %s→%s（%s）: %d 月，期望 %d" % (due_iso, paid_iso, month_basis, months, expect_months)
            )

    return result


def suite_b3_reduction(library: RuleLibrary) -> CheckResult:
    """B3 费减：真值对账 + 规则驱动边界枚举（恰好阈值 / 略低 / 共同主体 1&2 / 历史锚点）。

    规则驱动层从规则包阈值独立构造边界输入并推导期望
    （资格=严格小于、比例取 sole/combined 条目、实缴=full×(1-rate)），
    引擎结果与期望逐项断言。
    """
    result = CheckResult(suite="b3_reduction")

    keys = {
        "monthly": "reduction.threshold.individual_monthly_income",
        "annual": "reduction.threshold.individual_annual_income",
        "entity": "reduction.threshold.entity_taxable_income",
        "anchor": "reduction.threshold.effective_from",
        "sole": "reduction.rate.sole",
        "combined": "reduction.rate.combined",
        "open": "reduction.open_license_discount",
    }
    values = {k: _scalar_entry(library, v) for k, v in keys.items()}
    anchor_text = _text_entry(library, keys["anchor"])
    if any(values[k] is None for k in ("monthly", "annual", "entity", "sole", "combined")) or not anchor_text:
        result.implemented = False
        result.notes.append("规则包缺费减阈值/比例条目 —— 无可判定内容")
        return result
    if values["open"] is None:
        result.notes.append("规则包无开放许可减免条目 —— 多政策候选只含费减")

    from ..calc.reduction import ReductionRequest, compute_reduction, parse_applicants

    # ---- 第一层：真值对账 ----
    cases = _load_truth_cases(library)
    if cases is None:
        result.notes.append("真值库不可得（非仓库环境）—— 本轮只跑规则驱动层")
    else:
        red_cases = [c for c in cases if c.get("kind") == "reduction"]
        if not red_cases:
            result.notes.append("真值库无 reduction 算例（该类用例未生成）")
        for case in red_cases:
            result.total += 1
            try:
                expect = case["expect"]
                req = ReductionRequest(
                    patent_type=parse_patent_type(case["patent_type"]),
                    year=int(case["year"]),
                    as_of_year=int(case["as_of_year"]),
                    applicants=parse_applicants(case["applicants"]),
                    open_license=bool(case.get("open_license")),
                )
                res = compute_reduction(library, req)
            except Exception as exc:
                result.failures.append("%s 计算异常: %s" % (case.get("id"), exc))
                continue
            cands = [{"policy": c.policy, "rate": str(c.rate), "amount": str(c.amount)} for c in res.candidates]
            problems = []
            if res.eligible != expect.get("eligible"):
                problems.append("eligible=%s 期望 %s" % (res.eligible, expect.get("eligible")))
            if cands != expect.get("candidates"):
                problems.append("candidates=%s 期望 %s" % (cands, expect.get("candidates")))
            chosen_amount = str(res.chosen.amount) if res.chosen else None
            if chosen_amount != (expect.get("chosen") or {}).get("amount"):
                problems.append("chosen=%s 期望 %s" % (chosen_amount, (expect.get("chosen") or {}).get("amount")))
            payable = str(res.payable) if res.payable is not None else None
            if payable != expect.get("payable"):
                problems.append("payable=%s 期望 %s" % (payable, expect.get("payable")))
            if {k: str(v) for k, v in res.thresholds.items()} != expect.get("thresholds"):
                problems.append("thresholds 不符: %s" % dict(res.thresholds))
            if res.no_double_benefit_applied != bool(expect.get("no_double_benefit_applied")):
                problems.append("no_double_benefit_applied=%s 期望 %s"
                                % (res.no_double_benefit_applied, expect.get("no_double_benefit_applied")))
            if problems:
                result.failures.append("%s: %s" % (case.get("id"), "; ".join(problems)))
            else:
                result.passed += 1

    # ---- 第二层：规则驱动边界枚举 ----
    def _thresholds(as_of_year: int) -> Dict[str, Decimal]:
        anchor_year = int(anchor_text[:4])
        suffix = ".prev" if as_of_year < anchor_year else ""
        return {
            "monthly": _scalar_entry(library, keys["monthly"] + suffix),
            "annual": _scalar_entry(library, keys["annual"] + suffix),
            "entity": _scalar_entry(library, keys["entity"] + suffix),
        }

    def _check(tag: str, as_of_year: int, applicants: List[dict], expect_eligible: bool,
               expect_rate: Optional[Decimal], open_license: bool = False,
               patent_type: PatentType = PatentType.INVENTION, year: int = 5):
        result.total += 1
        thresholds = _thresholds(as_of_year)
        if any(v is None for v in thresholds.values()):
            result.notes.append("%s: 历史阈值条目缺失，该用例未生成" % tag)
            result.total -= 1
            return
        req = ReductionRequest(
            patent_type=patent_type, year=year, as_of_year=as_of_year,
            applicants=parse_applicants(applicants), open_license=open_license,
        )
        res = compute_reduction(library, req)
        if not res.computed:
            result.failures.append("%s: 未判定（reasons=%s）" % (tag, res.reasons))
            return
        problems = []
        if res.eligible is not expect_eligible:
            problems.append("eligible=%s 期望 %s" % (res.eligible, expect_eligible))
        if expect_rate is not None and str(res.reduction_rate) != str(expect_rate):
            problems.append("rate=%s 期望 %s" % (res.reduction_rate, expect_rate))
        if expect_eligible:
            expect_payable = quantize_amount(res.full_annuity * (Decimal(1) - expect_rate))
            if str(res.payable) != str(expect_payable):
                problems.append("payable=%s 期望 %s" % (res.payable, expect_payable))
        elif res.payable is not None and not open_license:
            problems.append("不合格且无开放许可时 payable 应为 None，得到 %s" % res.payable)
        if problems:
            result.failures.append("%s: %s" % (tag, "; ".join(problems)))
        else:
            result.passed += 1

    def _person(monthly: Decimal, annual: Decimal) -> dict:
        return {"kind": "individual", "monthly_avg_income": str(monthly), "annual_income": str(annual)}

    cur = _thresholds(2026)
    penny = Decimal("0.01")
    one = Decimal(1)

    # 恰好等于阈值 → 不合格（严格小于；个人为"月均或年收入"任一低于即可，
    # 故恰等于场景须两维同时等于才构成"恰好边界"）
    _check("个人两维恰等于阈值", 2026, [_person(cur["monthly"], cur["annual"])], False, None)
    _check("单位恰等于所得额阈值", 2026,
           [{"kind": "entity", "taxable_income": str(cur["entity"])}], False, None)
    # 略低 → 合格
    _check("个人略低", 2026,
           [_person(cur["monthly"] - penny, cur["annual"] - penny)], True, values["sole"])
    _check("单位略低", 2026,
           [{"kind": "entity", "taxable_income": str(cur["entity"] - penny)}], True, values["sole"])
    # 共同主体 1&2
    _check("共同主体均略低", 2026,
           [_person(cur["monthly"] - penny, cur["annual"] - penny),
            _person(cur["monthly"] - penny, cur["annual"] - penny)], True, values["combined"])
    _check("共同主体其一恰等于", 2026,
           [_person(cur["monthly"] - penny, cur["annual"] - penny),
            _person(cur["monthly"], cur["annual"])], False, None)
    # 历史锚点（.prev 口径）
    prev = _thresholds(2019 - 1)
    if all(v is not None for v in prev.values()):
        _check("历史锚点略低", 2019 - 1,
               [_person(prev["monthly"] - penny, prev["annual"] - penny)], True, values["sole"])
        _check("历史锚点恰等于", 2019 - 1,
               [_person(prev["monthly"], prev["annual"])], False, None)
    else:
        result.notes.append("历史阈值条目缺失，历史锚点用例未生成")

    return result


def suite_b4_portfolio(library: RuleLibrary) -> CheckResult:
    """B4 合成组合（M3 实装）。"""
    return CheckResult(suite="b4_portfolio", implemented=False, notes=["M3 实装：合成组合真值全量重算与跨轮对账"])


SUITES: Dict[str, Callable[[RuleLibrary], CheckResult]] = {
    "b1_ladder": suite_b1_ladder,
    "b2_late": suite_b2_late,
    "b3_reduction": suite_b3_reduction,
    "b4_portfolio": suite_b4_portfolio,
}

SUITE_ORDER: Tuple[str, ...] = ("b1_ladder", "b2_late", "b3_reduction", "b4_portfolio")


def suite_names() -> Tuple[str, ...]:
    return SUITE_ORDER


def run_suites(
    library: RuleLibrary,
    only: Sequence[str] = (),
) -> Tuple[Dict[str, CheckResult], List[str], List[str]]:
    """运行基准。

    :return: (结果表, 达标判定表, 未实装套件名)
    """
    if only:
        unknown = [name for name in only if name not in SUITES]
        if unknown:
            raise RulesetError(
                "未知基准套件: %s（可用: %s）" % (", ".join(unknown), ", ".join(SUITE_ORDER)),
                reason_code="usage_error",
            )
        names = tuple(n for n in SUITE_ORDER if n in only)
    else:
        names = SUITE_ORDER

    results: Dict[str, CheckResult] = {}
    verdicts: List[str] = []
    implemented: List[str] = []

    for name in names:
        res = SUITES[name](library)
        results[name] = res
        if not res.implemented:
            # 未实装套件不参与达标判定（"没测"不是"未达标"，也不是"达标"）
            continue
        implemented.append(name)
        threshold = library.benchmark_threshold(name)
        min_rate = Decimal(str(threshold.get("min_pass_rate", "1.0")))
        max_fail = int(threshold.get("max_fail", 0))
        ok = res.pass_rate >= min_rate and len(res.failures) <= max_fail
        verdicts.append("%s=%s" % (name, "达标" if ok else "未达标"))

    return results, verdicts, implemented
