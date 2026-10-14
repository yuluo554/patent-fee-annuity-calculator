# HANDOFF-M3 —— 交接快照（M2 计算引擎 → M3 组合排期与对账）

> **用法**：新对话用 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务`。
> **本文件状态**：M2 已完成，M3 待启动。更早交接见 [HANDOFF-M2.md](HANDOFF-M2.md)（含 K1–K26 既定口径与本机环境坑，仍然有效）。
> **写入日期**：2026-10-14

---

## 一、当前进度（M2 已完成）

| 里程碑出口判据 | 状态 | 证据 |
|---|---|---|
| `calc/late.py` 滞纳金引擎 | ✅ | 逐月累加 `全额×费率×月数`；`month_basis`/`grace_months`/`monthly_rate` 全部从规则包读（代码零写死，K20/K21）；超上限 → `late_exceeds_cap` warning（金额照算，不置 None）；恢复权利请求费/评价报告费按费率表条目列出（`related_fees`，不计入应缴合计） |
| `calc/reduction.py` 费减判定 | ✅ | 资格=**严格小于**阈值（个人"月均**或**年收入"任一低于即可）；共同主体逐个合格；比例取 `reduction.rate.sole/combined`（代码零写死）；按 `as_of_year` 对 316 号锚点（`reduction.threshold.effective_from`）取现行/`.prev` 阈值；多政策择一=**实缴最小**、`candidates[]`+`chosen` 全留痕、`no_double_benefit` 文本从规则包读 |
| 算例回归 100% | ✅ | truth 库 46 条全对上：late 4 条 + reduction 12 条由引擎重算逐字段对账（B2/B3 真值层 + `test_m2_engines.py`），annuity 30 条沿用 B1/M1 守门 |
| 阶梯/滞纳金/费减均走门控 | ✅ | late/reduction 引擎各经自己 scope 门控 + 年费基数另经 calc scope；**scope 隔离测试**：reduction 条目 pending 不连坐 calc 路径（`test_scope_isolation_pending_reduction_does_not_block_calc`） |
| 基准 B2/B3 实装（两层） | ✅ | 第一层=truth 库对账（真值不可得时显式留 note 不冒充分母）；第二层=规则驱动（费率/阈值边界枚举 + 月数口径零头语义）；**探活可证伪**：注入费率×2 → B2 必红；阈值+1 元 → B3 必红；真值算例数计入 total（防分母做小） |
| CLI 扩展 | ✅ | `patfee reduction <主体.json>`（不合格=有效结论 exit 0；未判定才 1）；`patfee calc --with-late`（缺 due_on/paid_on 时滞纳金"未判定"降级呈现、年费结论不受影响；超上限 exit 1） |
| 测试 | ✅ | **166 项**，py3.8 / py3.12 / 干净 venv 三处全绿，收集数一致 |
| 冻结与快照 | ✅ | `FROZEN_RULESETS_OK` / `SYNTHETIC_FROZEN_OK` / `AUTHORITY_SNAPSHOTS_OK`（8 份）全部复核通过 |
| CLI 退出码 | ✅ | calc=0 / calc --preview=1 / calc --with-late(超上限)=1 / reduction=0 / bench=0 / 缺文件=2 / bench 未知套件=2（实测） |
| 样例输入 | ✅ | `data/samples/patent-late-demo.json`、`data/samples/applicants-demo.json`（README 守门要求命令引用的输入真实存在） |

**M2 明确不做的事**：B4 组合排期（M3）、报告导出与证据链（M3/M5）、GUI（M5）、财税〔2018〕37 号原文获取（不阻断，见 plan/06 D43）。

## 二、下一里程碑待办（M3 组合排期与对账）

按 plan/04 §六详设 + plan/05 M3 条目：

1. **`calc/portfolio.py` 组合批量排期**：输入 `--in <目录/*.json>` 或清单文件（每件 = 合成组合条目：主体 + 专利 + 缴费记录）；
   - **失败隔离**：单件异常 → `{"id":…, "kind":"failed", "reason":"bad_format"}` 继续，**失败件不改变退出码**（退出码由"是否检出问题"决定）；
   - **到期预警**：按 `due_date - today` 升序输出"未来 N 个月内到期清单"。
2. **跨轮对账三集合**：`new_due` / `settled` / `still_unpaid`；辅助集 `content_changed` / `vanished`；配对主键 = **稳定身份键 `patent_no`**（不是内容指纹），内容指纹变化另立标记。**口径单一实现源**：`benchmark/cases.py` 的 `compare_rounds()` 供 CLI 与基准共用（plan/04 §六）。
3. **基准 B4 实装**：合成组合（`data/truth/portfolio.json` 18 件）植入真值全量重算对账；truth manifest 的 `controls.clean` / `controls.degrade` 是应零命中/应降级对照集，**基准层只读该声明**（生成器已备）；探活测试照旧。门槛从 manifest `benchmarks.b4_portfolio` 读（已下发：max_seconds=2.0）。
4. **CLI `patfee scan <目录> --out <目录>`**（plan/03 §八）+ 报告/证据链若排 M3（§四见下）。
5. **报告与证据链（plan/04 §七，M3/M5 切分待定）**：`report_sections(result)` 单一渲染源（Markdown/XLSX 同源）；报告四块（输入事实/参数来源块/逐项 steps 直render/**未启用章节显式写出**）；无外链硬断言；产物 sha256 + 逐字节可复现（zip 时间戳固定）。**若 M3 只做排期对账，此项整体顺延 M5，但"未启用章节显式写出"的纪律从 M3 的 scan 输出就要开始守。**

**M3 出口判据**（plan/05 里程碑表）：B1–B4 全达标；组合批量排期 + 到期预警 + 跨轮对账可用；失败隔离与退出码语义有测试守门。

## 三、M2 新增的既定口径（接 K1–K26，动了会打挂测试）

| # | 口径 | 值 / 语义 |
|---|---|---|
| K27 | 滞纳金月数折算 | `calendar_month` = 整自然月计数：自 due_on 逐次自然月推进（月末日不足取月末，细则第 5 条），**不超过 paid_on 的次数即月数，零头不计**。注意边界：1-31 → 8-01 仍是 6 整月（第 7 个整月要到 8-31"相应日"）——B2 月数口径用例锁死 |
| K28 | 超上限仍出金额 | 逾期 > grace → `late_exceeds_cap` 进 `reasons` + warning 文案，`surcharge` 照算不为 None；退出码 1；`payable` = 年费+滞纳金，**不含** `related_fees` |
| K29 | 费减资格"或"语义 | 个人合格 = 月均**或**年收入任一严格低于阈值（生成器 `_applicant_eligible` 同款）；恰好等于 → 不合格 |
| K30 | 费减年度锚定粒度 | 按 `as_of_year` 与锚点**年份**整数比较（`< 锚点年` → `.prev`），同年内不细分月日 —— 与真值库生成器 `_thresholds_for` 同款口径 |
| K31 | `reduction_rate` 语义 | 结果里始终是**费减比例**（sole/combined 条目值，eligible 时），即使 `chosen` 是开放许可（15%）—— 真值库 `multi_policy.*` 锁定 |
| K32 | 多政策择一基准 | `chosen` = candidates 中 **amount（实缴）最小**者；`no_double_benefit_applied` = `len(candidates) > 1`；不合格且无开放许可时 `candidates=[]`、`payable=None` |
| K33 | reduction 退出码 | 不合格=有效结论 exit 0；未判定（门控拒绝/规则缺失）=1；输入坏=2。与 calc 的"warning→1"不同：费减无 warning 通道 |
| K34 | `--with-late` 缺日期 | 输入无 due_on/paid_on 时滞纳金块"未判定"+`bad_format`，**年费结论不受影响**（整体退出码取决于年费块） |
| K35 | 基准两层分母纪律 | B2/B3 的 total = 真值算例数 + 规则驱动枚举数；真值库不可得 → 显式 note 不冒充分母；测试断言 `total >= 真值算例数` |

## 四、M2 实现要点（给 M3 的地图）

- **引擎落位**：`src/patfee/calc/late.py`（`LateRequest`/`compute_late`/`overdue_months_between`/`add_calendar_months`/`_related_fees`）、`src/patfee/calc/reduction.py`（`ReductionRequest`/`compute_reduction`/`thresholds_for_year`/`parse_applicants`/`applicant_eligible`）。输入解析/校验一律 UsageError（exit 2 语义）。
- **领域模型**：`domain/models.py` 新增 `LateResult`/`ReductionResult`/`RelatedFee`/`PolicyCandidate`（全部 Decimal 拒 float、`as_dict()` 确定性序列化）。
- **编排层**：`calc/pipeline.py` 新增 `LateRequest`/`ReductionRequest`（CLI 面向的 dataclass）、`build_late_request`/`build_reduction_request`、`compute_full_late`/`compute_full_reduction`、`late_lines`/`reduction_lines`、`late_exit_code_for`/`reduction_exit_code_for`。GUI（M5）只准消费这些公开函数。
- **CLI**：`cmd_reduction` 与 `cmd_calc --with-late`；`--with-late` 的滞纳金块在 JSON 输出里挂 `payload["late"]`。`reduction` 已进 `needs_library` 名单。
- **基准**：`benchmark/suites.py` 的 `suite_b2_late`/`suite_b3_reduction`；真值装载 `_load_truth_cases`（沿 `library.data_dir` 上溯找 `data/truth`）；B4 实装时复用 `_find_truth_dir`/`_load_truth_cases` 与 `CheckResult`。
- **测试**：`tests/test_m2_engines.py`（22 项：引擎语义/门控隔离/基准探活）；`test_cli_exit_codes.py` 追加 reduction/--with-late 退出码块；`test_benchmark.py` 的未实装断言改为只盯 b4_portfolio。

## 五、M2 过程中的决策留痕（已在代码注释，无需重核）

1. **门禁教训**：`late.py` 初版写了防御常数 `1200`（循环上限），被零字面量门禁命中——整月推进严格递增必然终止，守卫已删。**新代码里任何 ≥100 的整数都会被门禁拦**（含 docstring），日期/边界数一律走规则包或豁免表。
2. **B2 月数口径期望值修正**：`1-31 → 8-01` 应为 6 整月而非 7（细则第 5 条"相应日"语义），首版期望写错由引擎对账暴露——**这正是"规则驱动层期望不经引擎产出"的价值**。
3. **真值库 `effective_from` 是字符串条目**（`2019-07-01`），`entry.decimal()` 返回 None，须用 `_required_text` —— M3 读日期类条目时注意。
4. README 计数守门两处：门禁扫描文件数（现 **22**）与测试数（现 **166**）会随代码漂移，新增源码/测试后同步。

## 六、关键命令速查

```bash
# 环境
py -0p                                        # 看有哪些解释器通道
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（三处都要绿，收集数必须一致 = 166）
PYTHONPATH=src py -3.12 -X utf8 -m pytest tests -q
PYTHONPATH=src py -3.8 -X utf8 -m pytest tests -q
./.venv/Scripts/python.exe -m pytest tests -q

# 冻结与数据纪律
py -3.12 -X utf8 tools/gen_rulesets.py --check            # → FROZEN_RULESETS_OK
py -3.12 -X utf8 tools/gen_synthetic.py --check           # → SYNTHETIC_FROZEN_OK
py -3.12 -X utf8 tools/fetch_authorities.py --verify      # → AUTHORITY_SNAPSHOTS_OK（8 份）

# CLI 冒烟（退出码单独跑，不要接管道）
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli selfcheck
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli calc data/samples/patent-demo.json                 # exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli calc data/samples/patent-late-demo.json --with-late # 年费+滞纳金 exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli calc data/samples/patent-late-demo.json --with-late --json
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli reduction data/samples/applicants-demo.json        # exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli bench                                             # B1/B2/B3 达标、B4 未实装
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli rules diff reduction_316
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务
```

（入库文件内一律写相对路径 `plan/HANDOFF-M3.md`，绝对路径由用户在启动命令里拼。）
