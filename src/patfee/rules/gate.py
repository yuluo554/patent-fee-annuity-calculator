"""门控：计算前校验所引用规则条目的 ``status``。

语义（plan/06 D9/D10/D11）：

* ``verified``        —— 放行。
* ``pending``         —— **拒绝进计算路径**；``--preview`` 可预览口径但退出码仍为 1。
* ``input_required``  —— **放行门控**，但运行时必须显式索取该外部输入；
                         缺失即 exit 2，**绝不静默取 0/1**。
* 条目值为 ``None``（尚未入库）—— 拒绝，原因码 ``missing_value``。

门控**按作用域**（scope）分：一份规则包承载多种用途的参数时，
"整包全 verified 才放行"会让与本次计算无关的 ``pending`` 阻断整条路径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .loader import (
    STATUS_INPUT_REQUIRED,
    STATUS_PENDING,
    STATUS_VERIFIED,
    Entry,
    RuleLibrary,
)

# 作用域常量：各计算路径只校验自己引用的条目
SCOPE_CALC = "calc"          # 年费阶梯
SCOPE_LATE = "late"          # 滞纳金与恢复权利
SCOPE_REDUCTION = "reduction"  # 费减资格与减免额
SCOPE_CHECK = "check"        # 校核与对账阈值
ALL_SCOPES = (SCOPE_CALC, SCOPE_LATE, SCOPE_REDUCTION, SCOPE_CHECK)


@dataclass
class GateDecision:
    """门控结论。

    ``allowed`` 为 False 时，引擎不得产出金额（未判定）；
    ``required_inputs`` 是必须由调用方提供的外部输入（input_required 条目）。
    """

    scope: str
    allowed: bool
    blocked: List[Tuple[str, str]] = field(default_factory=list)      # (entry_key, reason_code)
    required_inputs: List[str] = field(default_factory=list)          # entry_key 列表
    permitted_unverified: List[str] = field(default_factory=list)     # preview 下放行的 pending
    statuses: Dict[str, str] = field(default_factory=dict)            # entry_key -> status

    @property
    def reasons(self) -> Tuple[str, ...]:
        out: List[str] = []
        for _, code in self.blocked:
            if code not in out:
                out.append(code)
        return tuple(out)

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "allowed": self.allowed,
            "blocked": [{"entry": k, "reason": c} for k, c in self.blocked],
            "required_inputs": list(self.required_inputs),
            "permitted_unverified": list(self.permitted_unverified),
            "statuses": dict(self.statuses),
        }


def evaluate(
    entries: Sequence[Entry],
    scope: str,
    preview: bool = False,
    provided_inputs: Sequence[str] = (),
) -> GateDecision:
    """对一组条目做门控。

    :param entries: 本次计算将引用的条目（由调用方从库中取出）。
    :param scope: 计算路径作用域；条目 scopes 不含该作用域时跳过（与本次计算无关）。
    :param preview: ``--preview``，允许 pending 参与但调用方必须把退出码置 1。
    :param provided_inputs: 调用方已提供的外部输入条目键（满足 input_required）。
    """
    provided = set(provided_inputs)
    decision = GateDecision(scope=scope, allowed=True, statuses={})

    for entry in entries:
        if entry.scopes and scope not in entry.scopes:
            continue  # 与本次计算无关，不参与门控
        decision.statuses[entry.key] = entry.status

        if entry.status == STATUS_VERIFIED:
            if not entry.has_value:
                decision.blocked.append((entry.key, "missing_value"))
                decision.allowed = False
            continue

        if entry.status == STATUS_INPUT_REQUIRED:
            # 放行门控，但运行时必须显式索取；未提供 = 计算前提不成立
            if entry.key not in provided:
                decision.required_inputs.append(entry.key)
            continue

        if entry.status == STATUS_PENDING:
            if preview:
                decision.permitted_unverified.append(entry.key)
            else:
                decision.blocked.append((entry.key, "gated_pending"))
                decision.allowed = False
            continue

        # 未知状态：schema 校验已拦，这里兜底
        decision.blocked.append((entry.key, "gated_pending"))
        decision.allowed = False

    if decision.required_inputs:
        decision.allowed = False
    return decision


def evaluate_keys(
    library: RuleLibrary,
    keys: Sequence[str],
    scope: str,
    preview: bool = False,
    provided_inputs: Sequence[str] = (),
) -> GateDecision:
    """按键取条目后门控；条目不存在记 ``untracked_entry``。"""
    entries: List[Entry] = []
    missing: List[Tuple[str, str]] = []
    for key in keys:
        entry = None
        for rs in library.rulesets.values():
            entry = rs.get(key)
            if entry is not None:
                break
        if entry is None:
            missing.append((key, "untracked_entry"))
        else:
            entries.append(entry)
    decision = evaluate(entries, scope, preview=preview, provided_inputs=provided_inputs)
    if missing:
        decision.blocked = missing + decision.blocked
        decision.allowed = False
    return decision
