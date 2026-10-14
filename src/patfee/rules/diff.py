"""规则版本差异报告（``patfee rules diff``）。

用途：把"政策换版"这件事做成可读、可机读的对照表，而不是让人去翻规则包 JSON。

本模块只做**呈现**：全部数值取自 ``data/rules/``（规则的单一事实源），
代码里不出现任何政策数值——这才是"改规则包即改结论"的兑现方式。

两类差异：

* **同族前后值对照**（阈值调整）：条目键形如 ``X`` 与 ``X.prev`` 成对出现时，
  按 ``X`` 报告 before/after 与是否变化。公告第 316 号把个人年收入阈值
  由 4.2 万调到 6 万、企业应纳税所得额由 30 万调到 100 万，即是此类。
* **新增/变更条目清单**：对某文号引入的新收费项目与减免（公告第 594 号的
  期限补偿请求费、补偿期年费、开放许可减免），逐条列出并标注它在
  费率表里是否有**同口径对应条目**（两处独立记载可互证）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .loader import Entry, RuleLibrary, Ruleset


def _value_text(entry: Entry) -> str:
    if entry.kind == "ladder":
        return "；".join(
            "%s-%s 年 %s" % (t.get("from_year"), t.get("to_year"), t.get("amount"))
            for t in entry.ladder
        ) or "（空阶梯）"
    if entry.value is None:
        return "（未入库）"
    unit = (entry.basis or {}).get("unit", "")
    return "%s%s" % (entry.value, (" " + unit) if unit else "")


def _entry_view(entry: Entry) -> dict:
    return {
        "key": entry.key,
        "label": entry.label,
        "status": entry.status,
        "value": _value_text(entry),
        "doc_no": (entry.basis or {}).get("doc_no", ""),
        "clause": (entry.basis or {}).get("clause", ""),
        "note": entry.note,
        "ruleset_id": entry.ruleset_id,
        "ruleset_version": entry.ruleset_version,
    }


def _pair_thresholds(ruleset: Ruleset) -> Tuple[List[dict], List[dict]]:
    """按 ``X`` / ``X.prev`` 配对。返回 (配对表, 未配对条目)。"""
    pairs: List[dict] = []
    used = set()
    for key in sorted(ruleset.entries):
        if key.endswith(".prev"):
            continue
        prev_key = key + ".prev"
        prev = ruleset.get(prev_key)
        if prev is None:
            continue
        cur = ruleset.entries[key]
        used.add(key)
        used.add(prev_key)
        pairs.append({
            "key": key,
            "label": cur.label,
            "before": _value_text(prev),
            "after": _value_text(cur),
            "changed": _value_text(prev) != _value_text(cur),
            "before_basis": (prev.basis or {}).get("clause", ""),
            "after_basis": (cur.basis or {}).get("clause", ""),
        })
    leftovers = [_entry_view(ruleset.entries[k]) for k in sorted(ruleset.entries) if k not in used]
    return pairs, leftovers


_SUFFIXES = ("_594", "_316", "_78")


def _base_key(key: str) -> str:
    """去掉版本后缀（``_594`` 一类）得到规范化键。"""
    base = key
    for suffix in _SUFFIXES:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def _cross_reference(library: RuleLibrary) -> Dict[str, List[str]]:
    """跨规则集的同口径条目索引（规范化键 → ``id@version#key`` 列表，含自身）。

    用于回答"594 号里的期限补偿请求费，费率表里是不是也有一条同口径的"。
    两处独立记载即互证；调用方负责剔除自身。
    """
    index: Dict[str, List[str]] = {}
    for rs in sorted(library.rulesets.values(), key=lambda r: r.id):
        for key in sorted(rs.entries):
            index.setdefault(_base_key(key), []).append(
                "%s@%s#%s" % (rs.id, rs.version, key)
            )
    return index


def diff_ruleset(library: RuleLibrary, ruleset_id: str) -> dict:
    """对一份规则集产出差异报告。

    :raises RulesetError: 规则集不存在（调用方转 exit 2）。
    """
    ruleset = library.ruleset(ruleset_id)
    pairs, leftovers = _pair_thresholds(ruleset)
    xref = _cross_reference(library)

    new_items: List[dict] = []
    for key in sorted(ruleset.entries):
        if key.endswith(".prev") or any(p["key"] == key for p in pairs):
            continue
        entry = ruleset.entries[key]
        item = _entry_view(entry)
        self_ref = "%s@%s#%s" % (ruleset.id, ruleset.version, key)
        others = [r for r in xref.get(_base_key(key), []) if r != self_ref]
        item["cross_reference"] = "；".join(others)
        new_items.append(item)
    # leftovers 与 new_items 同源（都是未配对条目），此处统一以 new_items 呈现
    del leftovers

    counts = ruleset.status_counts()
    return {
        "ruleset": {
            "id": ruleset.id,
            "version": ruleset.version,
            "title": ruleset.title,
            "doc_no": ruleset.doc_no,
            "anchor_from": ruleset.anchor_from,
            "anchor_to": ruleset.anchor_to,
            "entries": len(ruleset.entries),
            "status_counts": counts,
        },
        "thresholds": pairs,
        "items": new_items,
        "notes": [
            "thresholds 段 = 同族前后值对照（X vs X.prev），回答『阈值改了多少』。",
            "items 段 = 本规则集引入的条目清单；cross_reference 非空表示另一规则集"
            "有同口径条目（两处独立记载，可互证）。",
            "全部数值取自 data/rules/，本报告不重算、不内联政策值。",
        ],
    }


def render_text(payload: dict) -> List[str]:
    """人类可读渲染（表现层只做排版）。"""
    rs = payload["ruleset"]
    lines: List[str] = []
    lines.append("== 规则差异报告 ==")
    lines.append("规则集: %s@%s  %s" % (rs["id"], rs["version"], rs["title"]))
    lines.append("文号: %s" % rs["doc_no"])
    lines.append("锚点: %s ~ %s" % (rs["anchor_from"], rs["anchor_to"] or "（现行）"))
    counts = rs["status_counts"]
    lines.append("条目: %d（verified=%d pending=%d input_required=%d）"
                 % (rs["entries"], counts.get("verified", 0),
                    counts.get("pending", 0), counts.get("input_required", 0)))

    lines.append("")
    if payload["thresholds"]:
        lines.append("-- 阈值/取值前后对照（%d 组）--" % len(payload["thresholds"]))
        for pair in payload["thresholds"]:
            flag = "变更" if pair["changed"] else "未变"
            lines.append("  [%s] %s（%s）" % (flag, pair["label"], pair["key"]))
            lines.append("        调整前: %s" % pair["before"])
            lines.append("        调整后: %s" % pair["after"])
    else:
        lines.append("-- 阈值/取值前后对照: 本规则集无成对历史值（无 X/X.prev 配对）--")

    lines.append("")
    lines.append("-- 本规则集条目清单（%d 条）--" % len(payload["items"]))
    for item in payload["items"]:
        lines.append("  [%s] %s  %s" % (item["status"], item["key"], item["label"]))
        lines.append("        值: %s" % item["value"])
        if item.get("cross_reference"):
            lines.append("        同口径条目: %s" % item["cross_reference"])

    lines.append("")
    for note in payload["notes"]:
        lines.append("注: %s" % note)
    return lines
