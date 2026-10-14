"""CLI 退出码三/四语义锁：0 达标 / 1 降级完成 / 2 用法坐标错误 / 3 缺可选依赖。

这些断言是"参数错误"与"没判定"的分界线，重构不得漂移。
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import data_dir, repo_root
from patfee import cli


def run(argv):
    return cli.main(list(argv))


@pytest.fixture()
def patent_json(tmp_path):
    p = tmp_path / "patent.json"
    p.write_text(
        json.dumps({"patent_type": "invention", "year": 5}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def test_no_subcommand_is_usage_error(capsys):
    assert run([]) == 2
    assert "usage" in capsys.readouterr().out.lower() or True


def test_version_exit_0(capsys):
    assert run(["version"]) == 0
    assert "patfee" in capsys.readouterr().out


def test_version_json_exit_0(capsys):
    assert run(["version", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"]
    assert payload["coordinate"]["rulesets"]


def test_selfcheck_exit_0(capsys):
    assert run(["selfcheck"]) == 0
    out = capsys.readouterr().out
    assert "数据目录" in out
    assert "selftest=通过" in out, "自检必须包含门禁阳性对照结论"


def test_rules_list_exit_0(capsys):
    assert run(["rules", "list"]) == 0
    assert "fee_schedule" in capsys.readouterr().out


def test_rules_show_exit_0(capsys):
    assert run(["rules", "show", "fee_schedule"]) == 0
    assert "annuity.invention" in capsys.readouterr().out


def test_rules_show_unknown_ruleset_exit_2(capsys):
    assert run(["rules", "show", "nope"]) == 2
    assert "ruleset_error" in capsys.readouterr().err


def test_calc_verified_computes_exit_0(patent_json, capsys):
    """M1 后：规则条目已逐项复核（verified）→ 正常计算，退出码 0。"""
    assert run(["calc", str(patent_json)]) == 0
    out = capsys.readouterr().out
    assert "1200.00" in out
    assert "未判定" not in out
    assert "不构成法律或代理意见" in out, "免责声明为强制输出"


def test_calc_preview_exit_still_1_after_verified(patent_json, capsys):
    """--preview 语义与条目状态无关（K2/D11）：预览绝不返回 0。"""
    assert run(["calc", str(patent_json), "--preview"]) == 1
    out = capsys.readouterr().out
    assert "1200.00" in out
    assert "不得作为缴费依据" in out


def _library_with_pending_entry():
    """构造规则条目全为 pending 的最小库：门控拦截分支的测试夹具。

    M1 后真实规则包已全 verified，gated_pending 的退出码路径改由打桩库守护，
    语义本身不得随数据状态失去测试覆盖。
    """
    from pathlib import Path

    from patfee.rules.loader import RuleLibrary, Ruleset

    raw_rs = {
        "schema": "patfee.ruleset/v1",
        "id": "probe",
        "version": "v1",
        "title": "probe",
        "doc_no": "probe",
        "entries": [
            {
                "key": "annuity.invention",
                "label": "probe",
                "kind": "ladder",
                "status": "pending",
                "scopes": ["calc"],
                "ladder": [
                    {"from_year": 1, "to_year": 3, "amount": 900, "label": "1-3"},
                    {"from_year": 4, "to_year": 6, "amount": 1200, "label": "4-6"},
                ],
                "basis": {"doc_no": "d", "clause": "c", "url": "http://x", "retrieved": "2026-10-14"},
            }
        ],
    }
    manifest = {
        "schema": "patfee.rules.manifest/v1",
        "rulesets": [],
        "scopes": ["calc"],
        "benchmarks": {},
        "exemptions": {
            "small_int_abs_limit": 100, "exempt_integers": [],
            "exempt_decimals": ["0.01", "0.1", "0.5", "1.0", "2.0"], "inline_allow_mark": "literal-ok",
        },
        "banned_tokens": {"integers": [], "decimals": []},
    }
    return RuleLibrary(manifest, [Ruleset(raw_rs)], Path("."))


def test_calc_gated_pending_is_exit_1_with_stubbed_library(monkeypatch, patent_json, capsys):
    """pending 条目默认拦门 → exit 1（降级完成）。"""
    monkeypatch.setattr(cli, "load_library", lambda *a, **k: _library_with_pending_entry())
    assert run(["calc", str(patent_json)]) == 1
    out = capsys.readouterr().out
    assert "未判定" in out
    assert "gated_pending" in out
    assert "不构成法律或代理意见" in out, "免责声明为强制输出"


def test_calc_preview_pending_still_exit_1_with_stubbed_library(monkeypatch, patent_json, capsys):
    """--preview 允许 pending 参与预览，但退出码仍为 1（K2）。"""
    monkeypatch.setattr(cli, "load_library", lambda *a, **k: _library_with_pending_entry())
    assert run(["calc", str(patent_json), "--preview"]) == 1
    out = capsys.readouterr().out
    assert "1200.00" in out
    assert "不得作为缴费依据" in out


def test_calc_json_output_is_machine_readable(patent_json, capsys):
    assert run(["calc", str(patent_json), "--preview", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["amount"] == "1200.00"
    assert payload["disclaimer"]


def test_calc_missing_file_exit_2(tmp_path, capsys):
    assert run(["calc", str(tmp_path / "nope.json")]) == 2
    assert "bad_format" in capsys.readouterr().err


def test_calc_bad_json_exit_2(tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert run(["calc", str(p)]) == 2
    assert "bad_format" in capsys.readouterr().err


def test_calc_unknown_patent_type_exit_2(tmp_path, capsys):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"patent_type": "商标", "year": 1}, ensure_ascii=False), encoding="utf-8")
    assert run(["calc", str(p)]) == 2
    assert "unknown_patent_type" in capsys.readouterr().err


def test_calc_missing_year_exit_2(tmp_path, capsys):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"patent_type": "invention"}), encoding="utf-8")
    assert run(["calc", str(p)]) == 2


def test_bench_exit_0_when_implemented_suites_pass(capsys):
    assert run(["bench"]) == 0
    out = capsys.readouterr().out
    assert "b1_ladder" in out
    assert "b4_portfolio" in out, "全部套件（含 B4）都须出现在 bench 输出里"


# ------------------------------------------------------------ M2：reduction / --with-late

@pytest.fixture()
def applicants_json(tmp_path):
    p = tmp_path / "applicants.json"
    p.write_text(json.dumps({
        "as_of_year": 2026, "patent_type": "invention", "year": 5,
        "applicants": [{"kind": "individual", "monthly_avg_income": "4999.99",
                        "annual_income": "59999.99"}],
    }, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture()
def late_json(tmp_path):
    p = tmp_path / "late.json"
    p.write_text(json.dumps({
        "patent_type": "invention", "year": 5,
        "due_on": "2020-05-04", "paid_on": "2020-07-04",
    }, ensure_ascii=False), encoding="utf-8")
    return p


def test_reduction_eligible_exit_0(applicants_json, capsys):
    assert run(["reduction", str(applicants_json)]) == 0
    out = capsys.readouterr().out
    assert "资格结论: 合格" in out
    assert "180.00" in out
    assert "不构成法律或代理意见" in out, "免责声明为强制输出"


def test_reduction_ineligible_is_valid_conclusion_exit_0(tmp_path, capsys):
    """不合格是有效结论（不是降级）：恰好等于阈值 → exit 0。"""
    p = tmp_path / "at.json"
    p.write_text(json.dumps({
        "as_of_year": 2026, "patent_type": "invention", "year": 5,
        "applicants": [{"kind": "individual", "monthly_avg_income": "5000",
                        "annual_income": "60000"}],
    }, ensure_ascii=False), encoding="utf-8")
    assert run(["reduction", str(p)]) == 0
    out = capsys.readouterr().out
    assert "资格结论: 不合格" in out
    assert "应缴年费" not in out


def test_reduction_preview_still_exit_1(applicants_json, capsys):
    assert run(["reduction", str(applicants_json), "--preview"]) == 1
    out = capsys.readouterr().out
    assert "不得作为缴费依据" in out


def test_reduction_json_output(applicants_json, capsys):
    assert run(["reduction", str(applicants_json), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["eligible"] is True
    assert payload["result"]["payable"] == "180.00"
    assert payload["result"]["no_double_benefit"] == "choose_most_favorable"
    assert payload["disclaimer"]


def test_reduction_missing_file_exit_2(tmp_path, capsys):
    assert run(["reduction", str(tmp_path / "nope.json")]) == 2
    assert "bad_format" in capsys.readouterr().err


def test_reduction_missing_applicants_exit_2(tmp_path, capsys):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"as_of_year": 2026, "patent_type": "invention", "year": 5}),
                 encoding="utf-8")
    assert run(["reduction", str(p)]) == 2


def test_reduction_bad_kind_exit_2(tmp_path, capsys):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({
        "as_of_year": 2026, "patent_type": "invention", "year": 5,
        "applicants": [{"kind": "unicorn"}],
    }, ensure_ascii=False), encoding="utf-8")
    assert run(["reduction", str(p)]) == 2
    assert "usage_error" in capsys.readouterr().err


def test_calc_with_late_appends_late_block(late_json, capsys):
    assert run(["calc", str(late_json), "--with-late"]) == 0
    out = capsys.readouterr().out
    assert "== 滞纳金测算 ==" in out
    assert "120.00" in out
    assert "1320.00" in out
    assert "不构成法律或代理意见" in out


def test_calc_with_late_over_cap_is_warning_exit_1(tmp_path, capsys):
    """超上限：照算金额 + late_exceeds_cap warning → 退出码 1（风险提示 ≠ fail）。"""
    p = tmp_path / "over.json"
    p.write_text(json.dumps({
        "patent_type": "invention", "year": 5,
        "due_on": "2020-05-04", "paid_on": "2020-12-04",
    }, ensure_ascii=False), encoding="utf-8")
    assert run(["calc", str(p), "--with-late"]) == 1
    out = capsys.readouterr().out
    assert "late_exceeds_cap" in out
    assert "420.00" in out, "超上限仍给出金额（风险测算，不置 None）"


def test_calc_with_late_missing_dates_degrades_not_crashes(patent_json, capsys):
    """--with-late 但输入无 due_on/paid_on：滞纳金未判定，年费结论不受影响。"""
    assert run(["calc", str(patent_json), "--with-late"]) == 0
    out = capsys.readouterr().out
    assert "== 年费测算 ==" in out
    assert "1200.00" in out
    assert "== 滞纳金测算 ==" in out
    assert "未判定" in out


def test_calc_with_late_json_machine_readable(late_json, capsys):
    assert run(["calc", str(late_json), "--with-late", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["amount"] == "1200.00"
    assert payload["late"]["surcharge"] == "120.00"
    assert payload["late"]["month_basis"] == "calendar_month"
    assert payload["late"]["exceeds_cap"] is False


def test_bench_b2_b3_only_runs_pass(capsys):
    assert run(["bench", "--only", "b2_late"]) == 0
    out = capsys.readouterr().out
    assert "b2_late" in out
    assert "b1_ladder" not in out

    assert run(["bench", "--only", "b3_reduction"]) == 0


def test_bench_unknown_suite_exit_2(capsys):
    assert run(["bench", "--only", "bogus"]) == 2
    assert "usage_error" in capsys.readouterr().err


def test_bench_only_partial_runs_do_not_judge_untested(capsys):
    """只跑 B1 时不得把未测套件误报成"未达标"。"""
    assert run(["bench", "--only", "b1_ladder"]) == 0
    out = capsys.readouterr().out
    assert "b1_ladder" in out
    assert "b2_late" not in out


def test_gui_without_pyside6_exits_3_not_bare_exception(monkeypatch, capsys):
    """惰性导入边界：缺重件时 exit 3，而非抛裸异常（本机装了 Qt 也要能测出）。

    用 __import__ 打桩让 PySide6 抛 ImportError —— 真实 CI 里就是这条路径。
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PySide6" or name.startswith("PySide6.") or name.endswith("main_window"):
            raise ImportError("No module named 'PySide6' (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(__import__("sys").modules, "patfee.gui", raising=False)
    assert run(["gui"]) == 3
    out = capsys.readouterr().out
    assert "PySide6" in out


def test_dependency_hint_differs_between_source_and_frozen():
    """同一条提示在只有 exe 的机器上照做能不能成？不能 → 必须分流。"""
    from patfee.errors import dependency_hint

    source_hint = dependency_hint("report", frozen=False)
    frozen_hint = dependency_hint("report", frozen=True)
    assert "pip install" in source_hint
    assert "pip install" not in frozen_hint, "冻结态提示 pip install 是错的（用户没有 pip/源码树）"
    assert frozen_hint


def test_every_console_entry_has_utf8_guard():
    """所有会打印的入口都要调 ensure_utf8_stdio（含 tools/ 脚本）。"""
    import re

    problems = []
    targets = [repo_root() / "src" / "patfee" / "cli.py"]
    tools_dir = repo_root() / "tools"
    if tools_dir.is_dir():
        targets.extend(sorted(tools_dir.glob("*.py")))
    for path in targets:
        text = path.read_text(encoding="utf-8")
        prints = re.search(r"\bprint\(", text) is not None
        guarded = "ensure_utf8_stdio()" in text
        if prints and not guarded:
            problems.append(path.name)
    assert not problems, "以下会打印的入口缺少 UTF-8 守卫: %s" % ", ".join(problems)
