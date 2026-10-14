"""M1 交付物守门测试：规则差异报告 / 合成真值库 / 上位法依据索引。

M1 出口判据（HANDOFF-M1 §二）：

* ``verified`` 计数 > 0 且每条挂 ``basis``（test_rules_loader 已守）；
* ``gen_rulesets.py --check`` 位级一致（test_repo_guards 已守）；
* 真值库生成可复现（两次运行逐字节一致）—— 本文件守；
* ``rules diff`` 命令（316 号前后阈值、594 号新增项目差异报告）—— 本文件守。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import data_dir, repo_root


# ------------------------------------------------------------ rules diff

@pytest.fixture(scope="module")
def lib():
    from patfee.rules.loader import load_library

    return load_library(data_dir())


def test_diff_316_reports_threshold_pairs(lib):
    """316 号差异报告：三组阈值前后对照，全部标记为变更。"""
    from patfee.rules.diff import diff_ruleset

    payload = diff_ruleset(lib, "reduction_316")
    assert len(payload["thresholds"]) == 3
    keys = {p["key"] for p in payload["thresholds"]}
    assert keys == {
        "reduction.threshold.individual_monthly_income",
        "reduction.threshold.individual_annual_income",
        "reduction.threshold.entity_taxable_income",
    }
    for pair in payload["thresholds"]:
        assert pair["changed"] is True, "316 号三组阈值都应标记为变更"
        assert pair["before"] != pair["after"]


def test_diff_594_reports_cross_reference_to_fee_schedule(lib):
    """594 号新增条目须标注费率表里的同口径条目（两处独立记载互证）。"""
    from patfee.rules.diff import diff_ruleset

    payload = diff_ruleset(lib, "reduction_594")
    xref = {i["key"]: i["cross_reference"] for i in payload["items"]}
    assert xref["check.fee.term_compensation_request_594"] == \
        "fee_schedule@v2024#check.fee.term_compensation_request"
    assert xref["check.fee.compensation_annuity_594"] == \
        "fee_schedule@v2024#check.fee.compensation_annuity"
    # 无版本后缀的条目不该有同口径条目（避免自配对）
    assert xref["reduction.open_license_discount"] == ""


def test_diff_unknown_ruleset_raises_ruleset_error(lib):
    from patfee.errors import RulesetError
    from patfee.rules.diff import diff_ruleset

    with pytest.raises(RulesetError):
        diff_ruleset(lib, "nope")


def test_diff_render_text_lists_sections(lib):
    from patfee.rules.diff import diff_ruleset, render_text

    lines = render_text(diff_ruleset(lib, "reduction_316"))
    text = "\n".join(lines)
    assert "阈值/取值前后对照" in text
    assert "调整前" in text and "调整后" in text


def test_cli_rules_diff_exit_0_and_json(capsys):
    from patfee import cli

    assert cli.main(["rules", "diff", "reduction_316"]) == 0
    out = capsys.readouterr().out
    assert "阈值/取值前后对照" in out

    assert cli.main(["rules", "diff", "reduction_316", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ruleset"]["id"] == "reduction_316"
    assert len(payload["thresholds"]) == 3


def test_cli_rules_diff_unknown_exit_2(capsys):
    from patfee import cli

    assert cli.main(["rules", "diff", "nope"]) == 2
    assert "ruleset_error" in capsys.readouterr().err


# ------------------------------------------------------------ truth library

TRUTH_DIR_PY = repo_root_py = Path(__file__).resolve().parent.parent / "data" / "truth"


def _truth_dir() -> Path:
    d = repo_root() / "data" / "truth"
    assert (d / "manifest.json").is_file(), "真值库缺失 —— 先跑 tools/gen_synthetic.py"
    return d


def test_truth_library_loads_and_schema_valid():
    truth = json.loads((_truth_dir() / "truth.json").read_text(encoding="utf-8"))
    portfolio = json.loads((_truth_dir() / "portfolio.json").read_text(encoding="utf-8"))
    assert truth["schema"] == "patfee.truth/v1"
    assert portfolio["schema"] == "patfee.portfolio/v1"
    assert truth["generated_at"] == "1970-01-01T00:00:00Z", "真值库不得含当前时间"
    assert truth["cases"], "真值库不得为空"


def test_truth_generation_is_byte_reproducible():
    """M1 出口判据：真值库生成可复现 —— 再生成两次，逐字节一致。"""
    gen = repo_root() / "tools" / "gen_synthetic.py"
    snapshot = {
        p.name: p.read_bytes() for p in sorted(_truth_dir().glob("*.json"))
    }
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, str(gen), "--check"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(repo_root()),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "SYNTHETIC_FROZEN_OK" in proc.stdout
    for name, data in snapshot.items():
        assert (_truth_dir() / name).read_bytes() == data, \
            "%s 再生成后字节漂移 —— 生成器混入了非确定性来源" % name


def test_truth_portfolio_uses_synthetic_number_ranges():
    """零真实信息纪律：专利号走 99000000…SYN 号段，主体名带（合成）。"""
    portfolio = json.loads((_truth_dir() / "portfolio.json").read_text(encoding="utf-8"))
    assert portfolio["patents"]
    for patent in portfolio["patents"]:
        assert patent["patent_no"].startswith("99") and patent["patent_no"].endswith("SYN"), \
            "专利号必须走测试号段 99…SYN: %s" % patent["patent_no"]
        assert "（合成）" in patent["title"]
    for subject in portfolio["subjects"]:
        assert "（合成）" in subject["name"], "主体名必须带（合成）标记"
    for uscc in portfolio.get("subject_uscc", {}).values():
        assert uscc.startswith("90000000") and uscc.endswith("SYN")


def test_truth_covers_boundary_archives():
    """算例覆盖：三类专利阶梯首末档 / 滞纳金 1/2/6 月 + 超上限 / 费减阈值边界 / 多政策。"""
    truth = json.loads((_truth_dir() / "truth.json").read_text(encoding="utf-8"))
    archives = truth["coverage"]["by_archive"]
    assert archives.get("ladder_boundary", 0) >= 15, "三类专利各档首末年须各有算例"
    assert archives.get("late_months", 0) >= 3, "滞纳金 1/2/6 月算例缺失"
    assert archives.get("late_exceeds_cap", 0) >= 1, "超上限降级件缺失"
    assert archives.get("reduction_boundary", 0) >= 5, "费减边界算例缺失"
    assert archives.get("multi_policy", 0) >= 2, "多政策择一算例缺失"
    kinds = truth["coverage"]["by_kind"]
    assert kinds["annuity"] > 0 and kinds["late"] > 0 and kinds["reduction"] > 0


def test_truth_boundary_values_match_rules():
    """真值边界与规则包一致：费减恰好等于阈值 → 不合格（严格小于）；6 月不超限、7 月超限。"""
    from decimal import Decimal

    from patfee.rules.loader import load_library

    lib = load_library(data_dir())
    truth = json.loads((_truth_dir() / "truth.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in truth["cases"]}

    at = cases["reduction.sole.individual.at_threshold"]
    assert at["expect"]["eligible"] is False, "恰好等于阈值必须不合格（『低于』为严格小于）"
    monthly = Decimal(at["applicants"][0]["monthly_avg_income"])
    threshold = Decimal(at["expect"]["thresholds"]["individual_monthly_income"])
    assert monthly == threshold, "边界算例的输入必须恰等于阈值"

    grace = lib.ruleset("fee_schedule").get("late.grace_months").decimal()
    at_cap = cases["late.invention.y%02d.m%d" % (5, int(grace))]
    over_cap = cases["late.invention.y%02d.m%d" % (5, int(grace) + 1)]
    assert at_cap["expect"]["exceeds_cap"] is False
    assert over_cap["expect"]["exceeds_cap"] is True
    assert over_cap["expect"]["reason_code"] == "late_exceeds_cap"


def test_truth_multi_policy_chooses_most_favorable():
    """多政策择一：候选并存时选中实缴最小者，且 no_double_benefit 生效。"""
    from decimal import Decimal

    truth = json.loads((_truth_dir() / "truth.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in truth["cases"]}

    case = cases["multi_policy.sole_eligible_and_open_license"]
    chosen = case["expect"]["chosen"]
    amounts = [Decimal(c["amount"]) for c in case["expect"]["candidates"]]
    assert len(case["expect"]["candidates"]) == 2, "应同时列出费减与开放许可两个候选"
    assert Decimal(chosen["amount"]) == min(amounts), "择最优惠 = 实缴额最小"
    assert case["expect"]["no_double_benefit_applied"] is True


def test_truth_controls_declare_clean_and_degrade():
    """误报对照集显式声明：基准层只读该声明，不自行挑选对照档案。"""
    truth = json.loads((_truth_dir() / "truth.json").read_text(encoding="utf-8"))
    controls = truth["controls"]
    assert controls["clean"], "应有应零命中的干净档案"
    assert controls["degrade"], "应有应降级（warning 而非 fail）的档案"
    assert not set(controls["clean"]) & set(controls["degrade"])


def test_truth_manifest_sha256_matches_files():
    import hashlib

    manifest = json.loads((_truth_dir() / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "patfee.truth.manifest/v1"
    for meta in manifest["files"]:
        actual = hashlib.sha256((_truth_dir() / meta["name"]).read_bytes()).hexdigest()
        assert actual == meta["sha256"], "%s 的 sha256 与 manifest 不一致" % meta["name"]


# ------------------------------------------------------------ clauses index

def test_clauses_index_loads_and_documents_located():
    """上位法依据索引：三部上位法均已定位（M1 待办 #3），条目级结论挂 verified。"""
    path = repo_root() / "data" / "knowledge" / "clauses.json"
    assert path.is_file(), "clauses.json 缺失"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["schema"] == "patfee.clauses/v1"
    by_id = {d["id"]: d for d in doc["documents"]}
    assert set(by_id) == {"patent_law", "patent_law_rules", "exam_guidelines"}
    for d in doc["documents"]:
        assert d["effective_from"], "%s 缺施行日期" % d["id"]
        assert d["source"]["url"].startswith("http")
        assert (repo_root() / d["snapshot"]).is_file(), "%s 的原文快照缺失" % d["id"]
        assert d["current"] is True, "%s 应登记为现行有效" % d["id"]

    # 实施细则须有条款级结论（M1 待办 #4 的原文依据）
    rules = by_id["patent_law_rules"]
    assert rules["verification"] == "clause_verified"
    nos = {c["no"] for c in rules["clauses"]}
    assert {"第五条", "第一百一十五条"} <= nos, "缺第 5/115 条（月数口径与 6 个月补缴期的原文依据）"
    for clause in rules["clauses"]:
        assert clause["verified"] is True, "%s 未核对不得登记" % clause["no"]
        assert clause["gist"] and clause["conclusion"]


def test_clauses_index_no_unverified_clause_conclusions():
    """纪律：未核到的条款级结论一律不登记（宁缺毋错）。"""
    doc = json.loads((repo_root() / "data" / "knowledge" / "clauses.json").read_text(encoding="utf-8"))
    for d in doc["documents"]:
        if d["verification"] != "clause_verified":
            assert d["clauses"] == [], \
                "%s 未到 clause_verified 却登记了条款级结论" % d["id"]
