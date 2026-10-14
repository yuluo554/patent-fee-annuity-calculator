"""滞纳金与恢复权利引擎（M2）。

四条纪律：

1. **月数口径与上限只来自规则包** —— ``late.month_basis`` / ``late.grace_months``
   由规则包承载（M1 D40：自然月 / 6 个月，依细则第 5/115 条），本模块按
   ``month_basis`` 分派口径实现，代码内不写死任何月数或费率；
2. **金额只由 Decimal 产生** —— 费率取 ``late.monthly_rate``，逐月累加；
3. **自然月推进** —— ``calendar_month`` 口径下月末日不足取该月最后一日
   （细则第 5 条："以最后一月的相应日为期限届满日"）；不足一个整月不计入月数；
   ``thirty_day`` 口径按每 30 天折一月；
4. **超上限是风险提示不是法律判定** —— 逾期月数超过 ``grace_months`` 时照算金额，
   附 ``late_exceeds_cap``（warning 类原因码），不拦截、不置 ``None``。

恢复权利请求费（``check.fee.ruc``）与专利权评价报告请求费
（``check.fee.evaluation_report``）按费率表条目金额随结果列出（不计入滞纳金），
超上限恢复权利场景由调用方据其组装应缴合计。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from ..domain.models import (
    AnnuityResult,
    FeeBasis,
    LateResult,
    PatentType,
    RelatedFee,
    quantize_amount,
)
from ..errors import PatfeeError, RulesetError
from ..rules import gate as gate_mod
from ..rules.loader import Entry, RuleLibrary

RELATED_FEE_KEYS = ("check.fee.ruc", "check.fee.evaluation_report")

MONTH_BASIS_CALENDAR = "calendar_month"
MONTH_BASIS_THIRTY_DAY = "thirty_day"


@dataclass(frozen=True)
class LateRequest:
    """滞纳金计算输入：应缴年度 + 规定缴费期限 + 实际缴费日。"""

    patent_type: PatentType
    year: int
    due_on: date
    paid_on: date
    preview: bool = False


def _entry(library: RuleLibrary, key: str) -> Optional[Entry]:
    for rs in library.rulesets.values():
        entry = rs.get(key)
        if entry is not None:
            return entry
    return None


def _required_scalar(library: RuleLibrary, key: str, scope: str) -> Decimal:
    """取标量条目值；条目缺失或值未入库即报配置错（绝不静默取 0）。"""
    entry = _entry(library, key)
    if entry is None:
        raise RulesetError("规则包缺条目: %s（scope=%s）" % (key, scope))
    value = entry.decimal()
    if value is None:
        raise RulesetError("条目 %s 值未入库（missing_value）" % key)
    return value


def add_calendar_months(d: date, months: int) -> date:
    """自然月推进：月末日不足时取该月最后一日（细则第 5 条口径）。"""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def overdue_months_between(
    due_on: date, paid_on: date, month_basis: str
) -> Tuple[int, List[str]]:
    """按规则包口径折算逾期月数，返回 (月数, 步骤留痕)。

    * ``calendar_month``：整自然月计数 —— ``due_on`` 逐次自然月推进，
      不超过 ``paid_on`` 的次数即月数（不足整月的零头不计入）；
    * ``thirty_day``：每 30 天折一月。
    其他口径值 = 规则包升级后代码未跟进，显式报错，不猜测。
    """
    steps: List[str] = []
    if paid_on <= due_on:
        return 0, ["未逾期（paid_on <= due_on），月数=0"]
    if month_basis == MONTH_BASIS_THIRTY_DAY:
        days = (paid_on - due_on).days
        months = days // 30
        steps.append("口径=thirty_day：逾期 %d 天 ÷ 30 = %d 月（零头不计）" % (days, months))
        return months, steps
    if month_basis == MONTH_BASIS_CALENDAR:
        months = 0
        probe = due_on
        # 整月推进严格递增，循环必然终止于超过 paid_on 的第一个相应日
        while add_calendar_months(due_on, months + 1) <= paid_on:
            months += 1
            probe = add_calendar_months(due_on, months)
        steps.append(
            "口径=calendar_month：自 %s 整自然月推进至 %s，共 %d 个整月（零头不计）"
            % (due_on.isoformat(), probe.isoformat(), months)
        )
        return months, steps
    raise PatfeeError(
        "规则包 late.month_basis 值不识别: %r（引擎支持 %s/%s，请扩展口径实现）"
        % (month_basis, MONTH_BASIS_CALENDAR, MONTH_BASIS_THIRTY_DAY),
        reason_code="ruleset_error",
    )


def compute_late(
    library: RuleLibrary,
    request: LateRequest,
    annuity: Optional[AnnuityResult] = None,
) -> LateResult:
    """计算某年度年费自 ``due_on`` 逾期至 ``paid_on`` 的滞纳金。

    ``annuity`` 可传入同一请求已算出的年费结果（避免重复走阶梯）；
    未传时按同年度现算。门控走 ``late`` 与 ``calc`` 两个 scope：
    滞纳金路径引用 late.* 条目，金额基数引用 annuity 条目。
    """
    annuity_key = "annuity." + request.patent_type.value
    late_keys = ("late.monthly_rate", "late.grace_months", "late.month_basis")
    decision = gate_mod.evaluate_keys(
        library, list(late_keys) + [annuity_key], gate_mod.SCOPE_LATE,
        preview=request.preview,
    )
    # annuity 条目的 scopes 只含 calc，不会在 late scope 被拦；
    # 基数金额本身仍须经 calc scope 门控（阶梯数据是否可进计算路径）。
    annuity_gate = gate_mod.evaluate_keys(library, [annuity_key], gate_mod.SCOPE_CALC)
    reasons: List[str] = list(decision.reasons)
    if not annuity_gate.allowed:
        reasons.extend(annuity_gate.reasons)

    warnings: List[str] = []
    steps: List[str] = []

    basis_entry = _entry(library, annuity_key)
    basis: Optional[FeeBasis] = None
    if basis_entry is not None:
        raw = basis_entry.basis or {}
        basis = FeeBasis(
            ruleset_id=basis_entry.ruleset_id,
            ruleset_version=basis_entry.ruleset_version,
            entry_key=basis_entry.key,
            doc_no=raw.get("doc_no") or "",
            clause=raw.get("clause") or "",
            url=raw.get("url") or "",
            retrieved=raw.get("retrieved") or "",
        )

    def _uncomputed(extra_steps: Tuple[str, ...] = ()) -> LateResult:
        return LateResult(
            patent_type=request.patent_type,
            year=request.year,
            due_on=request.due_on.isoformat(),
            paid_on=request.paid_on.isoformat(),
            overdue_months=None,
            month_basis=_basis_text(library, default=""),
            grace_months=None,
            full_annuity=None,
            monthly_rate=None,
            surcharge=None,
            payable=None,
            exceeds_cap=False,
            annuity_entry_key=annuity_key,
            basis=basis,
            reasons=tuple(dict.fromkeys(reasons)) or ("gated_pending",),
            warnings=tuple(warnings),
            steps=extra_steps,
            coordinate=library.coordinate(),
        )

    steps.append("逾期区间: %s ~ %s" % (request.due_on.isoformat(), request.paid_on.isoformat()))
    if not decision.allowed or not annuity_gate.allowed:
        if decision.required_inputs:
            steps.append("缺少必须显式提供的外部输入: %s" % ", ".join(decision.required_inputs))
        return _uncomputed(tuple(steps))

    # ---- 年费全额（基数） ----
    if annuity is not None and annuity.computed:
        full = annuity.amount
        annuity_entry_key = annuity.basis.entry_key if annuity.basis else annuity_key
        steps.append("年费全额（沿用年费计算结果）: %s 元" % full)
    else:
        from . import annuity as annuity_mod

        annuity_result = annuity_mod.compute_annuity(
            library, request.patent_type, request.year, preview=request.preview
        )
        if not annuity_result.computed:
            reasons.extend(annuity_result.reasons)
            steps.append("年费全额未判定: %s" % "; ".join(annuity_result.reasons))
            return _uncomputed(tuple(steps))
        full = annuity_result.amount
        annuity_entry_key = (
            annuity_result.basis.entry_key if annuity_result.basis else annuity_key
        )
        steps.append("年费全额: %s 元（第 %d 年）" % (full, request.year))

    # ---- 滞纳金参数（全部来自规则包） ----
    rate = _required_scalar(library, "late.monthly_rate", gate_mod.SCOPE_LATE)
    grace_dec = _required_scalar(library, "late.grace_months", gate_mod.SCOPE_LATE)
    grace = int(grace_dec)
    month_basis_entry = _entry(library, "late.month_basis")
    month_basis = (
        str(month_basis_entry.value).strip()
        if month_basis_entry is not None and month_basis_entry.value is not None
        else ""
    )
    steps.append("滞纳金费率=%s/月（规则包 late.monthly_rate）" % rate)
    steps.append("补缴上限=%d 个月（规则包 late.grace_months）" % grace)
    steps.append("月数口径=%s（规则包 late.month_basis）" % month_basis)

    months, month_steps = overdue_months_between(request.due_on, request.paid_on, month_basis)
    steps.extend(month_steps)

    surcharge = quantize_amount(full * rate * Decimal(months))
    exceeds_cap = months > grace
    payable = quantize_amount(full + surcharge)
    if exceeds_cap:
        reasons.append("late_exceeds_cap")
        warnings.append(
            "逾期 %d 个月已超过规则包补缴上限 %d 个月：专利权自应当缴纳年费期满之日起终止"
            "（进入失效流程口径，须另行办理恢复权利）；本金额为风险测算，不构成法律判定"
            % (months, grace)
        )

    steps.append("滞纳金=%s × %s × %d = %s 元" % (full, rate, months, surcharge))
    steps.append("应缴合计（年费+滞纳金）=%s 元" % payable)
    if exceeds_cap:
        steps.append("逾期月数 %d > 上限 %d → late_exceeds_cap（warning ≠ fail）" % (months, grace))

    related = _related_fees(library)
    for fee in related:
        if fee.amount is not None:
            steps.append("关联费用 %s: %s 元（按费率表条目，另行缴纳）" % (fee.label, fee.amount))

    return LateResult(
        patent_type=request.patent_type,
        year=request.year,
        due_on=request.due_on.isoformat(),
        paid_on=request.paid_on.isoformat(),
        overdue_months=months,
        month_basis=month_basis,
        grace_months=grace,
        full_annuity=full,
        monthly_rate=rate,
        surcharge=surcharge,
        payable=payable,
        exceeds_cap=exceeds_cap,
        annuity_entry_key=annuity_entry_key,
        basis=basis,
        related_fees=related,
        reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(warnings),
        steps=tuple(steps),
        coordinate=library.coordinate(),
    )


def _basis_text(library: RuleLibrary, default: str) -> str:
    entry = _entry(library, "late.month_basis")
    if entry is not None and entry.value is not None:
        return str(entry.value).strip()
    return default


def _related_fees(library: RuleLibrary) -> Tuple[RelatedFee, ...]:
    """恢复权利请求费 / 评价报告请求费：费率表条目列出，缺失不编造。"""
    labels = {
        "check.fee.ruc": "恢复权利请求费",
        "check.fee.evaluation_report": "专利权评价报告请求费",
    }
    out: List[RelatedFee] = []
    for key in RELATED_FEE_KEYS:
        entry = _entry(library, key)
        if entry is None:
            continue
        out.append(RelatedFee(entry_key=key, label=labels.get(key, entry.label), amount=entry.decimal()))
    return tuple(out)
