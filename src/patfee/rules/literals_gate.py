"""零政策字面量门禁：扫描源码里的禁用数值 token。

WHY：规则值只能来自 ``data/rules/``。抄进代码的第二份真相必然与规则包漂移，
且让"改规则包即改行为"的承诺失效。

扫描面（随交付形态扩张，见 plan/06 D17）：

* ``src/patfee/**/*.py``  —— **含 docstring 与注释**
* ``tools/`` 下的报告/审计脚本（生成器除外：它是规则值的唯一来源）

豁免口径来自 ``rules/literals.py``（与 manifest.json 镜像，测试守一致）；
行内 ``literal-ok: <理由>`` 免疫该行，但**仍会打印**（可审计"为什么放过"）。

可证伪：:func:`selftest` 在内存副本里注入一个禁用 token 并断言必须报红——
防"门禁全绿其实什么都没查"（token 集为空同样报配置错误）。
"""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import literals

# 永不参与扫描的文件（生成器是规则值的唯一写入者与来源）
EXCLUDED_RELATIVE = {
    "tools/gen_rulesets.py",
    "tools/gen_synthetic.py",
}


@dataclass
class Hit:
    path: str
    lineno: int
    token: str
    kind: str
    line: str


@dataclass
class ScanResult:
    hits: List[Hit]
    allowed: List[Hit]
    scanned_files: List[str]
    banned_integers: Set[int]
    banned_decimals: Set[str]

    @property
    def ok(self) -> bool:
        return not self.hits


_NUMBER_RE = re.compile(r"(?<![0-9A-Za-z_.])(\d+(?:\.\d+)?)(?![0-9A-Za-z_])")


def _iter_source_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _candidate_files(root: Path, include: Sequence[str]) -> List[Path]:
    """收集扫描面文件。"""
    root = Path(root)
    files: List[Path] = []
    for pattern in include:
        for p in sorted(root.glob(pattern)):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if rel in EXCLUDED_RELATIVE:
                continue
            files.append(p)
    seen = set()
    out = []
    for p in files:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def scan_source(
    root: Path,
    banned_integers: Iterable[int],
    banned_decimals: Iterable[str],
    include: Sequence[str] = ("src/patfee/**/*.py", "tools/*.py"),
) -> ScanResult:
    """扫描源码。禁用整数按词边界匹配；禁用小数按原样字符串匹配。"""
    root = Path(root)
    ints = set(int(v) for v in banned_integers)
    decs = set(str(v) for v in banned_decimals)
    hits: List[Hit] = []
    allowed: List[Hit] = []
    scanned: List[str] = []

    for path in _candidate_files(root, include):
        rel = path.relative_to(root).as_posix()
        scanned.append(rel)
        lines = _iter_source_lines(path)
        in_docstring = False
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            # 粗略跟踪三引号 docstring 边界，文档字符串同样在扫描面内
            quotes = stripped.count('"""') + stripped.count("'''")
            inside = in_docstring
            if quotes % 2 == 1:
                in_docstring = not in_docstring
            if literals.INLINE_ALLOW_MARK in line:
                for match in _NUMBER_RE.finditer(line):
                    tok = match.group(1)
                    if _is_banned(tok, ints, decs):
                        allowed.append(Hit(rel, idx, tok, "inline-allowed", line.strip()))
                continue
            for match in _NUMBER_RE.finditer(line):
                tok = match.group(1)
                kind = _banned_kind(tok, ints, decs)
                if kind:
                    hits.append(Hit(rel, idx, tok, kind, line.strip()))
    return ScanResult(hits, allowed, scanned, ints, decs)


def _is_banned(token: str, ints: Set[int], decs: Set[str]) -> bool:
    return _banned_kind(token, ints, decs) != ""


def _banned_kind(token: str, ints: Set[int], decs: Set[str]) -> str:
    if "." in token:
        return "banned_decimal" if token in decs else ""
    try:
        value = int(token)
    except ValueError:
        return ""
    return "banned_integer" if value in ints else ""


def selftest(
    root: Path,
    banned_integers: Iterable[int],
    banned_decimals: Iterable[str],
) -> Tuple[bool, str]:
    """阳性对照：把禁用 token 写进一个临时探针文件，断言扫描器必须报红。

    探针写在**系统临时目录**里（不碰仓库树），扫描时把该目录当作扫描根、
    文件名配进 include —— 复用与真实扫描完全相同的代码路径。

    返回 (通过, 说明)。token 集为空 → 直接判定为配置错误（防"什么都没查"）。
    """
    import tempfile

    ints = set(int(v) for v in banned_integers)
    decs = set(str(v) for v in banned_decimals)
    if not ints and not decs:
        return False, "禁用 token 集为空 —— 门禁什么都没查，属配置错误"
    if not ints:
        return False, "禁用整数集为空，无法注入整数探针"

    injected = sorted(ints)[0]
    tmp_dir = Path(tempfile.mkdtemp(prefix="patfee_gate_probe_"))
    try:
        probe = tmp_dir / "gate_probe.py"
        probe.write_text("# 门禁阳性对照探针（临时）\nPROBE = %d\n" % injected, encoding="utf-8")
        result = scan_source(tmp_dir, ints, decs, include=("gate_probe.py",))
    finally:
        try:
            probe.unlink()
            tmp_dir.rmdir()
        except OSError:  # pragma: no cover - 清理失败不影响判定
            pass

    if result.ok:
        return False, "注入禁用 token %d 后扫描仍全绿 —— 门禁失效" % injected
    return True, "已检出注入的禁用 token %d" % injected


def format_report(result: ScanResult) -> str:
    buf = io.StringIO()
    buf.write("零政策字面量门禁扫描\n")
    buf.write("  扫描文件: %d\n" % len(result.scanned_files))
    buf.write("  禁用 token: 整数 %d 个 / 小数 %d 个\n"
              % (len(result.banned_integers), len(result.banned_decimals)))
    if result.allowed:
        buf.write("  行内放行 %d 处（仍列出，可审计）:\n" % len(result.allowed))
        for hit in result.allowed[:24]:
            buf.write("    %s:%d [%s] %s\n" % (hit.path, hit.lineno, hit.token, hit.line[:120]))
    if result.hits:
        buf.write("  命中 %d 处（硬门）:\n" % len(result.hits))
        for hit in result.hits[:64]:
            buf.write("    %s:%d [%s %s] %s\n" % (hit.path, hit.lineno, hit.kind, hit.token, hit.line[:120]))
    else:
        buf.write("  命中 0 处\n")
    return buf.getvalue()
