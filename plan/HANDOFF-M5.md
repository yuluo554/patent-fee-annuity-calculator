# HANDOFF-M5 —— 交接快照（M4 基准收尾 → M5 桌面交付）

> **用法**：新对话用 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务`。
> **本文件状态**：M4 已完成（commit `8f96dd9`），M5 待启动。更早交接见 [HANDOFF-M4.md](HANDOFF-M4.md)（含 K1–K42 既定口径与本机环境坑，仍然有效）。
> **写入日期**：2026-10-14

---

## 一、当前进度（M4 已完成）

| 里程碑出口判据（plan/05 §二 M4 行） | 状态 | 证据 |
|---|---|---|
| 门槛随 manifest 下发 | ✅ | `min_pass_rate` / `max_fail` / `max_seconds` 三项**全部实际执行**（M4 前 `max_seconds` 只下发未执行，M4 实装为真实判定）；超时判未达标并在判定文案给原因；门槛缺失报配置错误 exit 2 |
| 每套件探活可证伪 | ✅ | 探活矩阵 **9 条**：B1 空洞/重叠、B2 费率翻倍、B3 阈值抬高、B4 金额篡改 + controls 失效注入（grace 6→7 打穿 degrade 对照）+ 对账漏报 vanished 注入、计时门槛桩计时注入超时×2；B4 第三层补 vanished/new_due 语义断言（46→**48** 条） |
| 指标进 README | ✅ | 评测基准表固化为实测快照：B1 99/99·0.001s、B2 18/18·0.002s、B3 20/20·0.003s、B4 48/48·0.008s（实测耗时列 + manifest 门槛列）；`--json` 输出 `elapsed_seconds` |

**M4 其他交付**：`bench` 人类可读输出带耗时；`--only b4_portfolio` 部分运行语义实测复核（exit 0，只判定点名套件）；测试 **196 项**（191 + 5）三解释器全绿（py3.8 / py3.12 / 干净 venv，收集数一致）；冻结三项 OK；零字面量门禁 23 文件 0 命中；DoD 表落盘 plan/05 §三之五（M4-1~M4-6 无偏差）；证据 `.verify-out/M4-local-equivalence.txt`。

**M4 明确不做的事**（顺延 M5）：XLSX 双格式报告与逐字节可复现导出（M3 偏差说明 1）；GUI；技术报告。

## 二、下一里程碑待办（M5 桌面交付）

按 plan/05 §二 M5 行：

1. **PySide6 桌面界面**：`patfee gui` 子命令已有 exit 3 骨架（`cmd_gui` 惰性导入 + `dependency_hint`）；GUI **必须走编排层 `calc.pipeline`（唯一编排源），不绕过直接调引擎**；GUI AST 门禁三条齐上（plan/05 M5 行：具体清单见 plan/03/04 GUI 节，动手前先核对）。
2. **PyInstaller 打包**：exe `--selftest` 冻结态断言通过；数据目录内嵌（`is_frozen()` 路径已有分支）；extras `build`；**老解释器风险**：PySide6 在 py3.8 侧 extras 写上下界 `<6.7`（plan/05 §五），干净环境先验证再写代码。
3. **报告导出**：XLSX 双格式（openpyxl，extras `report`，惰性导入）+ 逐字节可复现导出；scan 报告"未启用章节显式写出 + 无外链"两条纪律延续（K42），"没查≠查了没问题"的声明格式照 M3 的 Markdown 版。
4. **技术报告**（题目交付物之一，plan/00/01 有要求）。
5. **三方对账测试**（M5 行出口判据；M3 的 `compare_rounds` 与 B4 对账口径是基础）。

**M5 出口判据**（plan/05 里程碑表）：GUI AST 门禁三条齐上；exe `--selftest` 冻结态断言通过；三方对账测试。

## 三、M4 新增的既定口径（接 K1–K42，动了会打挂测试）

| # | 口径 | 值 / 语义 |
|---|---|---|
| K43 | 计时门槛实际执行 | manifest `max_seconds` 从"下发未执行"变为 `run_suites` 实测计时并判定；每套件运行即计时（`CheckResult.elapsed_seconds`，3 位小数 Decimal，`--json` 字段 `elapsed_seconds`）；超时 → `未达标（耗时 Xs > max_seconds Ys）`；未实装套件不计时不判定（"没测"不参与达标语义） |
| K44 | B4 断言数 48 | 第三层（对账口径）新增 vanished / new_due 语义断言 → `suite_b4_portfolio` 48/48（历史快照 46/46 见 M3 DoD 与 README 归档）；**探活前提 = 有独立期望 + 有断言可打红** |
| K45 | 探活矩阵 9 条 | B1×2 / B2×1 / B3×1 / B4×3（金额 / controls / 对账）/ 计时×2（判定函数直接喂超时结果 + 桩 `perf_counter` 注入后撤桩复验）；探活库构造函数 `_probe_library()`（tests/test_m3_portfolio.py，复制现行条目置 verified，manifest benchmarks 留空） |
| K46 | 指标快照与实时判定分离 | README 评测基准表的耗时是**实测快照**（写死数字随环境漂移，仅展示）；门槛判定用每次运行实时值——两者语义不同，勿把 README 数字当门槛 |

## 四、M5 实现要点（地图与落位）

- **GUI 入口**：`src/patfee/cli.py` 的 `cmd_gui`（惰性导入 try 包住"import 到调用完成"整段，缺依赖 exit 3，未实装 exit 2）——M5 把 `main_window.main()` 变成真实现，落位 `src/patfee/gui/`。
- **编排层**：`calc/pipeline.py` 的 `compute_full_calculation` / `compute_full_reduction` / `compute_full_portfolio` 已带免责声明与行输出——GUI 取数走这三个，**不要绕过 pipeline 直接调 `calc.annuity/late/reduction/portfolio`**（README 分层图的约定）。
- **计时门槛**：`benchmark/suites.py` 的 `_threshold_problems(res, threshold)`（独立函数）+ `run_suites` 内 `time.perf_counter` 计时；CLI 展示在 `cmd_bench`。
- **报告纪律**：`cmd_scan` 的 `_scan_not_enabled_sections` / `_write_scan_report`（Markdown 四块 + evidence.json sha256）——XLSX 版照此对等，M5 出口判据"两格式内容对等"。
- **测试落位**：门槛与指标测试在 `tests/test_benchmark.py` 末段（`# M4：计时门槛与指标固化` 节）；B4 探活在 `tests/test_m3_portfolio.py`。

## 五、M4 过程中的决策留痕（已在代码注释，无需重核）

1. **`max_seconds` 之前是摆设**：HANDOFF-M4 原文写"实测计时核对"，复核发现 manifest 已下发但 `run_suites` 只判定 `min_pass_rate`/`max_fail`——M4 把它实装为真实判定（"门槛随 manifest 下发"若不执行就只是文档声明）。教训：**交接文档写的"已下发"≠"已生效"，接手时先验证**。
2. **计时门槛的可证伪方式**：不与真实计时竞态（注入慢代码脆弱）——`_threshold_problems` 独立成函数直接喂超时结果，另加一条桩 `perf_counter` 走完整 `run_suites` 的端到端探活（撤桩后复验全达标，防桩残留假红）。
3. **B4 46→48**：给对账口径补 vanished/new_due 断言是探活的前提——没有断言，"漏报 vanished"注入就探不出（与 K41"期望与实现同源"同一教训）。
4. **README 计数守门**：守门测试只锁门禁扫描文件数（现 23）；测试数靠手动同步 README 两处（目录树注释 +「开发」节，现 196）。
5. **交接文件纪律**：每里程碑完成时**新建**下一里程碑的 HANDOFF-*.md，上一份原文保留（本文件即此惯例产物）——不要原地改写上一份。

## 六、关键命令速查

```bash
# 环境
py -0p                                        # 看有哪些解释器通道
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（三处都要绿，收集数必须一致 = 196）
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
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli bench                                             # B1–B4 全达标（含计时门槛）exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli bench --only b4_portfolio                          # 单套件 exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli gui                                                # 缺 PySide6 → exit 3
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli rules diff reduction_316
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务
```

（入库文件内一律写相对路径 `plan/HANDOFF-M5.md`，绝对路径由用户在启动命令里拼。）
