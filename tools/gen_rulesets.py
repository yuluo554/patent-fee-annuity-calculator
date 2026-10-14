"""规则包生成器 —— ``data/rules/`` 的**唯一写入者**。

纪律：

* 产物**禁手改**：改体例/加条目一律改本脚本后整目录重生成。
* **确定性落盘**：固定无时间戳、无 dict 迭代序依赖、无 ``random``；
  一律 ``write_bytes`` 写 LF，两次运行**逐字节一致**。
* ``--check``：重生成到内存 → 与磁盘逐字节比对 → 一致打印 ``FROZEN_RULESETS_OK``。
  这是"改完还自洽"的统一证据（比人肉判断硬）。
* 值一律挂 ``basis``（文号 / 条款 / URL / 抓取日期）。**本脚本是规则值的唯一来源，
  因此不在零字面量门禁的扫描面内**（见 plan/06 D17）。

M0 状态口径（plan/06 D20）：条目**带值但一律 `status=pending`**。
值取自 2026-10-14 直连获取的 CNIPA 公示费率表与三份政策原文（可溯源）；
但"可溯源" ≠ "已逐项复核"，故 M0 一律 pending，M1 逐项复核后改 verified。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from patfee.console import ensure_utf8_stdio  # noqa: E402
from patfee.rules import literals  # noqa: E402

ensure_utf8_stdio()

RULES_DIR = ROOT / "data" / "rules"

# 快照抓取日期（基准日）。产物不含当前时间——确定性优先。
RETRIEVED = "2026-10-14"

# 已直连获取的官方来源坐标
SRC_FEE_SCHEDULE = {
    "channel": "国家知识产权局专利业务办理系统 公示页",
    "url": "https://cponline.cnipa.gov.cn/GzfwYwblGlwhTMVC/GzfwYwblGlwhT/selectByNoticeId?weihuRid=286",
    "retrieved": RETRIEVED,
    "verification": "anchor_verified",
    "raw_snapshot": "data/knowledge/raw/cnipa_fee_schedule_286.html",
}
SRC_78 = {
    "channel": "财政部 财政文告（mof.gov.cn）",
    "url": "http://www.mof.gov.cn/gkml/caizhengwengao/wg2016/wg201609/201702/t20170209_2531813.htm",
    "retrieved": RETRIEVED,
    "verification": "anchor_verified",
    "raw_snapshot": "data/knowledge/raw/mof_2016_78.html",
}
SRC_316 = {
    "channel": "中国政府网 政策文件库（gov.cn）",
    "url": "https://www.gov.cn/zhengce/zhengceku/2019-12/09/content_5459661.htm",
    "retrieved": RETRIEVED,
    "verification": "anchor_verified",
    "raw_snapshot": "data/knowledge/raw/gov_316.html",
}
SRC_594 = {
    "channel": "中国政府网 政策文件库（gov.cn）",
    "url": "https://www.gov.cn/zhengce/zhengceku/202408/content_6967596.htm",
    "retrieved": RETRIEVED,
    "verification": "anchor_verified",
    "raw_snapshot": "data/knowledge/raw/gov_594.html",
}

DOC_FEE_SCHEDULE = "国家知识产权局专利收费标准（专利业务办理系统公示）"
DOC_78 = "《专利收费减缴办法》财税〔2016〕78 号"
DOC_316 = "国家知识产权局公告第 316 号"
DOC_594 = "国家知识产权局公告第 594 号"


def _scalar(key: str, label: str, value: Any, unit: str, clause: str, scopes: List[str],
            status: str = "pending", source: Optional[dict] = None,
            doc_no: str = DOC_FEE_SCHEDULE, note: str = "") -> dict:
    src = source or SRC_FEE_SCHEDULE
    return {
        "key": key,
        "label": label,
        "kind": "scalar",
        "status": status,
        "scopes": scopes,
        "value": value,
        "basis": {
            "doc_no": doc_no,
            "clause": clause,
            "unit": unit,
            "url": src["url"],
            "retrieved": src["retrieved"],
            "channel": src["channel"],
        },
        "note": note,
    }


def _ladder(key: str, label: str, tiers: List[dict], scopes: List[str],
            status: str = "pending", source: Optional[dict] = None,
            doc_no: str = DOC_FEE_SCHEDULE, clause: str = "", note: str = "") -> dict:
    src = source or SRC_FEE_SCHEDULE
    return {
        "key": key,
        "label": label,
        "kind": "ladder",
        "status": status,
        "scopes": scopes,
        "ladder": tiers,
        "basis": {
            "doc_no": doc_no,
            "clause": clause,
            "url": src["url"],
            "retrieved": src["retrieved"],
            "channel": src["channel"],
        },
        "note": note,
    }


# --------------------------------------------------------------- 费率表

def build_fee_schedule() -> dict:
    """现行专利收费标准表（费率表版本 v2024，基准日 2026-10-14 直连获取）。

    全部数值逐项来自 `patent收费、集成电路布图设计收费标准` 公示页
    （国家知识产权局 2024 年 8 月 6 日发布，页面含 594 号新增项目）。
    M0 一律 pending：值可溯源但尚未逐项复核到条目级。
    """
    pending_note = "锚点级已获取（HTTP 200 全文）；待 M1 逐项复核费率表页后置 verified"
    entries = [
        _ladder(
            "annuity.invention",
            "发明专利年费阶梯",
            [
                {"from_year": 1, "to_year": 3, "amount": 900, "label": "第 1-3 年"},
                {"from_year": 4, "to_year": 6, "amount": 1200, "label": "第 4-6 年"},
                {"from_year": 7, "to_year": 9, "amount": 2000, "label": "第 7-9 年"},
                {"from_year": 10, "to_year": 12, "amount": 4000, "label": "第 10-12 年"},
                {"from_year": 13, "to_year": 15, "amount": 6000, "label": "第 13-15 年"},
                {"from_year": 16, "to_year": 20, "amount": 8000, "label": "第 16-20 年"},
            ],
            scopes=["calc"],
            clause="（七）年费 · 1.发明专利：1-3 年（每年）900；4-6 年 1200；7-9 年 2000；"
                   "10-12 年 4000；13-15 年 6000；16-20 年 8000",
            note=pending_note,
        ),
        _ladder(
            "annuity.utility_model",
            "实用新型专利年费阶梯",
            [
                {"from_year": 1, "to_year": 3, "amount": 600, "label": "第 1-3 年"},
                {"from_year": 4, "to_year": 5, "amount": 900, "label": "第 4-5 年"},
                {"from_year": 6, "to_year": 8, "amount": 1200, "label": "第 6-8 年"},
                {"from_year": 9, "to_year": 10, "amount": 2000, "label": "第 9-10 年"},
            ],
            scopes=["calc"],
            clause="（七）年费 · 2.实用新型专利：1-3 年 600；4-5 年 900；6-8 年 1200；9-10 年 2000",
            note=pending_note,
        ),
        _ladder(
            "annuity.design",
            "外观设计专利年费阶梯",
            [
                {"from_year": 1, "to_year": 3, "amount": 600, "label": "第 1-3 年"},
                {"from_year": 4, "to_year": 5, "amount": 900, "label": "第 4-5 年"},
                {"from_year": 6, "to_year": 8, "amount": 1200, "label": "第 6-8 年"},
                {"from_year": 9, "to_year": 10, "amount": 2000, "label": "第 9-10 年"},
                {"from_year": 11, "to_year": 15, "amount": 3000, "label": "第 11-15 年"},
            ],
            scopes=["calc"],
            clause="（七）年费 · 3.外观设计专利：1-3 年 600；4-5 年 900；6-8 年 1200；"
                   "9-10 年 2000；11-15 年 3000",
            note=pending_note,
        ),
        _scalar(
            "late.monthly_rate", "年费滞纳金月费率", "0.05", "ratio",
            "（八）年费滞纳金：每超过规定的缴费时间 1 个月，加收当年全额年费的 5%",
            scopes=["late"], note=pending_note,
        ),
        _scalar(
            "late.grace_months", "滞纳金计收月数上限（进入失效流程口径）", None, "month",
            "待核对：《专利法实施细则》关于年费缴纳期限与滞纳期起止的规定",
            scopes=["late"],
            note="【待核对】实施细则原文未定位到条目级 → 值留空，计算路径将按 missing_value 拒绝",
        ),
        _scalar(
            "late.month_basis", "滞纳金月数计算口径", None, "enum",
            "待核对：细则原文对'超过规定缴费时间 1 个月'的月数计算口径",
            scopes=["late"],
            note="【待核对】M1 核对细则后定；口径值由规则包承载，不在代码里写死",
        ),
        _scalar(
            "check.fee.ruc", "恢复权利请求费", 1000, "CNY",
            "（九）恢复权利请求费 1000", scopes=["late", "check"], note=pending_note,
        ),
        _scalar(
            "check.fee.evaluation_report", "专利权评价报告请求费", 2400, "CNY",
            "（十二）专利权评价报告请求费：1.实用新型专利 2400；2.外观设计专利 2400",
            scopes=["late", "check"], note=pending_note,
        ),
        _scalar(
            "check.fee.term_compensation_request", "专利权期限补偿请求费", 200, "CNY",
            "（十五）专利权期限补偿请求费（每件）200",
            scopes=["check"], note="与公告第 594 号一致（每件 200 元）；" + pending_note,
        ),
        _scalar(
            "check.fee.compensation_annuity", "专利权补偿期年费", 8000, "CNY/year",
            "（十六）专利权补偿期年费（每年，不足一年部分不收取）8000",
            scopes=["check"], note=pending_note,
        ),
        _scalar(
            "check.fee.application.invention", "发明专利申请费", 900, "CNY",
            "（一）申请费 · 1.发明专利 900", scopes=["check"], note=pending_note,
        ),
        _scalar(
            "check.fee.application.utility_model", "实用新型专利申请费", 500, "CNY",
            "（一）申请费 · 2.实用新型专利 500", scopes=["check"], note=pending_note,
        ),
        _scalar(
            "check.fee.application.design", "外观设计专利申请费", 500, "CNY",
            "（一）申请费 · 3.外观设计专利 500", scopes=["check"], note=pending_note,
        ),
        _scalar(
            "check.fee.substantive_examination", "发明专利申请实质审查费", 2500, "CNY",
            "（五）发明专利申请实质审查费 2500", scopes=["check"], note=pending_note,
        ),
        _scalar(
            "check.fee.priority_claim", "优先权要求费（每项）", 80, "CNY",
            "（四）优先权要求费（每项）80", scopes=["check"], note=pending_note,
        ),
        _scalar(
            "check.fee.publication_printing", "公布印刷费", 50, "CNY",
            "（三）公布印刷费 50", scopes=["check"], note=pending_note,
        ),
    ]
    return {
        "schema": "patfee.ruleset/v1",
        "id": "fee_schedule",
        "version": "v2024",
        "title": "专利收费标准表",
        "doc_no": DOC_FEE_SCHEDULE,
        "anchor_from": "2024-08-06",
        "anchor_to": "",
        "source": SRC_FEE_SCHEDULE,
        "entries": entries,
    }


# --------------------------------------------------------- 财税〔2016〕78 号

def build_reduction_78() -> dict:
    """费减比例与减缴项目（财税〔2016〕78 号，自 2016-09-01 施行）。"""
    note = ("锚点级已获取并逐字核对第四条/第十二条；待 M1 完成条目级复核后置 verified。"
            "【口径要点】比例取决于主体是否『共同』，与个人/单位无关")
    return {
        "schema": "patfee.ruleset/v1",
        "id": "reduction_78",
        "version": "v2016",
        "title": "专利收费减缴办法（减缴比例与减缴项目）",
        "doc_no": DOC_78,
        "anchor_from": "2016-09-01",
        "anchor_to": "",
        "source": SRC_78,
        "entries": [
            _scalar(
                "reduction.rate.sole", "单主体减缴比例", "0.85", "ratio",
                "第四条：专利申请人或者专利权人为个人或者单位的，减缴本办法第二条规定收费的 85%",
                scopes=["reduction"], source=SRC_78, doc_no=DOC_78,
                note=note,
            ),
            _scalar(
                "reduction.rate.combined", "共同主体减缴比例", "0.70", "ratio",
                "第四条：两个或者两个以上的个人或者单位为共同专利申请人或者共有专利权人的，"
                "减缴本办法第二条规定收费的 70%",
                scopes=["reduction"], source=SRC_78, doc_no=DOC_78,
                note=note,
            ),
            _scalar(
                "reduction.effective_from", "本办法施行日期", "2016-09-01", "date",
                "第十二条：本办法自 2016 年 9 月 1 日起施行",
                scopes=["reduction"], source=SRC_78, doc_no=DOC_78, note=note,
            ),
            _scalar(
                "reduction.eligible_categories", "可减缴的收费种类",
                "申请费（不含公布印刷费、申请附加费）、发明专利申请实质审查费、复审费、"
                "年费（自授予专利权当年起十年内的年费）",
                "text",
                "第二条 + 费率表『费减种类』栏（现行口径已含开放实施许可期间的年费）",
                scopes=["reduction"], source=SRC_78, doc_no=DOC_78,
                note="【待核对】减缴项目清单随 594 号与现行费率表口径扩展，M1 逐项核对后定稿",
            ),
        ],
    }


# ------------------------------------------------------ 公告第 316 号

def build_reduction_316() -> dict:
    """费减阈值调整（公告第 316 号，自 2019-07-01 起）。"""
    note = ("锚点级已获取并逐字核对；306→316 的阈值调整前后值均出自本公告原文。"
            "待 M1 条目级复核后置 verified")
    return {
        "schema": "patfee.ruleset/v1",
        "id": "reduction_316",
        "version": "v2019",
        "title": "调整专利收费减缴条件（阈值）",
        "doc_no": DOC_316,
        "anchor_from": "2019-07-01",
        "anchor_to": "",
        "source": SRC_316,
        "entries": [
            _scalar(
                "reduction.threshold.individual_annual_income", "个人年收入阈值",
                60000, "CNY/year",
                "一、……由上年度月均收入低于 3500 元（年 4.2 万元）的个人，"
                "调整为上年度月均收入低于 5000 元（年 6 万元）的个人",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316, note=note,
            ),
            _scalar(
                "reduction.threshold.individual_monthly_income", "个人月均收入阈值",
                5000, "CNY/month",
                "一、……调整为上年度月均收入低于 5000 元（年 6 万元）的个人",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316, note=note,
            ),
            _scalar(
                "reduction.threshold.entity_taxable_income", "企业应纳税所得额阈值",
                1000000, "CNY/year",
                "一、……由上年度企业应纳税所得额低于 30 万元的企业，"
                "调整为上年度企业应纳税所得额低于 100 万元的企业",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316, note=note,
            ),
            _scalar(
                "reduction.threshold.effective_from", "调整生效日期", "2019-07-01", "date",
                "……国家知识产权局将于 2019 年 7 月 1 日起调整专利收费减缴条件",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316, note=note,
            ),
            # 调整前的历史值：供 rules diff 输出差异报告，并支撑历史年度回算
            _scalar(
                "reduction.threshold.individual_annual_income.prev", "个人年收入阈值（316 号前）",
                42000, "CNY/year",
                "一、……由上年度月均收入低于 3500 元（年 4.2 万元）的个人",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316,
                note="【历史值】用于差异报告与 2019-07-01 前年度回算；不参与当前判定",
            ),
            _scalar(
                "reduction.threshold.individual_monthly_income.prev", "个人月均收入阈值（316 号前）",
                3500, "CNY/month",
                "一、……由上年度月均收入低于 3500 元（年 4.2 万元）的个人",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316,
                note="【历史值】用于差异报告与 2019-07-01 前年度回算",
            ),
            _scalar(
                "reduction.threshold.entity_taxable_income.prev", "企业应纳税所得额阈值（316 号前）",
                300000, "CNY/year",
                "一、……由上年度企业应纳税所得额低于 30 万元的企业",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316,
                note="【历史值】用于差异报告与 2019-07-01 前年度回算",
            ),
        ],
    }


# ------------------------------------------------------ 公告第 594 号

def build_reduction_594() -> dict:
    """新增收费项目与减免（公告第 594 号，2024-08-06 成文）。"""
    note = "锚点级已获取并逐字核对；待 M1 条目级复核后置 verified"
    return {
        "schema": "patfee.ruleset/v1",
        "id": "reduction_594",
        "version": "v2024",
        "title": "调整部分专利收费标准和减缴政策（新增项目与减免）",
        "doc_no": DOC_594,
        "anchor_from": "2024-08-06",
        "anchor_to": "",
        "source": SRC_594,
        "entries": [
            _scalar(
                "reduction.open_license_discount", "开放许可实施期间年费减免比例", "0.15", "ratio",
                "二、对专利开放许可实施期间的专利年费减免 15%。同时适用其他专利收费减免政策的，"
                "可以选择适用最优惠的政策，但不得重复享受",
                scopes=["reduction"], source=SRC_594, doc_no=DOC_594, note=note,
            ),
            _scalar(
                "reduction.no_double_benefit", "多政策择一规则", "choose_most_favorable", "enum",
                "二、……同时适用其他专利收费减免政策的，可以选择适用最优惠的政策，但不得重复享受",
                scopes=["reduction"], source=SRC_594, doc_no=DOC_594,
                note="择最优惠且不叠加；判定过程必须在结果中留痕（候选集 + 选中项）",
            ),
            _scalar(
                "check.fee.term_compensation_request_594", "专利权期限补偿请求费（594 号口径）",
                200, "CNY",
                "一、专利权人提出专利权期限补偿请求，应缴纳专利权期限补偿请求费，"
                "收费标准为每件 200 元",
                scopes=["check"], source=SRC_594, doc_no=DOC_594, note=note,
            ),
            _scalar(
                "check.fee.compensation_annuity_594", "专利权补偿期年费（594 号口径）",
                8000, "CNY/year",
                "一、……专利权补偿期年费，收费标准为每件每年 8000 元，不足一年部分不收取",
                scopes=["check"], source=SRC_594, doc_no=DOC_594, note=note,
            ),
            _scalar(
                "check.effective_from_594", "本公告日期", "2024-08-06", "date",
                "国家知识产权局 2024 年 8 月 6 日",
                scopes=["check"], source=SRC_594, doc_no=DOC_594, note=note,
            ),
        ],
    }


# --------------------------------------------------------------- 序列化

def dump_json(obj: Any) -> bytes:
    """确定性序列化：固定缩进、不排序 dict（显式构造顺序即语义顺序）、LF 结尾。"""
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def _collect_values(rulesets: List[dict]) -> List[Any]:
    values: List[Any] = []
    for rs in rulesets:
        for entry in rs["entries"]:
            if entry.get("kind") == "ladder":
                for tier in entry.get("ladder") or []:
                    values.append(tier.get("amount"))
                    values.append(tier.get("from_year"))
                    values.append(tier.get("to_year"))
            else:
                values.append(entry.get("value"))
    return values


def _banned_extra() -> Dict[str, List[Any]]:
    """补充禁用整数：费率表里 <100 但属政策数值的项（在豁免上界之下，须显式补录）。"""
    return {"extra_integers": [80, 50]}


def build_manifest(rulesets: List[dict], files: Dict[str, bytes]) -> dict:
    ints, decs = literals.collect_tokens(_collect_values(rulesets))
    extra = _banned_extra()
    for v in extra["extra_integers"]:
        ints.add(int(v))
    metas = []
    for rs in rulesets:
        fname = "%s.%s.json" % (rs["id"], rs["version"])
        counts = {"verified": 0, "pending": 0, "input_required": 0}
        for entry in rs["entries"]:
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        metas.append({
            "id": rs["id"],
            "version": rs["version"],
            "title": rs["title"],
            "doc_no": rs["doc_no"],
            "anchor_from": rs["anchor_from"],
            "anchor_to": rs["anchor_to"],
            "source": rs["source"],
            "file": fname,
            "sha256": hashlib.sha256(files[fname]).hexdigest(),
            "status_counts": counts,
        })
    return {
        "schema": "patfee.rules.manifest/v1",
        "generated_by": "tools/gen_rulesets.py",
        "generated_at": "1970-01-01T00:00:00Z",
        "retrieved": RETRIEVED,
        "rulesets": metas,
        "scopes": ["calc", "late", "reduction", "check"],
        "exemptions": literals.mirror_payload(),
        "banned_tokens": {
            "integers": sorted(ints),
            "decimals": sorted(decs),
            "extra_integers": extra["extra_integers"],
        },
        "benchmarks": {
            "b1_ladder": {"min_pass_rate": "1.0", "max_fail": 0, "max_seconds": "1.0"},
            "b2_late": {"min_pass_rate": "1.0", "max_fail": 0, "max_seconds": "1.0"},
            "b3_reduction": {"min_pass_rate": "1.0", "max_fail": 0, "max_seconds": "1.0"},
            "b4_portfolio": {"min_pass_rate": "1.0", "max_fail": 0, "max_seconds": "2.0"},
        },
        "notes": [
            "本目录为生成器冻结产物，禁手改；改体例走 tools/gen_rulesets.py 整目录重生成。",
            "M0：全部条目 status=pending（值可溯源但未逐项复核）——未核对不得进计算路径。",
        ],
    }


def generate() -> Dict[str, bytes]:
    rulesets = [
        build_fee_schedule(),
        build_reduction_78(),
        build_reduction_316(),
        build_reduction_594(),
    ]
    files: Dict[str, bytes] = {}
    for rs in rulesets:
        fname = "%s.%s.json" % (rs["id"], rs["version"])
        files[fname] = dump_json(rs)
    manifest = build_manifest(rulesets, files)
    files["manifest.json"] = dump_json(manifest)
    return files


def write_all(files: Dict[str, bytes]) -> None:
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (RULES_DIR / name).write_bytes(data)


def check(files: Dict[str, bytes]) -> int:
    """与磁盘逐字节比对。一致打印 FROZEN_RULESETS_OK 并返回 0。"""
    problems: List[str] = []
    for name, data in sorted(files.items()):
        path = RULES_DIR / name
        if not path.is_file():
            problems.append("缺少文件: %s" % name)
            continue
        on_disk = path.read_bytes()
        if on_disk != data:
            problems.append(
                "字节不一致: %s（磁盘 %d 字节 / 重生成 %d 字节，sha256 %s vs %s）"
                % (name, len(on_disk), len(data),
                   hashlib.sha256(on_disk).hexdigest()[:12],
                   hashlib.sha256(data).hexdigest()[:12])
            )
    extra = sorted(p.name for p in RULES_DIR.glob("*.json")) if RULES_DIR.is_dir() else []
    for name in extra:
        if name not in files:
            problems.append("白名单外多余文件: %s" % name)
    if problems:
        for p in problems:
            print("  FAIL %s" % p)
        return 1
    print("FROZEN_RULESETS_OK (%d 份文件逐字节一致)" % len(files))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="规则包生成器（data/rules/ 的唯一写入者）")
    parser.add_argument("--check", action="store_true", help="只比对不落盘，一致则打印 FROZEN_RULESETS_OK")
    args = parser.parse_args(argv)

    files = generate()
    if args.check:
        return check(files)
    write_all(files)
    print("已生成 %d 份规则文件 -> %s" % (len(files), RULES_DIR))
    for name in sorted(files):
        print("  %s  %d 字节" % (name, len(files[name])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
