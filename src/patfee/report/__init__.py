"""报告层：单一渲染源 + Markdown / XLSX 双格式渲染器（M5）。

纪律（plan/04 §七 / D50 顺延项）：

* **单一渲染源**：:func:`scan_report_sections` 返回结构化章节列表，
  Markdown 与 XLSX 渲染器各自消费它 —— "两格式内容一致"是**结构性质**，
  由三方对账测试守门，不是人工比对。
* **四块齐备**：输入事实 / 逐项结论与计算过程 / 未启用章节 / 适用依据与免责声明。
* **未启用章节显式写出**（"没查"≠"查了没问题"，K42）。
* **无外链**：机读产物断网可开——XLSX 单元格与 Markdown 正文不含 URL，
  URL 只落依据的**文本列**（文号 + 锚点表达，不生成超链接对象）。
* **逐字节可复现**：XLSX zip 条目 ``ZIP_STORED`` + 固定 ``date_time`` +
  ``create_system=0``，文档属性时间戳固定（实测两次导出 sha256 一致）。
"""

from __future__ import annotations

from .base import Section
from .sections import scan_report_sections

__all__ = ["Section", "scan_report_sections"]
