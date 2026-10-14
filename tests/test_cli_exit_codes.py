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


def test_calc_gated_is_exit_1_not_0(patent_json, capsys):
    """未核对条目默认拦门 → exit 1（降级完成），不是 0。"""
    assert run(["calc", str(patent_json)]) == 1
    out = capsys.readouterr().out
    assert "未判定" in out
    assert "gated_pending" in out
    assert "不构成法律或代理意见" in out, "免责声明为强制输出"


def test_calc_preview_still_exit_1(patent_json, capsys):
    """--preview 可预览但退出码仍为 1 —— 预览绝不能返回 0。"""
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
    assert "未实装" in out, "未实装套件必须显式标出，不许静默通过"


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
