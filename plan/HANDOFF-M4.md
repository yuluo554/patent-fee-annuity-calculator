# HANDOFF-M4 —— 交接快照（M3 组合排期与对账 → M4 基准收尾）

> **用法**：新对话用 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务`。
> **本文件状态**：M3 已完成，M4 待启动。更早交接见 [HANDOFF-M3.md](HANDOFF-M3.md)（含 K1–K35 既定口径与本机环境坑，仍然有效）。
> **写入日期**：2026-10-14

---

## 一、当前进度（M3 已完成）

| 里程碑出口判据 | 状态 | 证据 |
|---|---|---|
| `calc/portfolio.py` 组合批量排期 | ✅ | 单件分类 settled/unpaid/not_due（含失败隔离 failed）；金额随排期输出（阶梯引擎，Decimal）；`today` 显式注入（引擎内禁取系统时钟，可复现） |
| 失败隔离与退出码语义 | ✅ | 坏格式/缺 patent_no/类型不识别 → `kind=failed`+`bad_format` 单列，整批继续；**失败件不改变退出码**——退出码由"是否检出问题"决定（未缴清/未判定/窗口内到期/失败件→1；全清→0）；三态断言 + CLI 实测锁进测试 |
| 到期预警 | ✅ | 按 `due_on - today` 升序输出未来 N 个月内清单；N 由输入 `window_months` 或 `--window-months` 覆盖（窗口上界 = N×31 天，结构参数非政策值） |
| 跨轮对账三集合 | ✅ | `compare_rounds()` 单一实现源（CLI 与基准共用）：`new_due`/`settled`/`still_unpaid` + 辅助集 `content_changed`/`vanished`；配对主键 = `patent_no`（D13）；期限变化 → content_changed 不退化成新增+移除；`paid_on` 变化**不**误报 content_changed（缴清与否由 settled/still_unpaid 承载） |
| 基准 B4 实装（三层） | ✅ | ① 18 件组合缴费记录全量重算，金额**锚定冻结真值**（`truth.json` 年金算例的 tier_from/tier_to→amount，防"期望与引擎读同一份被改规则包"）；② 失败隔离断言（3 种坏件）；③ controls 对照集只读 truth manifest 声明（clean 件零命中=settled、degrade 件照算+超上限降级）；④ 对账口径锁定（settled 配对 + 期限漂移→content_changed） |
| B4 探活可证伪 | ✅ | `test_b4_detects_amount_defect`：阶梯金额 +1 元注入 → B4 必红。**教训**：首版期望值读现行规则包（与引擎同源）时探活失效——期望必须锚定冻结真值 |
| CLI `patfee scan` | ✅ | `scan <组合.json> [--out <目录>] [--window-months N] [--preview] [--json]`；`--out` 落盘 `scan-report.md`（四块：输入事实/逐项结论/未启用章节/依据与免责）+ `evidence.json`（报告 sha256 指纹实测对账）；**未启用章节显式写出**（"没查≠查了没问题"）；**无外链**（报告正文禁 URL，有测试） |
| 算例/组合回归 100% | ✅ | B1 99/99、B2 18/18、B3 20/20、B4 46/46，四套件全达标（`bench` exit 0） |
| 测试 | ✅ | **191 项**（M2 166 + M3 25），py3.8 / py3.12 / 干净 venv 三处全绿，收集数一致 |
| 冻结与快照 | ✅ | `FROZEN_RULESETS_OK` / `SYNTHETIC_FROZEN_OK` / `AUTHORITY_SNAPSHOTS_OK`（8 份）全部复核通过 |
| README 计数守门 | ✅ | 门禁扫描文件数同步为 **23**（新增 `calc/portfolio.py`）；测试数同步为 **191** |

**M3 明确不做的事**：XLSX 双格式报告与逐字节可复现导出（M5，见 plan/05 §三之四偏差说明 1）；GUI（M5）；财税〔2018〕37 号原文获取（不阻断）。

## 二、下一里程碑待办（M4 基准收尾）

按 plan/05 §二 M4 行 + §五之二：

1. **基准指标固化**：`patfee bench` 四套件指标（B1 99/99、B2 18/18、B3 20/20、B4 46/46）复核后固化进 README 评测基准表；`max_seconds` 门槛（manifest 下发）实测计时核对（B4=2.0s，当前实测远低于此）。
2. **探活矩阵补全**：B4 目前 1 条缺陷注入（金额 +1 元）；可补 controls 对照失效注入（如把 degrade 件置成 clean 期望）与 vanished 误判注入。B1 已有 2 条（空洞/重叠）、B2/B3 各 1 条。
3. **`--only` 部分运行语义复核**：`bench --only b4_portfolio` 不误判未测套件（已有 `test_bench_only_partial_runs_do_not_judge_untested`，确认覆盖 B4 场景即可）。
4. **指标进 README**（M4 出口判据）：评测基准表更新实测数字；若 manifest 门槛变动只改数据不改代码。
5. **M4 DoD 落盘**：plan/05 加 §三之五 M4 DoD 表（纪律同 M0–M3：真实执行留证据才打勾）。

**M4 出口判据**（plan/05 里程碑表）：门槛随 manifest 下发；每套件探活可证伪；指标进 README。

## 三、M3 新增的既定口径（接 K1–K35，动了会打挂测试）

| # | 口径 | 值 / 语义 |
|---|---|---|
| K36 | scan 退出码 | 由"是否检出问题"决定：`unpaid` ∨ `uncomputed` ∨ `due_soon` ∨ `failed` → 1；全清 → 0；`--preview` 恒 1。**失败件计入"检出"但不放大严重度**（plan/03 §七：失败件不改变退出码语义） |
| K37 | 失败件原因码 | 统一 `bad_format`（缺 patent_no / 类型不识别 / 日期非法 / 载荷缺失 / 年度非法同码）；失败件与正常件同列表留痕 + `failed` 汇总 |
| K38 | 到期窗口语义 | `due_soon` = `not_due` 且 `0 <= days_until_due <= N×31`（N=window_months，31 为月长上界结构常数）；窗口外 not_due 不进清单不报警 |
| K39 | 对账配对与指纹 | 配对主键 = `patent_no`（同号多件按 `(year, due_on)` 排序逐位配对）；`content_fingerprint` 只含 `patent_no/year/due_on` —— **不含 `paid_on`**（缴清与否由集合承载）；期限/年度变化 → `content_changed`，同时仍参与 settled/still_unpaid 判定 |
| K40 | `today` 注入 | 引擎（`scan_portfolio`）必收显式 `today`；CLI 输入缺 `today` 字段时回退**当日**（真实台账语义）；合成样例显式给 `today: 2026-10-14` |
| K41 | B4 期望锚定 | B4 第一层金额期望**只读 truth.json 冻结值**（按 tier_from/tier_to 配档），不读现行规则包——探活可证伪的前提；B2/B3 的规则驱动层读现行规则包是另一层语义（端点枚举），两者不混 |
| K42 | scan 报告纪律 | Markdown 四块齐（缺一有测试）；`evidence.json` 携带报告 sha256；报告正文无 URL（无外链纪律自 M3 起守）；未启用章节显式写出（M5 才实装的能力也按此格式声明） |

## 四、M3 实现要点（给 M4 的地图）

- **引擎落位**：`src/patfee/calc/portfolio.py`（`PortfolioRequest`/`PortfolioEntry`/`PortfolioResult`/`build_portfolio_entry`/`scan_portfolio`/`compare_rounds`/`content_fingerprint`/`parse_portfolio_input`；kind 常量 `KIND_*`）。
- **编排层**：`calc/pipeline.py` 新增 `PortfolioRequest`（含 `rounds` 字段携带两轮台账）/`build_portfolio_request`/`compute_full_portfolio`（免责声明经 `_portfolio_with_disclaimer` 挂接）/`portfolio_exit_code_for`/`portfolio_rounds`/`portfolio_lines`。顺手清理了 M2 遗留的 `reduction_lines` 尾部死代码（缩进错误的不可达块）。
- **CLI**：`cmd_scan` + `_scan_not_enabled_sections`/`_scan_not_enabled_lines`/`_write_scan_report`（`--out` 落盘 MD + evidence.json）；`scan` 已进 `needs_library` 名单。
- **基准**：`benchmark/suites.py` 的 `suite_b4_portfolio`（复用 `_find_truth_dir` + 新增 `_load_truth_doc`/`_load_truth_portfolio`）；`_B4_WINDOW_MONTHS = 3` 模块常量。
- **样例**：`data/samples/portfolio-demo.json`（baseline 3 件 + current 7 件，含 1 件坏格式演示；`today`/`window_months` 显式）——README 守门要求命令引用的输入真实存在。
- **测试**：`tests/test_m3_portfolio.py`（25 项：分类/失败隔离/退出码三态/预警排序/对账五集合/指纹/pipeline/CLI scan/报告落盘/无外链/B4 探活）；`test_benchmark.py` 与 `test_m2_engines.py` 的"B4 未实装"断言已反转为"全实装"。

## 五、M3 过程中的决策留痕（已在代码注释，无需重核）

1. **B4 探活教训**：期望值不能与引擎同源（都读现行规则包）——注入缺陷后两边一起变，永远绿。B4 第一层期望改锚定 truth.json 冻结值后探活才生效（K41）。这与 B2 首版月数期望写错被对账暴露是同一纪律的两面：**期望要有独立来源**。
2. **`content_fingerprint` 剔除 `paid_on`**：首版含 paid_on 导致"这轮缴清了"同时报 content_changed + settled——缴清是集合语义不是内容漂移（K39）。
3. **`pipeline.py` 死代码**：M2 遗留一段缩进在 `reduction_lines` 里的退出码逻辑（不可达），M3 重构时清理；`exit_code_for`/`late_exit_code_for`/`result_lines` 现各只有一份定义。
4. README 计数守门两处：门禁扫描文件数（现 **23**）与测试数（现 **191**）会随代码漂移，新增源码/测试后同步。
5. `window_months` 的 CLI 覆盖实现是在 `cmd_scan` 里把 `--window-months` 写回 payload 再走 `build_portfolio_request`——引擎与编排层不认识 argparse。

## 六、关键命令速查

```bash
# 环境
py -0p                                        # 看有哪些解释器通道
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（三处都要绿，收集数必须一致 = 191）
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
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli reduction data/samples/applicants-demo.json        # exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli scan data/samples/portfolio-demo.json              # 检出问题 exit 1
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli scan data/samples/portfolio-demo.json --out .verify-out/scan-demo
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli bench                                             # B1–B4 全达标 exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli rules diff reduction_316
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务
```

（入库文件内一律写相对路径 `plan/HANDOFF-M4.md`，绝对路径由用户在启动命令里拼。）
