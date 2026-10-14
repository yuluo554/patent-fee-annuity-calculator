"""控制台入口守卫与环境探测。

编码加固三层之一：程序入口按 ``stream.encoding`` 探针决定是否 reconfigure。
中文本地控制台（cp936 / utf-8）保持不动，cp1252 一类西文代码页才改写——
本机习惯 `py -X utf8` 掩盖不了 CI 管道与真实用户机器的编码缺口。

`tools/` 下每个会打印的脚本同样调用 :func:`ensure_utf8_stdio`：
"入口集合随里程碑增长"，漏守新脚本是 CI 首跑全红的常见根因。
"""

from __future__ import annotations

import io
import sys
from typing import Optional

_TARGET = "utf-8"
# 这些编码本身已能表达全部输出，不必也不应改动（改动会破坏本地中文控制台）。
_ALREADY_FINE = {"utf-8", "utf8", "cp936", "gbk", "gb18030", "utf-16"}


def _needs_reconfigure(stream: Optional[object]) -> bool:
    if stream is None:
        return False
    enc = (getattr(stream, "encoding", None) or "").lower().replace("_", "-")
    if not enc:
        return False
    return enc not in _ALREADY_FINE


def ensure_utf8_stdio() -> bool:
    """探针式改写 stdout/stderr 为 UTF-8。返回是否发生了改写。

    只在编码确实无法表达中文时改写，避免误伤本地中文控制台。
    """
    changed = False
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if not _needs_reconfigure(stream):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding=_TARGET, errors="replace")
                changed = True
                continue
            except (ValueError, OSError):  # pragma: no cover - 平台相关
                pass
        try:
            setattr(sys, name, io.TextIOWrapper(stream.buffer, encoding=_TARGET, errors="replace"))
            changed = True
        except (AttributeError, ValueError):  # pragma: no cover - 平台相关
            pass
    return changed


def is_frozen() -> bool:
    """是否运行在 PyInstaller 冻结态。"""
    return bool(getattr(sys, "frozen", False))


def emit(text: str = "") -> None:
    """统一输出出口，便于测试捕获与编码兜底。"""
    try:
        print(text)
    except UnicodeEncodeError:  # pragma: no cover - 兜底，正常不应到达
        print(text.encode("utf-8", "replace").decode("ascii", "replace"))
