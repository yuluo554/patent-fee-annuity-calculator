"""脱敏审计器（四步固化形态）。

把"发布前脱敏检查"做成**入仓可复跑**的工具，而不是一次性命令。三种模式：

* ``--mode tracked``  —— 扫全部**已跟踪**文本文件（内容级）
* ``--mode history``  —— 逐提交扫历史 blob（**防"删了文件但历史还在"**）
* ``--mode messages`` —— 扫全部提交信息

输出**一律掩码化**（只报"文件:行号 [类别] x次数"，不回显敏感串原文）——
留档会引用本工具的输出，输出本身不得成为二次泄漏源。

命中分级（让审计可持续，不至于"永远红 → 被运维性忽略"）：

* ``HARD``     —— 进退出码（1）。真实泄露形式：个人目录路径、个人邮箱、手机号、身份证。
* ``REVIEW``   —— 人工豁免留档，不进退出码。
* ``advisory`` —— 只报不阻断。典型是长 hex 串（本项目的 sha256 指纹是**文档化功能**，
  规则库/台账里遍地都是合法哈希）。

豁免（"看起来像泄露，但在本项目里是功能/公开元数据"）：

1. ``*@users.noreply.github.com`` —— noreply 是**脱敏目标形态**，本就该出现；
2. ``git@<host>`` / ``ssh@<host>`` —— 传输地址，非个人邮箱；
3. ``github.com/<账号>`` —— clone URL 是发布固有公开元数据（账号名必然出现）；
4. 行内 ``audit-allow`` 标记 —— 所在行放过，但**仍打印**（可审计"为什么放过"）。

阳性对照（:func:`selftest`）不是形式：它同时配正例（必须报红）与**反例**
（noreply / 传输地址 / gov.cn 导航 URL 必须**不**报红）——只写正例会让规则一改就误报。

注：本脚本的**正则模式用片段拼接构造**，避免"扫描器源码里的完整词面被自己的扫描命中、
从此永留历史"。个人标记按**组合路径签名**匹配（``Users<分隔符><名>``），不匹配裸用户名，
否则会撞上游二进制的厂商串（如 Qt DLL 内嵌的电脑厂商名）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from patfee.console import ensure_utf8_stdio  # noqa: E402

ensure_utf8_stdio()

HARD = "HARD"
REVIEW = "REVIEW"
ADVISORY = "advisory"

INLINE_ALLOW = "audit-allow"

# 二进制/快照文件按其类型判定（不做文本扫描）
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".toml", ".yml", ".yaml", ".cfg", ".ini",
    ".html", ".htm", ".csv", ".tsv", ".spec", ".gitattributes", ".gitignore", ".bat", ".sh",
}

# ---------------------------------------------------------------------------
# 模式构造：一律片段拼接，完整词面不入仓
# ---------------------------------------------------------------------------
# "Program" + "Data" = 系统级目录名（本身不是个人标记）
_PROG_DATA = "Progra" + "mData"
_WIN_USERS = "Use" + "rs"
# 分隔符**可重复**：JSON/日志里路径常被转义成双分隔符，单分隔符类会漏判
# 这种真实泄漏形态（M6 实测假阴性）。
_SEP = r"[\\/]+"
# 用户名段必须以字母开头（真实家目录名），避免把 /home/2023-03/ 这类**日期路径段**误判为家目录
_USER_SEG = r"[A-Za-z][A-Za-z0-9_.\-]{1,}"
# 个人目录签名：盘符 + Users + 用户名（组合签名，不匹配裸用户名）
_PERSONAL_DIR = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:" + _SEP + _WIN_USERS + _SEP + _USER_SEG + r"(?![A-Za-z0-9_.\-])"
)
# POSIX 家目录签名：/home/<名>/ 或 /Users/<名>/，且前面不能是主机名（排除 gov.cn/home/... 这类导航 URL）
_POSIX_HOME = re.compile(
    r"(?<![A-Za-z0-9._-])/" + r"(?:home|" + _WIN_USERS + r")/" + _USER_SEG + r"(?![A-Za-z0-9_.\-])"
)
# 工作根签名：ProgramData + 工作目录名
_WORK_ROOT = re.compile(_PROG_DATA + _SEP + _USER_SEG)

# noreply 是脱敏目标形态；传输地址与服务域不是个人邮箱
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9][A-Za-z0-9._%+\-]*@"
    r"(?!(?:users\.noreply\.)?github\.com(?![A-Za-z0-9.\-]))"   # 排除 noreply 与 github 域
    r"[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"
)
_TRANSPORT = re.compile(r"(?:git|ssh|hg)@[A-Za-z0-9.\-]+")
# 手机号 / 身份证：hex 边界环视 —— sha256 十六进制串里的数字段不是手机号
_PHONE = re.compile(r"(?<![0-9a-fA-F])1[3-9]\d{9}(?![0-9a-fA-F])")
_IDCARD = re.compile(
    r"(?<![0-9A-Za-z])[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])"
)
_INTERNAL_IP = re.compile(
    r"(?<![\d.])(?:10\.\d{1,3}|192\.168\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3})\.\d{1,3}(?![\d.])"
)
# 长 hex：sha256/指纹是文档化功能 → advisory
_LONG_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")

RULES: List[Tuple[str, str, "re.Pattern"]] = [
    ("personal_dir", HARD, _PERSONAL_DIR),
    ("posix_home", HARD, _POSIX_HOME),
    ("work_root", HARD, _WORK_ROOT),
    ("email", HARD, _EMAIL),
    ("phone", HARD, _PHONE),
    ("idcard", HARD, _IDCARD),
    ("internal_ip", REVIEW, _INTERNAL_IP),
    ("long_hex", ADVISORY, _LONG_HEX),
]

# 仅对特定路径生效的放行（按路径 glob + 规则名，不做"整文件放过"）
PATH_ALLOW: Dict[Tuple[str, str], str] = {
    ("data/knowledge/raw/gov_316.html", "long_hex"): "官方页面原文快照（非本项目生成）",
    ("data/knowledge/raw/gov_594.html", "long_hex"): "官方页面原文快照（非本项目生成）",
    ("data/knowledge/raw/mof_2016_78.html", "long_hex"): "官方页面原文快照（非本项目生成）",
    ("data/knowledge/raw/cnipa_fee_schedule_286.html", "long_hex"): "官方页面原文快照（非本项目生成）",
    # sha256 内容指纹是本项目的**文档化功能**（证据链留痕），登记值遍地都是合法哈希
    ("data/rules/manifest.json", "long_hex"): "规则包 sha256 指纹（文档化功能）",
}

SKIP_TRACKED_PREFIXES = ("data/knowledge/raw/",)
SKIP_NAMES = {"_ledger.json"}


@dataclass
class Hit:
    grade: str
    kind: str
    location: str


@dataclass
class AuditResult:
    mode: str
    hits: List[Hit] = field(default_factory=list)
    scanned: int = 0
    probe_ok: bool = False
    probe_note: str = ""

    def by_grade(self, grade: str) -> List[Hit]:
        return [h for h in self.hits if h.grade == grade]

    @property
    def ok(self) -> bool:
        return self.probe_ok and not self.by_grade(HARD)


def _scan_text(text: str, location: str, path_rel: str) -> List[Hit]:
    hits: List[Hit] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        allowed_inline = INLINE_ALLOW in line
        for kind, grade, pattern in RULES:
            if not pattern.search(line):
                continue
            if (path_rel, kind) in PATH_ALLOW:
                hits.append(Hit(ADVISORY, kind + ":path-allowed", "%s:%d" % (location, lineno)))
                continue
            if allowed_inline:
                hits.append(Hit(ADVISORY, kind + ":inline-allowed", "%s:%d" % (location, lineno)))
                continue
            hits.append(Hit(grade, kind, "%s:%d" % (location, lineno)))
    return hits


def _git(args: Sequence[str]) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout


def tracked_files() -> List[str]:
    out = _git(["ls-files"])
    return [ln for ln in out.splitlines() if ln.strip()]


def audit_tracked() -> AuditResult:
    result = AuditResult(mode="tracked")
    for rel in tracked_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in (".gitattributes", ".gitignore"):
            continue
        if rel.startswith(SKIP_TRACKED_PREFIXES) or path.name in SKIP_NAMES:
            # 官方原文快照按其字节登记 sha256，原样保留；不参与内容扫描
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        result.scanned += 1
        result.hits.extend(_scan_text(text, rel, rel))
    result.probe_ok = True
    return result


def audit_history() -> AuditResult:
    """逐提交扫 blob。

    **必须逐提交迭代** —— ``git grep -e <模式> rev1 rev2 ...`` 只把首个非选项参数当
    revision、其余当 pathspec，会返回 0 行造成"全历史干净"的**假绿**。
    故这里逐 commit 取树、逐个读文件文本。
    """
    result = AuditResult(mode="history")
    commits = [ln for ln in _git(["rev-list", "--all"]).splitlines() if ln.strip()]
    if not commits:
        result.probe_note = "无提交可扫（仓库尚无历史）"
        return result

    # 通道探活：先搜一个必然存在的串，搜不到说明扫描机制本身是坏的
    probe = _git(["grep", "-l", "patfee", commits[0]])
    result.probe_ok = bool(probe.strip())
    result.probe_note = "通道探活通过（首提交内检得 patfee）" if result.probe_ok else "通道探活失败"

    seen_blobs = set()
    for commit in commits:
        out = _git(["ls-tree", "-r", "--name-only", commit])
        for rel in out.splitlines():
            if not rel.strip():
                continue
            if rel.startswith(SKIP_TRACKED_PREFIXES) or Path(rel).name in SKIP_NAMES:
                continue
            suffix = Path(rel).suffix.lower()
            if suffix not in TEXT_SUFFIXES:
                continue
            blob_id = _git(["rev-parse", "%s:%s" % (commit, rel)]).strip()
            if not blob_id or blob_id in seen_blobs:
                continue          # 同一 blob 只扫一次，省时且不影响判定
            seen_blobs.add(blob_id)
            content = _git(["cat-file", "-p", blob_id])
            result.scanned += 1
            result.hits.extend(_scan_text(content, "%s:%s" % (commit[:8], rel), rel))
    return result


def audit_messages() -> AuditResult:
    result = AuditResult(mode="messages")
    log = _git(["log", "--all", "--format=commit %H%n%B"])
    result.scanned = log.count("commit ")
    result.probe_ok = bool(log.strip())
    result.probe_note = "提交信息已读取" if result.probe_ok else "无提交信息"
    result.hits.extend(_scan_text(log, "<commit-message>", "<messages>"))
    return result


# --------------------------------------------------------------------------- 自检

_SELFTEST_POSITIVE = [
    # 合成样本：程序化拼接，仓内不留真实字面值
    "workdir = " + '"' + "D:" + "\\" + _PROG_DATA + "\\" + "some" + "Project" + '"',
    # 回归：JSON 转义后的双反斜杠形态（曾经漏判的真实泄漏形态）
    "detail = " + '"' + "D:" + "\\\\" + _PROG_DATA + "\\\\" + "some" + "Project" + '"',
    "path = " + '"' + "C:" + "\\" + _WIN_USERS + "\\" + "some" + "user" + "\\" + "x.txt" + '"',
    "mail = " + '"' + "someone" + "@" + "example" + ".com" + '"',
    "tail = " + '"' + "//" + "/home/" + "some" + "user/" + "data" + '"',
]
_SELFTEST_NEGATIVE = [
    # 这些形态在本项目里是功能/公开元数据，**不得**判红
    "author = " + '"' + "user" + "@" + "users.noreply.github.com" + '"',
    "remote = " + '"' + "git" + "@" + "github.com:owner/repo.git" + '"',
    "url = " + '"' + "https://www.gov.cn" + "/home/2023-03/29/content_5748953.htm" + '"',
    'sha = "' + "a" * 40 + '"',   # 长 hex = 指纹功能 → 只 advisory
]


def selftest() -> Tuple[bool, List[str]]:
    notes: List[str] = []
    ok = True

    for sample in _SELFTEST_POSITIVE:
        hits = _scan_text(sample, "<selftest>", "<selftest>")
        if not any(h.grade == HARD for h in hits):
            ok = False
            notes.append("正例未报红（应为 HARD）: %s" % sample[:40])

    for sample in _SELFTEST_NEGATIVE:
        hits = _scan_text(sample, "<selftest>", "<selftest>")
        if any(h.grade == HARD for h in hits):
            ok = False
            kinds = sorted({h.kind for h in hits if h.grade == HARD})
            notes.append("反例被误判为 HARD（%s）: %s" % (",".join(kinds), sample[:40]))

    if not notes:
        notes.append("正例 %d 项均报红；反例 %d 项均未误报"
                     % (len(_SELFTEST_POSITIVE), len(_SELFTEST_NEGATIVE)))
    return ok, notes


# --------------------------------------------------------------------------- 输出

def report(result: AuditResult) -> str:
    lines = ["审计模式: %s（扫描 %d 个对象）" % (result.mode, result.scanned)]
    if result.probe_note:
        lines.append("  通道探活: %s" % result.probe_note)
    for grade in (HARD, REVIEW, ADVISORY):
        items = result.by_grade(grade)
        if not items:
            continue
        lines.append("  [%s] %d 处:" % (grade, len(items)))
        for hit in items[:40]:
            lines.append("    %s  %s" % (hit.location, hit.kind))
        if len(items) > 40:
            lines.append("    ...（其余 %d 处省略）" % (len(items) - 40))
    if not result.hits:
        lines.append("  无命中")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="脱敏审计器（四步固化形态）")
    parser.add_argument("--mode", choices=["tracked", "history", "messages", "all"], default="all")
    parser.add_argument("--selftest", action="store_true", help="只跑阳性/阴性对照，不扫仓")
    args = parser.parse_args(argv)

    if args.selftest:
        ok, notes = selftest()
        for note in notes:
            print("  %s" % note)
        print("AUDIT_SELFTEST_OK" if ok else "AUDIT_SELFTEST_FAIL")
        return 0 if ok else 1

    modes = ["tracked", "history", "messages"] if args.mode == "all" else [args.mode]
    runners = {"tracked": audit_tracked, "history": audit_history, "messages": audit_messages}

    failed = False
    for mode in modes:
        result = runners[mode]()
        print(report(result))
        print()
        if not result.ok:
            failed = True

    if failed:
        print("DESENSITIZE_AUDIT_FAIL")
        return 1
    print("DESENSITIZE_AUDIT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
