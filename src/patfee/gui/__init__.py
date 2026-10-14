"""桌面界面（PySide6）：只消费 pipeline 公开函数，零判定逻辑（M5）。

纪律（plan/04 §十 / D26/D27）：

* GUI 只做：收集输入 → 经 ``calc.pipeline`` 构造请求与计算 → 渲染结果文本。
  任何判定（结论、退出码、原因码含义）都来自结果对象，本包不重算。
* 金额/年度输入一律文本框 + 字符串直传（Decimal 解析在编排层）。
* ``QT_QPA_PLATFORM=offscreen`` 由调用方（测试/``--selftest``）在首次
  import PySide6 前设置；本包 import 时不设（真实桌面会话会覆盖 offscreen）。
* 中文字体按 ``WINDIR`` 推导路径显式注册（不写死盘符）。
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ..errors import PatfeeError

APP_TITLE = "专利年费与费减合规计算工作台"


def _register_cjk_font(app: Any) -> None:
    """按 WINDIR 推导中文字体路径并注册（找不到则用系统默认，不报错）。"""
    import os

    windir = os.environ.get("WINDIR")
    if not windir:
        return
    from PySide6.QtGui import QFontDatabase

    for candidate in (
        os.path.join(windir, "Fonts", "msyh.ttc"),
        os.path.join(windir, "Fonts", "simhei.ttf"),
        os.path.join(windir, "Fonts", "simsun.ttc"),
    ):
        if os.path.isfile(candidate):
            QFontDatabase.addApplicationFont(candidate)
            return


def _run_calc(payload: Dict[str, Any], with_late: bool) -> List[str]:
    """年费（可选滞纳金）通路：唯一引擎调用点之一，经 pipeline。"""
    from ..calc import pipeline
    from ..rules.loader import load_library

    request = pipeline.build_request(payload, preview=bool(payload.get("preview")))
    result = pipeline.compute_full_calc(request)
    lines = pipeline.result_lines(result, load_library())
    exit_code = pipeline.exit_code_for(result, preview=bool(payload.get("preview")))
    if with_late:
        late_request = pipeline.build_late_request(payload, preview=bool(payload.get("preview")))
        late_result = pipeline.compute_full_late(late_request)
        lines.append("")
        lines.extend(pipeline.late_lines(late_result))
        late_code = pipeline.late_exit_code_for(late_result, preview=bool(payload.get("preview")))
        exit_code = max(exit_code, late_code)
    lines.append("")
    lines.append("退出码语义: %d（0 完成 / 1 降级或预览 / 2 输入错误 / 3 缺依赖）" % exit_code)
    return lines


def _run_reduction(payload: Dict[str, Any]) -> List[str]:
    """费减判定通路：经 pipeline。"""
    from ..calc import pipeline

    request = pipeline.build_reduction_request(payload, preview=bool(payload.get("preview")))
    result = pipeline.compute_full_reduction(request)
    return pipeline.reduction_lines(result)


def _run_scan(payload: Dict[str, Any]) -> List[str]:
    """组合排期通路：经 pipeline（含跨轮对账口径单一实现源）。"""
    from ..calc import pipeline
    from ..calc.portfolio import compare_rounds

    request = pipeline.build_portfolio_request(payload, preview=bool(payload.get("preview")))
    result = pipeline.compute_full_portfolio(request)
    baseline, current = pipeline.portfolio_rounds(request)
    reconciliation = compare_rounds(baseline, current)
    return pipeline.portfolio_lines(result, reconciliation)


def compute_lines(kind: str, payload: Dict[str, Any]) -> List[str]:
    """GUI 的唯一取数口：三条通路全部转发 pipeline（FR-8.2 唯一引擎调用点）。"""
    if kind == "calc":
        return _run_calc(payload, with_late=bool(payload.get("with_late")))
    if kind == "reduction":
        return _run_reduction(payload)
    if kind == "scan":
        return _run_scan(payload)
    raise PatfeeError("未知通路: %s" % kind, reason_code="usage_error")


def main() -> int:
    """事件循环入口。缺依赖的 ImportError 由 cmd_gui 的 try 捕获（exit 3）。"""
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    _register_cjk_font(app)
    window = MainWindow(service=compute_lines)
    window.show()
    return app.exec()
