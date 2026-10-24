# RELEASE-v0.2.0 — 发布面回填：`selfcheck` 复核锚 + `requires-python` 抬到 3.12

> 上一版：`v0.1.0`（2026-10-14）。
> 触发来源：轨 I（发布物一致性）I-1 —— `v0.1.0` 之后 `src/` 有 **2 个文件 / +50 行**的改动
> （`selfcheck` 新增复核锚判定 + CLI 渲染），**从未随任何 tag 发布过**。

## 一、相对 v0.1.0 改了什么

| 类别 | 内容 | 用户能否感知 |
|---|---|---|
`src/patfee/calc/pipeline.py` | 新增 `review_status(manifest, today=None)`（+42 行）：读出 `review_interval` / `reviewed` / `next_review` 并与今天比一次，给出 `overdue` / `days_overdue` / `note`；`selfcheck()` 的返回结构新增 `review` 键 | **能（机读）**：`--selftest` 的 JSON 多一个 `review` 段 |
`src/patfee/cli.py` | `cmd_selfcheck` 打印复核锚一行；逾期时追加 `⚠ …（逾期只提示，不改退出码）` | **能**：`selfcheck` 多 1–2 行 |
`requires-python` | `>=3.8` → **`>=3.12`** | **能（破坏性）**：3.8–3.11 装不上 |
`build-system` | `setuptools>=61` → **`>=77`**（PEP 639） | 构建期 |

**没有改**：费率表 32 条数值（全部仍 `verified`）、年费阶梯、滞纳金口径、费减判定、
组合排期与对账、基准 B1–B4 门槛、退出码语义（0/1/2/3）、CLI 子命令与旗标、XLSX 可复现配方。

**`today` 可注入**：`review_status(manifest, today=...)` 让冻结态自检不用系统时钟做判定
（本仓既有纪律：时间不是判定输入）。

## 二、为什么版本号是 0.2.0

`requires-python` 由 3.8 抬到 3.12 是**不兼容变更** → 0.x 阶段走 minor。
另外 `--selftest` 的 JSON 输出新增 `review` 键（严格 schema 消费方会感知）。

## 三、验证

| 项 | 命令 | 结果 |
|---|---|---|
| 全量测试 | `.venv/Scripts/python.exe -m pytest -q` | **229 passed**（= README 的 229 项） |
| HEAD 的 CI | `commits/e83ed40/check-runs` | 发布前 `e83ed40` 全 `success` |
| CLI exe `--version` | `dist/patfee-cli/patfee-cli.exe --version` | `patfee 0.2.0` |
| CLI exe `--selftest` | `dist/patfee-cli/patfee-cli.exe --selftest <out.json>` | exit 0，`ok=true` `frozen=true`，六项全 `ok` |
| GUI exe `--selftest` | `dist/patfee-gui/patfee-gui.exe --selftest <out.json>` | exit 0，六项全 `ok`（含 GUI offscreen 冒烟） |

CLI 冻结态六项（实测原文）：

```
data_dir_found      True  ...\dist\patfee-cli\_internal\data
data_dir_within_exe True  within=True
rules_loaded        True  verified=32
calc_pipeline       True  amount=900.00
benchmark_suites    True  b1_ladder=达标; b2_late=达标; b3_reduction=达标; b4_portfolio=达标
gui_offscreen_smoke True  PySide6 未内嵌（CLI-only 包），跳过
```

## 四、附件与三方对撞

两个附件各自三方一致（本地构建 / 二次打包逐字节 / GitHub asset digest / Release 正文）：

| 附件 | 字节 | sha256 |
|---|---|---|
`patfee-v0.2.0-windows-x64-cli.zip` | 7,390,097 / 27 条目 | `60191d419ffa2aed…3063`（全值见 `plan/DIST-sha256-v0.2.0.txt`） |
`patfee-v0.2.0-windows-x64-gui.zip` | 49,899,218 / 197 条目 | `66221d67b268dc86…89d8` 同上 |
`SHA256SUMS-v0.2.0.txt` | — | 附 |

**打包配方（本轮**首次留档**；v0.1.0 只写了"CLI 7.4MB / GUI 49.9MB zip"，没写配方）**：
目录条目 `ZIP_STORED` + 文件条目 `ZIP_DEFLATED(level=9)` + 条目名按 UTF-8 字节序排序
+ 全条目 `date_time=(1980,1,1,0,0,0)` + `create_system=0`（文件 `external_attr=0o644<<16`）
+ zip 内顶层目录 `patfee-cli/` / `patfee-gui/`。
同一 dist 连续两次打包逐字节一致（实测同 sha）。

> **一处必须说明的返工**：我第一版只打了**文件条目**（cli 21 条目），而 v0.1.0 的 cli.zip
> 是 **27 条目（6 个目录 + 21 文件）**。解压结果一样，但 zip 形态与旧版不同 —— 属口径漂移，
> 已按旧版结构重做（本轮 27 / 197 条目）。判定依据是**真下载 v0.1.0 附件读 `namelist()`**，
> 不是猜的。

> **一处必须说明的量级变化**：本版 CLI/GUI 的**解压后体积**与 v0.1.0 不同
> —— zip 7,390,097 / 49,899,218，与 v0.1.0 的 7,386,867 / 49,895,995 相差 +0.04% / +0.006%，
> 来源是本轮工具链（PyInstaller 6.22.3 + PySide6 6.12）与 v0.1.0 构建时的版本差异，
> **不是**打包配方变更（配方已对齐旧版结构）。

## 五、历史结论是否需重跑

**不需要。** 费率表 32 条、阶梯、滞纳金、费减、基准门槛**逐字节未改**，
`--selftest` 六项（含 B1–B4 达标）实测全绿。新增的是**提示与机读字段**，不参与判定。
