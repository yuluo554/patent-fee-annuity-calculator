"""门控语义测试：三态、分作用域、--preview、input_required。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import data_dir
from patfee.rules import gate as g
from patfee.rules.loader import Entry, RuleLibrary, Ruleset, load_library


def _entry(key, status, scopes, value="1.0", kind="scalar", ladder=None):
    raw = {
        "key": key,
        "label": key,
        "kind": kind,
        "status": status,
        "scopes": scopes,
        "value": value,
        "ladder": ladder or [],
        "basis": {"doc_no": "d", "clause": "c", "url": "http://x", "retrieved": "2026-10-14"},
    }
    return Entry(raw, "rs", "v1")


def test_pending_blocks_by_default():
    decision = g.evaluate([_entry("a", "pending", ["calc"])], "calc")
    assert decision.allowed is False
    assert decision.blocked == [("a", "gated_pending")]
    assert decision.reasons == ("gated_pending",)


def test_pending_allowed_under_preview_but_flagged():
    decision = g.evaluate([_entry("a", "pending", ["calc"])], "calc", preview=True)
    assert decision.allowed is True
    assert decision.permitted_unverified == ["a"]


def test_verified_allows():
    decision = g.evaluate([_entry("a", "verified", ["calc"])], "calc")
    assert decision.allowed is True
    assert decision.blocked == []


def test_verified_without_value_is_missing_value():
    decision = g.evaluate([_entry("a", "verified", ["calc"], value=None)], "calc")
    assert decision.allowed is False
    assert decision.blocked == [("a", "missing_value")]


def test_input_required_passes_gate_but_blocks_until_provided():
    """input_required 放行门控，但运行时必须显式索取——绝不静默取 0/1。"""
    pending = g.evaluate([_entry("ext", "input_required", ["calc"])], "calc")
    assert pending.allowed is False
    assert pending.required_inputs == ["ext"]

    provided = g.evaluate(
        [_entry("ext", "input_required", ["calc"])], "calc", provided_inputs=("ext",)
    )
    assert provided.allowed is True
    assert provided.required_inputs == []


def test_scope_isolation_unrelated_pending_does_not_block():
    """分作用域：与本次计算无关的 pending 不得阻断本条路径。"""
    entries = [
        _entry("calc.thing", "verified", ["calc"]),
        _entry("reduction.thing", "pending", ["reduction"]),
    ]
    decision = g.evaluate(entries, "calc")
    assert decision.allowed is True
    assert decision.blocked == []
    assert "reduction.thing" not in decision.statuses, "无关作用域条目不应进入门控视野"


def test_untracked_entry_reported():
    from patfee.rules.loader import load_library

    lib = load_library(data_dir())
    decision = g.evaluate_keys(lib, ["no.such.key"], "calc")
    assert decision.allowed is False
    assert ("no.such.key", "untracked_entry") in decision.blocked


def test_preview_does_not_satisfy_input_required():
    """预览不是"补输入"：input_required 在 preview 下同样不放行。"""
    decision = g.evaluate([_entry("ext", "input_required", ["calc"])], "calc", preview=True)
    assert decision.allowed is False
    assert decision.required_inputs == ["ext"]


def test_all_four_scopes_present_in_library():
    lib = load_library(data_dir())
    assert set(lib.scopes) == {"calc", "late", "reduction", "check"}
