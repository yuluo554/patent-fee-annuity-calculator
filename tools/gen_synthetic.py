"""合成专利组合与真值库生成器 —— ``data/truth/`` 的**唯一写入者**。

纪律（plan/05 §1.3、data/README §四）：

* **确定性**：自研 splitmix64 RNG + 固定 seed；**禁** stdlib ``random``、**禁** set
  迭代序、**禁**系统时钟。产物含 ``generated_at`` 固定哨兵值，两次运行**逐字节一致**。
* **零真实信息**：专利号走测试号段 ``99000000…SYN``、统一社会信用代码走
  ``90000000…SYN``、主体名一律带"（合成）"。不得出现真实专利号/申请人/代理机构/缴费记录。
* **植入真值**：期望年费 / 期望滞纳金 / 期望费减资格与减免额 / 期望到期日随组合入库，
  供**独立实现路径**（M2 引擎）对账。
* **算例覆盖**：三类专利各自的阶梯首末年度与跳档年；滞纳金逾期 1/2/6 月与超上限；
  费减边界（月均恰好 5000 / 应纳税所得额恰好 100 万 / 共同主体数 1 与 2）；多政策择一。
* **误报对照集**：显式声明"应零命中"的干净档案与"应降级（warning 而非 fail）"的档案；
  基准层只读该声明，不自行挑选对照档案。
* **政策值只来自规则包**：本脚本从 ``data/rules/`` 读费率与阈值（单一事实源），
  不在此处复写政策数值；本脚本产出的**是期望值**（被断言的一方），故**不在零字面量
  门禁的扫描面内**（见 plan/06 D17）。

用法::

    python tools/gen_synthetic.py            # 生成 data/truth/ 三份产物
    python tools/gen_synthetic.py --check    # 只比对不落盘，一致则打印 SYNTHETIC_FROZEN_OK
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from patfee.console import ensure_utf8_stdio  # noqa: E402
from patfee.domain.models import quantize_amount  # noqa: E402
from patfee.rules.loader import load_library  # noqa: E402

ensure_utf8_stdio()

TRUTH_DIR = ROOT / "data" / "truth"

# 固定哨兵：确定性优先，产物不得含当前时间。
GENERATED_AT = "1970-01-01T00:00:00Z"
# 基准日（与规则包 retrieved 同批）
AS_OF_DATE = "2026-10-14"
# 规则包年度锚点（半年切换点，本库只在锚点前后各取整年样本，避免年中歧义）
ANCHOR_316 = "2019-07-01"
# seed 由固定字串派生（sha256 跨平台稳定），避免留一个无来由的魔数。
SEED_SOURCE = b"patfee-synthetic-v1"


# --------------------------------------------------------------- 确定性 RNG

_MASK = (1 << 64) - 1


class SplitMix64:
    """自研确定性 PRNG（splitmix64）。禁止 stdlib ``random`` —— 其算法不收保证。"""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = seed & _MASK

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        return z ^ (z >> 31)

    def below(self, n: int) -> int:
        if n <= 0:
            raise ValueError("below(n) 要求 n > 0")
        return self.next_u64() % n

    def between(self, lo: int, hi: int) -> int:
        """闭区间 [lo, hi] 内取整。"""
        return lo + self.below(hi - lo + 1)

    def choice(self, seq: Sequence[Any]) -> Any:
        if not seq:
            raise ValueError("choice 收到空序列")
        return seq[self.below(len(seq))]


# --------------------------------------------------------------- 日期工具

def add_months(d: date, months: int) -> date:
    """自然月推进：月末日不足时取该月最后一日（细则第 5 条口径）。"""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def add_years(d: date, years: int) -> date:
    return add_months(d, years * 12)


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# --------------------------------------------------------------- 规则读取

class RuleView:
    """从规则包取政策参数（单一事实源），供本生成器独立实现计算。"""

    def __init__(self, library) -> None:
        self._lib = library

    def entry(self, key: str):
        for rs in self._lib.rulesets.values():
            e = rs.get(key)
            if e is not None:
                return e
        raise KeyError("规则包缺条目: %s" % key)

    def tiers(self, patent_type: str) -> List[Tuple[int, int, Decimal]]:
        entry = self.entry("annuity." + patent_type)
        out = []
        for raw in entry.tiers():
            out.append((int(raw["from_year"]), int(raw["to_year"]), _dec(raw["amount"])))
        return sorted(out, key=lambda t: t[0])

    def scalar(self, key: str) -> Decimal:
        value = self.entry(key).decimal()
        if value is None:
            raise ValueError("规则条目 %s 值为空，无法生成真值" % key)
        return value

    def text(self, key: str) -> str:
        entry = self.entry(key)
        return str(entry.value)

    def key_of(self, patent_type: str) -> str:
        return "annuity." + patent_type

    def coordinate(self) -> dict:
        return self._lib.coordinate()


def find_tier(tiers: Sequence[Tuple[int, int, Decimal]], year: int):
    """独立实现的取档：双闭区间，恰好跳档年归新档。"""
    for lo, hi, amount in tiers:
        if lo <= year <= hi:
            return (lo, hi, amount)
    return None


# --------------------------------------------------------------- 合成组合

PATENT_TYPES = ("invention", "utility_model", "design")
TYPE_LABEL = {
    "invention": "发明",
    "utility_model": "实用新型",
    "design": "外观设计",
}

SUBJECTS: List[dict] = [
    {"id": "S001", "kind": "individual", "name": "示例个人 A（合成）"},
    {"id": "S002", "kind": "individual", "name": "示例个人 B（合成）"},
    {"id": "S003", "kind": "entity", "name": "示例科技（合成）有限公司"},
    {"id": "S004", "kind": "entity", "name": "示例制造（合成）有限公司"},
    {"id": "S005", "kind": "entity", "name": "示例研究院（合成）"},
    {"id": "S006", "kind": "individual", "name": "示例个人 C（合成）"},
]

SUBJECT_USCC = {
    "S003": "90000000000000001SYN",
    "S004": "90000000000000002SYN",
    "S005": "90000000000000003SYN",
}

PATENT_COUNT = 18


def build_portfolio(rng: SplitMix64) -> dict:
    """合成组合：18 件虚构专利（三类循环）+ 6 个虚构主体 + 部分缴费记录。"""
    patents: List[dict] = []
    for i in range(PATENT_COUNT):
        ptype = PATENT_TYPES[i % len(PATENT_TYPES)]
        applied = date(rng.between(2014, 2022), rng.between(1, 12), rng.between(1, 28))
        grant_lag_months = 24 if ptype == "invention" else 12
        granted = add_months(applied, grant_lag_months)
        patents.append({
            "patent_no": "99%010dSYN" % (i + 1),
            "title": "一种示例%s装置（合成）" % TYPE_LABEL[ptype],
            "patent_type": ptype,
            "owner_id": SUBJECTS[i % len(SUBJECTS)]["id"],
            "applied_on": applied.isoformat(),
            "granted_on": granted.isoformat(),
        })

    payments: List[dict] = []
    for idx, patent in enumerate(patents):
        # 前 6 件记为"按期缴清"，其余留空（供 M3 组合排期与对账使用）
        if idx < 6:
            applied = date.fromisoformat(patent["applied_on"])
            granted = date.fromisoformat(patent["granted_on"])
            grant_year = granted.year - applied.year + 1
            for year in range(1, grant_year + 1):
                due = add_years(applied, year - 1)
                payments.append({
                    "patent_no": patent["patent_no"],
                    "year": year,
                    "due_on": due.isoformat(),
                    "paid_on": add_months(due, -1).isoformat(),
                    "on_time": True,
                    "note": "合成记录：按期缴纳（误报对照用）",
                })
    return {
        "schema": "patfee.portfolio/v1",
        "generated_by": "tools/gen_synthetic.py",
        "generated_at": GENERATED_AT,
        "as_of_date": AS_OF_DATE,
        "disclaimer": "全部专利号、主体名与缴费记录均为虚构合成数据，不含任何真实信息。",
        "subjects": SUBJECTS,
        "subject_uscc": SUBJECT_USCC,
        "patents": patents,
        "payments": payments,
    }


# --------------------------------------------------------------- 真值构造

def _amount(amount: Decimal) -> str:
    return str(quantize_amount(amount))


def build_annuity_cases(view: RuleView, portfolio: dict) -> List[dict]:
    """阶梯边界档案：每类专利**每个档的首年与末年**各一条（含恰好跳档年）。"""
    base = {p["patent_type"]: p for p in portfolio["patents"]}
    cases: List[dict] = []
    for ptype in PATENT_TYPES:
        patent = base[ptype]
        tiers = view.tiers(ptype)
        probe_years: List[int] = []
        for lo, hi, _ in tiers:
            probe_years.extend([lo, hi])
        for year in sorted(set(probe_years)):
            lo, hi, amount = find_tier(tiers, year)
            cases.append({
                "id": "annuity.%s.y%02d" % (ptype, year),
                "kind": "annuity",
                "archive": "ladder_boundary",
                "patent_no": patent["patent_no"],
                "patent_type": ptype,
                "year": year,
                "expect": {
                    "entry_key": view.key_of(ptype),
                    "ruleset": "fee_schedule@v2024",
                    "amount": _amount(amount),
                    "tier_from": lo,
                    "tier_to": hi,
                    "tier_is_first_year": year == lo,
                    "tier_is_last_year": year == hi,
                },
            })
    return cases


def build_late_cases(view: RuleView, portfolio: dict) -> List[dict]:
    """滞纳金档案：逾期 1/2/6 月（含上限）+ 超上限降级件。"""
    rate = view.scalar("late.monthly_rate")
    grace = int(view.scalar("late.grace_months"))
    basis_text = view.text("late.month_basis")
    patent = {p["patent_type"]: p for p in portfolio["patents"]}["invention"]
    year = 5
    _, _, full = find_tier(view.tiers("invention"), year)
    due = add_years(date.fromisoformat(patent["applied_on"]), year - 1)

    cases: List[dict] = []
    for months in (1, 2, grace, grace + 1):
        paid = add_months(due, months)
        surcharge = full * rate * Decimal(months)
        exceeds = months > grace
        case_id = "late.invention.y%02d.m%d" % (year, months)
        cases.append({
            "id": case_id,
            "kind": "late",
            "archive": "late_months" if not exceeds else "late_exceeds_cap",
            "patent_no": patent["patent_no"],
            "patent_type": "invention",
            "year": year,
            "inputs": {
                "due_on": due.isoformat(),
                "paid_on": paid.isoformat(),
                "overdue_months": months,
            },
            "expect": {
                "entry_key": view.key_of("invention"),
                "full_annuity": _amount(full),
                "monthly_rate": str(rate),
                "month_basis": basis_text,
                "grace_months": grace,
                "surcharge": _amount(surcharge),
                "exceeds_cap": exceeds,
                "reason_code": "late_exceeds_cap" if exceeds else None,
            },
        })
    return cases


def _thresholds_for(view: RuleView, as_of_year: int) -> Dict[str, Decimal]:
    """按年度锚定选阈值：< 2019 用 316 号前口径，其余用现行口径。"""
    if as_of_year < 2019:
        return {
            "individual_monthly_income": view.scalar("reduction.threshold.individual_monthly_income.prev"),
            "individual_annual_income": view.scalar("reduction.threshold.individual_annual_income.prev"),
            "entity_taxable_income": view.scalar("reduction.threshold.entity_taxable_income.prev"),
        }
    return {
        "individual_monthly_income": view.scalar("reduction.threshold.individual_monthly_income"),
        "individual_annual_income": view.scalar("reduction.threshold.individual_annual_income"),
        "entity_taxable_income": view.scalar("reduction.threshold.entity_taxable_income"),
    }


def _applicant_eligible(applicant: dict, thresholds: Dict[str, Decimal]) -> bool:
    """单主体资格：个人（月均**或**年收入低于阈值）/ 单位（应纳税所得额低于阈值）。严格小于。"""
    kind = applicant["kind"]
    if kind == "individual":
        monthly = applicant.get("monthly_avg_income")
        annual = applicant.get("annual_income")
        ok = False
        if monthly is not None and _dec(monthly) < thresholds["individual_monthly_income"]:
            ok = True
        if annual is not None and _dec(annual) < thresholds["individual_annual_income"]:
            ok = True
        return ok
    if kind == "entity":
        taxable = applicant.get("taxable_income")
        return taxable is not None and _dec(taxable) < thresholds["entity_taxable_income"]
    raise ValueError("主体类型不识别: %r" % kind)


def _reduction_expect(view: RuleView, case: dict) -> dict:
    """独立实现的费减判定 + 多政策择一（供 M2 引擎对账）。"""
    as_of_year = case["as_of_year"]
    thresholds = _thresholds_for(view, as_of_year)
    applicants = case["applicants"]
    combined = len(applicants) >= 2
    eligible = all(_applicant_eligible(a, thresholds) for a in applicants)

    rate_sole = view.scalar("reduction.rate.sole")
    rate_combined = view.scalar("reduction.rate.combined")
    open_rate = view.scalar("reduction.open_license_discount")
    no_double = view.text("reduction.no_double_benefit")

    tiers = view.tiers(case["patent_type"])
    _, _, full = find_tier(tiers, case["year"])

    candidates: List[dict] = []
    if eligible:
        rate = rate_combined if combined else rate_sole
        candidates.append({
            "policy": "费减",
            "rate": str(rate),
            "amount": _amount(full * (Decimal(1) - rate)),
        })
    if case.get("open_license"):
        candidates.append({
            "policy": "开放许可年费减免",
            "rate": str(open_rate),
            "amount": _amount(full * (Decimal(1) - open_rate)),
        })

    chosen = None
    payable = None
    if candidates:
        # 择最优惠 = 减免额最大 = 实缴额最小
        chosen = min(candidates, key=lambda c: Decimal(c["amount"]))
        payable = chosen["amount"]

    return {
        "entry_key": view.key_of(case["patent_type"]),
        "applicant_count": len(applicants),
        "combined": combined,
        "eligible": eligible,
        "thresholds": {k: str(v) for k, v in thresholds.items()},
        "anchor_316": ANCHOR_316,
        "full_annuity": _amount(full),
        "reduction_rate": str(rate_combined if combined else rate_sole) if eligible else None,
        "candidates": candidates,
        "chosen": chosen,
        "no_double_benefit": no_double,
        "no_double_benefit_applied": len(candidates) > 1,
        "payable": payable,
    }


def build_reduction_cases(view: RuleView) -> List[dict]:
    """费减边界档案：阈值恰好相等 / 略低 / 略高、共同主体数 1 与 2、**跨年度锚点**。"""
    cur = _thresholds_for(view, 2026)
    old = _thresholds_for(view, 2018)

    low = cur["individual_monthly_income"] - Decimal("0.01")
    low_annual = cur["individual_annual_income"] - Decimal("0.01")
    ent_low = cur["entity_taxable_income"] - Decimal("0.01")

    specs: List[dict] = [
        {
            "id": "reduction.sole.individual.below",
            "desc": "单主体个人，月均与年收入均略低于阈值 → 合格，减缴 85%",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "applicants": [{"kind": "individual", "name": "示例个人 A（合成）",
                            "monthly_avg_income": str(low), "annual_income": str(low_annual)}],
        },
        {
            "id": "reduction.sole.individual.at_threshold",
            "desc": "单主体个人，月均与年收入**恰好等于**阈值 → 不合格（『低于』为严格小于）",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "applicants": [{"kind": "individual", "name": "示例个人 A（合成）",
                            "monthly_avg_income": str(cur["individual_monthly_income"]),
                            "annual_income": str(cur["individual_annual_income"])}],
        },
        {
            "id": "reduction.sole.entity.below",
            "desc": "单主体单位，应纳税所得额略低于阈值 → 合格，减缴 85%",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "applicants": [{"kind": "entity", "name": "示例科技（合成）有限公司",
                            "taxable_income": str(ent_low)}],
        },
        {
            "id": "reduction.sole.entity.at_threshold",
            "desc": "单主体单位，应纳税所得额**恰好等于**阈值 → 不合格",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "applicants": [{"kind": "entity", "name": "示例科技（合成）有限公司",
                            "taxable_income": str(cur["entity_taxable_income"])}],
        },
        {
            "id": "reduction.combined.both_below",
            "desc": "两个主体均合格 → 共同主体，减缴 70%",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "applicants": [
                {"kind": "individual", "name": "示例个人 A（合成）",
                 "monthly_avg_income": str(low), "annual_income": str(low_annual)},
                {"kind": "individual", "name": "示例个人 B（合成）",
                 "monthly_avg_income": str(low), "annual_income": str(low_annual)},
            ],
        },
        {
            "id": "reduction.combined.one_at_threshold",
            "desc": "两个主体中一人恰好等于阈值 → 共同主体须**分别**符合，故整体不合格",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "applicants": [
                {"kind": "individual", "name": "示例个人 A（合成）",
                 "monthly_avg_income": str(low), "annual_income": str(low_annual)},
                {"kind": "individual", "name": "示例个人 B（合成）",
                 "monthly_avg_income": str(cur["individual_monthly_income"]),
                 "annual_income": str(cur["individual_annual_income"])},
            ],
        },
        {
            "id": "reduction.combined.entity_and_individual",
            "desc": "单位 + 个人共同申请，均合格 → 减缴 70%",
            "as_of_year": 2026,
            "patent_type": "utility_model", "year": 5,
            "applicants": [
                {"kind": "entity", "name": "示例制造（合成）有限公司",
                 "taxable_income": str(ent_low)},
                {"kind": "individual", "name": "示例个人 C（合成）",
                 "monthly_avg_income": str(low), "annual_income": str(low_annual)},
            ],
        },
        {
            "id": "reduction.anchor.2018.below_old_threshold",
            "desc": "锚定 2018 年：月均 3400 低于 316 号前阈值 3500 → 合格（历史口径）",
            "as_of_year": 2018,
            "patent_type": "invention", "year": 5,
            "applicants": [{"kind": "individual", "name": "示例个人 A（合成）",
                            "monthly_avg_income": str(old["individual_monthly_income"] - Decimal("100")),
                            "annual_income": str(old["individual_annual_income"] - Decimal("1200"))}],
        },
        {
            "id": "reduction.anchor.2018.above_old_threshold",
            "desc": "锚定 2018 年：月均 4000 高于 316 号前阈值 3500 → 不合格（历史口径）",
            "as_of_year": 2018,
            "patent_type": "invention", "year": 5,
            "applicants": [{"kind": "individual", "name": "示例个人 A（合成）",
                            "monthly_avg_income": str(old["individual_monthly_income"] + Decimal("500")),
                            "annual_income": str(old["individual_annual_income"] + Decimal("6000"))}],
        },
        {
            "id": "multi_policy.sole_eligible_and_open_license",
            "desc": "单主体合格 + 开放许可并存 → 择最优惠（减缴 85% 优于 15%），不叠加",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "open_license": True,
            "applicants": [{"kind": "individual", "name": "示例个人 A（合成）",
                            "monthly_avg_income": str(low), "annual_income": str(low_annual)}],
        },
        {
            "id": "multi_policy.ineligible_but_open_license",
            "desc": "单主体不合格 + 开放许可 → 只有 15% 可用（证明择一是按候选集，不是固定费减）",
            "as_of_year": 2026,
            "patent_type": "invention", "year": 5,
            "open_license": True,
            "applicants": [{"kind": "entity", "name": "示例科技（合成）有限公司",
                            "taxable_income": str(cur["entity_taxable_income"])}],
        },
        {
            "id": "multi_policy.combined_and_open_license",
            "desc": "共同主体合格（70%）+ 开放许可（15%）→ 择 70%，不叠加",
            "as_of_year": 2026,
            "patent_type": "design", "year": 3,
            "open_license": True,
            "applicants": [
                {"kind": "individual", "name": "示例个人 A（合成）",
                 "monthly_avg_income": str(low), "annual_income": str(low_annual)},
                {"kind": "individual", "name": "示例个人 B（合成）",
                 "monthly_avg_income": str(low), "annual_income": str(low_annual)},
            ],
        },
    ]

    cases: List[dict] = []
    for spec in specs:
        expect = _reduction_expect(view, spec)
        cases.append({
            "id": spec["id"],
            "kind": "reduction",
            "archive": "multi_policy" if spec.get("open_license") else "reduction_boundary",
            "desc": spec["desc"],
            "as_of_year": spec["as_of_year"],
            "patent_type": spec["patent_type"],
            "year": spec["year"],
            "open_license": bool(spec.get("open_license")),
            "applicants": spec["applicants"],
            "expect": expect,
        })
    return cases


def build_truth(view: RuleView, portfolio: dict) -> dict:
    cases: List[dict] = []
    cases.extend(build_annuity_cases(view, portfolio))
    cases.extend(build_late_cases(view, portfolio))
    cases.extend(build_reduction_cases(view))

    by_archive: Dict[str, int] = {}
    for case in cases:
        by_archive[case["archive"]] = by_archive.get(case["archive"], 0) + 1

    clean = [
        c["id"] for c in cases
        if c["kind"] == "late" and not c["expect"]["exceeds_cap"]
    ]
    degrade = [
        c["id"] for c in cases
        if c["kind"] == "late" and c["expect"]["exceeds_cap"]
    ]
    clean.extend(
        "payment.%s.y%02d" % (p["patent_no"], pay["year"])
        for p in portfolio["patents"][:6]
        for pay in portfolio["payments"]
        if pay["patent_no"] == p["patent_no"]
    )

    return {
        "schema": "patfee.truth/v1",
        "generated_by": "tools/gen_synthetic.py",
        "generated_at": GENERATED_AT,
        "as_of_date": AS_OF_DATE,
        "seed_source": SEED_SOURCE.decode("ascii"),
        "seed": str(int.from_bytes(hashlib.sha256(SEED_SOURCE).digest()[:8], "big")),
        "rules_coordinate": view.coordinate(),
        "controls": {
            "note": "误报对照集：基准层只读本声明，不自行挑选对照档案。"
                    "clean = 应零命中；degrade = 应报 warning（不是 fail）。",
            "clean": sorted(clean),
            "degrade": sorted(degrade),
            "clean_basis": "按期缴纳且金额正确的合成记录 / 未超滞纳金上限的逾期件",
            "degrade_basis": "逾期月数超过规则包 late.grace_months → 只报 late_exceeds_cap（风险提示≠法律判定）",
        },
        "coverage": {
            "by_archive": {k: by_archive[k] for k in sorted(by_archive)},
            "by_kind": {
                k: sum(1 for c in cases if c["kind"] == k)
                for k in ("annuity", "late", "reduction")
            },
            "patent_types": list(PATENT_TYPES),
            "boundary_notes": [
                "阶梯：每类专利每个档的首年与末年各一条（含恰好跳档年）",
                "滞纳金：逾期 1/2/6 月（6 = 规则包上限）+ 7 月（超上限，应降级）",
                "费减：阈值恰好相等 / 略低；共同主体数 1 与 2；跨 2019-07-01 锚点两套阈值",
                "多政策：开放许可 15% 与费减 85%/70% 并存时择最优惠且不叠加",
            ],
        },
        "cases": cases,
    }


def build_manifest(files: Dict[str, bytes]) -> dict:
    return {
        "schema": "patfee.truth.manifest/v1",
        "generated_by": "tools/gen_synthetic.py",
        "generated_at": GENERATED_AT,
        "as_of_date": AS_OF_DATE,
        "files": [
            {
                "name": name,
                "sha256": hashlib.sha256(files[name]).hexdigest(),
                "bytes": len(files[name]),
            }
            for name in sorted(files)
        ],
        "notes": [
            "本目录为生成器冻结产物，禁手改；改体例走 tools/gen_synthetic.py 整目录重生成。",
            "全部内容为合成数据（测试号段 + 虚构名称），不含任何真实专利或主体信息。",
            "生成确定性：自研 splitmix64 + 固定 seed、无时间戳、无 set 迭代序、无 stdlib random。",
        ],
    }


# --------------------------------------------------------------- 序列化

def dump_json(obj: Any) -> bytes:
    """确定性序列化：固定缩进、不排序 dict（显式构造顺序即语义顺序）、LF 结尾。"""
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def generate() -> Dict[str, bytes]:
    library = load_library(ROOT / "data")
    view = RuleView(library)
    seed = int.from_bytes(hashlib.sha256(SEED_SOURCE).digest()[:8], "big")
    rng = SplitMix64(seed)

    portfolio = build_portfolio(rng)
    truth = build_truth(view, portfolio)

    files: Dict[str, bytes] = {
        "portfolio.json": dump_json(portfolio),
        "truth.json": dump_json(truth),
    }
    files["manifest.json"] = dump_json(build_manifest(files))
    return files


def write_all(files: Dict[str, bytes]) -> None:
    TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (TRUTH_DIR / name).write_bytes(data)


def check(files: Dict[str, bytes]) -> int:
    """与磁盘逐字节比对。一致打印 SYNTHETIC_FROZEN_OK 并返回 0。"""
    problems: List[str] = []
    for name, data in sorted(files.items()):
        path = TRUTH_DIR / name
        if not path.is_file():
            problems.append("缺少文件: %s" % name)
            continue
        on_disk = path.read_bytes()
        if on_disk != data:
            problems.append(
                "字节不一致: %s（磁盘 %d 字节 / 重生成 %d 字节，sha256 %s vs %s）"
                % (name, len(on_disk), len(data),
                   hashlib.sha256(on_disk).hexdigest()[:12],
                   hashlib.sha256(data).hexdigest()[:12])
            )
    if TRUTH_DIR.is_dir():
        for path in sorted(TRUTH_DIR.glob("*.json")):
            if path.name not in files:
                problems.append("白名单外多余文件: %s" % path.name)
    if problems:
        for p in problems:
            print("  FAIL %s" % p)
        return 1
    print("SYNTHETIC_FROZEN_OK (%d 份文件逐字节一致)" % len(files))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="合成组合与真值库生成器（data/truth/ 的唯一写入者）")
    parser.add_argument("--check", action="store_true",
                        help="只比对不落盘，一致则打印 SYNTHETIC_FROZEN_OK")
    args = parser.parse_args(argv)

    files = generate()
    if args.check:
        return check(files)
    write_all(files)
    print("已生成 %d 份真值文件 -> %s" % (len(files), TRUTH_DIR))
    for name in sorted(files):
        print("  %s  %d 字节" % (name, len(files[name])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
