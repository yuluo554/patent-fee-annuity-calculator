"""编排层：CLI 与 GUI 共用的唯一业务编排入口。

纪律（plan/06 D26）：**同一个业务判断在项目里只能有一处实现**。
表现层只准经本模块的公开函数取数，不得自行复现任何判定逻辑。
后续里程碑的费减、滞纳金、组合排期同样上收到这里。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from ..domain.models import AnnuityResult, PatentType, parse_patent_type
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


def selfcheck(library: RuleLibrary) -> Dict[str, Any]:
    """数据与规则自检：目录定位、规则加载、status 门控计数、依赖可用性。"""
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
        "optional_dependencies": deps,
        "frozen": is_frozen(),
    }


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
