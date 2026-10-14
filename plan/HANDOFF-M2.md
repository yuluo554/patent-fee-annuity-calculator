# HANDOFF-M2 —— 交接快照（M1 数据先行 → M2 计算引擎）

> **用法**：新对话用 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务`。
> **本文件状态**：M1 已完成，M2 待启动。更早交接见 [HANDOFF-M1.md](HANDOFF-M1.md)（含 K1–K19 既定口径与本机环境坑，仍然有效）。
> **写入日期**：2026-10-14

---

## 一、当前进度（M1 已完成）

| 里程碑 | 状态 | 证据 |
|---|---|---|
| M1 出口判据三项 | ✅ | ① `verified=32`（selfcheck 实测，每条挂 `basis`）；② `gen_rulesets.py --check` → `FROZEN_RULESETS_OK`；③ 真值库再生成逐字节一致（`gen_synthetic.py --check` → `SYNTHETIC_FROZEN_OK`） |
| 费率表逐项复核（16 条） | ✅ | 14 条带值条目逐档回费率表页解码核对；复核痕迹（条目定位+结论）在每条 `basis.note` |
| 三份费减规则集逐项复核（16 条） | ✅ | 78 号第四条/第十二条、316 号第一条、594 号第一/二条逐字核对；`reduction.eligible_categories` 按现行费率表页口径定稿 |
| 上位法定位 + 依据索引 | ✅ | `data/knowledge/clauses.json`：实施细则=国务院令 **769 号**（2024-01-20 施行，**5 条条款级结论** `clause_verified`）；专利法=**2020 第四次修正**（2021-06-01 施行，文书级）；审查指南=**局令 78 号**（2024-01-20 施行）+**84 号**（2026-01-01 施行，文书级） |
| `late.grace_months` / `late.month_basis` 落值 | ✅ | `6` / `calendar_month`（细则第 115 条 / 第 5 条，D40）；原先 null → missing_value 的路径已消除 |
| 合成组合与真值库 | ✅ | `data/truth/`（portfolio 18 件虚构专利 + truth 46 条算例 + manifest）；splitmix64 + 固定 seed；**两次运行逐字节一致** |
| `patfee rules diff` | ✅ | 316 号 3 组阈值前后对照；594 号新增条目 + 跨规则集同口径互证（594↔费率表）；未知 id exit 2 |
| 测试 | ✅ | **132 项**，py3.8 / py3.12 / 干净 venv 三处全绿，收集数一致（`.verify-out/M1-local-equivalence.txt`） |
| 官方原文快照 | ✅ | **8 份**（原 4 份 + 769 号细则、专利法 2020、指南 78/84 号令）；sha256 台账复抓一致 |
| CLI 退出码 | ✅ | `calc`(verified)=0、`calc --preview`=1、`rules diff` 未知 id=2、`calc` 缺文件=2（`.verify-out/M1-cli-exit-codes.txt`） |

**M1 明确不做的事**（防 scope 失控）：滞纳金/费减计算引擎（M2）、组合排期与报告（M3/M5）、基准 B2–B4 实装（M2/M3/M4）、专利法条款级正文与财税〔2018〕37 号原文（不阻断，见 plan/06 待核对项）。

## 二、下一里程碑待办（M2 计算引擎）

按优先级：

1. **`calc/late.py` 滞纳金引擎**：`surcharge = 全额年费 × 5% × 逾期月数` 逐月累加；
   月数口径**从规则包 `late.month_basis` 读**（现值 `calendar_month`，代码不得写死）；
   上限 `late.grace_months`（现值 6），超过 → `late_exceeds_cap`（**warning ≠ fail**，风险提示≠法律判定）；
   恢复权利请求费（`check.fee.ruc`）与评价报告费（`check.fee.evaluation_report`）按费率表条目计入。
2. **`calc/reduction.py` 费减判定**（plan/04 §五 已有详设）：
   - 主体构成：`n==1` 单主体 / `n>=2` 共同主体 → 比例 `0.85`/`0.70`（从 `reduction_78` 读，**代码内不得出现这两个数**）；
   - 资格：**严格小于**阈值（恰好等于不合格）；共同主体须**逐个**都合格；
   - 按年度锚点选阈值：`as_of_year` 对应 316 号（2019-07-01）前后两套（`.prev` 条目供历史回算）；
   - 多政策择一（594 号）：候选集 {费减, 开放许可 15%} 取减免额最大者，`candidates[]`+`chosen` 全留痕，`no_double_benefit`；
   - 门控 scope=`reduction`。
3. **基准 B2/B3 实装**（`benchmark/suites.py` 注册函数已在）：两层 = 真值库对账（读 `data/truth/`）+ 规则驱动端点枚举；各配探活（可证伪）测试；门槛仍从 manifest 读。
4. **CLI `patfee reduction <主体.json>`** 子命令（plan/03 §八）+ `calc --with-late`。
5. **B4 留 M3**（组合排期），M2 不做。

**M2 出口判据**（plan/05 里程碑表）：B1/B2/B3 全达标；算例回归 100%（truth 库 46 条全对上）；阶梯/滞纳金/费减均走门控（scope 隔离测试）。

## 三、M1 新增的既定口径（接 M1 的 K1–K19，动了会打挂测试）

| # | 口径 | 值 / 语义 |
|---|---|---|
| K20 | 滞纳金上限 | `late.grace_months=6`（细则第 115 条）；超上限 → `late_exceeds_cap` warning，**不是** fail |
| K21 | 滞纳金月数口径 | `late.month_basis=calendar_month`（细则第 5 条自然月）；引擎从规则包读，**禁止写死** |
| K22 | 复核痕迹字段 | `basis.note` 以 "M1 逐项复核（…）" 开头 + 条目定位 + 结论；守门测试 `test_m1_all_entries_verified_with_review_trace` |
| K23 | 真值库冻结 | `data/truth/` 由 `gen_synthetic.py --check` 守位级一致（`SYNTHETIC_FROZEN_OK`）；号段 `99…SYN`/`90000000…SYN` 守门 |
| K24 | 快照台账 file 字段 | `_ledger.json` 每条有 `file`（快照可能是 .html 或 .json）；守门测试回落兼容 |
| K25 | 真值边界语义 | 恰好等于阈值 → 不合格（严格小于）；`6` 个月不超限、`7` 个月超限；多政策择**实缴最小**者 |
| K26 | 上位法登记纪律 | 条款级结论只在原文全文在手时登记（`clause_verified`）；核不到显式留痕，不填猜测值（D42） |

## 四、M1 新增本机环境坑（接 M1 HANDOFF §四，只写实测过的）

1. **flk.npc.gov.cn 接口**（M1 实测）：
   - 检索：`POST /law-search/search/list`，JSON 体 `{'searchContent':…,'searchRange':1,'sxrq':[],'gbrq':[],'sxx':[],'searchType':1,'pageNum':1,'pageSize':30}`，GET 一律 405/返回 SPA 壳；
   - 详情：`GET /law-search/search/flfgDetails?bbbs=<id>`（需 `Referer: https://flk.npc.gov.cn/`）；
   - **详情接口只返回元数据+章节目录树，无条款正文**；download/pc 与 hitDisplay 均不可用（M1 实测）。
2. **gov.cn 政策库检索接口**：`https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary&q=<URL编码>&sort=pubtime&sortType=1&searchfield=title&p=1&n=10`，JSON 的 `searchVO.catMap.<类目>.listVO`；`t=gongbao` 查国务院公报。空结果时 `searchVO` 可能为 None（要防 `None.get`）。
3. **官方快照稳定性**：gov.cn 公报页与 cponline 页两次抓取 sha256 一致（M1 实测），可直接入台账；flk 的 JSON 详情接口同样稳定。
4. **README 计数守门**：`test_readme_selfcheck_file_count_matches_reality` 锁门禁扫描文件数（现为 **20**）、`tests/`（**132** 项）等计数随代码漂移会被测出——新增源码/工具脚本后同步 README。
5. **`patfee rules diff` 挂进 `rules_sub`**：argparse 子命令组 `p_rules` 下；`rules` 无子命令时仍 exit 2（`p_rules.set_defaults(func=None)` 不能丢）。

## 五、M1 DoD 逐项 checklist

完整表见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §三之三。M1 结论：**M1-1 ~ M1-7 全部达成，无未完成项**。

**偏差说明（3 条，均已在 plan/06 留痕）**：
1. 《专利法》只完成文书级定位（flk 无条款正文）→ 不登记条款级结论；
2. 《审查指南》只完成文书级定位（78 号令基准 + 84 号令修改，与费减口径无关）；
3. 财税〔2018〕37 号原文未获取 → 减缴项目按现行费率表页口径承载，扩展依据留痕（D43）。

## 六、关键命令速查

```bash
# 环境
py -0p                                        # 看有哪些解释器通道
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（三处都要绿，收集数必须一致 = 132）
py -3.12 -X utf8 -m pytest tests -q                      # PYTHONPATH=src
PYTHONPATH=src py -3.8 -X utf8 -m pytest tests -q
./.venv/Scripts/python.exe -m pytest tests -q

# 冻结与数据纪律
py -3.12 -X utf8 tools/gen_rulesets.py --check            # → FROZEN_RULESETS_OK
py -3.12 -X utf8 tools/gen_synthetic.py --check           # → SYNTHETIC_FROZEN_OK
py -3.12 -X utf8 tools/fetch_authorities.py --verify      # → AUTHORITY_SNAPSHOTS_OK（8 份）
py -3.12 -X utf8 tools/fetch_authorities.py               # 重新抓取并刷新 sha256 台账

# CLI 冒烟（退出码单独跑，不要接管道）
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli selfcheck
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli calc data/samples/patent-demo.json          # verified → exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli calc data/samples/patent-demo.json --preview # 仍 exit 1
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli rules diff reduction_316
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli rules diff reduction_594
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli bench
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务
```

（入库文件内一律写相对路径 `plan/HANDOFF-M2.md`，绝对路径由用户在启动命令里拼。）
