"""零政策字面量门禁的豁免表（精度约定与日历常数）。

这份表是**门禁与代码之间的唯一契约**：任何在源码里合法出现的数字，
要么在豁免范围内（日历/精度/数组长度），要么来自规则包。
``data/rules/manifest.json`` 里有同内容的镜像登记，由测试守两处一致——
口径只写一处、两处必须同源，否则门禁与豁免会各自漂移。

豁免口径（写死，避免门禁刷屏后被运维性忽略）：

* 整数 ``abs(n) < 100``           —— 日历常数 / 年度档边界 / 数组长度
* 小数 ``0.01 0.1 0.5 1 2``       —— 精度与半量换算约定

注意：**政策数值本身（费率、阈值、比例、百分比）绝不在豁免范围内**。
它们只能来自 ``data/rules/``，这是"抄进代码的第二份真相"的防线。
"""

from __future__ import annotations

from decimal import Decimal
from typing import FrozenSet, Iterable, Tuple

# 精度与半量换算约定（非政策数值）
EXEMPT_DECIMALS: FrozenSet[str] = frozenset({"0.01", "0.1", "0.5", "1.0", "2.0"})

# 小整数豁免上界（不含）：abs(n) < 100 视为日历/结构常数
SMALL_INT_ABS_LIMIT = 100

# 显式豁免的整数字面量（已确认属日历/结构语义，防止误报刷屏）
EXEMPT_INTEGERS: FrozenSet[int] = frozenset()

# 行内放行标记：所在行含该标记即免疫，且**仍会打印在报告中**
INLINE_ALLOW_MARK = "literal-ok"


def is_exempt_integer(value: int) -> bool:
    return abs(value) < SMALL_INT_ABS_LIMIT or value in EXEMPT_INTEGERS


def is_exempt_decimal(token: str) -> bool:
    try:
        d = Decimal(token)
    except Exception:
        return False
    if not d.is_finite():
        return True  # inf/nan 不是金额
    if d == d.to_integral_value():
        return is_exempt_integer(int(d))
    return token in EXEMPT_DECIMALS


def mirror_payload() -> dict:
    """供 manifest.json 镜像登记用（两处一致由测试守门）。"""
    return {
        "small_int_abs_limit": SMALL_INT_ABS_LIMIT,
        "exempt_integers": sorted(EXEMPT_INTEGERS),
        "exempt_decimals": sorted(EXEMPT_DECIMALS),
        "inline_allow_mark": INLINE_ALLOW_MARK,
    }


def check_mirror(manifest_exemptions: dict) -> Tuple[bool, str]:
    """校验 manifest 里的镜像是否与本表一致。"""
    expected = mirror_payload()
    got = dict(manifest_exemptions or {})
    got.setdefault("exempt_integers", [])
    got.setdefault("exempt_decimals", [])
    if got.get("small_int_abs_limit") != expected["small_int_abs_limit"]:
        return False, "small_int_abs_limit 不一致: manifest=%r 代码=%r" % (
            got.get("small_int_abs_limit"),
            expected["small_int_abs_limit"],
        )
    if sorted(got.get("exempt_integers") or []) != expected["exempt_integers"]:
        return False, "exempt_integers 不一致"
    if sorted(got.get("exempt_decimals") or []) != expected["exempt_decimals"]:
        return False, "exempt_decimals 不一致"
    if got.get("inline_allow_mark") != expected["inline_allow_mark"]:
        return False, "inline_allow_mark 不一致"
    return True, "ok"


def collect_tokens(values: Iterable[object]) -> Tuple[set, set]:
    """从规则包值推导禁用 token（整数集 + 小数字符串集）。

    规则：绝对值 >= SMALL_INT_ABS_LIMIT 的整数进禁用整数集；
    非精度约定的小数按**原样字符串**进禁用小数集。
    """
    ints = set()
    decs = set()
    for raw in values:
        if raw is None:
            continue
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            if not is_exempt_integer(raw):
                ints.add(raw)
            continue
        if isinstance(raw, Decimal):
            if raw == raw.to_integral_value():
                iv = int(raw)
                if not is_exempt_integer(iv):
                    ints.add(iv)
            elif not is_exempt_decimal(str(raw)):
                decs.add(str(raw))
            continue
        text = str(raw).strip()
        if not text:
            continue
        try:
            d = Decimal(text)
        except Exception:
            continue
        if d == d.to_integral_value():
            iv = int(d)
            if not is_exempt_integer(iv):
                ints.add(iv)
        elif not is_exempt_decimal(text):
            decs.add(text)
    return ints, decs
