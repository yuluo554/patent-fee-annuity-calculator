"""依据原文抓取与快照台账工具。

用途：把官方政策原文、费率表页与上位法原文直连落盘到 ``data/knowledge/raw/``，
并重算 sha256 写进 ``_ledger.json``。

纪律：

* **搜索摘要一律不采信** —— 只用可直连的官方页面原文核对。
* 快照台账登记 `来源 + 文件 + 字节数 + sha256`；入库后由守门测试复算比对。
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
        "file": "cnipa_fee_schedule_286.html",
    },
    {
        "name": "mof_2016_78",
        "url": "http://www.mof.gov.cn/gkml/caizhengwengao/wg2016/wg201609/201702/t20170209_2531813.htm",
        "kind": "policy",
        "label": "《专利收费减缴办法》财税〔2016〕78 号",
        "file": "mof_2016_78.html",
    },
    {
        "name": "gov_316",
        "url": "https://www.gov.cn/zhengce/zhengceku/2019-12/09/content_5459661.htm",
        "kind": "policy",
        "label": "国家知识产权局公告第 316 号",
        "file": "gov_316.html",
    },
    {
        "name": "gov_594",
        "url": "https://www.gov.cn/zhengce/zhengceku/202408/content_6967596.htm",
        "kind": "policy",
        "label": "国家知识产权局公告第 594 号",
        "file": "gov_594.html",
    },
    # ---- M1 定位到的上位法（依据索引 data/knowledge/clauses.json 逐条引用） ----
    {
        # 国务院公报版：含《修改决定》全文 + 修订后《实施细则》全文，第 5 条（期限计算）
        # 与第 115 条（年费缴纳期限、6 个月补缴期、滞纳金 5%/月）均在此页。
        "name": "gov_769_rules",
        "url": "https://www.gov.cn/gongbao/2024/issue_11086/202401/content_6924971.html",
        "kind": "upper_law",
        "label": "《中华人民共和国专利法实施细则》国务院令第 769 号（2024-01-20 施行）",
        "file": "gov_769_rules.html",
    },
    {
        # 国家法律法规数据库（全国人大）检索接口返回的条目元数据 + 正文目录树。
        # 用 Referer 指明来源站，避免被当作外链抓取。
        "name": "flk_patent_law_2020",
        "url": "https://flk.npc.gov.cn/law-search/search/flfgDetails?bbbs=ff808081752b7d430175e4651cbd1547",
        "kind": "upper_law",
        "label": "《中华人民共和国专利法》（2020 年第四次修正，2021-06-01 施行）",
        "file": "flk_patent_law_2020.json",
        "referer": "https://flk.npc.gov.cn/",
    },
    {
        # 《专利审查指南》现行基准版本：国家知识产权局令第 78 号，自 2024-01-20 施行。
        "name": "cnipa_guidelines_78",
        "url": "https://www.gov.cn/gongbao/2024/issue_11166/202402/content_6931868.html",
        "kind": "upper_law",
        "label": "《专利审查指南》国家知识产权局令第 78 号（2024-01-20 施行）",
        "file": "cnipa_guidelines_78.html",
    },
    {
        # 现行最新一次修改：国家知识产权局令第 84 号，自 2026-01-01 施行。
        "name": "cnipa_guidelines_84",
        "url": "https://www.gov.cn/gongbao/2026/issue_12526/202601/content_7056486.html",
        "kind": "upper_law",
        "label": "《专利审查指南》国家知识产权局令第 84 号（2026-01-01 施行）",
        "file": "cnipa_guidelines_84.html",
    },
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def fetch_one(url: str, timeout: int = 40, referer: str = "") -> bytes:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _file_of(src: Dict[str, str]) -> str:
    return src.get("file") or (src["name"] + ".html")


def refresh() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ledger = []
    failures = []
    for src in SOURCES:
        try:
            data = fetch_one(src["url"], referer=src.get("referer", ""))
        except Exception as exc:  # noqa: BLE001 - 渠道失败要如实记录而非中断
            failures.append("%s: %s: %s" % (src["name"], type(exc).__name__, exc))
            continue
        fname = _file_of(src)
        (RAW_DIR / fname).write_bytes(data)
        ledger.append({
            "name": src["name"],
            "url": src["url"],
            "kind": src["kind"],
            "label": src["label"],
            "file": fname,
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
        path = RAW_DIR / _file_of(item)
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
