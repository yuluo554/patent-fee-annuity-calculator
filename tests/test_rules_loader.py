"""规则包加载与 schema 校验测试。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import data_dir
from patfee.errors import RulesetError
from patfee.rules.loader import (
    STATUS_INPUT_REQUIRED,
    STATUS_PENDING,
    STATUS_VERIFIED,
    load_library,
)


def test_library_loads_and_schema_valid():
    lib = load_library(data_dir())
    assert lib.rulesets, "至少应加载到一份规则集"
    assert set(lib.rulesets) >= {"fee_schedule", "reduction_78", "reduction_316", "reduction_594"}
    for rs in lib.rulesets.values():
        assert rs.entries, "规则集 %s 不应为空" % rs.id
        assert rs.doc_no, "规则集 %s 必须挂文号" % rs.id


def test_every_entry_has_basis_with_url_and_date():
    """每条规则必须挂出处（文号 + 条款 + URL + 抓取日期）——未挂原文不得落库。"""
    lib = load_library(data_dir())
    for rs in lib.rulesets.values():
        for key, entry in rs.entries.items():
            basis = entry.basis or {}
            assert basis.get("doc_no"), "%s 缺 doc_no" % key
            assert basis.get("clause"), "%s 缺 clause" % key
            assert basis.get("url", "").startswith("http"), "%s 缺合法 URL" % key
            assert basis.get("retrieved"), "%s 缺 retrieved 日期" % key


def test_status_values_are_valid():
    lib = load_library(data_dir())
    valid = {STATUS_VERIFIED, STATUS_PENDING, STATUS_INPUT_REQUIRED}
    for rs in lib.rulesets.values():
        for entry in rs.entries.values():
            assert entry.status in valid, "%s 的 status 非法: %s" % (entry.key, entry.status)


def test_m1_all_entries_verified_with_review_trace():
    """M1 口径（HANDOFF-M1 出口判据）：verified 计数 > 0 且**每条**挂复核痕迹。

    复核痕迹写在 ``basis.note``（条目定位 + 核对结论）——"值可溯源"（M0）与
    "已逐项复核"（M1）在字段上是可区分的。
    """
    lib = load_library(data_dir())
    counts = lib.status_counts()
    assert counts[STATUS_VERIFIED] > 0, "M1 出口判据：verified 计数必须 > 0"
    for rs in lib.rulesets.values():
        for entry in rs.entries.values():
            assert entry.status == STATUS_VERIFIED, (
                "%s 仍为 %s —— M1 逐项复核应全部完成（或显式降级并在台账记录原因）"
                % (entry.key, entry.status)
            )
            note = (entry.basis or {}).get("note", "")
            assert "M1 逐项复核" in note, "%s 的 basis.note 缺复核痕迹" % entry.key


def test_late_grace_and_month_basis_resolved_from_rules():
    """滞纳金上限与月数口径由规则包承载（M1 依实施细则落值），值非空。

    依据：《专利法实施细则》（国务院令第 769 号）第 115 条（6 个月补缴期）与
    第 5 条（自然月口径）。这两个值原为 null → missing_value；M1 后必须可用。
    """
    lib = load_library(data_dir())
    grace = lib.ruleset("fee_schedule").get("late.grace_months")
    basis = lib.ruleset("fee_schedule").get("late.month_basis")
    assert grace.decimal() is not None, "late.grace_months 未落值"
    assert basis.value, "late.month_basis 未落值"
    assert basis.value == "calendar_month"


def test_amounts_parsed_as_decimal_not_float():
    """JSON 必须用 parse_float=Decimal，费率值绝不能落到 float。"""
    lib = load_library(data_dir())
    entry = lib.ruleset("fee_schedule").get("late.monthly_rate")
    assert entry is not None
    value = entry.decimal()
    assert isinstance(value, Decimal)
    assert value == Decimal("0.05")
    for rs in lib.rulesets.values():
        for e in rs.entries.values():
            if e.value is not None and e.kind != "ladder":
                assert not isinstance(e.value, float), "%s 落到 float" % e.key


def test_ladder_values_are_exact_not_float():
    """阶梯金额必须是精确类型（int 或 Decimal）；落到 float 就说明 parse_float 失效。

    费率表原始数值是整数元，故规则包里是 int——int 精确，不引入尾差；
    引擎在 ``tiers_from_entry`` 内统一转 Decimal。
    """
    lib = load_library(data_dir())
    for rs in lib.rulesets.values():
        for entry in rs.entries.values():
            for tier in entry.ladder:
                amount = tier["amount"]
                assert not isinstance(amount, float), "%s 阶梯金额落到 float" % entry.key
                assert isinstance(amount, (int, Decimal)), "%s 阶梯金额类型异常: %r" % (
                    entry.key, type(amount))


def test_duplicate_entry_key_rejected(tmp_path):
    import json

    rules = tmp_path / "rules"
    rules.mkdir()
    dup = {
        "schema": "patfee.ruleset/v1",
        "id": "x",
        "version": "v1",
        "title": "t",
        "doc_no": "d",
        "entries": [
            {"key": "a", "kind": "scalar", "status": "pending", "scopes": ["calc"], "value": 1},
            {"key": "a", "kind": "scalar", "status": "pending", "scopes": ["calc"], "value": 2},
        ],
    }
    (rules / "x.v1.json").write_text(json.dumps(dup), encoding="utf-8")
    (rules / "manifest.json").write_text(
        json.dumps({
            "schema": "patfee.rules.manifest/v1",
            "rulesets": [{"id": "x", "version": "v1", "file": "x.v1.json"}],
            "scopes": ["calc"],
            "benchmarks": {},
            "exemptions": {
                "small_int_abs_limit": 100, "exempt_integers": [],
                "exempt_decimals": ["0.01", "0.1", "0.5", "1.0", "2.0"], "inline_allow_mark": "literal-ok",
            },
        }),
        encoding="utf-8",
    )
    with pytest.raises(RulesetError, match="key 重复"):
        load_library(tmp_path)


def test_missing_manifest_in_explicit_dir_raises_file_not_found(tmp_path):
    """"找不到"与"找到了但内容坏"是两种语义。

    前者一律 FileNotFoundError（CLI 转 exit 2 的 ruleset_error），
    后者才是 RulesetError —— 不要混成同一种错误，否则调用方无法区分。
    """
    with pytest.raises(FileNotFoundError, match="manifest 不存在"):
        load_library(tmp_path)


def test_malformed_manifest_raises_ruleset_error(tmp_path):
    """文件在但 schema 不符 → RulesetError。"""
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "manifest.json").write_text('{"schema": "wrong/v9"}', encoding="utf-8")
    with pytest.raises(RulesetError, match="schema 不符"):
        load_library(tmp_path)


def test_auto_discovery_failure_raises_file_not_found(tmp_path, monkeypatch):
    """不给目录且上溯也找不到时，抛 FileNotFoundError（调用方转 exit 2）。"""
    from patfee import data_paths

    monkeypatch.delenv(data_paths.ENV_DATA_DIR, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(data_paths, "_candidate_roots", lambda: [tmp_path / "nowhere"])
    with pytest.raises(FileNotFoundError):
        load_library()


def test_exemption_mirror_matches_code():
    """manifest 里的豁免镜像必须与 rules/literals.py 同源，否则门禁与豁免会各自漂移。"""
    from patfee.rules import literals

    lib = load_library(data_dir())
    ok, why = literals.check_mirror(lib.exemptions)
    assert ok, why
