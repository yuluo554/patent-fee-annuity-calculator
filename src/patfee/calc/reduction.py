"""费减资格判定与减免额引擎（M2）。

五条纪律：

1. **阈值与比例只来自规则包** —— 316 号阈值（含 ``.prev`` 历史口径）、
   78 号比例（``reduction.rate.sole`` / ``reduction.rate.combined``）、
   594 号开放许可减免（``reduction.open_license_discount``）全部按 key 读取，
   代码内不出现任何政策数值；
2. **资格 = 严格小于阈值**（"低于"口径，恰好等于不合格）；
   个人：月均收入**或**年收入低于对应阈值；单位：应纳税所得额低于阈值；
3. **共同主体须逐个合格** —— ``n >= 2`` 任一不合格则整体不合格；
   比例按主体构成取 ``sole`` / ``combined`` 条目；
4. **按年度锚定阈值版本** —— ``as_of_year`` 对应 316 号锚点（2019-07-01），
   锚点前用 ``.prev`` 历史条目；锚点日期本身从规则包 ``reduction.threshold.effective_from``
   读取，不写死；
5. **多政策择一（594 号）** —— 候选集 {费减比例, 开放许可减免}，取**实缴额最小**者
   （= 减免额最大）；``candidates`` 全留痕、``chosen`` 显式、不叠加；
   择一策略文本取 ``reduction.no_double_benefit`` 条目。

门控走 ``reduction`` scope；年费基数另经 ``calc`` scope 门控。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from ..domain.models import (
    FeeBasis,
    PatentType,
    PolicyCandidate,
    ReductionResult,
    quantize_amount,
)
from ..errors import RulesetError, UsageError
from ..rules import gate as gate_mod
from ..rules.loader import Entry, RuleLibrary

THRESHOLD_KEYS = (
    "reduction.threshold.individual_monthly_income",
    "reduction.threshold.individual_annual_income",
    "reduction.threshold.entity_taxable_income",
)
RATE_KEYS = ("reduction.rate.sole", "reduction.rate.combined")
POLICY_KEYS = THRESHOLD_KEYS + RATE_KEYS + (
    "reduction.threshold.effective_from",
    "reduction.open_license_discount",
    "reduction.no_double_benefit",
)

POLICY_FEE_REDUCTION = "费减"
POLICY_OPEN_LICENSE = "开放许可年费减免"

CANDIDATE_FEE_REDUCTION = "fee_reduction"
CANDIDATE_OPEN_LICENSE = "open_license"


@dataclass(frozen=True)
class ReductionRequest:
    """费减判定输入：主体列表 + 适用年度 + 年费年度 + 是否开放许可。"""

    patent_type: PatentType
    year: int
    as_of_year: int
    applicants: Tuple[Dict[str, Any], ...]
    open_license: bool = False
    preview: bool = False


def parse_applicants(payload: Any) -> Tuple[Dict[str, Any], ...]:
    """解析并校验主体列表；字段缺失/金额非法即 UsageError（exit 2 语义）。"""
    if not isinstance(payload, (list, tuple)) or not payload:
        raise UsageError("applicants 必须是非空数组")
    out: List[Dict[str, Any]] = []
    for idx, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise UsageError("applicants[%d] 必须是对象" % idx)
        kind = str(raw.get("kind") or "").strip()
        if kind not in ("individual", "entity"):
            raise UsageError(
                "applicants[%d].kind 不识别: %r（应为 individual/entity）" % (idx, kind)
            )
        item: Dict[str, Any] = {"kind": kind, "name": str(raw.get("name") or "")}
        if kind == "individual":
            item["monthly_avg_income"] = _optional_amount(raw, "monthly_avg_income", idx)
            item["annual_income"] = _optional_amount(raw, "annual_income", idx)
            if item["monthly_avg_income"] is None and item["annual_income"] is None:
                raise UsageError(
                    "applicants[%d] 个人主体须提供 monthly_avg_income 或 annual_income" % idx
                )
        else:
            item["taxable_income"] = _optional_amount(raw, "taxable_income", idx)
        out.append(item)
    return tuple(out)


def _optional_amount(raw: Dict[str, Any], field: str, idx: int) -> Optional[Decimal]:
    value = raw.get(field)
    if value in (None, ""):
        return None
    if isinstance(value, float):
        raise UsageError(
            "applicants[%d].%s 不接受浮点数（会引入 1 分尾差）: %r" % (idx, field, value)
        )
    try:
        return Decimal(str(value).strip())
    except Exception:
        raise UsageError("applicants[%d].%s 不是合法金额: %r" % (idx, field, value))


def _entry(library: RuleLibrary, key: str) -> Optional[Entry]:
    for rs in library.rulesets.values():
        entry = rs.get(key)
        if entry is not None:
            return entry
    return None


def _required_scalar(library: RuleLibrary, key: str) -> Decimal:
    entry = _entry(library, key)
    if entry is None:
        raise RulesetError("规则包缺条目: %s（scope=reduction）" % key)
    value = entry.decimal()
    if value is None:
        raise RulesetError("条目 %s 值未入库（missing_value）" % key)
    return value


def _required_text(library: RuleLibrary, key: str) -> str:
    entry = _entry(library, key)
    if entry is None or entry.value is None:
        raise RulesetError("规则包缺条目或值未入库: %s" % key)
    return str(entry.value).strip()


def thresholds_for_year(library: RuleLibrary, as_of_year: int) -> Tuple[Dict[str, Decimal], bool]:
    """按年度锚定阈值版本：< 锚点年用 .prev 历史口径，其余用现行口径。

    返回 (阈值表, 是否历史口径)。锚点日期取 ``reduction.threshold.effective_from``
    条目的字符串值（形如 ``2019-07-01``）；``as_of_year`` 早于锚点年份即用历史
    阈值（同年内按年粒度锚定，与真值库生成器 ``_thresholds_for`` 同款口径）。
    """
    anchor_text = _required_text(library, "reduction.threshold.effective_from")
    try:
        anchor_year = int(anchor_text[:4])
    except (TypeError, ValueError):
        raise RulesetError("条目 reduction.threshold.effective_from 值非法: %r" % (anchor_text,))
    historical = as_of_year < anchor_year
    suffix = ".prev" if historical else ""
    keys = {
        "individual_monthly_income": "reduction.threshold.individual_monthly_income" + suffix,
        "individual_annual_income": "reduction.threshold.individual_annual_income" + suffix,
        "entity_taxable_income": "reduction.threshold.entity_taxable_income" + suffix,
    }
    thresholds = {k: _required_scalar(library, key) for k, key in keys.items()}
    return thresholds, historical


def applicant_eligible(applicant: Dict[str, Any], thresholds: Dict[str, Decimal]) -> bool:
    """单主体资格：个人（月均**或**年收入严格小于阈值）/ 单位（应纳税所得额严格小于阈值）。"""
    kind = applicant["kind"]
    if kind == "individual":
        ok = False
        monthly = applicant.get("monthly_avg_income")
        annual = applicant.get("annual_income")
        if monthly is not None and monthly < thresholds["individual_monthly_income"]:
            ok = True
        if annual is not None and annual < thresholds["individual_annual_income"]:
            ok = True
        return ok
    if kind == "entity":
        taxable = applicant.get("taxable_income")
        return taxable is not None and taxable < thresholds["entity_taxable_income"]
    raise UsageError("主体类型不识别: %r" % (kind,))


def _basis_for(library: RuleLibrary, key: str) -> FeeBasis:
    entry = _entry(library, key)
    if entry is None:
        raise RulesetError("规则包缺条目: %s" % key)
    raw = entry.basis or {}
    return FeeBasis(
        ruleset_id=entry.ruleset_id,
        ruleset_version=entry.ruleset_version,
        entry_key=entry.key,
        doc_no=raw.get("doc_no") or "",
        clause=raw.get("clause") or "",
        url=raw.get("url") or "",
        retrieved=raw.get("retrieved") or "",
    )


def compute_reduction(
    library: RuleLibrary,
    request: ReductionRequest,
    annuity_amount: Optional[Decimal] = None,
) -> ReductionResult:
    """费减资格判定 + 多政策择一（同 plan/04 §五详设）。

    ``annuity_amount`` 可传入已算出的年费全额；未传时按同年度现算。
    """
    annuity_key = "annuity." + request.patent_type.value
    decision = gate_mod.evaluate_keys(
        library, list(POLICY_KEYS), gate_mod.SCOPE_REDUCTION, preview=request.preview
    )
    annuity_gate = gate_mod.evaluate_keys(library, [annuity_key], gate_mod.SCOPE_CALC)
    reasons: List[str] = list(decision.reasons)
    if not annuity_gate.allowed:
        reasons.extend(annuity_gate.reasons)

    bases: Tuple[FeeBasis, ...] = tuple(
        _basis_for(library, k) for k in ("reduction.rate.sole", "reduction.threshold.effective_from")
    )
    steps: List[str] = [
        "主体构成: %d 人（%s）" % (
            len(request.applicants),
            "共同主体" if len(request.applicants) >= 2 else "单主体",
        ),
        "适用年度: %d（阈值按 316 号锚点前后取版本）" % request.as_of_year,
    ]

    def _uncomputed(extra_steps: Tuple[str, ...]) -> ReductionResult:
        return ReductionResult(
            patent_type=request.patent_type,
            year=request.year,
            as_of_year=request.as_of_year,
            applicant_count=len(request.applicants),
            combined=len(request.applicants) >= 2,
            eligible=None,
            thresholds={},
            anchor_from="",
            threshold_policy_doc_no="",
            full_annuity=None,
            reduction_rate=None,
            candidates=(),
            chosen=None,
            no_double_benefit=_no_double_benefit_text(library),
            no_double_benefit_applied=False,
            payable=None,
            annuity_entry_key=annuity_key,
            bases=bases,
            reasons=tuple(dict.fromkeys(reasons)) or ("gated_pending",),
            steps=extra_steps,
            coordinate=library.coordinate(),
        )

    steps.append("门控: reduction scope %s" % ("放行" if decision.allowed else "拒绝"))
    if not decision.allowed or not annuity_gate.allowed:
        return _uncomputed(tuple(steps))

    thresholds, historical = thresholds_for_year(library, request.as_of_year)
    steps.append(
        "阈值（%s 口径）: 个人月均<%s 或 年收入<%s；单位应纳税所得额<%s"
        % (
            "历史" if historical else "现行",
            thresholds["individual_monthly_income"],
            thresholds["individual_annual_income"],
            thresholds["entity_taxable_income"],
        )
    )

    # ---- 逐主体资格判定（全部满足才通过） ----
    eligible = True
    for idx, applicant in enumerate(request.applicants):
        ok = applicant_eligible(applicant, thresholds)
        steps.append(
            "主体[%d] %s: %s" % (
                idx,
                applicant.get("name") or applicant["kind"],
                "合格" if ok else "不合格（须严格低于阈值，恰好等于不合格）",
            )
        )
        if not ok:
            eligible = False
    combined = len(request.applicants) >= 2

    # ---- 年费全额 ----
    full = annuity_amount
    if full is None:
        from . import annuity as annuity_mod

        annuity_result = annuity_mod.compute_annuity(
            library, request.patent_type, request.year, preview=request.preview
        )
        if not annuity_result.computed:
            reasons.extend(annuity_result.reasons)
            return _uncomputed(tuple(steps))
        full = annuity_result.amount
    steps.append("年费全额: %s 元（第 %d 年）" % (full, request.year))

    # ---- 多政策候选集 ----
    candidates: List[PolicyCandidate] = []
    rate_sole = _required_scalar(library, "reduction.rate.sole")
    rate_combined = _required_scalar(library, "reduction.rate.combined")
    reduction_rate = rate_combined if combined else rate_sole
    if eligible:
        candidates.append(PolicyCandidate(
            policy=POLICY_FEE_REDUCTION,
            rate=reduction_rate,
            amount=quantize_amount(full * (Decimal(1) - reduction_rate)),
        ))
    open_license_discount = _required_scalar(library, "reduction.open_license_discount")
    if request.open_license:
        candidates.append(PolicyCandidate(
            policy=POLICY_OPEN_LICENSE,
            rate=open_license_discount,
            amount=quantize_amount(full * (Decimal(1) - open_license_discount)),
        ))

    chosen: Optional[PolicyCandidate] = None
    payable: Optional[Decimal] = None
    if candidates:
        # 择最优惠 = 实缴额最小 = 减免额最大；策略文本由规则包承载
        chosen = min(candidates, key=lambda c: c.amount)
        payable = chosen.amount
        steps.append("候选政策: %s" % "; ".join(
            "%s(费率%s→实缴%s)" % (c.policy, c.rate, c.amount) for c in candidates
        ))
        steps.append("选中: %s（实缴 %s 元；不叠加）" % (chosen.policy, chosen.amount))
    else:
        steps.append("无可用减免政策 → 按全额缴纳")

    return ReductionResult(
        patent_type=request.patent_type,
        year=request.year,
        as_of_year=request.as_of_year,
        applicant_count=len(request.applicants),
        combined=combined,
        eligible=eligible,
        thresholds=thresholds,
        anchor_from=_required_text(library, "reduction.threshold.effective_from"),
        threshold_policy_doc_no=(
            (_entry(library, "reduction.threshold.effective_from").basis or {}).get("doc_no") or ""
        ),
        full_annuity=full,
        reduction_rate=reduction_rate if eligible else None,
        candidates=tuple(candidates),
        chosen=chosen,
        no_double_benefit=_no_double_benefit_text(library),
        no_double_benefit_applied=len(candidates) > 1,
        payable=payable,
        annuity_entry_key=annuity_key,
        bases=bases,
        reasons=tuple(dict.fromkeys(reasons)),
        steps=tuple(steps),
        coordinate=library.coordinate(),
    )


def _no_double_benefit_text(library: RuleLibrary) -> str:
    entry = _entry(library, "reduction.no_double_benefit")
    if entry is None or entry.value is None:
        return ""
    return str(entry.value).strip()
