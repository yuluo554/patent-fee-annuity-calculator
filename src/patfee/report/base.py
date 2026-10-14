"""报告层数据结构：Section（单一渲染源的章节载体）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Section:
    """报告章节：标题 + 行集合。

    ``rows`` 是"列名元组 + 行元组列表"的表；``lines`` 是纯文本行。
    两格式渲染器对同一 Section 消费：Markdown 把 rows 渲染成表格、
    XLSX 渲染成工作表；lines 两边都是文本。
    """

    title: str
    rows: Tuple[Tuple[str, ...], List[Tuple[Optional[str], ...]]] = ()
    lines: Tuple[str, ...] = ()
    heading: int = 2  # Markdown 标题级别（报告头 1、章节 2）；XLSX 不消费

    def header(self) -> Tuple[str, ...]:
        return tuple(self.rows[0]) if self.rows else ()

    def table_rows(self) -> List[Tuple[Optional[str], ...]]:
        return list(self.rows[1]) if self.rows else ()
