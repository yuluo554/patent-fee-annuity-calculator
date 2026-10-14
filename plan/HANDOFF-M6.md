# HANDOFF-M6 —— 交接快照（M5 桌面交付 → M6 脱敏发布）

> **用法**：新对话用 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务`。
> **本文件状态**：M5 已完成（2026-10-14）。更早交接见 [HANDOFF-M5.md](HANDOFF-M5.md)（含 K43–K46 既定口径，仍然有效）。
> **写入日期**：2026-10-14

---

## 一、当前进度（M5 已完成）

| 里程碑出口判据（plan/05 §二 M5 行） | 状态 | 证据 |
|---|---|---|
| GUI AST 门禁三条齐上 | ✅ | `tests/test_m5_gui.py`：① 不 import 规则层/领域层（AST ImportFrom 断言）② 无算术 BinOp（`* / - // % **` 全禁、`+`/`%` 仅限文本排版）③ 无政策数值字面量（同一份 BANNED_TOKENS）+ 扫描面覆盖断言；实测 GUI 占位文本的政策数值 5000 被门禁拦截后改正 |
| exe `--selftest` 冻结态断言通过 | ✅ | PyInstaller 6.22.3 onedir 双 exe 实测构建；`patfee-cli.exe --selftest` exit 0 frozen=True 六项全绿（数据落点 within_exe=True / 规则 verified=32 / calc 900.00 / 基准四套件达标）；`patfee-gui.exe --selftest` exit 0 六项全绿（GUI offscreen 冒烟真实执行）；dist 断言 9 份数据 sha256 对账一致、禁区 0 |
| 三方对账测试 | ✅ | `tests/test_m5_three_way.py`：scan 三方逐行相等（CLI stdout = 编排直调 = 报告章节）+ calc/reduction 两方 + CLI"未启用章节"附加段与报告"三"节同源断言 |

**M5 其他交付**：
- 报告导出：`report/` 单一渲染源（`scan_report_sections`）+ MD/XLSX 双格式；`scan --format xlsx`；XLSX **逐字节可复现**（重打包 ZIP_STORED + 固定时间戳 + `dcterms:modified` 替换，跨进程 sha256 一致实测）；无外链（K42）双格式同守；evidence.json 增 `report_xlsx`/`formats`；
- 技术报告：`plan/技术报告.md`（C6 定夺：纯 MD 入仓）；
- 测试 **226 项**（196 + 30）三解释器全绿（py3.8 / py3.12 / 干净 venv，收集数一致）；冻结三项 OK；零字面量门禁 31 文件 0 命中；DoD 表落盘 plan/05 §三之六（M5-1~M5-7 无偏差）；证据 `.verify-out/M5-local-equivalence.txt`。

## 二、下一里程碑待办（M6 脱敏发布）

按 plan/05 §二 M6 行：

1. **脱敏四步留档**：`tools/audit_desensitize.py --mode all`（自检 + 跟踪树 + 历史 + 提交信息）跑通并留证据；确认历史提交无敏感信息（本机路径 / 真实专利号 / 真实主体）；
2. **干净环境逐条跑通 README**：按 README 快速开始从头 `python -m venv` → 安装 → 全部命令逐条执行（README 里引用的文件路径守门测试已有，但"逐条可跑"要实测）；
3. **CI 三矩阵绿**：推远端后实跑（windows×{3.8,3.12} + ubuntu×3.12）；**C1 待决**：M1 结束仍无远端，本地等价校验沿用——M6 建仓时首跑 CI 是发布窗口，预算多轮诊断（plan/05 §五风险表）；
4. **GitHub Release（exe）**：双 exe 打包产物 + 演示 GIF/截图（plan/01 交付物 5）；GUI 演示 GIF 用 offscreen 或真机截屏；
5. **收尾固化**：plan/00 状态表 M6 打勾、README 里程碑表同步、决策记录 D49+ 补 M5/M6 条目、记忆文件更新。

**M6 起手前注意**：
- dist/、build/、.verify-out/ 不得入 git（查 .gitignore 是否已覆盖 dist/build——本次打包新增了这两个目录）；
- PyInstaller 构建是**环境依赖**的（本机 venv 构建），Release 产物要在干净环境重打并重跑 `--selftest`；
- py3.8 全量测试首轮曾出 3 项间歇失败（temp 竞态 / 子进程 0xC0000005，复跑全绿）——CI 上如复现按 plan/05 §三之六偏差说明 1 处理。

## 三、M5 新增的既定口径（接 K1–K46，动了会打挂测试）

| # | 口径 | 值 / 语义 |
|---|---|---|
| K47 | 报告单一渲染源 | Markdown 与 XLSX 各自消费 `report.scan_report_sections` 章节列表；报告头 `heading=1`、章节 `heading=2`（M3 的 `## 一、输入事实` 结构锁定不动）；XLSX 目录表 + 每章节一个工作表；两格式内容对等由测试锁死 |
| K48 | XLSX 可复现口径 | openpyxl save 后重打包：zip 条目 `ZIP_STORED` + `date_time=(1980,1,1,0,0,0)` + `create_system=0` + `external_attr=0o600<<16`；`dcterms:modified` 正则替换为 `1980-01-01T00:00:00Z`（替换串必须带 `xmlns:dcterms` + `xmlns:xsi` 声明——openpyxl 把命名空间声明在原标签上，整体替换会留下未定义前缀、lxml 直接报错）；evidence.json `report_xlsx.sha256` |
| K49 | GUI AST 门禁豁免边界 | `+`：字符串常量或 List/Tuple 字面量参与（排版拼接）豁免；`%`：左侧为 str 常量或 Name（格式化）豁免；其余 `* / - // % **` 一律禁止；banned token 走 loader 的同一份集合 |
| K50 | 三方对账剥离口径 | scan 的 CLI stdout 在编排行之后附加"未启用章节"段（`== 未启用章节…==` 起 3 行）；三方对账以 marker 剥离附加段 + 剥两端空行后逐行相等；附加段与报告"三"节 rows 同源断言 |
| K51 | exe 自检六项 | `data_dir_found` / `data_dir_within_exe`（冻结态必须 True，非冻结 None 不报错）/ `rules_loaded`（verified>0）/ `calc_pipeline`（invention 第 3 年 = 金额非空）/ `benchmark_suites`（全达标）/ `gui_offscreen_smoke`（PySide6 缺席时记"跳过"仍算过——CLI-only 包合法）；`--selftest` 是顶层 flag（先于子命令解析），退出码 0/1 |
| K52 | 打包单一事实源 | `packaging.build_datas()` 白名单 = data/rules + data/truth + data/knowledge/clauses.json（**raw/ 不入包**）；spec 的 datas 只能来自它；dist 断言禁区 = {plan, tests, _private, .git, .verify-out, tools} 任意层命中即失败；双 exe 同一入口 `packaging/run_patfee.py`（cli.py 相对导入不能直接做 Analysis 入口——实测教训） |

## 四、M5 实现要点（给 M6 的地图）

- **报告层**：`src/patfee/report/`（`base.py` Section / `sections.py` 单一渲染源 / `markdown_render.py` / `xlsx_render.py`）；`cli._write_scan_report` 消费它，`--format` 缺省 md（向后兼容，evidence.formats == ['md']）。
- **GUI**：`src/patfee/gui/`（`__init__.py` 服务层 `compute_lines` 三通路转发 pipeline + `main()` 事件循环；`main_window.py` 四页签）；AST 门禁测试在 `tests/test_m5_gui.py`（改 gui 代码前先看豁免边界 K49）。
- **自检**：`cli._frozen_selftest(out_path)`；顶层 `--selftest <json>` 在 `main()` 里先于 argparse 处理（注意：argv 显式传入时走 `--selftest in argv_list` 分支）。
- **打包**：`packaging/patfee.spec`（双 Analysis 双 EXE 双 COLLECT；CLI Analysis `excludes=["PySide6", "openpyxl"]`）；`src/patfee/packaging.py`（build_datas + assert_dist_clean）；构建命令 `pyinstaller --clean -y packaging/patfee.spec`。
- **测试落位**：报告 6 条 `tests/test_m5_report.py`、GUI 15 条 `tests/test_m5_gui.py`、三方 3 条 `tests/test_m5_three_way.py`、打包 6 条 `tests/test_m5_packaging.py`。

## 五、M5 过程中的决策留痕

1. **零字面量门禁连占位文本都拦**：GUI 费减页签 placeholder 写了月收入示例值 5000，扫描面（含 docstring/注释）立即报红——这是防线对"非计算代码"生效的实证，改为中性占位 `<月均收入>`。教训：新增源码文件前先想 token 面。
2. **openpyxl modified 戳不尊重属性赋值**：`Workbook.properties.modified` 赋固定值后 save 仍写当前时刻——产物层重打包时替换；第一版替换串丢了命名空间声明，py3.12（lxml 后端）解析直接报错而 venv（无 lxml，openpyxl 用后备解析器）静默通过——**三解释器回归的价值在依赖差异处**。
3. **PyInstaller EXE 漏 scripts = 静默空壳**：首版 spec 把 `gui.binaries/zipfiles/datas` 传给 EXE 却漏了 `scripts`，bootloader 无入口 0.03s exit 0；第二版 `exclude_binaries` 关键字重复致 spec 语法错误（构建日志尾部才见）——构建脚本必须"构建成功 + 产物行为验证"双重确认。
4. **py3.8 间歇失败处置**：首轮 3 项失败（子进程 TypeError / 0xC0000005 / 审计 RuntimeError），隔离复跑单项与组合均过、连续三轮全量 226 全绿——按"环境间歇非代码缺陷"记入偏差说明，不静默重试掩盖，留 CI 首跑观察项。
5. **交接纪律延续**：本文件为新建（上一份 HANDOFF-M5 原文保留）；入库文件内一律写相对路径 `plan/HANDOFF-M6.md`。

## 六、关键命令速查

```bash
# 环境
py -0p                                        # 看有哪些解释器通道
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m pip install -e ".[dev,report,gui,build]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（三处都要绿，收集数必须一致 = 226）
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
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli scan data/samples/portfolio-demo.json --out .verify-out/scan-demo --format xlsx
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli bench                                             # B1–B4 全达标 exit 0
PYTHONPATH=src py -3.12 -X utf8 -m patfee.cli --selftest .verify-out/selftest-src.json          # 源码态自检 exit 0

# GUI（offscreen 冒烟；真实窗口直接 patfee gui）
QT_QPA_PLATFORM=offscreen PYTHONPATH=src py -3.12 -X utf8 -c "from patfee.gui import main; import PySide6.QtWidgets as Q; app=Q.QApplication([]); from patfee.gui.main_window import MainWindow; from patfee.gui import compute_lines; w=MainWindow(service=compute_lines); w.show(); w.close(); print('OK')"

# 打包（PyInstaller ≥6，本机 3.12 venv 已装）
NO_PROXY="*" no_proxy="*" ./.venv/Scripts/python.exe -m PyInstaller --clean -y packaging/patfee.spec
./dist/patfee-cli/patfee-cli.exe --selftest .verify-out/selftest-frozen.json    # 冻结态自检 exit 0
./dist/patfee-gui/patfee-gui.exe --selftest .verify-out/selftest-frozen-gui.json

# 脱敏审计（M6 主线）
PYTHONPATH=src py -3.12 -X utf8 tools/audit_desensitize.py --mode all
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务
```

（M5 已完成；M6 启动时把本文件收尾为 HANDOFF-M7 或新建之。入库文件内一律写相对路径 `plan/HANDOFF-M*.md`，绝对路径由用户在启动命令里拼。）

## 八、M6 完成结论（2026-10-14 收尾补记）

> **M6 已完成，全里程碑（M0–M6）收官。** 本节为收尾补记，上文"待办"与"注意"保留原样作过程留痕。

| M6 出口判据（plan/05 §二 M6 行） | 状态 | 证据 |
|---|---|---|
| 脱敏四步留档 | ✅ | `tools/audit_desensitize.py --mode all`：tracked 94 对象 / history 143 blob / messages 8 提交，**HARD 0**（advisory 均为 sha256 指纹=文档化功能）；自检正例 4 报红、反例 4 未误报；证据 `.verify-out/M6-desensitize-audit.txt` |
| 干净环境逐条跑通 README | ✅ | git clone 全新目录 → `python -m venv` → `pip install -e ".[dev]"` → 13 条命令逐条执行退出码留档（gui exit 3 / scan exit 1 / calc --preview exit 1 均为 README 明示语义）；证据 `.verify-out/M6-readme-walkthrough.txt` |
| CI 三矩阵绿 | ✅ | 公开仓 github.com/yuluo554/patent-fee-annuity-calculator；**首跑即五 job 全绿**（run 38531986244：windows×{3.8,3.12} + ubuntu×3.12 + core-only + packaging-guard）；首轮一次拦截（见下"过程留痕"），amend 后全绿 |
| GitHub Release（exe + 演示） | ✅ | [v0.1.0](https://github.com/yuluo554/patent-fee-annuity-calculator/releases/tag/v0.1.0)：干净 clone 重打双 exe（CLI 7.4MB / GUI 49.9MB zip），冻结态 `--selftest` 双 exit 0（frozen=true 六项绿，`.verify-out/selftest-clean-{cli,gui}.json`）+ `SHA256SUMS-v0.1.0.txt` + GUI 演示截图三张（offscreen 真实计算态，`QT_QPA_FONTDIR` 指向 Windows Fonts 解决 CJK 渲染） |
| 收尾固化 | ✅ | plan/00 里程碑表 M5/M6 打勾 + 承诺台账两项收口 + CI 诚实口径补记；README 里程碑表同步；决策记录补 D51 + C1/C6/C8 定夺；记忆文件更新 |

### M6 过程留痕（新增坑与教训）

1. **安装面缺口（本里程碑最有价值的发现）**：干净 venv 只装 README 原文的 `.[dev]` 时，`test_m5_report.py` 三条 XLSX 测试**硬失败**（openpyxl 缺席 → `scan --format xlsx` 静默无产物）——M5 的"三解释器全绿"是在装齐 extras 的环境跑的，测试面与安装面从未对齐过。修复：README + CI `test`/`packaging-guard` 统一 `.[dev,report]`（D51②）。
2. **脱敏守门第一次真实拦截**：CI 首轮三个 job 齐报 `work_root` 命中——我自己写的 M6 留档里贴了本机绝对路径（`patfee selfcheck` 的数据目录输出行）。修复：留档内路径改中性占位 + `--amend` 强推消除坏 blob。教训：**留档也是被扫对象**，贴命令输出前先想扫描面。
3. **GUI offscreen 截图两坑**：缺 CJK 字体出方块（`QT_QPA_FONTDIR=C:\Windows\Fonts` 解决）；截窗不切页签（`QTimer` 里先 `setCurrentIndex` 再 `grab`）。演示截图一律用"填表 → 点击 → 出结果"的真实计算态，不用空表单。
4. **发布形态用户定夺为公开仓**（原计划按 plan/05 风险表先私有后议）——切换时机：先修完坏 blob 再切公开，公开前历史已干净。

### 遗留（无阻断项）

- GIF 演示以三张静态截图替代（plan/01 交付物 5 的"GIF/截图"按截图口径交付）；
- PyPI 发布按 C8 留扩展；
- py3.8 CI 未见 HANDOFF-M6 §二预告的间歇失败（M5 本机现象，CI 环境 2m30s 全绿一次通过）。
