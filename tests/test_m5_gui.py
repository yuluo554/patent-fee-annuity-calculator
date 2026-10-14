"""M5：桌面界面（PySide6）—— 零判定逻辑 AST 门禁三条 + offscreen 冒烟。

口径（plan/04 §十 / D26/D27 / FR-8.2）：

* AST 门禁三条齐上（扫 ``src/patfee/gui/``）：
  ① 不 import 规则层/领域层内部模块（只准 ``..calc.pipeline`` 与上层公开面）；
  ② 无算术 ``BinOp``（``* / - // % **`` 全禁；``+`` 仅限字符串/列表排版拼接）；
  ③ 无政策数值字面量（同一份 BANNED_TOKENS，零字面量门禁扫描面已覆盖
     ``src/patfee/**/*.py``，gui 文件天然在内——本测试用 AST 再显式断言）。
* offscreen 交互测试：构造真实窗口、注入桩服务、断言结果区渲染的是
  服务层（编排层）返回的行——界面不做任何自行判定。
* ``QT_QPA_PLATFORM=offscreen`` 由 conftest 在首次 import PySide6 前设置。
"""

from __future__ import annotations

import ast

import pytest

from conftest import repo_root, data_dir

GUI_DIR = repo_root() / "src" / "patfee" / "gui"


def _gui_sources() -> dict:
    return {
        p.relative_to(GUI_DIR).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(GUI_DIR.glob("*.py"))
    }


# ------------------------------------------------------------- 门禁① import 面

def test_gui_ast_gate_no_rule_layer_imports():
    """GUI 不 import 规则层/领域层内部模块（只准 pipeline 与上层公开面）。"""
    banned_prefixes = (
        "..rules", "..domain", "..data_paths", "..benchmark",
        "..calc.annuity", "..calc.late", "..calc.reduction",
    )
    sources = _gui_sources()
    assert sources, "gui 源码目录为空 —— 门禁什么都没查"
    for rel, text in sources.items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if node.level >= 1:
                    for prefix in banned_prefixes:
                        assert not mod.startswith(prefix), (
                            "%s: GUI 禁止 import %s（只准经 calc.pipeline）" % (rel, mod)
                        )
                else:
                    assert not mod.startswith("patfee.rules"), (
                        "%s: GUI 禁止绝对导入 %s" % (rel, mod)
                    )
                    assert not mod.startswith("patfee.domain"), (
                        "%s: GUI 禁止绝对导入 %s" % (rel, mod)
                    )


# ------------------------------------------------------------- 门禁② 无算术 BinOp

def test_gui_ast_gate_no_arithmetic_binop():
    """GUI 无算术运算（金额拼接、年度换算都在编排层）。

    豁免：字符串/列表/元组字面量参与的 ``+``（文本排版与行集合拼接）；
    其余 ``+`` 与全部 ``* / - // % **`` 一律禁止。
    """
    def _is_layout_operand(node: ast.AST) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return True
        return False

    for rel, text in _gui_sources().items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            if isinstance(node.op, ast.Mod):
                # ``%`` 字符串格式化（左侧为 str 常量/名称）是文本排版，非取模
                if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                    continue
                if isinstance(node.left, ast.Name):
                    continue
                raise AssertionError(
                    "%s:%d: GUI 出现非格式化取模（算术应在编排层）" % (rel, node.lineno)
                )
            if isinstance(node.op, ast.Add):
                if _is_layout_operand(node.left) or _is_layout_operand(node.right):
                    continue
                raise AssertionError(
                    "%s:%d: GUI 出现非排版加法（算术应在编排层）" % (rel, node.lineno)
                )
            raise AssertionError(
                "%s:%d: GUI 出现算术运算符 %s（应在编排层）"
                % (rel, node.lineno, type(node.op).__name__)
            )


# ------------------------------------------------------------- 门禁③ 政策数值字面量

def test_gui_ast_gate_no_policy_number_literals():
    """GUI 无政策数值字面量（同一份 BANNED_TOKENS；AST 显式断言防正则漏检）。"""
    from patfee.rules.loader import load_library

    lib = load_library(data_dir())
    banned_ints = set(int(v) for v in lib.banned_integers)
    banned_decs = set(str(v) for v in lib.banned_decimals)

    for rel, text in _gui_sources().items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            value = node.value
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and value in banned_ints:
                raise AssertionError(
                    "%s:%d: GUI 出现禁用整数字面量 %d" % (rel, node.lineno, value)
                )
            if isinstance(value, float):
                token = repr(value)
                assert token not in banned_decs, (
                    "%s:%d: GUI 出现禁用小数字面量 %s" % (rel, node.lineno, token)
                )


def test_gui_files_covered_by_literals_gate_scan():
    """gui 源文件确实在零字面量门禁扫描面内（防 include 模式变化后脱守）。"""
    from patfee.rules import literals_gate
    from patfee.rules.loader import load_library

    lib = load_library(data_dir())
    result = literals_gate.scan_source(
        repo_root(), lib.banned_integers, lib.banned_decimals
    )
    for rel in _gui_sources():
        assert ("src/patfee/gui/" + rel) in result.scanned_files, (
            "gui 文件未进门禁扫描面: %s" % rel
        )


# ------------------------------------------------------------- offscreen 交互

class _StubService:
    """桩服务：记录调用并返回固定行——验证界面只渲染服务层输出。"""

    def __init__(self):
        self.calls = []

    def __call__(self, kind, payload):
        self.calls.append((kind, payload))
        return ["== 桩输出 ==", "kind=%s" % kind, "patent_type=%s" % payload.get("patent_type")]


@pytest.fixture()
def stub_window():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from patfee.gui.main_window import MainWindow

    _ = QApplication.instance() or QApplication([])
    service = _StubService()
    w = MainWindow(service=service)
    yield w, service
    w.close()


def _tab_at(window, index):
    from PySide6.QtWidgets import QTabWidget

    tw = window.findChild(QTabWidget)
    assert tw is not None
    return tw.widget(index)


def _readonly_output(tab):
    from PySide6.QtWidgets import QPlainTextEdit

    outputs = [w for w in tab.findChildren(QPlainTextEdit) if w.isReadOnly()]
    assert outputs, "页签缺少只读结果区"
    return outputs[0]


def _press_button(tab):
    from PySide6.QtWidgets import QPushButton

    buttons = tab.findChildren(QPushButton)
    assert buttons, "页签缺少计算按钮"
    buttons[0].click()


def test_main_window_constructs_with_four_tabs(stub_window):
    from PySide6.QtWidgets import QTabWidget

    window, _ = stub_window
    tw = window.findChild(QTabWidget)
    assert tw.count() == 4
    assert tw.tabText(0) == "年费测算"
    assert tw.tabText(3) == "口径说明"


def test_calc_tab_forwards_payload_and_renders_service_lines(stub_window):
    """年费页签：表单内容进 payload、结果区渲染服务层行（零自行判定）。"""
    from PySide6.QtWidgets import QCheckBox, QLineEdit

    window, service = stub_window
    tab = _tab_at(window, 0)
    edits = tab.findChildren(QLineEdit)
    edits[0].setText("invention")
    edits[1].setText("3")
    _press_button(tab)
    kind, payload = service.calls[-1]
    assert kind == "calc"
    assert payload["patent_type"] == "invention"
    assert payload["year"] == "3"  # 文本直传（Decimal 解析在编排层）
    assert "kind=calc" in _readonly_output(tab).toPlainText()


def test_calc_tab_with_late_flag_in_payload(stub_window):
    from PySide6.QtWidgets import QCheckBox, QLineEdit

    window, service = stub_window
    tab = _tab_at(window, 0)
    edits = tab.findChildren(QLineEdit)
    edits[0].setText("invention")
    edits[1].setText("3")
    for box in tab.findChildren(QCheckBox):
        if "滞纳金" in box.text():
            box.setChecked(True)
    _press_button(tab)
    _, payload = service.calls[-1]
    assert payload["with_late"] is True


def test_service_exception_renders_error_not_crash(stub_window):
    """服务层抛异常：结果区显示错误文案，界面不崩、不自行归因。"""
    from PySide6.QtWidgets import QLineEdit

    window, service = stub_window

    def boom(kind, payload):
        raise ValueError("编排层异常原文")

    tab = _tab_at(window, 0)
    tab._service = boom
    tab.findChildren(QLineEdit)[0].setText("invention")
    _press_button(tab)
    assert "编排层异常原文" in _readonly_output(tab).toPlainText()


def test_reduction_tab_forwards_applicants_json(stub_window):
    import json

    window, service = stub_window
    tab = _tab_at(window, 1)
    tab._applicants.setPlainText('[{"kind": "individual", "monthly_income": "5000"}]')
    _press_button(tab)
    kind, payload = service.calls[-1]
    assert kind == "reduction"
    assert payload["applicants"] == [{"kind": "individual", "monthly_income": "5000"}]
    assert "kind=reduction" in _readonly_output(tab).toPlainText()


def test_reduction_tab_bad_json_shows_error(stub_window):
    window, _ = stub_window
    tab = _tab_at(window, 1)
    tab._applicants.setPlainText("{bad json")
    _press_button(tab)
    assert "错误" in _readonly_output(tab).toPlainText()


def test_scan_tab_forwards_json_payload(stub_window):
    window, service = stub_window
    tab = _tab_at(window, 2)
    tab._input.setPlainText('{"today": "2026-10-14", "items": []}')
    _press_button(tab)
    kind, payload = service.calls[-1]
    assert kind == "scan"
    assert payload["today"] == "2026-10-14"
    assert "kind=scan" in _readonly_output(tab).toPlainText()


def test_scan_tab_bad_json_shows_error(stub_window):
    window, _ = stub_window
    tab = _tab_at(window, 2)
    tab._input.setPlainText("{not json")
    _press_button(tab)
    assert "错误" in _readonly_output(tab).toPlainText()


def test_real_service_through_pipeline_calc(stub_window):
    """接线真服务（compute_lines）：结果区渲染引擎金额（900.00 来自规则包）。"""
    from PySide6.QtWidgets import QLineEdit

    from patfee.gui import compute_lines

    window, _ = stub_window
    tab = _tab_at(window, 0)
    tab._service = compute_lines
    edits = tab.findChildren(QLineEdit)
    edits[0].setText("invention")
    edits[1].setText("3")
    _press_button(tab)
    text = _readonly_output(tab).toPlainText()
    assert "应缴年费: 900.00 元" in text, text
    assert "不构成法律或代理意见" in text


def test_about_tab_static_and_no_external_links(stub_window):
    from PySide6.QtWidgets import QTextBrowser

    window, _ = stub_window
    tab = _tab_at(window, 3)
    for browser in tab.findChildren(QTextBrowser):
        assert not browser.openExternalLinks()


def test_gui_main_entry_offscreen_smoke(monkeypatch):
    """main() 装配可用（offscreen；事件循环经 quit 定时器立即退出）。"""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from patfee.gui import main

    _ = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "patfee.gui.main_window.MainWindow.show", lambda self: None
    )
    QTimer.singleShot(0, _.quit)
    assert main() == 0
