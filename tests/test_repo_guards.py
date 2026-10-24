"""仓库级守门测试：冻结产物、EOL、CI workflow。

这些门覆盖"本机 Windows 开发环境永远跑不出来"的一类问题：跨平台行尾、
zip 容器元数据、CI 配置语法与矩阵接线。CI 首跑全红的常见根因都在这里。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import data_dir, repo_root

yaml = pytest.importorskip("yaml", reason="dev extra 缺 pyyaml：CI workflow 守门无法运行")


# ------------------------------------------------------------ 冻结产物

def test_rulesets_are_frozen_and_regenerate_byte_identical():
    """规则包为生成器冻结产物：再生成必须逐字节一致（禁手改）。"""
    import importlib.util
    import sys

    name = "patfee_gen_rulesets"
    if name not in sys.modules:
        gen_path = repo_root() / "tools" / "gen_rulesets.py"
        spec = importlib.util.spec_from_file_location(name, gen_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    module = sys.modules[name]

    files = module.generate()
    rules_dir = data_dir() / "rules"
    for name_, data in files.items():
        on_disk = (rules_dir / name_).read_bytes()
        assert on_disk == data, "%s 与重生成结果字节不一致 —— 产物被手改过或生成器漂移" % name_


def test_rulesets_have_no_carriage_return():
    """冻结产物必须 LF：CRLF 会让跨平台比对全挂（.gitattributes 只管检出，不管脚本怎么写）。"""
    problems = []
    for path in sorted((data_dir() / "rules").glob("*.json")):
        raw = path.read_bytes()
        if b"\r" in raw:
            problems.append(path.name)
    assert not problems, "以下冻结产物含 CR（跨平台复现性破坏）: %s" % ", ".join(problems)


def test_rulesets_have_no_timestamp_drift():
    """产物不得含当前时间：generated_at 必须是固定哨兵值。"""
    import json

    manifest = json.loads((data_dir() / "rules" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["generated_at"] == "1970-01-01T00:00:00Z"


def test_gen_rulesets_check_reports_ok():
    """--check 是"改完还自洽"的统一证据。"""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(repo_root() / "tools" / "gen_rulesets.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(repo_root()),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "FROZEN_RULESETS_OK" in proc.stdout


def test_manifest_sha256_matches_files():
    """manifest 登记的 sha256 必须与磁盘实际一致（防"台账写着旧值"）。"""
    import hashlib
    import json

    manifest = json.loads((data_dir() / "rules" / "manifest.json").read_text(encoding="utf-8"))
    for meta in manifest["rulesets"]:
        path = data_dir() / "rules" / meta["file"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == meta["sha256"], "%s 的 sha256 与 manifest 不一致" % meta["file"]


# ------------------------------------------------------------ 原文快照

def test_authority_snapshots_exist_and_recorded():
    """依据原文快照必须在库，且 sha256 可复算（含量快照入库即需可校验）。"""
    import hashlib
    import json

    ledger_path = data_dir() / "knowledge" / "raw" / "_ledger.json"
    assert ledger_path.is_file(), "原文快照台账缺失"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(ledger) >= 3, "至少应有三份政策原文快照"
    for item in ledger:
        # M1 起台账登记 file 字段（快照可能是 .html 或 .json）；缺省回落 name.html
        fname = item.get("file") or (item["name"] + ".html")
        path = data_dir() / "knowledge" / "raw" / fname
        assert path.is_file(), "快照文件缺失: %s" % path
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == item["sha256"], "%s 的 sha256 与台账不一致" % item["name"]


def test_ledger_urls_are_official_domains():
    """快照来源必须是官方域名（gov.cn / mof.gov.cn / cnipa.gov.cn）。"""
    import json

    ledger = json.loads((data_dir() / "knowledge" / "raw" / "_ledger.json").read_text(encoding="utf-8"))
    allowed = ("gov.cn", "mof.gov.cn", "cnipa.gov.cn")
    for item in ledger:
        assert any(d in item["url"] for d in allowed), "非官方来源: %s" % item["url"]


# ------------------------------------------------------------ CI workflow

@pytest.fixture(scope="module")
def workflow():
    path = repo_root() / ".github" / "workflows" / "ci.yml"
    assert path.is_file(), "CI workflow 缺失"
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    assert isinstance(data, dict), "workflow YAML 解析结果不是映射（非法 YAML 会让 GitHub 不建任何 job）"
    return data, raw


def test_workflow_parses_and_jobs_are_wellformed(workflow):
    """非法 YAML 会让 GitHub 静默不建任何 job（run 0 秒失败、jobs=0）。"""
    data, _ = workflow
    jobs = data.get("jobs")
    assert isinstance(jobs, dict) and jobs, "workflow 必须定义 jobs"
    for name, job in jobs.items():
        assert job.get("runs-on"), "job %s 缺 runs-on" % name
        assert job.get("steps"), "job %s 缺 steps" % name


def test_workflow_triggers_defined(workflow):
    data, _ = workflow
    # YAML 会把裸 `on:` 解析成布尔 True
    triggers = data.get("on", data.get(True))
    assert triggers, "workflow 必须定义触发条件"


def test_workflow_matrix_covers_required_environments(workflow):
    """矩阵 = {windows,ubuntu}×3.12（解释器底线 3.12，自 2026-10-19 起，见 plan/06 D54）。"""
    _, raw = workflow
    assert "windows-latest" in raw
    assert "ubuntu-latest" in raw
    assert "3.12" in raw
    # 已 EOL 的解释器不得回到矩阵（否则"声明支持的版本"与"实际验证的版本"再次分叉）
    assert "3.8" not in raw, "不得再保留 3.8 通道（已 EOL，底线 3.12）"


def test_workflow_sets_utf8_env(workflow):
    """编码加固三层之一：CI 全局 PYTHONUTF8 —— 只救 CI，但必须上。"""
    _, raw = workflow
    assert "PYTHONUTF8" in raw
    assert "PYTHONIOENCODING" in raw


def test_workflow_checkout_uses_full_history(workflow):
    """历史扫描类守门依赖 git 历史；浅克隆会让它在 CI 里静默空验。"""
    data, _ = workflow
    for name, job in data["jobs"].items():
        for step in job["steps"]:
            uses = str(step.get("uses", ""))
            if "checkout" in uses:
                depth = (step.get("with") or {}).get("fetch-depth")
                assert depth == 0, "job %s 的 checkout 必须 fetch-depth: 0（否则历史扫描假绿）" % name


def test_workflow_installs_dev_extras_in_test_jobs(workflow):
    """extras 必须覆盖全部里程碑门的依赖，否则门在 CI 上静默跳过。"""
    _, raw = workflow
    assert ".[dev]" in raw or "[dev]" in raw, "CI 必须装 dev extra（含 pytest 与 pyyaml）"


def test_workflow_core_only_job_installs_pytest(workflow):
    """core-only job 证明"核心层零第三方依赖"，但 pytest 本身是测试期依赖。

    装 core-only 不等于装齐"跑测试所需" —— 漏装会让守门测试整批 ImportError（不是 skip）。
    """
    _, raw = workflow
    if "core-only" not in raw and "core only" not in raw.lower():
        pytest.skip("本 workflow 无 core-only job")
    # core-only 段落里必须显式出现 pytest 与 -e .
    idx = raw.lower().find("core-only")
    tail = raw[idx:]
    assert "pytest" in tail, "core-only job 必须显式装 pytest"


def test_workflow_is_valid_lf_and_no_tabs(workflow):
    """YAML 里的制表符与 CRLF 都会让 GitHub 解析失败。"""
    _, raw = workflow
    assert "\r" not in raw, "workflow 含 CR"
    assert "\t" not in raw, "workflow 含制表符（YAML 非法）"


def test_workflow_step_names_with_colon_are_quoted(workflow):
    """未加引号且含「冒号+空格」的纯量 step 名会让整份 workflow 非法。"""
    _, raw = workflow
    for line in raw.splitlines():
        m = re.match(r"^\s*-\s+name:\s+(.*)$", line)
        if not m:
            continue
        value = m.group(1).strip()
        if value.startswith(('"', "'", "|", ">")):
            continue
        assert ": " not in value, "step 名含「冒号+空格」且未加引号，会让 workflow 非法: %r" % value


# ------------------------------------------------------------ 仓库卫生

def test_gitattributes_normalizes_lf():
    raw = (repo_root() / ".gitattributes").read_text(encoding="utf-8")
    assert "text=auto" in raw and "eol=lf" in raw


def test_gitignore_covers_private_and_build_artifacts():
    raw = (repo_root() / ".gitignore").read_text(encoding="utf-8")
    for token in ("_private", "dist/", "build/", ".venv"):
        assert token in raw, ".gitignore 未覆盖 %s" % token


def test_pyproject_declares_dev_extras_with_test_deps():
    """dev extra 必须含测试期依赖，且 core 无运行时依赖。"""
    text = (repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    assert "pytest" in text and "pyyaml" in text
    assert re.search(r"^dependencies\s*=\s*\[\s*\]", text, re.M), "核心层必须零运行时依赖"


def test_pyproject_pins_setuptools_below_81_in_build_extra():
    """PyInstaller 仍 import pkg_resources，setuptools 81 起移除它。"""
    text = (repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    assert "setuptools<81" in text


def test_pyproject_declares_single_pyside6_floor():
    """解释器底线抬到 3.12 后，gui extra 不再需要按解释器分叉的上限钉。

    旧口径：3.8 通道钉 `PySide6>=6.6,<6.7`（6.7+ 要求 python>=3.9）——3.8 下线后这条钉
    只会让 3.12 用户也被挡在 6.6.x，属"historical pin"漂移（plan/06 D54）。
    """
    text = (repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    assert "PySide6>=6.6" in text
    assert "PySide6>=6.6,<6.7" not in text, "3.8 通道已下线，不应再按解释器分叉钉 PySide6 上限"
    assert "python_version < '3.9'" not in text, "不应再有 3.8 专用的 marker 分支"


def test_ruleset_manifest_carries_review_anchor():
    """规则/快照元数据必须带"下次复核"锚点（只记"核对过"、"何时再看"无人拦的失效模式）。

    锚点解析自 `manifest.json`：规约"费率表可能逐年调整"若只有 `reviewed` 而没有 `next_review`，
    换版就没人被提醒（plan/06 D55）。
    """
    import json

    manifest = json.loads(
        (repo_root() / "data" / "rules" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.get("review_interval"), "manifest 缺 review_interval"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", manifest.get("reviewed") or ""), \
        "manifest 的 reviewed 必须为 YYYY-MM-DD"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", manifest.get("next_review") or ""), \
        "manifest 的 next_review 必须为 YYYY-MM-DD"
    assert manifest["next_review"] > manifest["reviewed"], \
        "next_review 必须晚于 reviewed（锚点不能是过去式）"

    assert manifest.get("rulesets"), "manifest 未登记规则集"
    for meta in manifest["rulesets"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta.get("next_review") or ""), \
            "规则集 %s 缺 next_review（YYYY-MM-DD）" % meta.get("id")
        assert meta.get("review_interval") == manifest["review_interval"], \
            "规则集 %s 的复核周期与 manifest 顶层不一致" % meta.get("id")
        assert meta.get("next_review") == manifest["next_review"], \
            "规则集 %s 的 next_review 与 manifest 顶层不一致" % meta.get("id")


def test_review_status_flags_overdue_but_never_crashes():
    """逾期判据的阳性/阴性对照（新增判据不得只是"永远绿"的装饰）。"""
    from datetime import date

    from patfee.calc.pipeline import review_status

    manifest = {
        "review_interval": "annual",
        "reviewed": "2026-10-14",
        "next_review": "2027-10-14",
    }
    before = review_status(manifest, today=date(2027, 10, 13))
    assert before["overdue"] is False, "复核日之前不得报逾期"
    on_due = review_status(manifest, today=date(2027, 10, 14))
    assert on_due["overdue"] is False, "复核日当天不算逾期"
    after = review_status(manifest, today=date(2027, 10, 15))
    assert after["overdue"] is True and after["days_overdue"] == 1, "逾期 1 天必须报出来"

    # 缺锚点 / 坏格式：不得崩，也不得静默装成"未逾期"（note 必须说明原因）
    missing = review_status({}, today=date(2027, 1, 1))
    assert missing["overdue"] is False and missing["note"], "缺 next_review 必须给出说明而非静默放行"
    broken = review_status({"next_review": "2027/10/14"}, today=date(2027, 1, 1))
    assert broken["overdue"] is False and "YYYY-MM-DD" in broken["note"], \
        "坏格式必须显式说明，不得当作未逾期"


def test_pyproject_uses_spdx_license_expression():
    """license 必须用 PEP 639 的 SPDX 字符串，且不得再挂 license classifier。

    两种旧写法（`license = { text = ... }` 表 + `License ::` classifier）都被 setuptools
    弃用，带硬期限（2027-02-18 起不再支持）—— 已弃用的写法一旦回归，构建会在未来某天硬失败，
    所以这里锁死"正确写法"而不是"当前恰好没警告"。
    """
    text = (repo_root() / "pyproject.toml").read_text(encoding="utf-8")

    assert not re.search(r"^license\s*=\s*\{", text, re.M), \
        "license 不得用 TOML 表写法（{ text = ... }），已弃用"
    assert re.search(r'^license\s*=\s*"[^"]+"\s*$', text, re.M), \
        "license 必须是 SPDX 表达式字符串（例如 license = \"MIT\"）"
    assert "License ::" not in text, "不得再使用 License :: classifier（PEP 639 已弃用）"

    # SPDX 字符串自 setuptools 77 起支持：构建下限必须跟上，否则旧构建环境装不上
    block = re.search(r"^\[build-system\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    assert block, "pyproject 缺 [build-system] 段"
    floors = [tuple(int(x) for x in m.group(1).split("."))
              for m in re.finditer(r"setuptools>=(\d+(?:\.\d+)*)", block.group(1))]
    assert floors and max(floors) >= (77,), \
        "build-system 的 setuptools 下限必须 >=77（SPDX license 表达式的最低支持版本）"


# ------------------------------------------------------------ 脱敏审计器

def _audit_module():
    """导入审计器。

    必须**先注册进 sys.modules 再 exec** —— 否则模块内的 ``@dataclass``
    在解析字段注解时会 ``sys.modules.get(cls.__module__)`` 拿到 None 而崩。
    """
    import importlib.util
    import sys

    name = "patfee_audit_desensitize"
    if name in sys.modules:
        return sys.modules[name]
    path = repo_root() / "tools" / "audit_desensitize.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module


def test_desensitize_audit_selftest_passes():
    """审计器自身的阳性+阴性对照必须通过。

    只写正例（必须报红）会让规则一改就误报——反例同样必要：
    noreply、传输地址、gov.cn 导航 URL、长 hex 指纹都**不得**判红。
    """
    module = _audit_module()
    ok, notes = module.selftest()
    assert ok, "; ".join(notes)


def test_desensitize_audit_tracked_has_no_hard_hits():
    """仓库跟踪树不得含硬门命中（个人目录路径/个人邮箱/手机/身份证）。"""
    module = _audit_module()
    result = module.audit_tracked()
    hard = result.by_grade(module.HARD)
    assert not hard, "硬门命中: %s" % ", ".join("%s %s" % (h.location, h.kind) for h in hard)


#: 历史脱敏门的**已知缺陷白名单**（2026-10-24 用户拍板「乙案」：不改写已推送历史）。
#:
#: 为什么是白名单而不是 skip：`pytest.skip` / `xfail` 会让这条门对**任何**新命中都不再报红，
#: 等于把门改瞎。这里收窄成「允许集合恰好等于这两处」——多一处、少一处都会红：
#:
#:   * 多一处  → 有新的本机路径进了历史（必须当场知道）
#:   * 少一处  → 这两处已不在历史里了（例如有人改写了历史 / 换了仓库），白名单必须同步删除，
#:               否则它就成了「永久豁免」的化石。
#:
#: 来源：
#:   * `17dc75d`（v0.2.0 发布提交）新增的 `.verify-out/selftest-*.json` 第 4 行 `detail`
#:     含本机绝对路径。该提交已推送并已被 `v0.2.0` tag 指向，改写它会破坏「按 tag 可复现」。
#:   * `13e785e`（乙案落地提交）在 `plan/RELEASE-v0.2.0.md` §六 里**引用了该路径的字面原文**
#:     来说明缺陷，被本仓同一道门当场命中（CI 三条 job 红）。工作树已改为占位符描述，
#:     但该提交已推送 → 同样不可修复。**教训：声明泄露时不要复制泄露本身。**
#: 工作树版本**已脱敏**（另见 `test_desensitize_audit_tracked_has_no_hard_hits`）。
#: 声明位置：`plan/RELEASE-v0.2.0.md` §已知缺陷、`README.md` §限制与免责、
#: `v0.2.0` 的 Release 说明。
KNOWN_HISTORY_HARD_HITS = frozenset({
    "17dc75d4:.verify-out/selftest-cli.json:4",
    "17dc75d4:.verify-out/selftest-gui.json:4",
    "13e785ee:plan/RELEASE-v0.2.0.md:87",
})


def test_desensitize_audit_history_has_no_unknown_hard_hits():
    """历史硬门命中**只允许**已知的这两处（见 ``KNOWN_HISTORY_HARD_HITS``）。

    判据是「差集为空」而不是「集合为空」——这条门原本守的是「删了文件但历史还在」，
    乙案下那件事已经发生且不可修复；剩下的价值是**盯住有没有新增**。
    """
    module = _audit_module()
    result = module.audit_history()
    hits = result.by_grade(module.HARD)
    found = {(h.location, h.kind) for h in hits}
    expected = {(loc, "work_root") for loc in KNOWN_HISTORY_HARD_HITS}

    unexpected = sorted(found - expected)
    assert not unexpected, "历史出现新的硬门命中: %s" % ", ".join(
        "%s %s" % (loc, kind) for loc, kind in unexpected
    )

    vanished = sorted(expected - found)
    assert not vanished, (
        "已知缺陷白名单里的位置已不在历史命中中：%s —— "
        "若确实已修复（例如历史被改写），请同步删除 KNOWN_HISTORY_HARD_HITS 里对应条目"
        % ", ".join("%s %s" % (loc, kind) for loc, kind in vanished)
    )


def test_audit_history_scanner_is_alive():
    """历史扫描必须配通道探活——否则它可能一直是空的（假绿）。"""
    module = _audit_module()
    result = module.audit_history()
    assert result.probe_ok, "历史扫描通道探活失败: %s" % result.probe_note


def test_desensitize_tool_guards_its_own_output():
    """审计器源码不得含完整词面（否则扫描器扫自己必中、从此永留历史）。"""
    text = (repo_root() / "tools" / "audit_desensitize.py").read_text(encoding="utf-8")
    for literal in ("C:\\Users\\", "D:\\ProgramData\\", "ASUS"):
        assert literal not in text, "审计器源码含完整词面 %r，会被自己的扫描命中" % literal


def test_tools_scripts_are_parseable_and_lf():
    """tools/ 下全部脚本必须可解析、且为 LF（构建脚本的行为差异会污染产物）。"""
    import ast

    for path in sorted((repo_root() / "tools").glob("*.py")):
        raw = path.read_bytes()
        assert b"\r" not in raw, "%s 含 CR" % path.name
        ast.parse(raw.decode("utf-8"))


def test_plan_docs_complete_and_index_links_resolve():
    """plan/ 00–06 六份齐备，且 00 的索引链接不自指失效。"""
    plan = repo_root() / "plan"
    for name in ("00-README总览.md", "01-题目详细定义.md", "02-需求解读.md",
                 "03-架构与技术选型.md", "04-模块详设.md", "05-数据计划与里程碑.md",
                 "06-决策记录.md"):
        assert (plan / name).is_file(), "plan 文档缺失: %s" % name


def test_readme_commands_reference_existing_inputs():
    """README 里每条命令的输入文件必须真实存在（防"文档说能跑但没给可跑输入"）。

    这类缺口在本地会被工作目录残留掩盖，只有干净树才暴露——
    所以断言"路径存在"必须从**命令里抽参数**，而不是扫仓内路径字面量。
    """
    text = (repo_root() / "README.md").read_text(encoding="utf-8")
    # 只抽**具体路径**参数；`<专利.json>` 这类尖括号占位符不算引用
    referenced = re.findall(r"patfee\s+(?:calc|scan|reduction)\s+([^\s<>]+\.json)", text)
    assert referenced, "README 应给出可复制的 calc 命令"
    for rel in referenced:
        assert (repo_root() / rel).is_file(), "README 引用的输入文件不存在: %s" % rel


def test_readme_selfcheck_file_count_matches_reality():
    """README 中写死的门禁扫描文件数必须与实测一致（文档计数会随里程碑漂移）。"""
    text = (repo_root() / "README.md").read_text(encoding="utf-8")
    m = re.search(r"零字面量门禁:\s*扫描\s*(\d+)\s*文件", text)
    assert m, "README 未给出 selfcheck 的门禁扫描示例输出"
    claimed = int(m.group(1))

    from patfee.rules.loader import load_library
    from patfee.rules import literals_gate

    lib = load_library(data_dir())
    actual = len(literals_gate.scan_source(
        repo_root(), lib.banned_integers, lib.banned_decimals).scanned_files)
    assert claimed == actual, (
        "README 写扫描 %d 文件，实测 %d —— 新增/改名了源码或工具脚本，请同步 README" % (claimed, actual)
    )
