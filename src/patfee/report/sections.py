"""scan 报告的单一渲染源：结果对象 → 结构化章节（M5）。

Markdown（M3 起）与 XLSX（M5 起）两个渲染器消费同一份章节列表，
"两格式内容一致"因此成为结构性质。章节构成（plan/04 §七四块）：

1. 报告头（基准日 / 预警窗口 / 规则包坐标 / 口径）
2. 一、输入事实（逐件输入与排期结论表，含失败隔离件）
3. 二、逐项结论与计算过程（直接渲染引擎输出，报告层不重算）
4. 三、未启用章节（"没查"≠"查了没问题"，显式写出）
5. 四、适用依据与免责声明（含参数来源：文号 + 锚点，文本列）

无外链纪律：章节里不写 URL（依据定位在报告正文用文号表达，URL 只存
evidence.json 的 coordinate 区——机读产物断网可开）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .base import Section


def scan_report_sections(
    result: Any,
    reconciliation: Any,
    library: Any,
    preview: bool,
    not_enabled: Dict[str, str],
    disclaimer: str,
) -> List[Section]:
    """把组合排期结果映射为结构化章节列表（唯一渲染源）。"""
    coord = library.coordinate()

    head_lines: List[Tuple[str, ...]] = (
        ("基准日", str(result.today)),
        ("预警窗口", "未来 %d 个月" % result.window_months),
        ("规则包", ", ".join(
            "%s@%s" % (rs["id"], rs["version"]) for rs in coord.get("rulesets", [])
        )),
    )
    if preview:
        head_lines = head_lines + (("口径", "预览（--preview），结论不得作为缴费依据"),)

    sections: List[Section] = []

    # ---- 报告头（两格式都以文本行呈现） ----
    sections.append(Section(
        title="专利组合费用排期报告",
        heading=1,
        lines=tuple("%s: %s" % (k, v) for k, v in head_lines) + ("",),
    ))

    # ---- 一、输入事实 ----
    fact_header = ("件", "专利号", "类型", "年度", "到期日", "缴费日", "结论", "应缴年费")
    fact_rows: List[Tuple[Optional[str], ...]] = []
    for e in result.entries:
        fact_rows.append((
            e.id, e.patent_no, e.patent_type,
            None if e.year is None else str(e.year),
            e.due_on, e.paid_on, e.kind,
            None if e.amount is None else "%s 元" % e.amount,
        ))
    sections.append(Section(
        title="一、输入事实",
        heading=2,
        rows=(fact_header, tuple(fact_rows)),
        lines=("逐件输入与排期结论（含失败隔离件）。", ""),
    ))

    # ---- 二、逐项结论与计算过程 ----
    from ..calc.pipeline import portfolio_lines

    body = list(portfolio_lines(result, reconciliation))
    sections.append(Section(
        title="二、逐项结论与计算过程",
        heading=2,
        lines=tuple(body) + ("",),
    ))

    # ---- 三、未启用章节 ----
    ne_lines: List[Tuple[str, ...]] = tuple(
        ("%s" % key, text) for key, text in not_enabled.items()
    )
    sections.append(Section(
        title="三、未启用章节（没查 ≠ 查了没问题）",
        heading=2,
        rows=(("能力", "说明"), ne_lines),
        lines=("本次导出未覆盖的能力在上方显式声明，不留空。", ""),
    ))

    # ---- 四、适用依据与免责声明 ----
    basis_rows: List[Tuple[Optional[str], ...]] = []
    for rs in coord.get("rulesets", []):
        basis_rows.append((
            "%s@%s" % (rs.get("id"), rs.get("version")),
            rs.get("title") or "",
            rs.get("doc_no") or "",
            "%s ~ %s" % (rs.get("anchor_from") or "?", rs.get("anchor_to") or "现行"),
        ))
    sections.append(Section(
        title="四、适用依据与免责声明",
        heading=2,
        rows=(("规则集", "标题", "文号", "锚点"), tuple(basis_rows)),
        lines=(disclaimer, ""),
    ))
    return sections
