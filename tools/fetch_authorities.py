"""依据原文抓取与快照台账工具。

用途：把官方政策原文与费率表页直连落盘到 ``data/knowledge/raw/``，
并重算 sha256 写进 ``_ledger.json``。

纪律：

* **搜索摘要一律不采信** —— 只用可直连的官方页面原文核对。
* 快照台账登记 `来源 + 字节数 + sha256`；入库后由守门测试复算比对。
* 抓取失败**不编造**：把"待核对"记进 ``data/README.md``，继续推进。

用法::

    python tools/fetch_authorities.py            # 抓取并刷新台账
    python tools/fetch_authorities.py --verify   # 只复算既有快照的 sha256，不联网

注：快照含官方页面原文，**不入 PyInstaller 包**（版权与体积）；规则包只引用其坐标。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from patfee.console import ensure_utf8_stdio  # noqa: E402

ensure_utf8_stdio()

RAW_DIR = ROOT / "data" / "knowledge" / "raw"
LEDGER = RAW_DIR / "_ledger.json"

# 基准日 2026-10-14 实测可直连的官方来源。
# 注意：费率表页原记录的 URL 已失效（404），现行地址多了一段路径前缀
# `GzfwYwblGlwhTMVC/GzfwYwblGlwhT/` —— 这类 URL 迁移要记进 data/README.md。
SOURCES: List[Dict[str, str]] = [
    {
        "name": "cnipa_fee_schedule_286",
        "url": "https://cponline.cnipa.gov.cn/GzfwYwblGlwhTMVC/GzfwYwblGlwhT/selectByNoticeId?weihuRid=286",
        "kind": "fee_schedule",
        "label": "国家知识产权局专利收费标准（公示页）",
    },
    {
        "name": "mof_2016_78",
        "url": "http://www.mof.gov.cn/gkml/caizhengwengao/wg2016/wg201609/201702/t20170209_2531813.htm",
        "kind": "policy",
        "label": "《专利收费减缴办法》财税〔2016〕78 号",
    },
    {
        "name": "gov_316",
        "url": "https://www.gov.cn/zhengce/zhengceku/2019-12/09/content_5459661.htm",
        "kind": "policy",
        "label": "国家知识产权局公告第 316 号",
    },
    {
        "name": "gov_594",
        "url": "https://www.gov.cn/zhengce/zhengceku/202408/content_6967596.htm",
        "kind": "policy",
        "label": "国家知识产权局公告第 594 号",
    },
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def fetch_one(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def refresh() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ledger = []
    failures = []
    for src in SOURCES:
        try:
            data = fetch_one(src["url"])
        except Exception as exc:  # noqa: BLE001 - 渠道失败要如实记录而非中断
            failures.append("%s: %s: %s" % (src["name"], type(exc).__name__, exc))
            continue
        (RAW_DIR / (src["name"] + ".html")).write_bytes(data)
        ledger.append({
            "name": src["name"],
            "url": src["url"],
            "kind": src["kind"],
            "label": src["label"],
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
        print("  OK  %-28s %7d 字节" % (src["name"], len(data)))
    if ledger:
        LEDGER.write_bytes((json.dumps(ledger, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    for item in failures:
        print("  FAIL %s" % item)
    print("台账已刷新: %d 份快照 -> %s" % (len(ledger), LEDGER))
    return 1 if failures else 0


def verify() -> int:
    if not LEDGER.is_file():
        print("台账缺失: %s" % LEDGER)
        return 1
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    problems = []
    for item in ledger:
        path = RAW_DIR / (item["name"] + ".html")
        if not path.is_file():
            problems.append("快照缺失: %s" % path.name)
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != item["sha256"]:
            problems.append("%s 的 sha256 不一致（磁盘 %s / 台账 %s）"
                            % (path.name, actual[:12], item["sha256"][:12]))
    if problems:
        for p in problems:
            print("  FAIL %s" % p)
        return 1
    print("AUTHORITY_SNAPSHOTS_OK (%d 份快照 sha256 与台账一致)" % len(ledger))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="依据原文抓取与快照台账")
    parser.add_argument("--verify", action="store_true", help="只复算既有快照 sha256，不联网")
    args = parser.parse_args(argv)
    return verify() if args.verify else refresh()


if __name__ == "__main__":
    sys.exit(main())
