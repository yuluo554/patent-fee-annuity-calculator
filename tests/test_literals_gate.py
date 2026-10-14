"""零政策字面量门禁测试（含阳性对照与变异验证）。

纪律：门禁"全绿"可能只是"什么都没查" —— 所以本文件既验真实扫描面干净，
也验**门禁本身可证伪**（注入禁用 token 必须报红、token 集为空必须报配置错误）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import data_dir, repo_root
from patfee.rules import literals, literals_gate
from patfee.rules.loader import load_library


@pytest.fixture(scope="module")
def lib():
    return load_library(data_dir())


def test_scan_face_is_nonempty(lib):
    result = literals_gate.scan_source(repo_root(), lib.banned_integers, lib.banned_decimals)
    assert len(result.scanned_files) >= 8, "扫描面过小，门禁覆盖不足"
    assert any("cli.py" in f for f in result.scanned_files), "CLI 必须在扫描面内"
    assert any("annuity.py" in f for f in result.scanned_files), "引擎必须在扫描面内"


def test_banned_token_set_is_nonempty(lib):
    """token 集为空 = 门禁什么都没查，属配置错误。"""
    assert lib.banned_integers, "禁用整数集为空"
    assert "0.05" in {str(v) for v in lib.banned_decimals}, "滞纳金月费率必须进禁用小数集"


def test_policy_values_are_banned(lib):
    """政策数值必须在禁用 token 集内（防抄进代码的第二份真相）。"""
    for value in (900, 1200, 2000, 4000, 6000, 8000, 500, 2500, 200, 1000, 2400,
                  60000, 1000000, 5000, 42000, 300000, 3500):
        assert value in lib.banned_integers, "%d 未进禁用整数集" % value
    for value in ("0.05", "0.85", "0.70", "0.15"):
        assert value in set(str(v) for v in lib.banned_decimals), "%s 未进禁用小数集" % value


def test_engine_sources_are_clean(lib):
    result = literals_gate.scan_source(repo_root(), lib.banned_integers, lib.banned_decimals)
    assert result.ok, "源码命中禁用 token（硬门）:\n%s" % literals_gate.format_report(result)


def test_generator_is_out_of_scan_face(lib):
    """生成器是规则值的唯一来源，必须不在扫描面内（否则自己报自己）。"""
    result = literals_gate.scan_source(repo_root(), lib.banned_integers, lib.banned_decimals)
    assert "tools/gen_rulesets.py" not in result.scanned_files


def test_selftest_detects_injected_token_mutation(lib):
    """变异验证：注入禁用 token → 门禁必须报红。

    这是"新增守门要做变异验证"的落地——故意弄坏被测行为，门必须变红。
    """
    ok, note = literals_gate.selftest(repo_root(), lib.banned_integers, lib.banned_decimals)
    assert ok, note


def test_selftest_refuses_empty_token_set():
    """token 集为空时门禁必须拒绝自证（不许报"通过"）。"""
    ok, note = literals_gate.selftest(repo_root(), [], [])
    assert ok is False
    assert "配置错误" in note


def test_empty_token_set_scan_reports_ok_but_selftest_catches(tmp_path):
    """反证：token 集为空时扫描一定"全绿"——正因如此才必须有 selftest 兜底。"""
    src = tmp_path / "src" / "patfee"
    src.mkdir(parents=True)
    (src / "x.py").write_text("A = 900\n", encoding="utf-8")
    result = literals_gate.scan_source(tmp_path, [], [])
    assert result.ok is True, "空 token 集下扫描必然全绿（这正是需要自检的原因）"
    ok, _ = literals_gate.selftest(tmp_path, [], [])
    assert ok is False


def test_inline_allow_mark_is_reported_not_silently_dropped(tmp_path):
    """行内放行必须仍然打印（可审计"为什么放过"），不许静默吞。"""
    src = tmp_path / "src" / "patfee"
    src.mkdir(parents=True)
    (src / "y.py").write_text("A = 900  # literal-ok: 测试夹具\n", encoding="utf-8")
    result = literals_gate.scan_source(tmp_path, [900], [])
    assert result.ok is True
    assert len(result.allowed) == 1
    report = literals_gate.format_report(result)
    assert "行内放行 1 处" in report
    assert "900" in report


def test_decimal_and_integer_matching_uses_word_boundaries(tmp_path):
    """词边界：1200 不应命中 12000 或 0.1200。"""
    src = tmp_path / "src" / "patfee"
    src.mkdir(parents=True)
    (src / "z.py").write_text("A = 12000\nB = 'x1200y'\nC = 1200\n", encoding="utf-8")
    result = literals_gate.scan_source(tmp_path, [1200], [])
    assert len(result.hits) == 1
    assert result.hits[0].lineno == 3


def test_exemptions_cover_calendar_and_precision_constants():
    """豁免口径写死：小整数（日历/结构）与精度约定小数。"""
    assert literals.is_exempt_integer(12)
    assert literals.is_exempt_integer(99)
    assert not literals.is_exempt_integer(100)
    assert literals.is_exempt_decimal("0.01")
    assert not literals.is_exempt_decimal("0.05")
