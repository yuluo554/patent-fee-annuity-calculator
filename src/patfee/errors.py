"""退出码语义（定稿后锁进 CLI 测试，重构不漂移）。

    0  完成（结论达标）
    1  降级完成 / 计算非法 —— 门控拒绝、基准未达标、结果带 warning
    2  输入 / 参数 / 坐标错误 —— 文件不存在、坏 JSON、类型不识别、未知子命令
    3  缺可选依赖 —— 源码态缺 extras；冻结态功能未内嵌

批量通路的纪律：失败件（坏格式/缺字段）记原因码单列，**不改变退出码**——
"没判定"与"判出问题"是两种语义。退出码只由"是否检出问题"决定。
"""

from __future__ import annotations

from enum import Enum


class ExitCode(Enum):
    OK = 0
    DEGRADED = 1
    USAGE = 2
    MISSING_DEP = 3


class PatfeeError(Exception):
    """本工具所有可预期错误的基类；错误必须携带原因码。"""

    reason_code = "error"

    def __init__(self, message: str, reason_code: str = "") -> None:
        super().__init__(message)
        self.message = message
        if reason_code:
            self.reason_code = reason_code


class UsageError(PatfeeError):
    """输入/参数/坐标错误 → exit 2。"""

    reason_code = "usage_error"


class RulesetError(PatfeeError):
    """规则包缺失、schema 不符、坐标不可解析 → exit 2。"""

    reason_code = "ruleset_error"


class GatedError(PatfeeError):
    """门控拒绝：引用了未核对的规则条目 → exit 1。"""

    reason_code = "gated_pending"


class OutOfRangeError(PatfeeError):
    """计算前提超出规则覆盖范围（如缴费年度超过阶梯上限）。"""

    reason_code = "out_of_range"


class MissingDependencyError(PatfeeError):
    """缺可选依赖 → exit 3；提示须按冻结态分流。"""

    reason_code = "missing_dependency"


# 引擎与报告层共用的原因码表（人读说明 + 归类）。
# "未判定"（unresolved）不报警；只有 fail/warning 才改变结论。
REASON_CATALOG = {
    "missing_value": ("规则条目值尚未入库（value = null）", "unresolved"),
    "gated_pending": ("引用条目 status=pending，门控拒绝进入计算路径", "unresolved"),
    "input_required": ("规则包不承载该外部输入，运行时必须显式索取", "unresolved"),
    "untracked_entry": ("规则包中不存在该条目", "unresolved"),
    "unknown_patent_type": ("专利类型不识别", "unresolved"),
    "bad_format": ("输入文件格式不可解析", "unresolved"),
    "missing_field": ("输入缺少必填字段", "unresolved"),
    "out_of_range": ("缴费年度超出阶梯覆盖范围", "unresolved"),
    "late_exceeds_cap": ("逾期月数超过规则包上限（进入失效流程口径）", "warning"),
    "anchor_mismatch": ("该年度没有可用锚点的有效规则版本", "unresolved"),
}

# 冻结态与源码态的提示分流：exe 用户没有 pip / 源码树，
# 源码态说 pip install 是对的，冻结态必须改口。见 plan/06 D22。
_SOURCE_HINT = {
    "report": 'python -m pip install -e ".[report]"',
    "gui": 'python -m pip install -e ".[gui]"',
    "build": 'python -m pip install -e ".[build]"',
}

_FROZEN_HINT = {
    "report": "本发行包未内嵌 XLSX 导出所需组件；可改用 --format csv 导出机读报告。",
    "gui": "本发行包未内嵌桌面界面组件；请使用 CLI 入口。",
    "build": "本发行包已构建完成，无需 PyInstaller。",
}


def dependency_hint(extra: str, frozen: bool) -> str:
    """按冻结态分流的缺依赖提示。"""
    table = _FROZEN_HINT if frozen else _SOURCE_HINT
    return table.get(extra, "")
