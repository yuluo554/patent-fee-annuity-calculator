"""主窗口：多页签布局，页签内零判定逻辑（plan/04 §十）。

每个页签的形态：左侧输入表单（文本框，金额/年度/日期均为字符串直传），
右侧只读结果文本。判定（结论/原因码/免责声明）全部来自 pipeline 返回的
渲染行——本模块不 import 规则层、不做算术、不写政策数值（AST 门禁三条，
tests/test_m5_gui.py 守门）。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import __version__

Service = Callable[[str, Dict[str, Any]], List[str]]


class _ResultBox(QGroupBox):
    """只读结果区（所有页签共用，只渲染编排层返回的文本行）。"""

    def __init__(self) -> None:
        super().__init__("结果（渲染引擎输出，界面零判定逻辑）")
        layout = QVBoxLayout(self)
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        layout.addWidget(self._output)

    def show_lines(self, lines: List[str]) -> None:
        self._output.setPlainText("\n".join(lines))

    def show_error(self, message: str) -> None:
        self._output.setPlainText("错误: %s" % message)


class _CalcTab(QWidget):
    """年费（可选滞纳金）页签。"""

    def __init__(self, service: Service) -> None:
        super().__init__()
        self._service = service
        self._fields: Dict[str, QLineEdit] = {}
        self._checkboxes: Dict[str, QCheckBox] = {}

        layout = QHBoxLayout(self)
        form_box = QGroupBox("输入（合成演示号段 99000000…SYN）")
        form = QFormLayout(form_box)
        for name, label, default in (
            ("patent_type", "专利类型（invention/utility_model/design）", "invention"),
            ("year", "缴费年度", "3"),
            ("due_on", "规定缴费期限（YYYY-MM-DD，勾选滞纳金时）", ""),
            ("paid_on", "实际缴费日（YYYY-MM-DD，勾选滞纳金时）", ""),
        ):
            edit = QLineEdit(default)
            self._fields[name] = edit
            form.addRow(QLabel(label), edit)
        for name, label in (
            ("with_late", "追加滞纳金测算（需 due_on/paid_on）"),
            ("preview", "预览口径（结论不作缴费依据）"),
        ):
            box = QCheckBox(label)
            self._checkboxes[name] = box
            form.addRow(box)
        button = QPushButton("计算")
        button.clicked.connect(self._on_compute)
        form.addRow(button)
        layout.addWidget(form_box, stretch=2)
        self._result = _ResultBox()
        layout.addWidget(self._result, stretch=3)

    def _on_compute(self) -> None:
        payload: Dict[str, Any] = {
            name: edit.text().strip() for name, edit in self._fields.items()
        }
        for name, box in self._checkboxes.items():
            payload[name] = box.isChecked()
        try:
            self._result.show_lines(self._service("calc", payload))
        except Exception as exc:  # 编排层异常原样呈现，界面不自行归因
            self._result.show_error(str(exc))


class _ReductionTab(QWidget):
    """费减页签：applicants 以 JSON 文本输入，转发编排层解析。"""

    def __init__(self, service: Service) -> None:
        super().__init__()
        self._service = service
        self._fields: Dict[str, QLineEdit] = {}

        layout = QHBoxLayout(self)
        form_box = QGroupBox("费减输入")
        form = QFormLayout(form_box)
        for name, label, default in (
            ("patent_type", "专利类型", "invention"),
            ("year", "缴费年度", "3"),
            ("as_of_year", "费减资格适用年度", "2026"),
        ):
            edit = QLineEdit(default)
            self._fields[name] = edit
            form.addRow(QLabel(label), edit)
        self._applicants = QPlainTextEdit()
        self._applicants.setPlaceholderText(
            '[{"kind": "individual", "monthly_income": "<月均收入>"}]'
        )
        form.addRow(QLabel("主体列表 JSON"), self._applicants)
        self._open_license = QCheckBox("开放许可（多政策择一不叠加）")
        form.addRow(self._open_license)
        self._preview = QCheckBox("预览口径")
        form.addRow(self._preview)
        button = QPushButton("计算")
        button.clicked.connect(self._on_compute)
        form.addRow(button)
        layout.addWidget(form_box, stretch=2)
        self._result = _ResultBox()
        layout.addWidget(self._result, stretch=3)

    def _on_compute(self) -> None:
        payload: Dict[str, Any] = {
            name: edit.text().strip() for name, edit in self._fields.items()
        }
        payload["open_license"] = self._open_license.isChecked()
        payload["preview"] = self._preview.isChecked()
        applicants_text = self._applicants.toPlainText().strip()
        if applicants_text:
            try:
                payload["applicants"] = json.loads(applicants_text)
            except ValueError as exc:
                self._result.show_error("主体列表 JSON 非法（%s）" % exc)
                return
        try:
            self._result.show_lines(self._service("reduction", payload))
        except Exception as exc:
            self._result.show_error(str(exc))


class _ScanTab(QWidget):
    """组合排期页签：JSON 直贴输入（批量台账天然是 JSON）。"""

    def __init__(self, service: Service) -> None:
        super().__init__()
        self._service = service
        layout = QHBoxLayout(self)
        form_box = QGroupBox("组合台账 JSON（items 或 baseline/current；today 显式给定可复现）")
        form_layout = QVBoxLayout(form_box)
        self._input = QPlainTextEdit()
        self._input.setPlaceholderText('{\n  "today": "2026-10-14",\n  "items": [ ... ]\n}')
        form_layout.addWidget(self._input)
        button = QPushButton("扫描")
        button.clicked.connect(self._on_compute)
        form_layout.addWidget(button)
        layout.addWidget(form_box, stretch=2)
        self._result = _ResultBox()
        layout.addWidget(self._result, stretch=3)

    def _on_compute(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            self._result.show_error("请粘贴组合台账 JSON")
            return
        try:
            payload = json.loads(text)
        except ValueError as exc:
            self._result.show_error("JSON 非法（%s）" % exc)
            return
        try:
            self._result.show_lines(self._service("scan", payload))
        except Exception as exc:
            self._result.show_error(str(exc))


class _AboutTab(QWidget):
    """口径说明页签（静态文案，无计算）。"""

    def __init__(self) -> None:
        super().__init__()
        text = QTextBrowser()
        text.setOpenExternalLinks(False)  # 零上传/零外跳
        text.setPlainText(
            "口径说明\n"
            "--------\n"
            "* 本界面只渲染引擎结果：所有结论、原因码、免责声明来自编排层\n"
            "  （calc.pipeline），界面零判定逻辑（AST 门禁三条守门）。\n"
            "* 金额与年度为文本输入，Decimal 解析在编排层（NFR-2 计价精度）。\n"
            "* 全本地处理、零上传、零 API 依赖（NFR-3/4）。\n"
            "* 免责声明：本输出为基于官方费率表与政策文本的费用测算，\n"
            "  不构成法律或代理意见；正式缴费金额以国家知识产权局规定与缴费通知为准。\n"
        )
        layout = QVBoxLayout(self)
        layout.addWidget(text)


class MainWindow(QWidget):
    """主窗口：三个业务页签 + 一个口径说明页签。"""

    def __init__(self, service: Service) -> None:
        super().__init__()
        self.setWindowTitle("专利年费与费减合规计算工作台 v%s" % __version__)

        tabs = QTabWidget()
        tabs.addTab(_CalcTab(service), "年费测算")
        tabs.addTab(_ReductionTab(service), "费减判定")
        tabs.addTab(_ScanTab(service), "组合排期")
        tabs.addTab(_AboutTab(), "口径说明")

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        self.resize(1080, 640)
