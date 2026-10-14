"""年费阶梯引擎测试：档位端点只来自规则包、边界显式、Decimal 计价。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import data_dir
from patfee.calc import annuity
from patfee.domain.models import PatentType, Tier
from patfee.errors import RulesetError
from patfee.rules.loader import load_library


@pytest.fixture(scope="module")
def lib():
    return load_library(data_dir())


def test_find_tier_boundaries_are_inclusive_and_switch_to_new_tier():
    """双闭区间：第 3 年属第 1 档、第 4 年属第 2 档（恰好跳档年归新档）。"""
    tiers = [
        Tier(1, 3, Decimal("900"), "第 1-3 年"),
        Tier(4, 6, Decimal("1200"), "第 4-6 年"),
    ]
    assert annuity.find_tier(tiers, 3).amount == Decimal("900")
    assert annuity.find_tier(tiers, 4).amount == Decimal("1200")
    assert annuity.find_tier(tiers, 1).amount == Decimal("900")
    assert annuity.find_tier(tiers, 6).amount == Decimal("1200")


def test_out_of_range_reason_code(lib):
    result = annuity.compute_annuity(lib, PatentType.INVENTION, 30, preview=True)
    assert result.amount is None
    assert "out_of_range" in result.reasons


def test_gate_blocks_without_preview(lib):
    result = annuity.compute_annuity(lib, PatentType.INVENTION, 5)
    assert result.amount is None
    assert "gated_pending" in result.reasons
    assert result.basis is not None, "被拦时仍应给出依据坐标，便于定位是哪条没核对"


def test_preview_computes_but_carries_warning(lib):
    result = annuity.compute_annuity(lib, PatentType.INVENTION, 5, preview=True)
    assert result.amount == Decimal("1200.00")
    assert result.tier is not None
    assert (result.tier.from_year, result.tier.to_year) == (4, 6)
    assert result.warnings, "预览口径必须带提示"


@pytest.mark.parametrize(
    "patent_type,year,expected",
    [
        (PatentType.INVENTION, 1, "900.00"),
        (PatentType.INVENTION, 3, "900.00"),
        (PatentType.INVENTION, 4, "1200.00"),
        (PatentType.INVENTION, 9, "2000.00"),
        (PatentType.INVENTION, 10, "4000.00"),
        (PatentType.INVENTION, 15, "6000.00"),
        (PatentType.INVENTION, 16, "8000.00"),
        (PatentType.INVENTION, 20, "8000.00"),
        (PatentType.UTILITY_MODEL, 1, "600.00"),
        (PatentType.UTILITY_MODEL, 5, "900.00"),
        (PatentType.UTILITY_MODEL, 6, "1200.00"),
        (PatentType.UTILITY_MODEL, 10, "2000.00"),
        (PatentType.DESIGN, 8, "1200.00"),
        (PatentType.DESIGN, 11, "3000.00"),
        (PatentType.DESIGN, 15, "3000.00"),
    ],
)
def test_ladder_values_match_official_schedule(lib, patent_type, year, expected):
    """断言值来自官方费率表（表见 data/knowledge/raw/cnipa_fee_schedule_286.html）。"""
    result = annuity.compute_annuity(lib, patent_type, year, preview=True)
    assert result.amount == Decimal(expected), result.steps


def test_amount_is_decimal_two_places(lib):
    result = annuity.compute_annuity(lib, PatentType.INVENTION, 7, preview=True)
    assert isinstance(result.amount, Decimal)
    assert str(result.amount) == "2000.00"


def test_float_amount_rejected_in_domain_model():
    with pytest.raises(TypeError, match="Decimal"):
        Tier(1, 3, 900.0, "x")


def test_tiers_from_entry_rejects_missing_amount():
    from patfee.rules.loader import Entry

    entry = Entry(
        {
            "key": "k", "kind": "ladder", "status": "verified", "scopes": ["calc"],
            "ladder": [{"from_year": 1, "to_year": 3, "amount": None, "label": "x"}],
            "basis": {"doc_no": "d", "clause": "c", "url": "http://x", "retrieved": "2026-10-14"},
        },
        "rs", "v1",
    )
    with pytest.raises(RulesetError, match="缺少金额"):
        annuity.tiers_from_entry(entry)


def test_no_public_year_literals_in_engine_source():
    """引擎源码里不得出现档位端点数字（档位只来自规则包）。"""
    import re
    from pathlib import Path

    from conftest import repo_root

    src = (repo_root() / "src" / "patfee" / "calc" / "annuity.py").read_text(encoding="utf-8")
    # 去掉注释与 docstring 后仍不该出现裸露的档位数字
    code_lines = [ln.split("#")[0] for ln in src.splitlines()]
    joined = "\n".join(code_lines)
    for token in ("1200", "2000", "4000", "6000", "8000", "900"):
        assert not re.search(r"(?<![0-9A-Za-z_])%s(?![0-9A-Za-z_])" % token, joined), \
            "引擎源码出现档位数值字面量 %s —— 档位必须只来自规则包" % token
