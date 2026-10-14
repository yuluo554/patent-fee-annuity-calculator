"""规则包生成器 —— ``data/rules/`` 的**唯一写入者**。

纪律：

* 产物**禁手改**：改体例/加条目一律改本脚本后整目录重生成。
* **确定性落盘**：固定无时间戳、无 dict 迭代序依赖、无 ``random``；
  一律 ``write_bytes`` 写 LF，两次运行**逐字节一致**。
* ``--check``：重生成到内存 → 与磁盘逐字节比对 → 一致打印 ``FROZEN_RULESETS_OK``。
  这是"改完还自洽"的统一证据（比人肉判断硬）。
* 值一律挂 ``basis``（文号 / 条款 / URL / 抓取日期 / 复核痕迹）。**本脚本是规则值的
  唯一来源，因此不在零字面量门禁的扫描面内**（见 plan/06 D17）。

M1 状态口径（plan/06 D20 + M1 DoD）：32 条条目**逐项回到官方原文/费率表页复核后置
``status=verified``**，复核痕迹写进 ``basis.note``（含条目定位）。复核基准日 2026-10-14：

* 费率表 14 条带值条目 → 逐档回 ``cnipa_fee_schedule_286`` 解码页核对；
* ``late.grace_months`` / ``late.month_basis`` 两个【待核对】条目 → 依《专利法实施细则》
  （国务院令第 769 号，2024-01-20 施行）第 115 条 / 第 5 条落值（原先留空）；
* ``reduction_78`` 减缴项目 → 按现行费率表页「费减种类」栏口径定稿（78 号原文的
  "六年内"已被后续文件扩展，历史口径记入 note，现行口径挂费率表页依据）；
* ``reduction_316`` / ``reduction_594`` → 逐条回政策原文核对。
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
# M1 逐项复核日期（与抓取日同批）。复核结论写进 basis.note。
REVIEWED = "2026-10-14"

# 已直连获取的官方来源坐标
SRC_FEE_SCHEDULE = {
    "channel": "国家知识产权局专利业务办理系统 公示页",
    "url": "https://cponline.cnipa.gov.cn/GzfwYwblGlwhTMVC/GzfwYwblGlwhT/selectByNoticeId?weihuRid=286",
    "retrieved": RETRIEVED,
    "verification": "item_reviewed",
    "raw_snapshot": "data/knowledge/raw/cnipa_fee_schedule_286.html",
}
SRC_78 = {
    "channel": "财政部 财政文告（mof.gov.cn）",
    "url": "http://www.mof.gov.cn/gkml/caizhengwengao/wg2016/wg201609/201702/t20170209_2531813.htm",
    "retrieved": RETRIEVED,
    "verification": "item_reviewed",
    "raw_snapshot": "data/knowledge/raw/mof_2016_78.html",
}
SRC_316 = {
    "channel": "中国政府网 政策文件库（gov.cn）",
    "url": "https://www.gov.cn/zhengce/zhengceku/2019-12/09/content_5459661.htm",
    "retrieved": RETRIEVED,
    "verification": "item_reviewed",
    "raw_snapshot": "data/knowledge/raw/gov_316.html",
}
SRC_594 = {
    "channel": "中国政府网 政策文件库（gov.cn）",
    "url": "https://www.gov.cn/zhengce/zhengceku/202408/content_6967596.htm",
    "retrieved": RETRIEVED,
    "verification": "item_reviewed",
    "raw_snapshot": "data/knowledge/raw/gov_594.html",
}
# M1 新定位：《专利法实施细则》国务院令第 769 号（2024-01-20 施行）。
# 国务院公报版一页含《修改决定》全文与修订后细则全文（第 5 条 / 第 115 条所在）。
SRC_RULES_769 = {
    "channel": "国务院公报（gov.cn）",
    "url": "https://www.gov.cn/gongbao/2024/issue_11086/202401/content_6924971.html",
    "retrieved": RETRIEVED,
    "verification": "item_reviewed",
    "raw_snapshot": "data/knowledge/raw/gov_769_rules.html",
}

DOC_FEE_SCHEDULE = "国家知识产权局专利收费标准（专利业务办理系统公示）"
DOC_78 = "《专利收费减缴办法》财税〔2016〕78 号"
DOC_316 = "国家知识产权局公告第 316 号"
DOC_594 = "国家知识产权局公告第 594 号"
DOC_RULES_769 = "《中华人民共和国专利法实施细则》国务院令第 769 号"


def _review(locator: str, conclusion: str) -> str:
    """M1 复核痕迹（进 ``basis.note``）：条目定位 + 核对结论。"""
    return "M1 逐项复核（%s）：%s；%s" % (REVIEWED, locator, conclusion)


def _scalar(key: str, label: str, value: Any, unit: str, clause: str, scopes: List[str],
            status: str = "verified", source: Optional[dict] = None,
            doc_no: str = DOC_FEE_SCHEDULE, note: str = "",
            basis_note: str = "") -> dict:
    src = source or SRC_FEE_SCHEDULE
    basis = {
        "doc_no": doc_no,
        "clause": clause,
        "unit": unit,
        "url": src["url"],
        "retrieved": src["retrieved"],
        "channel": src["channel"],
        "note": basis_note,
    }
    return {
        "key": key,
        "label": label,
        "kind": "scalar",
        "status": status,
        "scopes": scopes,
        "value": value,
        "basis": basis,
        "note": note,
    }


def _ladder(key: str, label: str, tiers: List[dict], scopes: List[str],
            status: str = "verified", source: Optional[dict] = None,
            doc_no: str = DOC_FEE_SCHEDULE, clause: str = "", note: str = "",
            basis_note: str = "") -> dict:
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
            "note": basis_note,
        },
        "note": note,
    }


# --------------------------------------------------------------- 费率表

def build_fee_schedule() -> dict:
    """现行专利收费标准表（费率表版本 v2024，基准日 2026-10-14 直连获取）。

    全部数值逐项来自 `专利收费、集成电路布图设计收费标准` 公示页
    （国家知识产权局 2024 年 8 月 6 日发布，页面含 594 号新增项目）。
    M1 已逐项回到该页（URL 编码 HTML，解码后）核对并置 ``verified``。
    """
    verified_note = "M1 逐项复核已通过（基准日 %s）；复核痕迹见 basis.note" % REVIEWED
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
            note=verified_note,
            basis_note=_review(
                "费率表页「（七）年费 · 1.发明专利」",
                "6 个区间的端点（1-3/4-6/7-9/10-12/13-15/16-20）与金额"
                "（900/1200/2000/4000/6000/8000）逐档与页面文字一致，无缺档、无重叠",
            ),
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
            note=verified_note,
            basis_note=_review(
                "费率表页「（七）年费 · 2.实用新型专利」",
                "4 个区间的端点（1-3/4-5/6-8/9-10）与金额（600/900/1200/2000）逐档一致",
            ),
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
            note=verified_note,
            basis_note=_review(
                "费率表页「（七）年费 · 3.外观设计专利」",
                "5 个区间的端点（1-3/4-5/6-8/9-10/11-15）与金额（600/900/1200/2000/3000）"
                "逐档一致（第 11-15 年为外观设计独有档）",
            ),
        ),
        _scalar(
            "late.monthly_rate", "年费滞纳金月费率", "0.05", "ratio",
            "（八）年费滞纳金：每超过规定的缴费时间 1 个月，加收当年全额年费的 5%",
            scopes=["late"], note=verified_note,
            basis_note=_review(
                "费率表页「（八）年费滞纳金」",
                "原文『每超过规定的缴费时间1个月，加收当年全额年费的5%』与值 0.05（ratio）一致；"
                "并已与《专利法实施细则》第 115 条同款表述互证",
            ),
        ),
        _scalar(
            "late.grace_months", "滞纳金计收月数上限（进入失效流程口径）", 6, "month",
            "《专利法实施细则》第一百一十五条：专利权人未缴纳或者未缴足的，国务院专利行政部门"
            "应当通知专利权人自应当缴纳年费期满之日起 6 个月内补缴，同时缴纳滞纳金；"
            "期满未缴纳的，专利权自应当缴纳年费期满之日起终止",
            scopes=["late"], source=SRC_RULES_769, doc_no=DOC_RULES_769,
            note="M1 已定位《实施细则》原文落值（原【待核对】）；依据坐标见 basis",
            basis_note=_review(
                "《专利法实施细则》（国务院令第 769 号）第一百一十五条",
                "『自应当缴纳年费期满之日起 6 个月内补缴』→ 滞纳金计收月数上限 = 6；"
                "『期满未缴纳的，专利权自应当缴纳年费期满之日起终止』即进入失效流程的时点",
            ),
        ),
        _scalar(
            "late.month_basis", "滞纳金月数计算口径", "calendar_month", "enum",
            "《专利法实施细则》第五条：期限以年或者月计算的，以其最后一月的相应日为期限届满日；"
            "该月无相应日的，以该月最后一日为期限届满日",
            scopes=["late"], source=SRC_RULES_769, doc_no=DOC_RULES_769,
            note="M1 已依《实施细则》第 5 条定口径 = calendar_month（原【待核对】）；"
                 "代码不得写死该口径，运行时读本条目",
            basis_note=_review(
                "《专利法实施细则》（国务院令第 769 号）第五条 + 第一百一十五条",
                "第 5 条规定『期限以年或者月计算的，以其最后一月的相应日为期限届满日』→ `月` 为"
                "自然月（calendar_month），非三十日近似；故『每超过 1 个月』按自然月相应日推算。"
                "备选 thirty_day 口径因与第 5 条不符而弃用",
            ),
        ),
        _scalar(
            "check.fee.ruc", "恢复权利请求费", 1000, "CNY",
            "（九）恢复权利请求费 1000", scopes=["late", "check"], note=verified_note,
            basis_note=_review("费率表页「（九）恢复权利请求费」", "原文『1000』与条目值一致"),
        ),
        _scalar(
            "check.fee.evaluation_report", "专利权评价报告请求费", 2400, "CNY",
            "（十二）专利权评价报告请求费：1.实用新型专利 2400；2.外观设计专利 2400",
            scopes=["late", "check"], note=verified_note,
            basis_note=_review(
                "费率表页「（十二）专利权评价报告请求费」",
                "实用新型 2400 与外观设计 2400 两行均与条目值一致",
            ),
        ),
        _scalar(
            "check.fee.term_compensation_request", "专利权期限补偿请求费", 200, "CNY",
            "（十五）专利权期限补偿请求费（每件）200",
            scopes=["check"],
            note="与公告第 594 号第一条一致（每件 200 元）；" + verified_note,
            basis_note=_review(
                "费率表页「（十五）专利权期限补偿请求费（每件）」",
                "原文『200』与条目值一致；并与公告第 594 号『每件 200 元』互证",
            ),
        ),
        _scalar(
            "check.fee.compensation_annuity", "专利权补偿期年费", 8000, "CNY/year",
            "（十六）专利权补偿期年费（每年，不足一年部分不收取）8000",
            scopes=["check"], note=verified_note,
            basis_note=_review(
                "费率表页「（十六）专利权补偿期年费（每年，不足一年部分不收取）」",
                "原文『8000』与条目值一致；『不足一年部分不收取』口径同公告第 594 号",
            ),
        ),
        _scalar(
            "check.fee.application.invention", "发明专利申请费", 900, "CNY",
            "（一）申请费 · 1.发明专利 900", scopes=["check"], note=verified_note,
            basis_note=_review("费率表页「（一）申请费 · 1.发明专利」", "原文『900』与条目值一致"),
        ),
        _scalar(
            "check.fee.application.utility_model", "实用新型专利申请费", 500, "CNY",
            "（一）申请费 · 2.实用新型专利 500", scopes=["check"], note=verified_note,
            basis_note=_review("费率表页「（一）申请费 · 2.实用新型专利」", "原文『500』与条目值一致"),
        ),
        _scalar(
            "check.fee.application.design", "外观设计专利申请费", 500, "CNY",
            "（一）申请费 · 3.外观设计专利 500", scopes=["check"], note=verified_note,
            basis_note=_review("费率表页「（一）申请费 · 3.外观设计专利」", "原文『500』与条目值一致"),
        ),
        _scalar(
            "check.fee.substantive_examination", "发明专利申请实质审查费", 2500, "CNY",
            "（五）发明专利申请实质审查费 2500", scopes=["check"], note=verified_note,
            basis_note=_review("费率表页「（五）发明专利申请实质审查费」", "原文『2500』与条目值一致"),
        ),
        _scalar(
            "check.fee.priority_claim", "优先权要求费（每项）", 80, "CNY",
            "（四）优先权要求费（每项）80", scopes=["check"], note=verified_note,
            basis_note=_review("费率表页「（四）优先权要求费（每项）」", "原文『80』与条目值一致"),
        ),
        _scalar(
            "check.fee.publication_printing", "公布印刷费", 50, "CNY",
            "（三）公布印刷费 50", scopes=["check"], note=verified_note,
            basis_note=_review("费率表页「（三）公布印刷费」", "原文『50』与条目值一致"),
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
    """费减比例与减缴项目（财税〔2016〕78 号，自 2016-09-01 施行）。

    口径要点：比例取决于主体是否『共同』，与个人/单位无关（第四条原文）。
    """
    rate_note = "M1 逐项复核已通过（基准日 %s）；复核痕迹见 basis.note" % REVIEWED
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
                scopes=["reduction"], source=SRC_78, doc_no=DOC_78, note=rate_note,
                basis_note=_review(
                    "财税〔2016〕78 号第四条",
                    "原文『为个人或者单位的，减缴本办法第二条规定收费的85%』→ 值 0.85；"
                    "比例取决于主体是否『共同』，与个人/单位之分无关",
                ),
            ),
            _scalar(
                "reduction.rate.combined", "共同主体减缴比例", "0.70", "ratio",
                "第四条：两个或者两个以上的个人或者单位为共同专利申请人或者共有专利权人的，"
                "减缴本办法第二条规定收费的 70%",
                scopes=["reduction"], source=SRC_78, doc_no=DOC_78, note=rate_note,
                basis_note=_review(
                    "财税〔2016〕78 号第四条",
                    "原文『两个或者两个以上的个人或者单位为共同专利申请人或者共有专利权人的，"
                    "减缴本办法第二条规定收费的70%』→ 值 0.70",
                ),
            ),
            _scalar(
                "reduction.effective_from", "本办法施行日期", "2016-09-01", "date",
                "第十二条：本办法自 2016 年 9 月 1 日起施行",
                scopes=["reduction"], source=SRC_78, doc_no=DOC_78, note=rate_note,
                basis_note=_review(
                    "财税〔2016〕78 号第十二条",
                    "原文『本办法自2016年9月1日起施行』→ 锚点 2016-09-01；本规则包 anchor_from 同值",
                ),
            ),
            _scalar(
                "reduction.eligible_categories", "可减缴的收费种类",
                "申请费（不包括公布印刷费、申请附加费）、发明专利申请实质审查费、复审费、"
                "年费（自授予专利权当年起十年内的年费，专利开放实施许可期间的年费）、"
                "指定中国的单独指定费（第一期和第二期）",
                "text",
                "现行费率表页「费减种类」栏：申请费（不包括公布印刷费、申请附加费）、"
                "发明专利申请实质审查费、复审费、年费（自授予专利权当年起十年内的年费，"
                "专利开放实施许可期间的年费）、指定中国的单独指定费（第一期和第二期）",
                scopes=["reduction"], source=SRC_FEE_SCHEDULE, doc_no=DOC_FEE_SCHEDULE,
                note="M1 定稿：按**现行**费率表页「费减种类」栏口径落值（用于计算的必须是现行口径）；"
                     "历史沿革见 basis.note",
                basis_note=_review(
                    "现行费率表页「费减种类」栏（本次计算适用的现行口径）",
                    "页面原文与条目值逐字一致。历史沿革：财税〔2016〕78 号第二条原文为"
                    "『年费（自授予专利权当年起六年内的年费）』；现行口径已扩展为『十年内的年费』"
                    "并含『专利开放实施许可期间的年费』（费率表页自述收费依据含财税〔2018〕37 号）。"
                    "**注意**：财税〔2018〕37 号原文本次未获取（gov.cn 检索未命中）→ 该扩展的"
                    "一级依据留待取得原文后另立条目；本条目只承载**现行费率表页**所公示的口径",
                ),
            ),
        ],
    }


# ------------------------------------------------------ 公告第 316 号

def build_reduction_316() -> dict:
    """费减阈值调整（公告第 316 号，自 2019-07-01 起）。"""
    note = "M1 逐项复核已通过（基准日 %s）；复核痕迹见 basis.note" % REVIEWED
    prev_note = "【历史值】316 号前口径，供差异报告与 2019-07-01 前年度回算；" + note
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
                basis_note=_review(
                    "公告第 316 号第一条",
                    "原文『调整为上年度月均收入低于5000元（年6万元）的个人』→ 年阈值 60000",
                ),
            ),
            _scalar(
                "reduction.threshold.individual_monthly_income", "个人月均收入阈值",
                5000, "CNY/month",
                "一、……调整为上年度月均收入低于 5000 元（年 6 万元）的个人",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316, note=note,
                basis_note=_review(
                    "公告第 316 号第一条",
                    "原文『月均收入低于5000元』→ 月阈值 5000；判定为**严格小于**（恰好等于不满足）",
                ),
            ),
            _scalar(
                "reduction.threshold.entity_taxable_income", "企业应纳税所得额阈值",
                1000000, "CNY/year",
                "一、……由上年度企业应纳税所得额低于 30 万元的企业，"
                "调整为上年度企业应纳税所得额低于 100 万元的企业",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316, note=note,
                basis_note=_review(
                    "公告第 316 号第一条",
                    "原文『上年度企业应纳税所得额低于100万元的企业』→ 阈值 1000000",
                ),
            ),
            _scalar(
                "reduction.threshold.effective_from", "调整生效日期", "2019-07-01", "date",
                "……国家知识产权局将于 2019 年 7 月 1 日起调整专利收费减缴条件",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316, note=note,
                basis_note=_review(
                    "公告第 316 号正文（施行时点）",
                    "原文『将于2019年7月1日起调整专利收费减缴条件』→ 锚点 2019-07-01；"
                    "成文日期 2019 年 6 月 28 日，本规则包 anchor_from 取施行日",
                ),
            ),
            # 调整前的历史值：供 rules diff 输出差异报告，并支撑历史年度回算
            _scalar(
                "reduction.threshold.individual_annual_income.prev", "个人年收入阈值（316 号前）",
                42000, "CNY/year",
                "一、……由上年度月均收入低于 3500 元（年 4.2 万元）的个人",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316,
                note=prev_note,
                basis_note=_review(
                    "公告第 316 号第一条（调整前值）",
                    "原文『由上年度月均收入低于3500元（年4.2万元）的个人』→ 调整前年阈值 42000",
                ),
            ),
            _scalar(
                "reduction.threshold.individual_monthly_income.prev", "个人月均收入阈值（316 号前）",
                3500, "CNY/month",
                "一、……由上年度月均收入低于 3500 元（年 4.2 万元）的个人",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316,
                note=prev_note,
                basis_note=_review(
                    "公告第 316 号第一条（调整前值）",
                    "原文『月均收入低于3500元』→ 调整前月阈值 3500",
                ),
            ),
            _scalar(
                "reduction.threshold.entity_taxable_income.prev", "企业应纳税所得额阈值（316 号前）",
                300000, "CNY/year",
                "一、……由上年度企业应纳税所得额低于 30 万元的企业",
                scopes=["reduction"], source=SRC_316, doc_no=DOC_316,
                note=prev_note,
                basis_note=_review(
                    "公告第 316 号第一条（调整前值）",
                    "原文『由上年度企业应纳税所得额低于30万元的企业』→ 调整前阈值 300000",
                ),
            ),
        ],
    }


# ------------------------------------------------------ 公告第 594 号

def build_reduction_594() -> dict:
    """新增收费项目与减免（公告第 594 号，2024-08-06 成文）。"""
    note = "M1 逐项复核已通过（基准日 %s）；复核痕迹见 basis.note" % REVIEWED
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
                basis_note=_review(
                    "公告第 594 号第二条",
                    "原文『对专利开放许可实施期间的专利年费减免15%』→ 值 0.15",
                ),
            ),
            _scalar(
                "reduction.no_double_benefit", "多政策择一规则", "choose_most_favorable", "enum",
                "二、……同时适用其他专利收费减免政策的，可以选择适用最优惠的政策，但不得重复享受",
                scopes=["reduction"], source=SRC_594, doc_no=DOC_594,
                note="择最优惠且不叠加；判定过程必须在结果中留痕（候选集 + 选中项）；" + note,
                basis_note=_review(
                    "公告第 594 号第二条",
                    "原文『可以选择适用最优惠的政策，但不得重复享受』→ 枚举值 choose_most_favorable；"
                    "另与费率表页注『同时符合两项专利年费减缴条件的，按照其中减缴比例较高的一项"
                    "予以减缴』互证",
                ),
            ),
            _scalar(
                "check.fee.term_compensation_request_594", "专利权期限补偿请求费（594 号口径）",
                200, "CNY",
                "一、专利权人提出专利权期限补偿请求，应缴纳专利权期限补偿请求费，"
                "收费标准为每件 200 元",
                scopes=["check"], source=SRC_594, doc_no=DOC_594, note=note,
                basis_note=_review(
                    "公告第 594 号第一条",
                    "原文『收费标准为每件200元』→ 值 200；与费率表页（十五）互证",
                ),
            ),
            _scalar(
                "check.fee.compensation_annuity_594", "专利权补偿期年费（594 号口径）",
                8000, "CNY/year",
                "一、……专利权补偿期年费，收费标准为每件每年 8000 元，不足一年部分不收取",
                scopes=["check"], source=SRC_594, doc_no=DOC_594, note=note,
                basis_note=_review(
                    "公告第 594 号第一条",
                    "原文『收费标准为每件每年8000元，不足一年部分不收取』→ 值 8000；"
                    "与费率表页（十六）互证",
                ),
            ),
            _scalar(
                "check.effective_from_594", "本公告日期", "2024-08-06", "date",
                "国家知识产权局 2024 年 8 月 6 日",
                scopes=["check"], source=SRC_594, doc_no=DOC_594, note=note,
                basis_note=_review(
                    "公告第 594 号落款",
                    "gov.cn 页面成文日期『2024年08月06日』、落款『国家知识产权局 2024年8月6日』→ "
                    "锚点 2024-08-06；本规则包 anchor_from 同值",
                ),
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
    """补充禁用整数：费率表里 <100 但属政策数值的项（在豁免上界之下，须显式补录）。

    只补录**在源码里不会与日历/结构常数撞车**的政策值（80 = 优先权要求费、
    50 = 公布印刷费）。``late.grace_months`` 的 6 虽也有政策语义，但 6 与
    ``plan/06``、``PyInstaller 6``、``1[6-9]`` 一类结构/正则常数同形，
    按 plan/06 D18 的豁免口径（``abs(n) < 100`` = 日历/结构常数）不补录——
    补录会让门禁刷屏，反而被运维性忽略。
    """
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
        "reviewed": REVIEWED,
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
            "M1：32 条条目已逐项回到官方原文/费率表页复核，全部 status=verified；"
            "复核痕迹写在每条 basis.note（条目定位 + 核对结论）。",
            "late.grace_months / late.month_basis 的原文出自《专利法实施细则》国务院令第 769 号"
            "（第 115 条 / 第 5 条），故这两条的 basis 指向细则快照而非费率表页。",
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
