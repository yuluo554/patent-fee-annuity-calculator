# M6 干净环境逐条跑通 README（2026-10-14）
环境：git clone 本仓到全新目录 tmp-m6-clean（无 .venv/build/dist 残留），python -m venv 全新 3.12.10，按 README §快速开始安装 .[dev] 后逐条执行。

## 阶段一：按 README 原文安装 .[dev]（3.12.10 全新 venv）→ 成功

== patfee version ==
patfee 0.1.0
frozen=no
ruleset fee_schedule@v2024 (专利收费标准表) verified=16 pending=0 input_required=0
ruleset reduction_316@v2019 (调整专利收费减缴条件（阈值）) verified=7 pending=0 input_required=0
ruleset reduction_594@v2024 (调整部分专利收费标准和减缴政策（新增项目与减免）) verified=5 pending=0 input_required=0
ruleset reduction_78@v2016 (专利收费减缴办法（减缴比例与减缴项目）) verified=4 pending=0 input_required=0
exit=0

== patfee selfcheck ==
== patfee selfcheck ==
数据目录: <clean-clone>/data
冻结态: 否
作用域: calc, late, reduction, check
规则集:
  - fee_schedule@v2024 专利收费标准表: 条目 16（verified=16 pending=0 input_required=0）
  - reduction_316@v2019 调整专利收费减缴条件（阈值）: 条目 7（verified=7 pending=0 input_required=0）
  - reduction_594@v2024 调整部分专利收费标准和减缴政策（新增项目与减免）: 条目 5（verified=5 pending=0 input_required=0）
  - reduction_78@v2016 专利收费减缴办法（减缴比例与减缴项目）: 条目 4（verified=4 pending=0 input_required=0）
合计: verified=32 pending=0 input_required=0
零字面量门禁: 扫描 31 文件, 硬门命中 0, 行内放行 0, selftest=通过
可选依赖 [report] openpyxl: 不可用 — python -m pip install -e ".[report]"
可选依赖 [gui] PySide6: 不可用 — python -m pip install -e ".[gui]"
可选依赖 [build] PyInstaller: 不可用 — python -m pip install -e ".[build]"
exit=0

== patfee rules list ==
规则集清单（按 依据文件 × 版本 组织）:
  fee_schedule@v2024  专利收费标准表
      文号: 国家知识产权局专利收费标准（专利业务办理系统公示）
      锚点: 2024-08-06 ~ （现行）
      条目: 16（verified=16 pending=0 input_required=0）
  reduction_316@v2019  调整专利收费减缴条件（阈值）
      文号: 国家知识产权局公告第 316 号
      锚点: 2019-07-01 ~ （现行）
      条目: 7（verified=7 pending=0 input_required=0）
  reduction_594@v2024  调整部分专利收费标准和减缴政策（新增项目与减免）
      文号: 国家知识产权局公告第 594 号
      锚点: 2024-08-06 ~ （现行）
      条目: 5（verified=5 pending=0 input_required=0）
  reduction_78@v2016  专利收费减缴办法（减缴比例与减缴项目）
      文号: 《专利收费减缴办法》财税〔2016〕78 号
      锚点: 2016-09-01 ~ （现行）
      条目: 4（verified=4 pending=0 input_required=0）
exit=0
== patfee rules show fee_schedule ==
规则集 fee_schedule@v2024  专利收费标准表
文号: 国家知识产权局专利收费标准（专利业务办理系统公示）
来源: https://cponline.cnipa.gov.cn/GzfwYwblGlwhTMVC/GzfwYwblGlwhT/selectByNoticeId?weihuRid=286
抓取: 2026-10-14 核验: item_reviewed
  [verified] annuity.design  外观设计专利年费阶梯
        第 1-3 年: 600 元
        第 4-5 年: 900 元
        第 6-8 年: 1200 元
        第 9-10 年: 2000 元
        第 11-15 年: 3000 元
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （七）年费 · 3.外观设计专利：1-3 年 600；4-5 年 900；6-8 年 1200；9-10 年 2000；11-15 年 3000
  [verified] annuity.invention  发明专利年费阶梯
        第 1-3 年: 900 元
        第 4-6 年: 1200 元
        第 7-9 年: 2000 元
        第 10-12 年: 4000 元
        第 13-15 年: 6000 元
        第 16-20 年: 8000 元
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （七）年费 · 1.发明专利：1-3 年（每年）900；4-6 年 1200；7-9 年 2000；10-12 年 4000；13-15 年 6000；16-20 年 8000
  [verified] annuity.utility_model  实用新型专利年费阶梯
        第 1-3 年: 600 元
        第 4-5 年: 900 元
        第 6-8 年: 1200 元
        第 9-10 年: 2000 元
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （七）年费 · 2.实用新型专利：1-3 年 600；4-5 年 900；6-8 年 1200；9-10 年 2000
  [verified] check.fee.application.design  外观设计专利申请费
        值: 500 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （一）申请费 · 3.外观设计专利 500
  [verified] check.fee.application.invention  发明专利申请费
        值: 900 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （一）申请费 · 1.发明专利 900
  [verified] check.fee.application.utility_model  实用新型专利申请费
        值: 500 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （一）申请费 · 2.实用新型专利 500
  [verified] check.fee.compensation_annuity  专利权补偿期年费
        值: 8000 CNY/year
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （十六）专利权补偿期年费（每年，不足一年部分不收取）8000
  [verified] check.fee.evaluation_report  专利权评价报告请求费
        值: 2400 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （十二）专利权评价报告请求费：1.实用新型专利 2400；2.外观设计专利 2400
  [verified] check.fee.priority_claim  优先权要求费（每项）
        值: 80 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （四）优先权要求费（每项）80
  [verified] check.fee.publication_printing  公布印刷费
        值: 50 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （三）公布印刷费 50
  [verified] check.fee.ruc  恢复权利请求费
        值: 1000 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （九）恢复权利请求费 1000
  [verified] check.fee.substantive_examination  发明专利申请实质审查费
        值: 2500 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （五）发明专利申请实质审查费 2500
  [verified] check.fee.term_compensation_request  专利权期限补偿请求费
        值: 200 CNY
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （十五）专利权期限补偿请求费（每件）200
  [verified] late.grace_months  滞纳金计收月数上限（进入失效流程口径）
        值: 6 month
        依据: 《中华人民共和国专利法实施细则》国务院令第 769 号 · 《专利法实施细则》第一百一十五条：专利权人未缴纳或者未缴足的，国务院专利行政部门应当通知专利权人自应当缴纳年费期满之日起 6 个月内补缴，同时缴纳滞纳金；期满未缴纳的，专利权自应当缴纳年费期满之日起终止
  [verified] late.month_basis  滞纳金月数计算口径
        值: calendar_month enum
        依据: 《中华人民共和国专利法实施细则》国务院令第 769 号 · 《专利法实施细则》第五条：期限以年或者月计算的，以其最后一月的相应日为期限届满日；该月无相应日的，以该月最后一日为期限届满日
  [verified] late.monthly_rate  年费滞纳金月费率
        值: 0.05 ratio
        依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · （八）年费滞纳金：每超过规定的缴费时间 1 个月，加收当年全额年费的 5%
合计: verified=16 pending=0 input_required=0
exit=0

== patfee calc data/samples/patent-demo.json --preview ==
== 年费测算 ==
专利类型: invention
缴费年度: 第 5 年
应缴年费: 1200.00 元
所处区间: 第 4-6 年
费率依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · 第 4-6 年
依据坐标: fee_schedule@v2024#annuity.invention
  - 专利类型=invention
  - 缴费年度=第 5 年
  - 命中区间=第 4-6 年（第 4-6 年）
  - 区间年费=1200
  - 结果=1200.00

本输出为基于官方费率表与政策文本的费用测算，不构成法律或代理意见；正式缴费金额以国家知识产权局规定与缴费通知为准。
注意: --preview 仅用于预览口径，不得作为缴费依据。
exit=1

== patfee calc data/samples/patent-late-demo.json --with-late ==
== 年费测算 ==
专利类型: invention
缴费年度: 第 5 年
应缴年费: 1200.00 元
所处区间: 第 4-6 年
费率依据: 国家知识产权局专利收费标准（专利业务办理系统公示） · 第 4-6 年
依据坐标: fee_schedule@v2024#annuity.invention
  - 专利类型=invention
  - 缴费年度=第 5 年
  - 命中区间=第 4-6 年（第 4-6 年）
  - 区间年费=1200
  - 结果=1200.00

本输出为基于官方费率表与政策文本的费用测算，不构成法律或代理意见；正式缴费金额以国家知识产权局规定与缴费通知为准。

== 滞纳金测算 ==
专利类型: invention
缴费年度: 第 5 年
规定缴费期限: 2020-05-04
实际缴费日: 2020-07-04
逾期月数: 2 个月（口径 calendar_month）
年费全额: 1200.00 元
滞纳金费率: 0.05 / 月
滞纳金: 120.00 元
应缴合计（年费+滞纳金）: 1320.00 元
补缴上限: 6 个月
关联费用: 恢复权利请求费 1000 元（按费率表条目，另行缴纳）
关联费用: 专利权评价报告请求费 2400 元（按费率表条目，另行缴纳）
  - 逾期区间: 2020-05-04 ~ 2020-07-04
  - 年费全额: 1200.00 元（第 5 年）
  - 滞纳金费率=0.05/月（规则包 late.monthly_rate）
  - 补缴上限=6 个月（规则包 late.grace_months）
  - 月数口径=calendar_month（规则包 late.month_basis）
  - 口径=calendar_month：自 2020-05-04 整自然月推进至 2020-07-04，共 2 个整月（零头不计）
  - 滞纳金=1200.00 × 0.05 × 2 = 120.00 元
  - 应缴合计（年费+滞纳金）=1320.00 元
  - 关联费用 恢复权利请求费: 1000 元（按费率表条目，另行缴纳）
  - 关联费用 专利权评价报告请求费: 2400 元（按费率表条目，另行缴纳）

本输出为基于官方费率表与政策文本的费用测算，不构成法律或代理意见；正式缴费金额以国家知识产权局规定与缴费通知为准。
exit=0

== patfee reduction data/samples/applicants-demo.json ==
== 费减资格判定 ==
专利类型: invention
缴费年度: 第 5 年
适用年度: 2026
主体构成: 1 人（单主体）
资格结论: 合格
阈值 entity_taxable_income: 1000000
阈值 individual_annual_income: 60000
阈值 individual_monthly_income: 5000
阈值锚点: 国家知识产权局公告第 316 号（自 2019-07-01 起）
年费全额: 1200.00 元
候选政策: 费减（减免比例 0.85 → 实缴 180.00 元）
选中政策: 费减（不叠加，no_double_benefit=choose_most_favorable）
减免后应缴: 180.00 元
费减比例: 0.85
  - 主体构成: 1 人（单主体）
  - 适用年度: 2026（阈值按 316 号锚点前后取版本）
  - 门控: reduction scope 放行
  - 阈值（现行 口径）: 个人月均<5000 或 年收入<60000；单位应纳税所得额<1000000
  - 主体[0] 示例个人 A（合成）: 合格
  - 年费全额: 1200.00 元（第 5 年）
  - 候选政策: 费减(费率0.85→实缴180.00)
  - 选中: 费减（实缴 180.00 元；不叠加）

本输出为基于官方费率表与政策文本的费用测算，不构成法律或代理意见；正式缴费金额以国家知识产权局规定与缴费通知为准。
exit=0
== patfee scan data/samples/portfolio-demo.json ==
== 组合批量排期 ==
基准日: 2026-10-14
件数合计: 7（失败隔离 1）
已缴清: 2 件
已到期未缴清: 2 件
尚未到期: 2 件
失败件（单列，不改变退出码语义）:
  - item[6]: bad_format
未来 3 个月内到期清单（按剩余天数升序）:
  - 990000000005SYN  第 2 年  2026-10-20 到期（还有 6 天）  应缴年费 600.00 元
  - 990000000004SYN  第 3 年  2026-11-15 到期（还有 32 天）  应缴年费 900.00 元
已到期未缴清: 990000000003SYN 第 3 年（2018-10-09 到期）
已到期未缴清: 990000000006SYN 第 2 年（2018-07-08 到期）
== 跨轮对账（配对主键 patent_no）==
新增到期: #y5, 990000000004SYN#y3, 990000000005SYN#y2, 990000000006SYN#y2
已缴清: 990000000001SYN#y3, 990000000002SYN#y2
持续未缴: 990000000003SYN#y3
本输出为基于官方费率表与政策文本的费用测算，不构成法律或代理意见；正式缴费金额以国家知识产权局规定与缴费通知为准。
== 未启用章节（没查 ≠ 查了没问题）==
  - 本次组合排期未启用逐件滞纳金测算（对已逾期件用 `patfee calc <件.json> --with-late` 启用）
  - 本次组合排期未启用费减资格判定（对单件用 `patfee reduction <主体.json>` 启用）
exit=1

== patfee scan ... --out 报告目录（md）==
== 组合批量排期 ==
基准日: 2026-10-14
件数合计: 7（失败隔离 1）
已缴清: 2 件
已到期未缴清: 2 件
尚未到期: 2 件
失败件（单列，不改变退出码语义）:
  - item[6]: bad_format
未来 3 个月内到期清单（按剩余天数升序）:
  - 990000000005SYN  第 2 年  2026-10-20 到期（还有 6 天）  应缴年费 600.00 元
  - 990000000004SYN  第 3 年  2026-11-15 到期（还有 32 天）  应缴年费 900.00 元
已到期未缴清: 990000000003SYN 第 3 年（2018-10-09 到期）
已到期未缴清: 990000000006SYN 第 2 年（2018-07-08 到期）
== 跨轮对账（配对主键 patent_no）==
新增到期: #y5, 990000000004SYN#y3, 990000000005SYN#y2, 990000000006SYN#y2
已缴清: 990000000001SYN#y3, 990000000002SYN#y2
持续未缴: 990000000003SYN#y3
本输出为基于官方费率表与政策文本的费用测算，不构成法律或代理意见；正式缴费金额以国家知识产权局规定与缴费通知为准。
== 未启用章节（没查 ≠ 查了没问题）==
  - 本次组合排期未启用逐件滞纳金测算（对已逾期件用 `patfee calc <件.json> --with-late` 启用）
  - 本次组合排期未启用费减资格判定（对单件用 `patfee reduction <主体.json>` 启用）
报告已写出: .verify-out\scan-demo\scan-report.md
证据已写出: .verify-out\scan-demo\evidence.json（含报告 sha256 指纹）
exit=1

== patfee bench ==
  b1_ladder      通过 99/99  达标率=1.0000  耗时=0.001s
      注: annuity.design_intl 未在规则包中建条目（该类用例未生成）
  b2_late        通过 18/18  达标率=1.0000  耗时=0.003s
  b3_reduction   通过 20/20  达标率=1.0000  耗时=0.003s
  b4_portfolio   通过 48/48  达标率=1.0000  耗时=0.009s
  判定: b1_ladder=达标, b2_late=达标, b3_reduction=达标, b4_portfolio=达标
exit=0

== patfee gui（缺 PySide6 → 预期 exit 3）==
桌面界面需要可选依赖 PySide6。
python -m pip install -e ".[gui]"
（原始错误: No module named 'PySide6'）
exit=3

== patfee --selftest 自检结果.json（源码态）==
自检结果已写出: .verify-out/自检结果.json
{
  "checks": [
    {
      "detail": "<clean-clone>\\data",
      "name": "data_dir_found",
      "ok": true
    },
    {
      "detail": "within=None",
      "name": "data_dir_within_exe",
      "ok": true
    },
    {
      "detail": "verified=32",
      "name": "rules_loaded",
      "ok": true
    },
    {
      "detail": "amount=900.00",
      "name": "calc_pipeline",
      "ok": true
    },
    {
      "detail": "b1_ladder=达标; b2_late=达标; b3_reduction=达标; b4_portfolio=达标",
      "name": "benchmark_suites",
      "ok": true
    },
    {
      "detail": "PySide6 未内嵌（CLI-only 包），跳过",
      "name": "gui_offscreen_smoke",
      "ok": true
    }
  ],
  "frozen": false,
  "ok": true
}

exit=0

## 阶段二结论（逐条可跑核对）
| 命令 | 退出码 | 判定 |
|---|---|---|
| python -m venv + pip install -e ".[dev]" | 0 | 安装成功 |
| patfee version | 0 | ✅ |
| patfee selfcheck | 0 | ✅ |
| patfee rules list | 0 | ✅ |
| patfee rules show fee_schedule | 0 | ✅ |
| patfee calc patent-demo.json --preview | 1 | ✅ 预览语义（README 明示） |
| patfee calc patent-late-demo.json --with-late | 0 | ✅ |
| patfee reduction applicants-demo.json | 0 | ✅ |
| patfee scan portfolio-demo.json | 1 | ✅ 检出问题语义（README 明示） |
| patfee scan ... --out 报告目录 | 1 | ✅ 报告落盘 scan-demo/ |
| patfee bench | 0 | ✅ |
| patfee gui（干净 venv 缺 PySide6） | 3 | ✅ 缺依赖提示（README 明示 exit 3） |
| patfee --selftest 自检结果.json | 0 | ✅ 源码态自检 |

## 阶段三：发现缺口 —— 测试面与安装面不一致
干净 venv 只装 .[dev] 时：tests/test_m5_report.py 3 条 XLSX 测试**硬失败**
（openpyxl 缺席 → scan --format xlsx 静默无产物）。补装 .[report] 后：215 passed, 11 skipped（226 收集数一致；11 skip = GUI 交互测试 importorskip，按设计）。

处置（M6 实测结论）：README 快速开始与 CI test job 安装面统一改为 .[dev,report]；
gui 交互测试按既有设计 importorskip（AST 门禁三条不依赖 PySide6，CI 照跑）。
