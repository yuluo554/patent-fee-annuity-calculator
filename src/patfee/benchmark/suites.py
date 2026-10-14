"""基准套件实现。

新增套件必须同时注册进 :data:`SUITES`，未知名走 exit 2（不许静默跳过）。
每套件配探活（可证伪）测试：注入缺陷后必须报未达标。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..domain.models import PatentType
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


def suite_b2_late(library: RuleLibrary) -> CheckResult:
    """B2 滞纳金（M2 实装）。"""
    return CheckResult(suite="b2_late", implemented=False, notes=["M2 实装：滞纳金跨月累加与上限边界枚举"])


def suite_b3_reduction(library: RuleLibrary) -> CheckResult:
    """B3 费减判定（M2 实装）。"""
    return CheckResult(suite="b3_reduction", implemented=False, notes=["M2 实装：阈值边界与共同主体数 1/2"])


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
