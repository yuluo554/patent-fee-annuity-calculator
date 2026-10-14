"""组合批量排期与跨轮对账引擎（M3）。

五条纪律（plan/04 §六、D13）：

1. **失败隔离** —— 单件异常（坏 JSON / 缺字段 / 类型不识别 / 年度超范围）转成
   ``kind="failed"`` 条目单列留痕，继续处理其余件；**失败件不改变退出码**
   （退出码由"是否检出问题"决定，plan/03 §七批量通路纪律）；
2. **配对主键 = 稳定身份键 ``patent_no``**，不是内容指纹 —— 内容指纹变化另立
   ``content_changed`` 标记，不让它退化成"新增 + 移除"（plan/06 D13）；
3. **对账三集合** —— ``new_due``（本轮新增到期）/ ``settled``（已缴清）/
   ``still_unpaid``（持续未缴）；辅助集 ``content_changed`` / ``vanished``；
   ``compare_rounds()`` 是**口径单一实现源**，CLI 与基准共用（plan/04 §六）；
4. **到期预警** —— 按 ``due_on - today`` 升序输出未来 N 个月内到期清单；
   ``today`` 由调用方显式注入（可复现性：引擎内**禁**取系统时钟）；
5. **零政策字面量** —— 预警月数、排序规则等结构参数由调用方传入，
   代码内不写死月数（``abs(n) >= 100`` 的整数会被门禁拦）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..domain.models import PatentType, parse_patent_type
from ..errors import UsageError

# 跨轮对账的条目种类（机读 kind 值）
KIND_FAILED = "failed"
KIND_UNCOMPUTED = "uncomputed"
KIND_SETTLED = "settled"
KIND_UNPAID = "unpaid"
KIND_NOT_DUE = "not_due"

REASON_BAD_FORMAT = "bad_format"


@dataclass(frozen=True)
class PortfolioRequest:
    """组合排期输入契约：文件路径清单 + 预警窗口 + 基准日。

    ``today`` 显式注入（CLI 默认取当日、基准固定取合成基准日），
    保证同输入同输出——可复现性不允许引擎内取系统时钟。
    """

    sources: Tuple[Tuple[str, Optional[Dict[str, Any]]], ...]
    """(来源名, 已解析的 JSON payload)；payload 为 None 表示文件读取/解析已失败。"""

    today: date
    window_months: int = 3
    preview: bool = False


@dataclass(frozen=True)
class PortfolioEntry:
    """单件排期结论。

    ``kind`` 四态：``settled``（该年度已缴清）/ ``unpaid``（已到期未缴清）/
    ``not_due``（尚未到期）/ ``failed``（输入坏格式，失败隔离单列）；
    ``uncomputed`` 保留给"文件合法但引擎未判定"（门控拒绝）的场景。
    """

    source: str
    id: str
    kind: str
    patent_no: str = ""
    patent_type: str = ""
    year: Optional[int] = None
    due_on: str = ""
    paid_on: str = ""
    days_until_due: Optional[int] = None
    amount: Optional[Decimal] = None
    reason: str = ""
    reasons: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("PortfolioEntry.amount 必须是 Decimal，收到 float: %r" % (self.amount,))

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "id": self.id,
            "kind": self.kind,
            "patent_no": self.patent_no,
            "patent_type": self.patent_type,
            "year": self.year,
            "due_on": self.due_on,
            "paid_on": self.paid_on,
            "days_until_due": self.days_until_due,
            "amount": None if self.amount is None else str(self.amount),
            "reason": self.reason,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PortfolioResult:
    """组合排期的确定性结果：逐件条目 + 三集合 + 预警清单 + 失败件。"""

    today: str
    window_months: int
    entries: Tuple[PortfolioEntry, ...] = ()
    failed: Tuple[PortfolioEntry, ...] = ()
    settled: Tuple[str, ...] = ()
    unpaid: Tuple[str, ...] = ()
    not_due: Tuple[str, ...] = ()
    uncomputed: Tuple[str, ...] = ()
    due_soon: Tuple[PortfolioEntry, ...] = ()
    coordinate: dict = field(default_factory=dict)
    disclaimer: str = ""

    @property
    def detected(self) -> bool:
        """是否检出问题（退出码依据）：未缴清 / 未判定 / 预警窗口内有到期 / 失败件。

        失败件计入"检出"（它们是**记录在案的问题**），但不放大严重度——
        plan/03 §七：失败件不改变退出码语义，"没判定"与"判出问题"都不假成功。
        """
        return bool(self.unpaid or self.uncomputed or self.due_soon or self.failed)

    def as_dict(self) -> dict:
        return {
            "today": self.today,
            "window_months": self.window_months,
            "entries": [e.as_dict() for e in self.entries],
            "failed": [e.as_dict() for e in self.failed],
            "counts": {
                "settled": len(self.settled),
                "unpaid": len(self.unpaid),
                "not_due": len(self.not_due),
                "uncomputed": len(self.uncomputed),
                "failed": len(self.failed),
                "due_soon": len(self.due_soon),
            },
            "settled": list(self.settled),
            "unpaid": list(self.unpaid),
            "not_due": list(self.not_due),
            "uncomputed": list(self.uncomputed),
            "due_soon": [e.as_dict() for e in self.due_soon],
            "coordinate": self.coordinate,
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True)
class RoundReconciliation:
    """跨轮对账结果：三集合 + 辅助集（plan/04 §六）。

    配对主键 = ``patent_no``（稳定身份键）。``content_changed`` 记
    "身份在但本轮内容与上轮不同"的件（金额/期限变了，须人工看），
    ``vanished`` 记"上轮有本轮无"的件。
    """

    new_due: Tuple[str, ...] = ()
    settled: Tuple[str, ...] = ()
    still_unpaid: Tuple[str, ...] = ()
    content_changed: Tuple[str, ...] = ()
    vanished: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "new_due": list(self.new_due),
            "settled": list(self.settled),
            "still_unpaid": list(self.still_unpaid),
            "content_changed": list(self.content_changed),
            "vanished": list(self.vanished),
            "counts": {
                "new_due": len(self.new_due),
                "settled": len(self.settled),
                "still_unpaid": len(self.still_unpaid),
                "content_changed": len(self.content_changed),
                "vanished": len(self.vanished),
            },
        }


def _entry_id(source: str, payload: Dict[str, Any]) -> str:
    """条目标识：优先 patent_no+year，退回来源名（失败隔离时 id 必须有值）。"""
    no = str(payload.get("patent_no") or "")
    year = payload.get("year")
    if no:
        return "%s#y%s" % (no, year if year not in (None, "") else "?")
    return source


def build_portfolio_entry(
    source: str,
    payload: Any,
    today: date,
    library: Any = None,
) -> PortfolioEntry:
    """单件输入 → 排期结论；坏格式走 ``kind=failed``（失败隔离，不抛异常）。

    ``library`` 传入时取该年度年费金额（未传则金额留空，由调用方另行计算）；
    金额缺失不阻断排期结论本身。
    """
    if not isinstance(payload, dict):
        return PortfolioEntry(
            source=source, id=source, kind=KIND_FAILED, reason=REASON_BAD_FORMAT
        )
    entry_id = _entry_id(source, payload)

    patent_no = str(payload.get("patent_no") or "")
    if not patent_no:
        return PortfolioEntry(
            source=source, id=entry_id, kind=KIND_FAILED, reason=REASON_BAD_FORMAT,
            reasons=(REASON_BAD_FORMAT,),
        )

    type_raw = payload.get("patent_type")
    if type_raw in (None, ""):
        return PortfolioEntry(
            source=source, id=entry_id, kind=KIND_FAILED, patent_no=patent_no,
            reason=REASON_BAD_FORMAT, reasons=(REASON_BAD_FORMAT,),
        )
    try:
        patent_type = parse_patent_type(str(type_raw))
    except ValueError:
        return PortfolioEntry(
            source=source, id=entry_id, kind=KIND_FAILED, patent_no=patent_no,
            reason=REASON_BAD_FORMAT, reasons=(REASON_BAD_FORMAT,),
        )

    year_raw = payload.get("year")
    try:
        year = int(year_raw)
    except (TypeError, ValueError):
        return PortfolioEntry(
            source=source, id=entry_id, kind=KIND_FAILED, patent_no=patent_no,
            patent_type=patent_type.value, reason=REASON_BAD_FORMAT,
            reasons=(REASON_BAD_FORMAT,),
        )
    if year < 1:
        return PortfolioEntry(
            source=source, id=entry_id, kind=KIND_FAILED, patent_no=patent_no,
            patent_type=patent_type.value, reason=REASON_BAD_FORMAT,
            reasons=(REASON_BAD_FORMAT,),
        )

    due_raw = payload.get("due_on") or ""
    try:
        due_on = date.fromisoformat(str(due_raw))
    except ValueError:
        return PortfolioEntry(
            source=source, id=entry_id, kind=KIND_FAILED, patent_no=patent_no,
            patent_type=patent_type.value, year=year, reason=REASON_BAD_FORMAT,
            reasons=(REASON_BAD_FORMAT,),
        )

    paid_raw = str(payload.get("paid_on") or "")
    paid_on: Optional[date] = None
    if paid_raw:
        try:
            paid_on = date.fromisoformat(paid_raw)
        except ValueError:
            return PortfolioEntry(
                source=source, id=entry_id, kind=KIND_FAILED, patent_no=patent_no,
                patent_type=patent_type.value, year=year, due_on=due_on.isoformat(),
                reason=REASON_BAD_FORMAT, reasons=(REASON_BAD_FORMAT,),
            )

    amount: Optional[Decimal] = None
    warnings: List[str] = []
    if library is not None:
        from . import annuity as annuity_mod

        annuity_result = annuity_mod.compute_annuity(library, patent_type, year)
        if annuity_result.computed and annuity_result.amount is not None:
            amount = annuity_result.amount
        else:
            warnings.append("年费金额未判定: %s" % ", ".join(annuity_result.reasons))

    days_until_due = (due_on - today).days
    if paid_on is not None:
        kind = KIND_SETTLED
    elif days_until_due < 0:
        kind = KIND_UNPAID
    else:
        kind = KIND_NOT_DUE

    return PortfolioEntry(
        source=source,
        id=entry_id,
        kind=kind,
        patent_no=patent_no,
        patent_type=patent_type.value,
        year=year,
        due_on=due_on.isoformat(),
        paid_on=paid_on.isoformat() if paid_on is not None else "",
        days_until_due=days_until_due,
        amount=amount,
        warnings=tuple(warnings),
    )


def _sorted_entries(entries: Sequence[PortfolioEntry]) -> Tuple[PortfolioEntry, ...]:
    """确定性排序：id 升序（不依赖 dict 迭代序）。"""
    return tuple(sorted(entries, key=lambda e: e.id))


def scan_portfolio(request: PortfolioRequest, library: Any = None) -> PortfolioResult:
    """组合批量排期：逐件结论 + 失败隔离 + 到期预警。

    失败件与正常件同列表留痕（``entries`` 含全部件），另在 ``failed`` 汇总；
    排期结论不受失败件影响。
    """
    entries: List[PortfolioEntry] = []
    failed: List[PortfolioEntry] = []

    for source, payload in request.sources:
        if payload is None:
            entry = PortfolioEntry(
                source=source, id=source, kind=KIND_FAILED, reason=REASON_BAD_FORMAT,
                reasons=(REASON_BAD_FORMAT,),
            )
        else:
            try:
                entry = build_portfolio_entry(source, payload, request.today, library)
            except Exception:
                # 失败隔离的最后一道：任何单件异常都不拖垮整批
                entry = PortfolioEntry(
                    source=source, id=source, kind=KIND_FAILED,
                    reason=REASON_BAD_FORMAT, reasons=(REASON_BAD_FORMAT,),
                )
        entries.append(entry)
        if entry.kind == KIND_FAILED:
            failed.append(entry)

    live = [e for e in entries if e.kind != KIND_FAILED]
    settled = tuple(sorted(e.id for e in live if e.kind == KIND_SETTLED))
    unpaid = tuple(sorted(e.id for e in live if e.kind == KIND_UNPAID))
    not_due = tuple(sorted(e.id for e in live if e.kind == KIND_NOT_DUE))
    uncomputed_ids = tuple(sorted(
        e.id for e in live if e.kind == KIND_UNCOMPUTED
    ))

    # 到期预警：窗口内（0 <= days <= 窗口上界）按剩余天数升序；已到期未缴的排最前
    upper = request.window_months * 31
    due_soon = tuple(sorted(
        (e for e in live if e.kind == KIND_NOT_DUE and 0 <= (e.days_until_due or 0) <= upper),
        key=lambda e: (e.days_until_due or 0, e.id),
    ))

    return PortfolioResult(
        today=request.today.isoformat(),
        window_months=request.window_months,
        entries=_sorted_entries(entries),
        failed=_sorted_entries(failed),
        settled=settled,
        unpaid=unpaid,
        not_due=not_due,
        uncomputed=uncomputed_ids,
        due_soon=due_soon,
        coordinate=library.coordinate() if library is not None else {},
    )


def content_fingerprint(payload: Dict[str, Any]) -> str:
    """单件内容指纹：参与对账语义的关键字段（金额/期限，plan/04 §六口径）。

    指纹只用于**变化检测**（``content_changed``），不是配对主键（配对用
    ``patent_no``，D13）。``paid_on`` 不参与指纹：缴清与否正是 ``settled`` /
    ``still_unpaid`` 两集合承载的正常轮转，不能让"这轮缴清了"同时再报一条
    "内容变化"。
    """
    import hashlib
    import json as _json

    relevant = {
        "patent_no": payload.get("patent_no"),
        "year": payload.get("year"),
        "due_on": payload.get("due_on"),
    }
    blob = _json.dumps(relevant, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compare_rounds(
    previous: Sequence[Dict[str, Any]],
    current: Sequence[Dict[str, Any]],
) -> RoundReconciliation:
    """跨轮对账（**口径单一实现源**：CLI 与基准共用，plan/04 §六）。

    * 配对主键 = ``patent_no``（稳定身份键，D13）—— 不是内容指纹；
    * ``new_due``：上轮未出现、本轮出现的件；
    * ``settled``：两轮都出现、且本轮已缴清（``paid_on`` 非空）；
    * ``still_unpaid``：两轮都出现、本轮仍未缴清；
    * ``content_changed``：身份在但内容指纹变了（另立标记，不混入新增/移除）；
    * ``vanished``：上轮有、本轮无。

    同一 ``patent_no`` 多件时按 ``(year, due_on)`` 排序后逐位配对，
    多出的件按新增/消失处理——对账口径对输入形状不挑食。
    """
    def _index(items: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            no = str(item.get("patent_no") or "")
            out.setdefault(no, []).append(item)
        for lst in out.values():
            lst.sort(key=lambda d: (str(d.get("year") or ""), str(d.get("due_on") or "")))
        return out

    prev_index = _index(previous)
    curr_index = _index(current)

    new_due: List[str] = []
    settled: List[str] = []
    still_unpaid: List[str] = []
    content_changed: List[str] = []

    for no in sorted(curr_index):
        curr_list = curr_index[no]
        prev_list = prev_index.get(no, [])
        for idx, cur in enumerate(curr_list):
            key = "%s#y%s" % (no, cur.get("year") if cur.get("year") not in (None, "") else "?")
            if idx >= len(prev_list):
                new_due.append(key)
                continue
            prev = prev_list[idx]
            if content_fingerprint(prev) != content_fingerprint(cur):
                content_changed.append(key)
            if str(cur.get("paid_on") or ""):
                settled.append(key)
            else:
                still_unpaid.append(key)

    vanished: List[str] = []
    for no in sorted(prev_index):
        prev_list = prev_index[no]
        curr_list = curr_index.get(no, [])
        for idx, prev in enumerate(prev_list):
            if idx >= len(curr_list):
                vanished.append(
                    "%s#y%s" % (no, prev.get("year") if prev.get("year") not in (None, "") else "?")
                )

    return RoundReconciliation(
        new_due=tuple(new_due),
        settled=tuple(settled),
        still_unpaid=tuple(still_unpaid),
        content_changed=tuple(content_changed),
        vanished=tuple(vanished),
    )


def parse_portfolio_input(raw: Any) -> Tuple[Tuple[str, Optional[Dict[str, Any]]], ...]:
    """清单/组合输入 → (来源名, payload) 序列。

    接受两种形状：条目数组，或 ``{"items": [...]}``。单件坏格式**不在此抛**——
    由 ``build_portfolio_entry`` 转 failed 条目（失败隔离在引擎，不在解析）。
    """
    if isinstance(raw, dict):
        items = raw.get("items")
    elif isinstance(raw, list):
        items = raw
    else:
        raise UsageError("组合输入必须是数组或 {\"items\": [...]} 对象")
    if not isinstance(items, list):
        raise UsageError("组合输入的 items 必须是数组")
    out: List[Tuple[str, Optional[Dict[str, Any]]]] = []
    for idx, item in enumerate(items):
        name = ""
        if isinstance(item, dict):
            name = str(item.get("patent_no") or "")
        out.append((name or "item[%d]" % idx, item))
    return tuple(out)
