"""领域模型与标签。

金额字段一律 ``Decimal``：``__post_init__`` 显式拒收 ``float``。
1 分差异必须可检出，float 尾差不可接受——JSON 侧同样用 ``parse_float=Decimal``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Sequence, Tuple


class PatentType(str, Enum):
    """专利类型。取值即规则包 ``annuity.<type>`` 的条目后缀。"""

    INVENTION = "invention"            # 发明专利
    UTILITY_MODEL = "utility_model"    # 实用新型专利
    DESIGN = "design"                  # 外观设计专利
    DESIGN_INTL = "design_intl"        # 外观设计国际注册（海牙体系，首期按需）


PATENT_TYPE_LABELS = {
    PatentType.INVENTION: "发明专利",
    PatentType.UTILITY_MODEL: "实用新型专利",
    PatentType.DESIGN: "外观设计专利",
    PatentType.DESIGN_INTL: "外观设计国际注册",
}


def parse_patent_type(raw: str) -> PatentType:
    """接受枚举值或中文名/别名，不识别时抛 ValueError。"""
    text = (raw or "").strip()
    for member in PatentType:
        if text == member.value or text == PATENT_TYPE_LABELS[member]:
            return member
    aliases = {
        "发明": PatentType.INVENTION,
        "实用新型": PatentType.UTILITY_MODEL,
        "外观设计": PatentType.DESIGN,
        "外观设计国际注册": PatentType.DESIGN_INTL,
        "invention_patent": PatentType.INVENTION,
        "utility": PatentType.UTILITY_MODEL,
        "design_patent": PatentType.DESIGN,
    }
    if text in aliases:
        return aliases[text]
    raise ValueError("专利类型不识别: %r" % (raw,))


def _reject_float(value: object, where: str) -> None:
    if isinstance(value, float):
        raise TypeError(
            "%s 金额必须是 Decimal，收到 float：%r。"
            "请用 Decimal('...') 构造，或 JSON 侧 parse_float=Decimal。" % (where, value)
        )


@dataclass(frozen=True)
class FeeBasis:
    """一条结论的政策依据（坐标 + 文号 + 条款 + 抓取日期）。"""

    ruleset_id: str
    ruleset_version: str
    entry_key: str
    doc_no: str
    clause: str
    url: str
    retrieved: str

    def coordinate(self) -> str:
        """规则包坐标串：`<id>@<version>#<entry_key>`。"""
        return "%s@%s#%s" % (self.ruleset_id, self.ruleset_version, self.entry_key)

    def as_dict(self) -> dict:
        return {
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "entry_key": self.entry_key,
            "doc_no": self.doc_no,
            "clause": self.clause,
            "url": self.url,
            "retrieved": self.retrieved,
            "coordinate": self.coordinate(),
        }


@dataclass(frozen=True)
class Tier:
    """年费阶梯的一个区间（双闭区间 [from_year, to_year]）。

    档位数字只来自规则包数据——代码里不出现 3/4/6/9 这类区间端点。
    """

    from_year: int
    to_year: int
    amount: Decimal
    label: str = ""

    def __post_init__(self) -> None:
        _reject_float(self.amount, "Tier.amount")
        if self.from_year > self.to_year:
            raise ValueError("阶梯区间非法: %d-%d" % (self.from_year, self.to_year))

    def contains(self, year: int) -> bool:
        return self.from_year <= year <= self.to_year


@dataclass(frozen=True)
class AnnuityResult:
    """年费计算的确定性结果。``amount is None`` 表示未判定（未进计算路径）。"""

    patent_type: PatentType
    year: int
    amount: Optional[Decimal]
    tier: Optional[Tier]
    basis: Optional[FeeBasis]
    reasons: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    steps: Tuple[str, ...] = ()
    coordinate: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _reject_float(self.amount, "AnnuityResult.amount")

    @property
    def computed(self) -> bool:
        return self.amount is not None

    def as_dict(self) -> dict:
        return {
            "patent_type": self.patent_type.value,
            "patent_type_label": PATENT_TYPE_LABELS.get(self.patent_type, self.patent_type.value),
            "year": self.year,
            "amount": None if self.amount is None else str(self.amount),
            "tier": None
            if self.tier is None
            else {
                "from_year": self.tier.from_year,
                "to_year": self.tier.to_year,
                "label": self.tier.label,
            },
            "basis": None if self.basis is None else self.basis.as_dict(),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "steps": list(self.steps),
            "computed": self.computed,
        }


@dataclass(frozen=True)
class Applicant:
    """费减资格判定的主体。金额字段同样强制 Decimal。"""

    kind: str                                   # "individual" | "entity"
    monthly_avg_income: Optional[Decimal] = None
    annual_income: Optional[Decimal] = None
    taxable_income: Optional[Decimal] = None

    def __post_init__(self) -> None:
        for name in ("monthly_avg_income", "annual_income", "taxable_income"):
            _reject_float(getattr(self, name), "Applicant." + name)
        if self.kind not in ("individual", "entity"):
            raise ValueError("主体类型不识别: %r（应为 individual/entity）" % (self.kind,))


@dataclass(frozen=True)
class RelatedFee:
    """滞纳金路径的关联费用条目（恢复权利请求费、评价报告费等，按需另行计入）。"""

    entry_key: str
    label: str
    amount: Optional[Decimal]

    def __post_init__(self) -> None:
        _reject_float(self.amount, "RelatedFee.amount")

    def as_dict(self) -> dict:
        return {
            "entry_key": self.entry_key,
            "label": self.label,
            "amount": None if self.amount is None else str(self.amount),
        }


@dataclass(frozen=True)
class LateResult:
    """滞纳金计算的确定性结果。``surcharge is None`` 表示未判定。"""

    patent_type: PatentType
    year: int
    due_on: str
    paid_on: str
    overdue_months: Optional[int]
    month_basis: str
    grace_months: Optional[int]
    full_annuity: Optional[Decimal]
    monthly_rate: Optional[Decimal]
    surcharge: Optional[Decimal]
    payable: Optional[Decimal]
    exceeds_cap: bool
    annuity_entry_key: str
    basis: Optional[FeeBasis]
    related_fees: Tuple[RelatedFee, ...] = ()
    reasons: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    steps: Tuple[str, ...] = ()
    coordinate: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _reject_float(self.full_annuity, "LateResult.full_annuity")
        _reject_float(self.surcharge, "LateResult.surcharge")
        _reject_float(self.payable, "LateResult.payable")

    @property
    def computed(self) -> bool:
        return self.surcharge is not None

    def as_dict(self) -> dict:
        return {
            "patent_type": self.patent_type.value,
            "year": self.year,
            "due_on": self.due_on,
            "paid_on": self.paid_on,
            "overdue_months": self.overdue_months,
            "month_basis": self.month_basis,
            "grace_months": self.grace_months,
            "full_annuity": None if self.full_annuity is None else str(self.full_annuity),
            "monthly_rate": None if self.monthly_rate is None else str(self.monthly_rate),
            "surcharge": None if self.surcharge is None else str(self.surcharge),
            "payable": None if self.payable is None else str(self.payable),
            "exceeds_cap": self.exceeds_cap,
            "annuity_entry_key": self.annuity_entry_key,
            "basis": None if self.basis is None else self.basis.as_dict(),
            "related_fees": [f.as_dict() for f in self.related_fees],
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "steps": list(self.steps),
            "computed": self.computed,
        }


@dataclass(frozen=True)
class PolicyCandidate:
    """多政策择一的一个候选（费减比例 / 开放许可减免等）。"""

    policy: str
    rate: Decimal
    amount: Decimal

    def __post_init__(self) -> None:
        _reject_float(self.rate, "PolicyCandidate.rate")
        _reject_float(self.amount, "PolicyCandidate.amount")

    def as_dict(self) -> dict:
        return {"policy": self.policy, "rate": str(self.rate), "amount": str(self.amount)}


@dataclass(frozen=True)
class ReductionResult:
    """费减资格判定与减免额的确定性结果。``eligible is None`` 表示未判定。"""

    patent_type: PatentType
    year: int
    as_of_year: int
    applicant_count: int
    combined: bool
    eligible: Optional[bool]
    thresholds: Dict[str, Decimal]
    anchor_from: str
    threshold_policy_doc_no: str
    full_annuity: Optional[Decimal]
    reduction_rate: Optional[Decimal]
    candidates: Tuple[PolicyCandidate, ...]
    chosen: Optional[PolicyCandidate]
    no_double_benefit: str
    no_double_benefit_applied: bool
    payable: Optional[Decimal]
    annuity_entry_key: str
    bases: Tuple[FeeBasis, ...] = ()
    reasons: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    steps: Tuple[str, ...] = ()
    coordinate: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _reject_float(self.full_annuity, "ReductionResult.full_annuity")
        _reject_float(self.reduction_rate, "ReductionResult.reduction_rate")
        _reject_float(self.payable, "ReductionResult.payable")
        for name, value in self.thresholds.items():
            _reject_float(value, "ReductionResult.thresholds[%s]" % name)

    @property
    def computed(self) -> bool:
        return self.eligible is not None

    def as_dict(self) -> dict:
        return {
            "patent_type": self.patent_type.value,
            "patent_type_label": PATENT_TYPE_LABELS.get(self.patent_type, self.patent_type.value),
            "year": self.year,
            "as_of_year": self.as_of_year,
            "applicant_count": self.applicant_count,
            "combined": self.combined,
            "eligible": self.eligible,
            "thresholds": {k: str(v) for k, v in self.thresholds.items()},
            "anchors": {
                "threshold_policy": self.threshold_policy_doc_no,
                "anchor_from": self.anchor_from,
            },
            "full_annuity": None if self.full_annuity is None else str(self.full_annuity),
            "reduction_rate": None if self.reduction_rate is None else str(self.reduction_rate),
            "candidates": [c.as_dict() for c in self.candidates],
            "chosen": None if self.chosen is None else self.chosen.as_dict(),
            "no_double_benefit": self.no_double_benefit,
            "no_double_benefit_applied": self.no_double_benefit_applied,
            "payable": None if self.payable is None else str(self.payable),
            "annuity_entry_key": self.annuity_entry_key,
            "bases": [b.as_dict() for b in self.bases],
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "steps": list(self.steps),
            "computed": self.computed,
        }


def quantize_amount(value: Decimal) -> Decimal:
    """呈现/导出统一的两位小数口径（ROUND_HALF_UP）。

    ``0.01`` 属精度约定而非政策数值，已登记在 ``rules/literals.py`` 的豁免表内。
    """
    from decimal import ROUND_HALF_UP

    if not isinstance(value, Decimal):
        raise TypeError("quantize_amount 只接受 Decimal")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_reasons(reasons: Sequence[str]) -> Tuple[str, ...]:
    """去重并保序，便于断言与快照比对。"""
    seen = set()
    out = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return tuple(out)
