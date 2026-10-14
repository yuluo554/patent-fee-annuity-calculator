# HANDOFF-M1 —— 交接快照（M0 收尾 → M1 数据先行）

> **用法**：新对话用 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务`。
> **本文件状态**：M0 已完成，M1 待启动。M0 之前无更早 HANDOFF。
> **写入日期**：2026-10-14

---

## 一、当前进度（M0 已完成）

| 里程碑 | 状态 | 证据 |
|---|---|---|
| M0 计划 00–06 定稿 | ✅ | `plan/00`–`06` 六份齐备；`tests/test_repo_guards.py` 守门 |
| M0 可运行骨架 | ✅ | `src/patfee/`（分层：cli → pipeline → calc → rules → data） |
| 规则包建库（32 条目） | ✅ | `data/rules/` 4 份 ruleset + manifest；全部 `status=pending` |
| 阶梯引擎 | ✅ | `calc/annuity.py`；档位端点只来自规则包 |
| 门控（三态 + 分作用域） | ✅ | `rules/gate.py`；`verified`/`pending`/`input_required` |
| 零字面量门禁 + 阳性对照 | ✅ | `rules/literals_gate.py`；`selfcheck` 内跑 selftest |
| 基准 B1（规则驱动） | ✅ | 99/99 达标；B2–B4 显式"未实装" |
| 测试 | ✅ | **112 项**，py3.8 / py3.12 / 干净 venv 三处全绿，收集数一致 |
| CI workflow | ✅ | `.github/workflows/ci.yml` 三矩阵；**尚未推送，未跑过真 CI** |
| 官方依据快照 | ✅ | `data/knowledge/raw/` 4 份 + `_ledger.json`（sha256） |
| 本地等价校验 | ✅ | `.verify-out/M0-local-equivalence.txt` |

**M0 明确定不做的事**（防 scope 失控）：真实费率逐项复核（M1）、费减/滞纳金/组合引擎（M2/M3）、GUI 与打包（M5）、建远端仓库（M6）。

## 二、下一里程碑待办（M1 数据先行）

按优先级：

1. **逐项复核 `fee_schedule.v2024.json` 的 16 条条目** → 改 `status=verified`，复核痕迹写进 `basis.note`。
   底稿在 `data/knowledge/raw/cnipa_fee_schedule_286.html`（41,504 字节，URL 编码 HTML，
   需 `urllib.parse.unquote` 后解析）。**逐项**指：每个阶梯档、每个 scalar 都回到页面确认。
2. **逐项复核三份费减规则集**（`reduction_78` 4 条 / `reduction_316` 7 条 / `reduction_594` 5 条）→ `verified`。
3. **定位上位法**：《专利法》《实施细则》《审查指南》现行版本与施行日期 →
   填 `data/knowledge/clauses.json`（M0 未尝试定位）。
4. **补两个【待核对】条目**：`late.grace_months`（滞纳期月数上限）与 `late.month_basis`（月数计算口径）——
   依赖《实施细则》原文。**当前值为空 → 走 `missing_value` 拒绝，不会给出猜测值。**
5. **写 `tools/gen_synthetic.py`**：产合成组合与真值库到 `data/truth/`（自研确定性 RNG + 固定 seed + 无时间戳）。
6. **M1 收尾**：`patfee rules diff` 命令（316 号前后阈值、594 号新增项目差异报告）。

**M1 出口判据**：`verified` 计数 > 0 且每条挂 `basis`；`gen_rulesets.py --check` 位级一致；
真值库生成可复现（两次运行逐字节一致）。

## 三、既定口径清单（动了会打挂基准/测试 —— 改前先看这里）

| # | 口径 | 值 / 语义 | 相关决策 |
|---|---|---|---|
| K1 | 退出码四态 | `0` 达标 / `1` 降级完成或计算非法 / `2` 输入参数坐标错误 / `3` 缺可选依赖 | D36 |
| K2 | `--preview` 语义 | 允许 `pending` 参与计算，**退出码仍为 1**，绝不返回 0 | D11 |
| K3 | 门控三态 | `verified` 放行 / `pending` 拦门 / `input_required` 放行但运行时必索（≠静默取 0/1） | D9 |
| K4 | 门控作用域 | `calc` / `late` / `reduction` / `check` 各自校验引用到的条目；**不用"整包全 verified"当唯一门** | D10 |
| K5 | 减缴比例 | **取决于主体是否共同**：单主体 `0.85`、共同主体 `0.70`（**不是**"个人 85%/企业 70%"） | D5 |
| K6 | 费减阈值锚点 | `2019-07-01` 前：个人月均 3500/年 4.2 万、企业 30 万；之后：个人月均 5000/年 6 万、企业 100 万 | D6 |
| K7 | 594 号锚点 | `2024-08-06`：期限补偿请求费 200/件、补偿期年费 8000/年、开放许可减免 15%（择最优惠不叠加） | D7 |
| K8 | 阶梯区间语义 | **双闭** `[from_year, to_year]`，**恰好跳档年归新档**；端点只来自规则包，代码里不得出现 3/4/6/9 这类档位数字 | — |
| K9 | 金额类型 | 全链路 `Decimal`；JSON `parse_float=Decimal`；呈现两位 `ROUND_HALF_UP`；`__post_init__` 拒收 float | D4 |
| K10 | 零字面量门禁豁免 | 整数 `abs(n) < 100` = 日历/结构常数；小数 `0.01/0.1/0.5/1/2` = 精度约定。豁免表在 `rules/literals.py` **与 manifest 镜像**，两处必须同源（测试守） | D18 |
| K11 | 门禁扫描面 | `src/patfee/**/*.py`（含 docstring/注释）+ `tools/*.py`，**生成器 `gen_rulesets.py` / `gen_synthetic.py` 除外** | D17 |
| K12 | 门禁阳性对照 | `selfcheck` 必跑 selftest（注入 token 必报红）；**token 集为空即报配置错误** | D19 |
| K13 | 基准门槛 | 随 `manifest.json` 下发（**数据非代码**）；缺失即退出码 2，**不回落代码默认值** | D14 |
| K14 | 未实装套件 | 显式报"未实装"，**不参与达标判定**（"没测"≠"达标"≠"未达标"）；未知名走退出码 2 | D16 |
| K15 | M0 规则值口径 | 条目**带值但一律 `status=pending`**（值可溯源 ≠ 已复核）；确实未获取的才留 `null` | D20 |
| K16 | 基准与门控关系 | 基准**不受 `status` 门控**（它验的是引擎机制）；费率核对进度由 `selfcheck` 的 `verified` 计数单独报告 | D21 |
| K17 | 数据目录定位优先级 | 显式/环境变量 → 冻结态 `_MEIPASS/data` → exe 目录 → 仓库 `data/` → CWD 上溯 | D34 |
| K18 | 提示按冻结态分流 | 源码态说 `pip install -e ".[x]"`；冻结态说"本发行包未内嵌该功能" | D22 |
| K19 | "找不到" vs "找到了但坏" | 一律 `FileNotFoundError` vs `RulesetError`（两类语义不混，CLI 都转退出码 2 但要能区分） | — |

## 四、本机环境坑（只写 M0 实测过的）

1. **`py` vs `python`**：本机 `python` 是 WindowsApps 商店占位符，`py` 是 launcher。
   跑脚本一律 `py -3.12 -X utf8` 或 `py -3.8 -X utf8`；README 里 venv 段用 `python -m pip`
   （**`py -m pip` 会无视 venv 装到系统 Python**，已实测）。
2. **两条解释器通道可用**：`py -0p` → 3.8.8-64 与 3.12.10-64。
   - py3.8：pytest 8.3.5；py3.12：pytest 9.1.1、pyyaml 6.0.3、PyInstaller、PySide6 均已装。
   - 项目底线 3.8：**所有源码必须 3.8 兼容**（不用 3.9+ 语法）。已实测 112 项在 3.8 全绿。
3. **pip 走系统代理会挂**：需 `NO_PROXY="*" no_proxy="*" ... -i https://pypi.tuna.tsinghua.edu.cn/simple`。
4. **建 venv**：`py -3.12 -m venv .venv` 一次成功；`.venv/Scripts/python.exe -m pip install -U pip` 需加 NO_PROXY。
5. **编码**：本机 `-X utf8` 掩盖编码缺口。源码入口已加 `console.ensure_utf8_stdio()`（探针式，
   中文控制台不动）；`tools/` 下每个会打印的脚本同样调用，且**有测试守着**
   （`test_every_console_entry_has_utf8_guard`）——**新增工具脚本忘加守卫会被测出**。
6. **费率表 URL 已迁移**（M0 实测，重要）：
   旧地址 `https://cponline.cnipa.gov.cn/selectByNoticeId?weihuRid=286` → **HTTP 404**；
   现行地址多一段前缀 `GzfwYwblGlwhTMVC/GzfwYwblGlwhT/`。
   已同步 `tools/fetch_authorities.py` 与规则包 `basis.url`。再失效时走 cponline 首页
   逐个 `weihuRid` 探测（首页 HTML 内含全部候选链接）。
7. **管道吞退出码**：`cmd | tail` 的 `$?` 是 `tail` 的。验退出码必须单独跑，
   或用 `${PIPESTATUS[0]}`——M0 的验证脚本已按"单独跑"写。

## 五、M0 DoD 逐项 checklist

完整表见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §三。M0 结论：

- **M0-1 ~ M0-16、M0-18 ~ M0-20**：✅ 达成（证据见 §一 表与 `.verify-out/`）。
- **M0-17（本地等价校验）**：✅ 达成，但**必须按诚实口径表述**——
  本项目 M0 结束时**无远端、一次 CI 都没跑过**，故只写"**本地等价校验**"
  （py3.8 + py3.12 + 干净 venv 三处全绿），**不写"CI 绿"**。真 CI 结论待 M6 首推据实补记。

**偏差说明**：无。M0 范围内无未完成项。

## 六、关键命令速查

```bash
# 环境
py -0p                                        # 看有哪些解释器通道
py -3.12 -m venv .venv                        # 建 venv
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（三处都要绿，收集数必须一致 = 106）
py -3.12 -X utf8 -m pytest tests -q                      # PYTHONPATH=src
PYTHONPATH=src py -3.8 -X utf8 -m pytest tests -q
./.venv/Scripts/python.exe -m pytest tests -q

# 冻结与数据纪律
py -3.12 -X utf8 tools/gen_rulesets.py --check            # → FROZEN_RULESETS_OK
py -3.12 -X utf8 tools/fetch_authorities.py --verify      # → AUTHORITY_SNAPSHOTS_OK
py -3.12 -X utf8 tools/fetch_authorities.py               # 重新抓取并刷新 sha256 台账

# CLI 冒烟（退出码单独跑，不要接管道）
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli selfcheck
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli calc data/samples/patent-demo.json --preview
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli bench
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务
```

（入库文件内一律写相对路径 `plan/HANDOFF-M1.md`，绝对路径由用户在启动命令里拼——
否则每份 HANDOFF 的用法行都带本机盘符，发布期脱敏扫描必中。）
