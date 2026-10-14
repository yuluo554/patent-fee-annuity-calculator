"""规则包加载与 schema 校验。

规则包按 **`依据文件 × 版本`** 组织：每份 ruleset 独立成集，各挂文号、条款、
URL 与抓取日期。金额一律用 ``parse_float=Decimal`` 解析，杜绝经 float 失真。

本模块**只读**：任何写入都归 ``tools/gen_rulesets.py``（唯一写入者）。
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..errors import RulesetError
from . import literals

MANIFEST_NAME = "manifest.json"
SCHEMA_MANIFEST = "patfee.rules.manifest/v1"
SCHEMA_RULESET = "patfee.ruleset/v1"

STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"
STATUS_INPUT_REQUIRED = "input_required"
VALID_STATUS = (STATUS_VERIFIED, STATUS_PENDING, STATUS_INPUT_REQUIRED)


class Entry:
    """规则条目。值为 ``None`` 表示尚未入库（原因码 missing_value）。"""

    __slots__ = ("key", "label", "kind", "status", "scopes", "basis", "value", "ladder", "note",
                 "ruleset_id", "ruleset_version")

    def __init__(self, raw: dict, ruleset_id: str, ruleset_version: str) -> None:
        self.key = raw.get("key") or ""
        self.label = raw.get("label") or ""
        self.kind = raw.get("kind") or "scalar"
        self.status = raw.get("status") or STATUS_PENDING
        self.scopes = tuple(raw.get("scopes") or ())
        self.basis = raw.get("basis") or {}
        self.value = raw.get("value", None)
        self.ladder = raw.get("ladder") or []
        self.note = raw.get("note") or ""
        self.ruleset_id = ruleset_id
        self.ruleset_version = ruleset_version

        if not self.key:
            raise RulesetError("规则条目缺少 key（ruleset=%s）" % ruleset_id)
        if self.status not in VALID_STATUS:
            raise RulesetError(
                "规则条目 %s 的 status 非法: %r（应为 %s）"
                % (self.key, self.status, "/".join(VALID_STATUS))
            )

    @property
    def verified(self) -> bool:
        return self.status == STATUS_VERIFIED

    @property
    def has_value(self) -> bool:
        if self.kind == "ladder":
            return bool(self.ladder)
        return self.value is not None

    def decimal(self) -> Optional[Decimal]:
        """标量条目的 Decimal 值；非数值/未入库返回 None。"""
        if self.value is None:
            return None
        if isinstance(self.value, bool):
            return None
        if isinstance(self.value, Decimal):
            return self.value
        if isinstance(self.value, int):
            return Decimal(self.value)
        if isinstance(self.value, float):  # 不应发生：加载器用 parse_float=Decimal
            raise RulesetError("条目 %s 值落到 float，加载器 parse_float 失效" % self.key)
        try:
            return Decimal(str(self.value).strip())
        except Exception:
            return None

    def tiers(self):
        """阶梯条目的区间列表（列表元素形如 {'from_year','to_year','amount','label'}）。

        返回**原始 dict**，由引擎负责构造 domain.Tier —— 规则层不认识领域层。
        """
        return list(self.ladder)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "status": self.status,
            "scopes": list(self.scopes),
            "value": None if self.value is None else str(self.value),
            "ladder": self.ladder,
            "basis": self.basis,
            "note": self.note,
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
        }


class Ruleset:
    def __init__(self, raw: dict, expected_sha: Optional[str] = None) -> None:
        if raw.get("schema") != SCHEMA_RULESET:
            raise RulesetError("ruleset schema 不符: %r" % (raw.get("schema"),))
        self.id = raw.get("id") or ""
        self.version = raw.get("version") or ""
        self.title = raw.get("title") or ""
        self.doc_no = raw.get("doc_no") or ""
        self.anchor_from = raw.get("anchor_from") or ""
        self.anchor_to = raw.get("anchor_to") or ""
        self.source = raw.get("source") or {}
        self.expected_sha256 = expected_sha
        if not self.id or not self.version:
            raise RulesetError("ruleset 缺少 id/version")
        self.entries: Dict[str, Entry] = {}
        for item in raw.get("entries") or []:
            entry = Entry(item, self.id, self.version)
            if entry.key in self.entries:
                raise RulesetError("ruleset %s 条目 key 重复: %s" % (self.id, entry.key))
            self.entries[entry.key] = entry

    def anchor(self) -> str:
        return "%s@%s" % (self.id, self.version)

    def status_counts(self) -> Dict[str, int]:
        counts = {s: 0 for s in VALID_STATUS}
        for entry in self.entries.values():
            counts[entry.status] = counts.get(entry.status, 0) + 1
        return counts

    def get(self, key: str) -> Optional[Entry]:
        return self.entries.get(key)


class RuleLibrary:
    """全部规则集的只读视图 + manifest 元信息。"""

    def __init__(self, manifest: dict, rulesets: List[Ruleset], data_dir: Path) -> None:
        if manifest.get("schema") != SCHEMA_MANIFEST:
            raise RulesetError("manifest schema 不符: %r" % (manifest.get("schema"),))
        self.raw_manifest = manifest
        self.data_dir = Path(data_dir)
        self.rulesets = {rs.id: rs for rs in rulesets}
        self.scopes = tuple(manifest.get("scopes") or ("calc",))
        self.benchmarks = manifest.get("benchmarks") or {}
        self.banned_integers = set(int(v) for v in (manifest.get("banned_tokens", {}) or {}).get("integers", []))
        self.banned_decimals = set(str(v) for v in (manifest.get("banned_tokens", {}) or {}).get("decimals", []))
        self.exemptions = manifest.get("exemptions") or {}

    def ruleset(self, ruleset_id: str) -> Ruleset:
        try:
            return self.rulesets[ruleset_id]
        except KeyError:
            raise RulesetError("规则集不存在: %r（可用: %s）" % (ruleset_id, ", ".join(sorted(self.rulesets))))

    def entries_with_prefix(self, prefix: str) -> List[Entry]:
        """跨全部规则集，按键前缀取条目（如 ``annuity.`` —— 按类型取年费阶梯）。"""
        found: List[Entry] = []
        for rs in self.rulesets.values():
            for key, entry in sorted(rs.entries.items()):
                if key.startswith(prefix):
                    found.append(entry)
        return found

    def status_counts(self) -> Dict[str, int]:
        counts = {s: 0 for s in VALID_STATUS}
        for rs in self.rulesets.values():
            for status, n in rs.status_counts().items():
                counts[status] = counts.get(status, 0) + n
        return counts

    def coordinate(self) -> dict:
        """报告头固定输出的规则包坐标。"""
        return {
            "manifest_schema": self.raw_manifest.get("schema"),
            "rulesets": [
                {
                    "id": rs.id,
                    "version": rs.version,
                    "title": rs.title,
                    "doc_no": rs.doc_no,
                    "anchor_from": rs.anchor_from,
                    "anchor_to": rs.anchor_to,
                    "sha256": rs.expected_sha256,
                    "status_counts": rs.status_counts(),
                }
                for rs in sorted(self.rulesets.values(), key=lambda r: r.id)
            ],
            "scope_gate": list(self.scopes),
        }

    def benchmark_threshold(self, suite: str) -> dict:
        """门槛随 manifest 下发（数据非代码）；缺失即报配置错误。"""
        cfg = self.benchmarks.get(suite)
        if not cfg:
            raise RulesetError(
                "manifest 未下发基准门槛: %s（门槛必须随规则包下发，不得回落代码默认值）" % suite
            )
        return cfg


def _load_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RulesetError("规则文件不可读: %s (%s)" % (path, exc))
    try:
        return json.loads(text, parse_float=Decimal)
    except ValueError as exc:
        raise RulesetError("规则文件 JSON 非法: %s (%s)" % (path, exc))


def load_library(data_dir: Optional[Path] = None) -> RuleLibrary:
    """加载 manifest 与全部 ruleset；schema 不符即抛 RulesetError。"""
    if data_dir is None:
        from ..data_paths import find_data_dir

        data_dir = find_data_dir()
    data_dir = Path(data_dir)
    rules_dir = data_dir / "rules"
    manifest_path = rules_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        # "找不到数据目录/文件"与"文件在但内容坏"是两种语义：
        # 前者由调用方转 exit 2 的 ruleset_error，后者是 schema 错。
        raise FileNotFoundError("规则包 manifest 不存在: %s" % manifest_path)
    manifest = _load_json(manifest_path)
    rulesets: List[Ruleset] = []
    for meta in manifest.get("rulesets") or []:
        fname = meta.get("file")
        if not fname:
            raise RulesetError("manifest 条目缺少 file: %r" % (meta.get("id"),))
        raw = _load_json(rules_dir / fname)
        if raw.get("id") != meta.get("id"):
            raise RulesetError("manifest 与 ruleset id 不一致: %r vs %r" % (meta.get("id"), raw.get("id")))
        if raw.get("version") != meta.get("version"):
            raise RulesetError(
                "manifest 与 ruleset version 不一致: %s %r vs %r"
                % (meta.get("id"), meta.get("version"), raw.get("version"))
            )
        rulesets.append(Ruleset(raw, expected_sha=meta.get("sha256")))
    library = RuleLibrary(manifest, rulesets, data_dir)
    ok, why = literals.check_mirror(library.exemptions)
    if not ok:
        raise RulesetError("零字面量门禁豁免表镜像不一致: %s" % why)
    return library


def all_numeric_values(library: RuleLibrary) -> Tuple[set, set]:
    """从全部规则条目值推导禁用 token（供生成器与门禁共用同一实现）。"""
    values: List[object] = []
    for rs in library.rulesets.values():
        for entry in rs.entries.values():
            if entry.kind == "ladder":
                for tier in entry.ladder:
                    values.append(tier.get("amount"))
                    values.append(tier.get("from_year"))
                    values.append(tier.get("to_year"))
            else:
                values.append(entry.value)
    values.extend(library.raw_manifest.get("banned_tokens", {}).get("extra_integers", []) or [])
    return literals.collect_tokens(values)


def iter_entries(library: RuleLibrary) -> Iterable[Entry]:
    for rs in sorted(library.rulesets.values(), key=lambda r: r.id):
        for key in sorted(rs.entries):
            yield rs.entries[key]
