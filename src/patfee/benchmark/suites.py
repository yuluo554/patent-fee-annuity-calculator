"""基准套件实现。

新增套件必须同时注册进 :data:`SUITES`，未知名走 exit 2（不许静默跳过）。
每套件配探活（可证伪）测试：注入缺陷后必须报未达标。

M2 起 B2/B3 为**两层**：

1. **真值层** —— 读 ``data/truth/truth.json`` 冻结算例，引擎重算逐项对账；
   真值库不可得（非仓库环境）时显式留 note，不冒充分母；
2. **规则驱动层** —— 从规则包参数独立推导端点期望（套件内自算，不经引擎），
   引擎结果与期望逐项断言。分母不许悄悄做小。

M3 起 B4 为**三层**（组合全量重算 / controls 误报对照集 / 跨轮对账口径），
对照集只读 truth manifest 的 ``controls`` 声明，不自行挑选。
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


def _load_truth_doc(library: RuleLibrary) -> Optional[dict]:
    """读整份真值库（含 controls 对照集声明）—— B4 只读该声明，不自行挑选对照档案。"""
    truth_dir = _find_truth_dir(library)
    if truth_dir is None:
        return None
    try:
        return json.loads((truth_dir / "truth.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_truth_portfolio(library: RuleLibrary) -> Optional[dict]:
    truth_dir = _find_truth_dir(library)
    if truth_dir is None:
        return None
    try:
        return json.loads((truth_dir / "portfolio.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


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
    """B4 合成组合（M3）：真值全量重算对账 + 跨轮对账口径 + 误报对照集。

    三层断言（分母不许做小）：

    1. **组合全量重算** —— ``data/truth/portfolio.json`` 的 18 件专利逐件走
       年费阶梯引擎（按合成 ``as_of_date`` 推当前年度），金额与规则包阶梯对账；
    2. **误报对照集** —— 只读 truth manifest 的 ``controls`` 声明：``clean``
       件（按期缴费）排期必须零命中（kind=settled 且不进 unpaid），
       ``degrade`` 件（超上限）必须降级为 warning 而非 fail；
    3. **跨轮对账口径** —— 用对照集缴费记录构造两轮台账，``compare_rounds``
       的三集合与辅助集必须与构造语义一致（单一实现源的行为锁定）。

    真值库不可得（非仓库环境）时显式留 note，不冒充分母。
    """
    result = CheckResult(suite="b4_portfolio")

    portfolio = _load_truth_portfolio(library)
    truth = _load_truth_doc(library)
    if portfolio is None:
        result.implemented = False
        result.notes.append("合成组合真值库不可得（非仓库环境）—— 无可判定内容")
        return result

    from ..calc.portfolio import (
        KIND_FAILED,
        KIND_NOT_DUE,
        KIND_SETTLED,
        KIND_UNCOMPUTED,
        KIND_UNPAID,
        PortfolioRequest,
        compare_rounds,
        scan_portfolio,
    )

    as_of = str(portfolio.get("as_of_date") or "")
    try:
        today = date.fromisoformat(as_of)
    except ValueError:
        result.implemented = False
        result.notes.append("合成组合 as_of_date 非法: %r" % (as_of,))
        return result

    patents = {p["patent_no"]: p for p in portfolio.get("patents") or []}
    payments = portfolio.get("payments") or []

    # ---- 第一层：全部缴费记录重算排期，逐条对账 ----
    sources = []
    for idx, pay in enumerate(payments):
        patent = patents.get(pay.get("patent_no")) or {}
        item = dict(pay)
        item["patent_type"] = patent.get("patent_type")
        sources.append(("payment[%d]" % idx, item))
    request = PortfolioRequest(
        sources=tuple(sources), today=today, window_months=_B4_WINDOW_MONTHS
    )
    scan = scan_portfolio(request, library)

    # 期望金额锚定**冻结真值**（不经引擎、不读现行规则包）：
    # 按类型找真值年金算例，用其 tier_from/tier_to 判定缴费年度所在档，
    # 期望 = 该算例生成时冻结的 amount —— 探活注入（改阶梯）才会被检出，
    # 防"期望与引擎读同一份（被改的）规则包"的自证。
    annuity_expect = {}
    for case in (truth or {}).get("cases") or []:
        if case.get("kind") != "annuity":
            continue
        key = (str(case.get("patent_type")), int(case["expect"]["tier_from"]),
               int(case["expect"]["tier_to"]))
        annuity_expect.setdefault(key, case["expect"]["amount"])

    def _expect_amount(patent_type, year):
        if patent_type is None or year is None:
            return None
        for (ptype, lo, hi), amount in annuity_expect.items():
            if ptype == str(patent_type) and lo <= int(year) <= hi:
                return quantize_amount(Decimal(str(amount)))
        return None

    for entry, (source, item) in zip(scan.entries, sources):
        result.total += 1
        if entry.kind == KIND_FAILED:
            result.failures.append("%s: 合成缴费记录被判失败（%s）" % (entry.id, entry.reason))
            continue
        if entry.kind == KIND_UNCOMPUTED:
            result.failures.append("%s: 未判定（%s）" % (entry.id, "; ".join(entry.reasons)))
            continue
        if entry.kind != KIND_SETTLED:
            # 按期缴纳的合成记录统一 paid_on < due_on → settled；
            # 走到 not_due/unpaid 说明 paid_on 解析或分类语义漂移
            result.failures.append(
                "%s: kind=%s（合成按期记录应为 settled）" % (entry.id, entry.kind)
            )
            continue
        expect_amount = _expect_amount(item.get("patent_type"), item.get("year"))
        if expect_amount is not None and entry.amount != expect_amount:
            result.failures.append(
                "%s: 年费 %s 期望 %s（阶梯独立推导）"
                % (entry.id, entry.amount, expect_amount)
            )
            continue
        result.passed += 1

    # 失败隔离：无 patent_no / 坏类型的条目必须单列 failed 且不影响其余件
    bad_sources = (
        ("bad[0]", None),
        ("bad[1]", {"patent_type": "invention", "year": 5, "due_on": "2026-01-01"}),
        ("bad[2]", {"patent_no": "990000000001SYN", "patent_type": "unicorn",
                    "year": 5, "due_on": "2026-01-01"}),
    )
    bad_scan = scan_portfolio(
        PortfolioRequest(sources=bad_sources, today=today, window_months=_B4_WINDOW_MONTHS),
        library,
    )
    result.total += 1
    failed_ids = {e.source for e in bad_scan.failed}
    if len(bad_scan.failed) == len(bad_sources) and failed_ids == {"bad[0]", "bad[1]", "bad[2]"}:
        result.passed += 1
    else:
        result.failures.append("失败隔离失效: failed=%s" % failed_ids)
    result.total += 1
    if all(e.kind == KIND_FAILED for e in bad_scan.entries if e.source.startswith("bad[")) \
            and len(bad_scan.entries) == len(bad_sources):
        result.passed += 1
    else:
        result.failures.append("失败件未与正常件同列表留痕或条目数不符")

    # ---- 第二层：误报对照集（只读 controls 声明）----
    controls = (truth or {}).get("controls") or {}
    clean_ids = list(controls.get("clean") or [])
    degrade_ids = list(controls.get("degrade") or [])
    if not clean_ids:
        result.notes.append("真值库未声明 controls.clean（对照集未生成）")
    by_case_id = {c.get("id"): c for c in (truth or {}).get("cases") or []}

    # clean 声明的 payment.* 件：重算必须 settled（零命中 = 无 unpaid / 无 failed）
    clean_payment_count = 0
    for cid in clean_ids:
        parts = cid.split(".")
        if len(parts) != 3 or parts[0] != "payment":
            continue
        no, y = parts[1], parts[2]
        patent = patents.get(no)
        pay = next((p for p in payments
                    if p.get("patent_no") == no and "y%02d" % p.get("year", 0) == y), None)
        if patent is None or pay is None:
            continue
        clean_payment_count += 1
        result.total += 1
        item = dict(pay)
        item["patent_type"] = patent.get("patent_type")
        entry = scan_portfolio(
            PortfolioRequest(sources=(("ctl", item),), today=today,
                             window_months=_B4_WINDOW_MONTHS),
            library,
        ).entries[0]
        if entry.kind == KIND_SETTLED:
            result.passed += 1
        else:
            result.failures.append("clean 件 %s 应零命中，实得 kind=%s" % (cid, entry.kind))
    if clean_payment_count == 0:
        result.notes.append("controls.clean 无可对应的组合缴费记录（该类用例未生成）")

    # degrade 声明的件（超上限滞纳金）：走滞纳金引擎必须降级 warning 而非拦截
    from ..calc.late import LateRequest, compute_late

    for cid in degrade_ids:
        case = by_case_id.get(cid)
        if case is None or case.get("kind") != "late":
            result.notes.append("degrade 件 %s 无对应算例（该类用例未生成）" % cid)
            continue
        result.total += 1
        inputs = case.get("inputs") or {}
        try:
            res = compute_late(library, LateRequest(
                patent_type=parse_patent_type(case["patent_type"]),
                year=int(case["year"]),
                due_on=date.fromisoformat(inputs["due_on"]),
                paid_on=date.fromisoformat(inputs["paid_on"]),
            ))
        except Exception as exc:
            result.failures.append("degrade 件 %s 计算异常: %s" % (cid, exc))
            continue
        if res.computed and res.exceeds_cap and res.surcharge is not None:
            result.passed += 1
        else:
            result.failures.append(
                "degrade 件 %s 应照算金额并超上限降级（computed=%s exceeds=%s）"
                % (cid, res.computed, res.exceeds_cap)
            )

    # ---- 第三层：跨轮对账口径（compare_rounds 单一实现源行为锁定）----
    settled_pays = [p for p in payments if p.get("on_time")]
    baseline: List[dict] = []
    current: List[dict] = []
    for pay in settled_pays:
        baseline.append({
            "patent_no": pay.get("patent_no"), "year": pay.get("year"),
            "due_on": pay.get("due_on"), "paid_on": "",
        })
        current.append({
            "patent_no": pay.get("patent_no"), "year": pay.get("year"),
            "due_on": pay.get("due_on"), "paid_on": pay.get("paid_on") or "",
        })
    if not baseline:
        result.notes.append("组合无按期缴费记录 —— 对账口径层该类用例未生成")
    rec = compare_rounds(baseline, current)
    for key in baseline:
        result.total += 1
        pid = "%s#y%s" % (key["patent_no"], key["year"])
        if pid in rec.settled and pid not in rec.new_due and pid not in rec.vanished:
            result.passed += 1
        else:
            result.failures.append("对账口径: %s 应配对 settled，实得 new_due=%s settled=%s vanished=%s"
                                   % (pid, pid in rec.new_due, pid in rec.settled, pid in rec.vanished))
    # 期限变化必须报 content_changed 且不退化成"新增+消失"（D13）
    if current:
        drifted = [dict(current[0])]
        drifted[0]["due_on"] = _shift_year(current[0].get("due_on"))
        rec2 = compare_rounds([baseline[0]], drifted)
        result.total += 1
        pid = "%s#y%s" % (current[0]["patent_no"], current[0]["year"])
        if pid in rec2.content_changed and pid not in rec2.new_due and pid not in rec2.vanished:
            result.passed += 1
        else:
            result.failures.append(
                "对账口径: %s 期限变化应报 content_changed（实得 changed=%s new=%s vanished=%s）"
                % (pid, pid in rec2.content_changed, pid in rec2.new_due, pid in rec2.vanished)
            )

    if result.total == 0:
        result.implemented = False
        result.notes.append("组合重算与对照集均无可用用例 —— 本套件无可判定内容")
    return result


def _shift_year(iso: Optional[str]) -> str:
    """把 ISO 日期推一年（对账口径用例：期限漂移 → content_changed）。"""
    if not iso:
        return ""
    d = date.fromisoformat(str(iso))
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:
        # 2-29 → 平年回退 2-28（仅测试用例构造，非政策语义）
        return d.replace(year=d.year + 1, day=d.day - 1).isoformat()


SUITES: Dict[str, Callable[[RuleLibrary], CheckResult]] = {
    "b1_ladder": suite_b1_ladder,
    "b2_late": suite_b2_late,
    "b3_reduction": suite_b3_reduction,
    "b4_portfolio": suite_b4_portfolio,
}

SUITE_ORDER: Tuple[str, ...] = ("b1_ladder", "b2_late", "b3_reduction", "b4_portfolio")

# B4 预警窗口（结构参数，非政策数值；窗口语义见 calc/portfolio.py）
_B4_WINDOW_MONTHS = 3


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
