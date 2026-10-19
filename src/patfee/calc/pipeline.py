"""编排层：CLI 与 GUI 共用的唯一业务编排入口。

纪律（plan/06 D26）：**同一个业务判断在项目里只能有一处实现**。
表现层只准经本模块的公开函数取数，不得自行复现任何判定逻辑。
后续里程碑的费减、滞纳金、组合排期同样上收到这里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from ..domain.models import (
    AnnuityResult,
    LateResult,
    PatentType,
    ReductionResult,
    parse_patent_type,
)
from ..errors import UsageError
from ..rules.loader import RuleLibrary, load_library

# 免责声明为强制输出：任何结论旁必须可读
DISCLAIMER = (
    "本输出为基于官方费率表与政策文本的费用测算，不构成法律或代理意见；"
    "正式缴费金额以国家知识产权局规定与缴费通知为准。"
)


@dataclass(frozen=True)
class CalcRequest:
    """单件年费计算的输入契约。"""

    patent_type: PatentType
    year: int
    patent_no: str = ""
    applied_on: str = ""
    granted_on: str = ""
    preview: bool = False
    provided_inputs: Tuple[str, ...] = ()


def parse_decimal_strict(raw: Any, field: str) -> Decimal:
    """严格 Decimal 解析：拒绝 float 直传，保证不是从二进制浮点转来的。"""
    if isinstance(raw, float):
        raise UsageError("%s 不接受浮点数（会引入 1 分尾差）：%r" % (field, raw))
    if isinstance(raw, Decimal):
        return raw
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError, TypeError) as exc:
        raise UsageError("%s 不是合法金额: %r (%s)" % (field, raw, exc))


def build_request(payload: Dict[str, Any], preview: bool = False) -> CalcRequest:
    """把输入 JSON（已解析）转成 CalcRequest；缺字段/类型不识别一律 exit 2 语义。"""
    if not isinstance(payload, dict):
        raise UsageError("输入必须是 JSON 对象")
    patent_type_raw = payload.get("patent_type")
    if patent_type_raw in (None, ""):
        raise UsageError("输入缺少必填字段 patent_type")
    try:
        patent_type = parse_patent_type(str(patent_type_raw))
    except ValueError as exc:
        raise UsageError(str(exc), reason_code="unknown_patent_type")

    year_raw = payload.get("year")
    if year_raw in (None, ""):
        raise UsageError("输入缺少必填字段 year")
    try:
        year = int(year_raw)
    except (TypeError, ValueError):
        raise UsageError("year 不是整数: %r" % (year_raw,))
    if year < 1:
        raise UsageError("year 必须为正整数: %d" % year)

    provided = payload.get("provided_inputs") or ()
    if isinstance(provided, str):
        provided = (provided,)
    return CalcRequest(
        patent_type=patent_type,
        year=year,
        patent_no=str(payload.get("patent_no") or ""),
        applied_on=str(payload.get("applied_on") or ""),
        granted_on=str(payload.get("granted_on") or ""),
        preview=preview,
        provided_inputs=tuple(provided),
    )


def compute_full_calc(
    request: CalcRequest, library: Optional[RuleLibrary] = None
) -> AnnuityResult:
    """编排：加载规则库 → 年费阶梯计算 → 返回结果对象（不做任何 I/O 渲染）。"""
    lib = library or load_library()
    from ..calc import annuity

    return annuity.compute_annuity(
        lib,
        request.patent_type,
        request.year,
        preview=request.preview,
        provided_inputs=request.provided_inputs,
    )


@dataclass(frozen=True)
class LateRequest:
    """滞纳金计算的输入契约（与 calc.late.LateRequest 同构，此处面向 CLI）。"""

    patent_type: PatentType
    year: int
    due_on: date
    paid_on: date
    preview: bool = False


def build_late_request(payload: Dict[str, Any], preview: bool = False) -> LateRequest:
    """把滞纳金输入 JSON 转成 LateRequest；缺字段/日期非法一律 exit 2 语义。"""
    if not isinstance(payload, dict):
        raise UsageError("输入必须是 JSON 对象")
    patent_type_raw = payload.get("patent_type")
    if patent_type_raw in (None, ""):
        raise UsageError("输入缺少必填字段 patent_type")
    try:
        patent_type = parse_patent_type(str(patent_type_raw))
    except ValueError as exc:
        raise UsageError(str(exc), reason_code="unknown_patent_type")

    year_raw = payload.get("year")
    if year_raw in (None, ""):
        raise UsageError("输入缺少必填字段 year")
    try:
        year = int(year_raw)
    except (TypeError, ValueError):
        raise UsageError("year 不是整数: %r" % (year_raw,))
    if year < 1:
        raise UsageError("year 必须为正整数: %d" % year)

    due_raw = payload.get("due_on")
    paid_raw = payload.get("paid_on")
    if not due_raw or not paid_raw:
        raise UsageError("滞纳金计算须提供 due_on（规定缴费期限）与 paid_on（实际缴费日）")
    try:
        due_on = date.fromisoformat(str(due_raw))
        paid_on = date.fromisoformat(str(paid_raw))
    except ValueError as exc:
        raise UsageError("日期格式非法（应为 YYYY-MM-DD）: %s" % exc)

    return LateRequest(
        patent_type=patent_type, year=year, due_on=due_on, paid_on=paid_on, preview=preview
    )


def compute_full_late(
    request: LateRequest, library: Optional[RuleLibrary] = None
) -> LateResult:
    """编排：年费阶梯 → 滞纳金引擎 → 结果对象（不做任何 I/O 渲染）。"""
    lib = library or load_library()
    from ..calc import late as late_mod

    return late_mod.compute_late(
        lib,
        late_mod.LateRequest(
            patent_type=request.patent_type,
            year=request.year,
            due_on=request.due_on,
            paid_on=request.paid_on,
            preview=request.preview,
        ),
    )


@dataclass(frozen=True)
class ReductionRequest:
    """费减判定的输入契约（与 calc.reduction.ReductionRequest 同构，面向 CLI）。"""

    patent_type: PatentType
    year: int
    as_of_year: int
    applicants: Tuple[Dict[str, Any], ...]
    open_license: bool = False
    preview: bool = False


def build_reduction_request(payload: Dict[str, Any], preview: bool = False) -> ReductionRequest:
    """把费减输入 JSON 转成 ReductionRequest；缺字段/金额非法一律 exit 2 语义。"""
    if not isinstance(payload, dict):
        raise UsageError("输入必须是 JSON 对象")
    patent_type_raw = payload.get("patent_type")
    if patent_type_raw in (None, ""):
        raise UsageError("输入缺少必填字段 patent_type")
    try:
        patent_type = parse_patent_type(str(patent_type_raw))
    except ValueError as exc:
        raise UsageError(str(exc), reason_code="unknown_patent_type")

    year_raw = payload.get("year")
    if year_raw in (None, ""):
        raise UsageError("输入缺少必填字段 year（年费缴费年度）")
    try:
        year = int(year_raw)
    except (TypeError, ValueError):
        raise UsageError("year 不是整数: %r" % (year_raw,))
    if year < 1:
        raise UsageError("year 必须为正整数: %d" % year)

    as_of_raw = payload.get("as_of_year")
    if as_of_raw in (None, ""):
        raise UsageError("输入缺少必填字段 as_of_year（费减资格适用年度）")
    try:
        as_of_year = int(as_of_raw)
    except (TypeError, ValueError):
        raise UsageError("as_of_year 不是整数: %r" % (as_of_raw,))
    if as_of_year < 1:
        raise UsageError("as_of_year 必须为正整数: %d" % as_of_year)

    from . import reduction as reduction_mod

    applicants = reduction_mod.parse_applicants(payload.get("applicants"))
    return ReductionRequest(
        patent_type=patent_type,
        year=year,
        as_of_year=as_of_year,
        applicants=applicants,
        open_license=bool(payload.get("open_license")),
        preview=preview,
    )


def compute_full_reduction(
    request: ReductionRequest, library: Optional[RuleLibrary] = None
) -> ReductionResult:
    """编排：费减判定引擎 → 结果对象（不做任何 I/O 渲染）。"""
    lib = library or load_library()
    from ..calc import reduction as reduction_mod

    return reduction_mod.compute_reduction(
        lib,
        reduction_mod.ReductionRequest(
            patent_type=request.patent_type,
            year=request.year,
            as_of_year=request.as_of_year,
            applicants=request.applicants,
            open_license=request.open_license,
            preview=request.preview,
        ),
    )


def late_lines(result: LateResult) -> List[str]:
    """滞纳金结果的人类可读渲染（表现层只做排版）。"""
    lines: List[str] = []
    lines.append("== 滞纳金测算 ==")
    lines.append("专利类型: %s" % result.patent_type.value)
    lines.append("缴费年度: 第 %d 年" % result.year)
    lines.append("规定缴费期限: %s" % result.due_on)
    lines.append("实际缴费日: %s" % result.paid_on)
    if result.computed:
        lines.append("逾期月数: %d 个月（口径 %s）" % (result.overdue_months, result.month_basis))
        lines.append("年费全额: %s 元" % result.full_annuity)
        lines.append("滞纳金费率: %s / 月" % result.monthly_rate)
        lines.append("滞纳金: %s 元" % result.surcharge)
        lines.append("应缴合计（年费+滞纳金）: %s 元" % result.payable)
        lines.append("补缴上限: %s 个月" % result.grace_months)
        for fee in result.related_fees:
            if fee.amount is not None:
                lines.append("关联费用: %s %s 元（按费率表条目，另行缴纳）" % (fee.label, fee.amount))
    else:
        lines.append("滞纳金: 未判定")
    for reason in result.reasons:
        lines.append("原因码: %s" % reason)
    for warning in result.warnings:
        lines.append("提示: %s" % warning)
    for step in result.steps:
        lines.append("  - %s" % step)
    lines.append("")
    lines.append(DISCLAIMER)
    return lines


def reduction_lines(result: ReductionResult) -> List[str]:
    """费减结果的人类可读渲染（表现层只做排版）。"""
    lines: List[str] = []
    lines.append("== 费减资格判定 ==")
    lines.append("专利类型: %s" % result.patent_type.value)
    lines.append("缴费年度: 第 %d 年" % result.year)
    lines.append("适用年度: %d" % result.as_of_year)
    lines.append("主体构成: %d 人（%s）" % (
        result.applicant_count, "共同主体" if result.combined else "单主体"))
    if result.computed:
        lines.append(
            "资格结论: %s" % ("合格" if result.eligible else "不合格（须严格低于阈值，恰好等于不合格）")
        )
        for key in sorted(result.thresholds):
            lines.append("阈值 %s: %s" % (key, result.thresholds[key]))
        if result.threshold_policy_doc_no or result.anchor_from:
            lines.append("阈值锚点: %s（自 %s 起）" % (result.threshold_policy_doc_no, result.anchor_from))
        lines.append("年费全额: %s 元" % result.full_annuity)
        for cand in result.candidates:
            lines.append("候选政策: %s（减免比例 %s → 实缴 %s 元）" % (cand.policy, cand.rate, cand.amount))
        if result.chosen is not None:
            lines.append("选中政策: %s（不叠加，no_double_benefit=%s）" % (
                result.chosen.policy, result.no_double_benefit))
        if result.payable is not None:
            lines.append("减免后应缴: %s 元" % result.payable)
        if result.reduction_rate is not None:
            lines.append("费减比例: %s" % result.reduction_rate)
    else:
        lines.append("资格结论: 未判定")
    for reason in result.reasons:
        lines.append("原因码: %s" % reason)
    for warning in result.warnings:
        lines.append("提示: %s" % warning)
    for step in result.steps:
        lines.append("  - %s" % step)
    lines.append("")
    lines.append(DISCLAIMER)
    return lines


def late_exit_code_for(result: LateResult, preview: bool = False) -> int:
    """滞纳金路径退出码：超上限（warning）与未判定均为降级 1。"""
    if result.warnings and result.computed:
        return 1
    if not result.computed:
        return 1
    if preview:
        return 1
    return 0


def reduction_exit_code_for(result: ReductionResult, preview: bool = False) -> int:
    """费减路径退出码：不合格结论是有效结论（不算降级），未判定才是 1。"""
    if not result.computed:
        return 1
    if preview:
        return 1
    return 0


def exit_code_for(result: AnnuityResult, preview: bool = False) -> int:
    """把结果映射成退出码（四态语义见 errors.ExitCode）。

    ``--preview`` 下即便算出了金额也返回 1：预览不是达标，
    否则 CI/自动化会把预览结论当可用结论。
    """
    if result.warnings and result.computed:
        return 1
    if not result.computed:
        return 1  # 未判定 = 降级完成（不崩、也不假成功）
    if preview:
        return 1
    return 0


def result_lines(result: AnnuityResult, library: RuleLibrary) -> List[str]:
    """人类可读渲染（表现层只做排版，判定全部来自结果对象）。"""
    lines: List[str] = []
    label = result.patent_type.value
    lines.append("== 年费测算 ==")
    lines.append("专利类型: %s" % label)
    lines.append("缴费年度: 第 %d 年" % result.year)
    if result.computed:
        lines.append("应缴年费: %s 元" % result.amount)
        if result.tier is not None:
            span = "第 %d-%d 年" % (result.tier.from_year, result.tier.to_year)
            label = result.tier.label or span
            lines.append("所处区间: %s" % (label if label.endswith(span) else "%s（%s）" % (label, span)))
        if result.basis is not None:
            lines.append("费率依据: %s · %s" % (result.basis.doc_no, result.basis.clause))
            lines.append("依据坐标: %s" % result.basis.coordinate())
    else:
        lines.append("应缴年费: 未判定")
    for reason in result.reasons:
        lines.append("原因码: %s" % reason)
    for warning in result.warnings:
        lines.append("提示: %s" % warning)
    for step in result.steps:
        lines.append("  - %s" % step)
    lines.append("")
    lines.append(DISCLAIMER)
    return lines


# ------------------------------------------------------- 组合批量排期（M3）

@dataclass(frozen=True)
class PortfolioRequest:
    """组合排期的输入契约（与 calc.portfolio.PortfolioRequest 同构，面向 CLI）。

    ``rounds`` 携带跨轮对账的两轮台账（``{"baseline": [...], "current": [...]}``），
    单轮排期输入（``items``）时为空 dict —— 对账口径单一实现源在
    ``calc.portfolio.compare_rounds``，本契约只搬运数据。
    """

    sources: Tuple[Tuple[str, Any], ...]
    today: date
    window_months: int = 3
    preview: bool = False
    rounds: Dict[str, Any] = field(default_factory=dict)


def build_portfolio_request(
    payload: Dict[str, Any], preview: bool = False
) -> "PortfolioRequest":
    """把组合输入 JSON 转成 PortfolioRequest。

    ``today`` 取输入的 ``today`` 字段（合成台账为可复现显式给定）；
    缺省回退**当日**（真实台账默认"从今天看未来"）。条目坏格式不在
    此处抛 —— 失败隔离在引擎（``build_portfolio_entry`` 转 failed）。
    """
    if not isinstance(payload, dict):
        raise UsageError("组合输入必须是 JSON 对象（含 baseline/current/items）")
    from . import portfolio as portfolio_mod

    today_raw = payload.get("today")
    if today_raw in (None, ""):
        today = date.today()
    else:
        try:
            today = date.fromisoformat(str(today_raw))
        except ValueError as exc:
            raise UsageError("today 不是合法日期（YYYY-MM-DD）: %r" % (today_raw,)) from exc

    window_raw = payload.get("window_months")
    if window_raw in (None, ""):
        window_months = 3
    else:
        try:
            window_months = int(window_raw)
        except (TypeError, ValueError) as exc:
            raise UsageError("window_months 不是整数: %r" % (window_raw,)) from exc
        if window_months < 1:
            raise UsageError("window_months 必须为正整数: %d" % window_months)

    if "current" in payload or "baseline" in payload:
        current = payload.get("current")
        if current is None:
            raise UsageError("组合输入给出 baseline/current 时缺 current")
        baseline = payload.get("baseline") or []
        sources = portfolio_mod.parse_portfolio_input({"items": current})
        return PortfolioRequest(
            sources=sources, today=today, window_months=window_months, preview=preview,
            rounds={"baseline": baseline, "current": current},
        )

    if "items" in payload or isinstance(payload.get("current"), list):
        sources = portfolio_mod.parse_portfolio_input(payload)
        return PortfolioRequest(
            sources=sources, today=today, window_months=window_months, preview=preview
        )

    raise UsageError("组合输入缺少 items（或 baseline/current 两轮台账）")


def compute_full_portfolio(
    request: "PortfolioRequest", library: Optional[RuleLibrary] = None
) -> PortfolioResult:
    """编排：组合批量排期 → 结果对象（不做任何 I/O 渲染）。"""
    lib = library or load_library()
    from . import portfolio as portfolio_mod

    inner = portfolio_mod.PortfolioRequest(
        sources=tuple(request.sources),
        today=request.today,
        window_months=request.window_months,
        preview=request.preview,
    )
    return _portfolio_with_disclaimer(portfolio_mod.scan_portfolio(inner, lib))


def _portfolio_with_disclaimer(result: "PortfolioResult") -> "PortfolioResult":
    """免责声明为强制输出：编排层统一挂接（引擎保持纯计算不背文案）。"""
    from dataclasses import replace

    return replace(result, disclaimer=DISCLAIMER)


def portfolio_exit_code_for(result: PortfolioResult, preview: bool = False) -> int:
    """组合排期退出码：**失败件不改变退出码**（plan/03 §七）——
    退出码由"是否检出问题"决定：未缴清 / 未判定 / 窗口内到期 / 失败件 → 1；
    全部已缴清且无到期无问题 → 0。``--preview`` 预览口径照旧为 1。
    """
    if preview:
        return 1
    return 1 if result.detected else 0


def portfolio_rounds(request: "PortfolioRequest") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """取跨轮对账的两轮台账（baseline/current）；单轮输入返回 (current, [])。

    对账口径单一实现源在 ``calc.portfolio.compare_rounds``，本函数只取数。
    """
    rounds = getattr(request, "rounds", None) or {}
    baseline = list(rounds.get("baseline") or [])
    current = list(rounds.get("current") or [])
    if not current:
        current = [payload for _, payload in request.sources if isinstance(payload, dict)]
    return baseline, current


def portfolio_lines(result: PortfolioResult, reconciliation: Optional[Any] = None) -> List[str]:
    """组合排期结果的人类可读渲染（表现层只做排版）。"""
    from . import portfolio as portfolio_mod

    lines: List[str] = []
    lines.append("== 组合批量排期 ==")
    lines.append("基准日: %s" % result.today)
    lines.append("件数合计: %d（失败隔离 %d）" % (len(result.entries), len(result.failed)))
    lines.append("已缴清: %d 件" % len(result.settled))
    lines.append("已到期未缴清: %d 件" % len(result.unpaid))
    lines.append("尚未到期: %d 件" % len(result.not_due))
    if result.uncomputed:
        lines.append("未判定: %d 件" % len(result.uncomputed))
    if result.failed:
        lines.append("失败件（单列，不改变退出码语义）:")
        for entry in result.failed:
            lines.append("  - %s: %s" % (entry.id, entry.reason))
    if result.due_soon:
        lines.append("未来 %d 个月内到期清单（按剩余天数升序）:" % result.window_months)
        for entry in result.due_soon:
            lines.append(
                "  - %s  第 %d 年  %s 到期（还有 %d 天）%s"
                % (
                    entry.patent_no,
                    entry.year or 0,
                    entry.due_on,
                    entry.days_until_due or 0,
                    "  应缴年费 %s 元" % entry.amount if entry.amount is not None else "",
                )
            )
    else:
        lines.append("未来 %d 个月内到期清单:（无）" % result.window_months)
    for entry in result.entries:
        if entry.kind == portfolio_mod.KIND_UNPAID:
            lines.append(
                "已到期未缴清: %s 第 %d 年（%s 到期）" % (entry.patent_no, entry.year or 0, entry.due_on)
            )
    if reconciliation is not None:
        rd = reconciliation.as_dict()
        lines.append("== 跨轮对账（配对主键 patent_no）==")
        lines.append("新增到期: %s" % (", ".join(rd["new_due"]) or "（无）"))
        lines.append("已缴清: %s" % (", ".join(rd["settled"]) or "（无）"))
        lines.append("持续未缴: %s" % (", ".join(rd["still_unpaid"]) or "（无）"))
        if rd["content_changed"]:
            lines.append("内容变化（另立标记）: %s" % ", ".join(rd["content_changed"]))
        if rd["vanished"]:
            lines.append("本轮消失: %s" % ", ".join(rd["vanished"]))
    for line in result.disclaimer.splitlines():
        lines.append(line)
    return lines


def selfcheck(library: RuleLibrary) -> Dict[str, Any]:
    """数据与规则自检：目录定位、规则加载、status 门控计数、复核锚点、依赖可用性。"""
    from ..console import is_frozen

    counts = library.status_counts()
    deps = _optional_dependency_status(is_frozen())
    return {
        "data_dir": str(library.data_dir),
        "rulesets": [
            {
                "id": rs.id,
                "version": rs.version,
                "title": rs.title,
                "doc_no": rs.doc_no,
                "entries": len(rs.entries),
                **rs.status_counts(),
            }
            for rs in sorted(library.rulesets.values(), key=lambda r: r.id)
        ],
        "status_counts": counts,
        "scopes": list(library.scopes),
        "banned_tokens": {
            "integers": sorted(library.banned_integers),
            "decimals": sorted(library.banned_decimals),
        },
        "review": review_status(library.raw_manifest),
        "optional_dependencies": deps,
        "frozen": is_frozen(),
    }


def review_status(manifest: Dict[str, Any], today: Optional[Any] = None) -> Dict[str, Any]:
    """复核锚点状态：manifest 的 ``review_interval`` / ``reviewed`` / ``next_review`` 对今天是否逾期。

    只记"核对过"、不记"何时再看"会让费率表换版无人察觉（失效模式 #15）。本函数把锚点读出来
    并与今天比一次；**逾期只提示，不参与退出码**——新增判据不得把既有仓库判红（plan/06 D55）。
    ``today`` 可注入（测试用固定日期，冻结态自检不用系统时钟做判定）。
    """
    interval = manifest.get("review_interval") or ""
    reviewed = manifest.get("reviewed") or ""
    next_review = manifest.get("next_review") or ""
    if today is None:
        today = date.today()
    info: Dict[str, Any] = {
        "interval": interval,
        "reviewed": reviewed,
        "next_review": next_review,
        "today": today.isoformat(),
        "overdue": False,
        "days_overdue": 0,
        "note": "",
    }
    if not next_review:
        info["note"] = "规则包未下发复核锚点（next_review 缺失）"
        return info
    try:
        due = date.fromisoformat(next_review)
    except ValueError:
        info["note"] = "next_review 不是 YYYY-MM-DD：%r（无法判定是否逾期）" % next_review
        return info
    if today > due:
        info["overdue"] = True
        info["days_overdue"] = (today - due).days
        info["note"] = ("规则包复核已逾期 %d 天（费率表可能已换版）——请回官方原文/费率表页"
                        "复核并在 plan/06 记录新的复核基准日" % info["days_overdue"])
    else:
        info["note"] = "复核未逾期"
    return info


def _optional_dependency_status(frozen: bool) -> Dict[str, Dict[str, Any]]:
    """探测可选依赖是否可用（惰性，不 import 重件）。"""
    import importlib.util

    out: Dict[str, Dict[str, Any]] = {}
    for extra, module in (("report", "openpyxl"), ("gui", "PySide6"), ("build", "PyInstaller")):
        available = importlib.util.find_spec(module) is not None
        from ..errors import dependency_hint

        out[extra] = {
            "module": module,
            "available": available,
            "hint": "" if available else dependency_hint(extra, frozen),
        }
    return out
