"""年费阶梯计算引擎（确定性内核）。

三条纪律：

1. **档位端点只来自规则包** —— 代码里不出现 "3 年 / 4 年" 这类区间数字；
   区间为**双闭** ``[from_year, to_year]``，恰好跳档年归**新档**。
2. **金额只由 Decimal 产生** —— 规则包加载已 ``parse_float=Decimal``，
   本模块只做取档与必要时的一元运算，绝不引入 float。
3. **未核对不得进计算路径** —— 计算前必经 ``rules.gate``；被拦时 ``amount=None``，
   结果携带原因码，由调用方决定退出码（**不抛裸异常**）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from ..domain.models import (
    AnnuityResult,
    FeeBasis,
    PatentType,
    Tier,
    normalize_reasons,
    quantize_amount,
)
from ..errors import OutOfRangeError, RulesetError
from ..rules import gate as gate_mod
from ..rules.loader import Entry, RuleLibrary

ENTRY_PREFIX = "annuity."


def entry_key_for(patent_type: PatentType) -> str:
    return ENTRY_PREFIX + patent_type.value


def tiers_from_entry(entry: Entry) -> List[Tier]:
    """把规则条目的 ladder 转成领域 Tier 列表；端点/金额缺失即报 schema 错。"""
    tiers: List[Tier] = []
    for raw in entry.tiers():
        try:
            from_year = int(raw["from_year"])
            to_year = int(raw["to_year"])
            amount = raw["amount"]
        except (KeyError, TypeError, ValueError) as exc:
            raise RulesetError("条目 %s 的阶梯区段非法: %r (%s)" % (entry.key, raw, exc))
        if amount is None:
            raise RulesetError("条目 %s 的阶梯区段缺少金额: %r" % (entry.key, raw))
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        tiers.append(
            Tier(
                from_year=from_year,
                to_year=to_year,
                amount=amount,
                label=raw.get("label") or "",
            )
        )
    if not tiers:
        raise RulesetError("条目 %s 没有阶梯区段" % entry.key)
    return tiers


def find_tier(tiers: List[Tier], year: int) -> Tier:
    """双闭区间取档；超出覆盖范围抛 OutOfRangeError（原因码 out_of_range）。

    边界语义由数据决定：第 N 年恰好落在某档 ``to_year`` 上时归该档，
    落在下一个 ``from_year`` 上时归新档 —— 两者由规则包的连续区间表达。
    """
    for tier in tiers:
        if tier.contains(year):
            return tier
    covered = ", ".join("%d-%d" % (t.from_year, t.to_year) for t in tiers)
    raise OutOfRangeError(
        "缴费年度 %d 超出该专利类型的阶梯覆盖范围（已覆盖: %s）" % (year, covered),
        reason_code="out_of_range",
    )


def basis_from_entry(entry: Entry, clause_override: Optional[str] = None) -> FeeBasis:
    basis = entry.basis or {}
    return FeeBasis(
        ruleset_id=entry.ruleset_id,
        ruleset_version=entry.ruleset_version,
        entry_key=entry.key,
        doc_no=basis.get("doc_no") or "",
        clause=clause_override or basis.get("clause") or "",
        url=basis.get("url") or "",
        retrieved=basis.get("retrieved") or "",
    )


def compute_annuity(
    library: RuleLibrary,
    patent_type: PatentType,
    year: int,
    preview: bool = False,
    provided_inputs: Tuple[str, ...] = (),
) -> AnnuityResult:
    """计算某专利类型第 ``year`` 年度应缴年费。

    返回的 ``amount`` 在门控拒绝或超范围时为 ``None``（未判定），
    并附 ``reasons`` 原因码；决策与退出码由调用方（pipeline / CLI）决定。
    """
    key = entry_key_for(patent_type)
    decision = gate_mod.evaluate_keys(
        library, [key], gate_mod.SCOPE_CALC, preview=preview, provided_inputs=provided_inputs
    )

    entry: Optional[Entry] = None
    for rs in library.rulesets.values():
        entry = rs.get(key)
        if entry is not None:
            break

    if entry is None:
        return AnnuityResult(
            patent_type=patent_type,
            year=year,
            amount=None,
            tier=None,
            basis=None,
            reasons=("untracked_entry",),
            steps=("未在规则包中找到条目 %s" % key,),
            coordinate=library.coordinate(),
        )

    if not decision.allowed:
        reasons = list(decision.reasons)
        if decision.required_inputs:
            reasons.append("input_required")
        steps = ["门控拒绝（scope=%s）：%s" % (decision.scope, ", ".join(decision.reasons))]
        if decision.required_inputs:
            steps.append("缺少必须显式提供的外部输入: %s" % ", ".join(decision.required_inputs))
        if preview and decision.permitted_unverified:
            # preview 只放行 pending，不放行 input_required —— 预览不是"补输入"
            pass
        return AnnuityResult(
            patent_type=patent_type,
            year=year,
            amount=None,
            tier=None,
            basis=basis_from_entry(entry),
            reasons=normalize_reasons(reasons),
            steps=tuple(steps),
            coordinate=library.coordinate(),
        )

    tiers = tiers_from_entry(entry)
    try:
        tier = find_tier(tiers, year)
    except OutOfRangeError as exc:
        return AnnuityResult(
            patent_type=patent_type,
            year=year,
            amount=None,
            tier=None,
            basis=basis_from_entry(entry),
            reasons=(exc.reason_code,),
            steps=("超出阶梯覆盖范围：%s" % exc.message,),
            coordinate=library.coordinate(),
        )

    amount = quantize_amount(tier.amount)
    warnings: List[str] = []
    if decision.permitted_unverified:
        warnings.append(
            "预览口径：条目 %s 尚未核对（status=pending），金额不得作为缴费依据"
            % ", ".join(decision.permitted_unverified)
        )

    steps = (
        "专利类型=%s" % patent_type.value,
        "缴费年度=第 %d 年" % year,
        "命中区间=%s（第 %d-%d 年）" % (tier.label or "第 %d-%d 年" % (tier.from_year, tier.to_year),
                                     tier.from_year, tier.to_year),
        "区间年费=%s" % tier.amount,
        "结果=%s" % amount,
    )

    return AnnuityResult(
        patent_type=patent_type,
        year=year,
        amount=amount,
        tier=tier,
        basis=basis_from_entry(
            entry, clause_override=(tier.label or entry.basis.get("clause") or "")
        ),
        reasons=(),
        warnings=tuple(warnings),
        steps=steps,
        coordinate=library.coordinate(),
    )
