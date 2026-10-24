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

## 六、已知缺陷：tag 树含本机绝对路径（不可修复）

### 6.1 事实

`v0.2.0` 的发布提交 **`17dc75d`** 新增了 `.verify-out/selftest-cli.json` 与
`.verify-out/selftest-gui.json`，两份文件第 4 行 `detail` 字段是构建机的绝对路径
（`<盘符>:\<系统级程序数据目录>\<工作根>\...\dist\patfee-{cli,gui}\_internal\data`）——
**本节刻意不写该路径的字面原文**：写出来等于把泄露再复制一份进仓库，本仓的脱敏门会当场命中
（2026-10-24 实测，见 6.6）。

`tests/test_repo_guards.py` 的历史脱敏门因此命中两条 HARD（`kind=work_root`）：

```
17dc75d4:.verify-out/selftest-cli.json:4
17dc75d4:.verify-out/selftest-gui.json:4
```

### 6.2 为什么不可修复

该提交**已推送**，且 `v0.2.0` tag 指向它。让它变绿的唯一方式是改写 `17dc75d`
后 force push —— 那会破坏本仓与整个计划反复确立的「**按 tag 可复现**」原则
（下一个人 `git clone --branch v0.2.0` 拿到的就不是 CI 验过的那棵树）。
**用户 2026-10-24 拍板：走乙案 —— 不改写历史，显式声明。**

### 6.3 已做的两侧处置

| 侧 | 处置 | 状态 |
|---|---|---|
| 工作树 | 两份 json 的 `detail` → `<解压目录>/_internal/data`；`name`/`ok`/`frozen` 与全部结论一字未动 | ✅ `test_desensitize_audit_tracked_has_no_hard_hits` 通过 |
| 历史 | **不改**（见 6.2） | ❌ 两条命中长期存在，已声明 |
| 门禁 | `test_desensitize_audit_history_has_no_hard_hits` → 更名 `..._has_no_unknown_hard_hits`，判据从「集合为空」收窄为「**差集为空**」，允许集合钉死为上述两处 | ✅ 见 6.4 |

### 6.4 门是怎么「收窄」而不是「改瞎」的

```python
KNOWN_HISTORY_HARD_HITS = frozenset({
    "17dc75d4:.verify-out/selftest-cli.json:4",
    "17dc75d4:.verify-out/selftest-gui.json:4",
})
# 断言 1：unexpected = found - expected 必须为空  → 新增命中会红
# 断言 2：vanished   = expected - found 必须为空  → 这两处消失也会红（防白名单变化石）
```

**没有**用 `pytest.skip` / `xfail(strict=True)`：那会让这条门对**任何**新命中都不再报红。

**负控（2026-10-24 实测，通过 pytest 插件替换 `audit_history()` 的返回集）**：

| # | 施加 | 期望 | 实测 |
|---|---|---|---|
| NC3 | 真实命中集（基线） | 通过 | ✅ `3 passed` |
| NC1 | 注入第三条硬命中 `.verify-out/injected.json:1` | **红** | ✅ `AssertionError: 历史出现新的硬门命中: 17dc75d4:.verify-out/injected.json:1 work_root` |
| NC2 | 从命中集里删掉 `selftest-cli.json:4` | **红** | ✅ `AssertionError: 已知缺陷白名单里的位置已不在历史命中中: …selftest-cli.json:4 …` |

### 6.5 看到这条门红时怎么判

- 报「历史出现新的硬门命中」→ **是真问题**，当场处理（这正是收窄后保留的能力）。
- 报「白名单里的位置已不在历史命中中」→ 说明历史被改写了或仓库换了，先查清再动白名单。

### 6.6 我自己在落地这一节时踩了同一个坑（实测记录）

第一版 §6.1 为了「说清楚缺陷」，把那条本机路径的**字面原文**贴进了本文档。
推上去后 CI 三条 job 立刻红：

```
AssertionError: 硬门命中: plan/RELEASE-v0.2.0.md:87 work_root
AssertionError: 历史出现新的硬门命中: 13e785ee:plan/RELEASE-v0.2.0.md:87 work_root
FAILED tests/test_repo_guards.py::test_desensitize_audit_tracked_has_no_hard_hits
FAILED tests/test_repo_guards.py::test_desensitize_audit_history_has_no_unknown_hard_hits
```

这件事本身是个**有价值的验证**：它证明收窄后的门并没有被改瞎 —— 我自己新造的命中被当场抓住，
而且**先在工作树侧红**（`tracked`）**再在历史侧红**（`history`）。但代价是 `13e785e` 已推送，
于是白名单从 2 条变 3 条。

- 工作树已改为占位符描述（`<盘符>:\<系统级程序数据目录>\<工作根>\...`），`tracked` 归零。
- 历史里那条**不可修复**，已登记进 `KNOWN_HISTORY_HARD_HITS` 并注明来源。
- **方法论**：声明一处泄露时，**不要复制泄露本身**。写「第 4 行 `detail` 字段含构建机
  绝对路径」就够了；贴原文只会让读者多拿到一份，还把自己变成新的泄露点。

## 七、一处配方更正（2026-10-24 实测）

`plan/DIST-sha256-v0.2.0.txt` 原写「文件条目 `ZIP_DEFLATED(level=9)`」——**这是笔误**。
2026-10-24 重建发布物时按 level=9 打出的 sha256 与台账对不上（cli 7,349,032 B vs 台账
7,390,097 B；gui 49,679,646 B vs 49,899,218 B），逐条目比对确认 27/27 与 197/197 条目名、
size、CRC 全同，只有 `compress_size` 差 → 压缩级别不符。

扫描 `zlib` 的 `level(1–9) × memLevel(1–9) × strategy` 组合后，**`level=6`（zlib 默认值，
也是 `zipfile.writestr` 不传 `compresslevel` 时的实际行为）逐字节命中台账值**。
台账已加更正行，配方其余部分（目录条目 `ZIP_STORED`、`date_time=(1980,1,1,0,0,0)`、
`create_system=0`、`external_attr=0o644<<16`、UTF-8 字节序排序、目录条目必须在）**实测无误**。

> **注意**：本节的更正落在**工作树**。`v0.2.0` tag 树（`17dc75d`）里的台账仍是原写法，
> 二者不同是预期的 —— tag 是不可变的发布快照。

