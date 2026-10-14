"""Markdown 渲染器：消费 report_sections 的结构化章节（表现层只做排版）。"""

from __future__ import annotations

from typing import List

from .base import Section


def _cell(value: object) -> str:
    if value is None:
        return "—"
    text = str(value)
    # Markdown 表格竖线转义（金额/编号不含，但来源文本可能含）
    return text.replace("|", "\\|")


def render_markdown(sections: List[Section]) -> str:
    """把结构化章节渲染成 Markdown 文本（不含末尾换行）。"""
    lines: List[str] = []
    for section in sections:
        lines.append("%s %s" % ("#" * max(1, section.heading), section.title))
        lines.append("")
        header = section.header()
        rows = section.table_rows()
        if header:
            lines.append("| %s |" % " | ".join(_cell(c) for c in header))
            lines.append("|%s|" % "---|" * len(header))
            for row in rows:
                lines.append("| %s |" % " | ".join(_cell(c) for c in row))
            lines.append("")
        for line in section.lines:
            lines.append(line)
        if section.lines or (not header and rows):
            lines.append("")
    # 去掉末尾多余空行，统一以单个换行结尾
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"
