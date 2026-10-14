"""CLI 入口（唯一 main）。

**编码守卫**：本模块 import 时即调用 ``console.ensure_utf8_stdio()`` —— pytest 与
``python -m patfee.cli`` 都经此路径。``tools/`` 下的脚本各自调用同一个函数
（入口集合随里程碑增长，漏守新脚本是 CI 首跑全红的常见根因）。

**惰性导入**：可选重件的 ``try`` 必须包住"从 import 到调用完成"的整段。
只包 import 行时会漏掉真正触发重件的调用点，缺依赖时抛裸异常而非 exit 3。
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .console import ensure_utf8_stdio, is_frozen
from .errors import ExitCode, PatfeeError, UsageError, dependency_hint
from .rules.loader import RuleLibrary, load_library
from .rules import literals_gate

# 必须在任何输出之前：探针式改写 stdout/stderr（本机中文控制台保持不动）
ensure_utf8_stdio()

PROG = "patfee"


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("不可序列化类型: %r" % (type(value),))


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)


def _load_json_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise UsageError("输入文件不存在: %s" % path, reason_code="bad_format")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError("输入文件不可读: %s (%s)" % (path, exc), reason_code="bad_format")
    try:
        return json.loads(text, parse_float=Decimal)
    except ValueError as exc:
        raise UsageError("输入文件 JSON 非法: %s (%s)" % (path, exc), reason_code="bad_format")


# ---------------------------------------------------------------- 子命令

def cmd_version(args: argparse.Namespace, library: Optional[RuleLibrary]) -> int:
    lines = ["patfee %s" % __version__]
    lines.append("frozen=%s" % ("yes" if is_frozen() else "no"))
    if library is not None:
        coord = library.coordinate()
        for rs in coord["rulesets"]:
            counts = rs["status_counts"]
            lines.append(
                "ruleset %s@%s (%s) verified=%d pending=%d input_required=%d"
                % (rs["id"], rs["version"], rs["title"], counts.get("verified", 0),
                   counts.get("pending", 0), counts.get("input_required", 0))
            )
    if getattr(args, "json", False):
        payload = {"version": __version__, "frozen": is_frozen()}
        if library is not None:
            payload["coordinate"] = library.coordinate()
        print(_dump(payload))
        return ExitCode.OK.value
    for line in lines:
        print(line)
    return ExitCode.OK.value


def cmd_selfcheck(args: argparse.Namespace, library: RuleLibrary) -> int:
    from .calc.pipeline import selfcheck

    info = selfcheck(library)
    gate = literals_gate.scan_source(
        _repo_root(), library.banned_integers, library.banned_decimals
    )
    gate_probe_ok, gate_probe_msg = literals_gate.selftest(
        _repo_root(), library.banned_integers, library.banned_decimals
    )
    info["literals_gate"] = {
        "scanned_files": len(gate.scanned_files),
        "hits": [h.__dict__ for h in gate.hits],
        "inline_allowed": len(gate.allowed),
        "selftest_ok": gate_probe_ok,
        "selftest_note": gate_probe_msg,
    }

    if getattr(args, "json", False):
        print(_dump(info))
    else:
        print("== patfee selfcheck ==")
        print("数据目录: %s" % info["data_dir"])
        print("冻结态: %s" % ("是" if info["frozen"] else "否"))
        print("作用域: %s" % ", ".join(info["scopes"]))
        print("规则集:")
        for rs in info["rulesets"]:
            print(
                "  - %s@%s %s: 条目 %d（verified=%d pending=%d input_required=%d）"
                % (rs["id"], rs["version"], rs["title"], rs["entries"],
                   rs.get("verified", 0), rs.get("pending", 0), rs.get("input_required", 0))
            )
        counts = info["status_counts"]
        print("合计: verified=%d pending=%d input_required=%d"
              % (counts.get("verified", 0), counts.get("pending", 0), counts.get("input_required", 0)))
        print("零字面量门禁: 扫描 %d 文件, 硬门命中 %d, 行内放行 %d, selftest=%s"
              % (info["literals_gate"]["scanned_files"], len(info["literals_gate"]["hits"]),
                 info["literals_gate"]["inline_allowed"],
                 "通过" if gate_probe_ok else "失败"))
        if counts.get("verified", 0) == 0:
            print("提示: 当前无 verified 条目（费率与政策待 M1 逐项复核）——"
                  "常规计算按门控拒绝，用 --preview 可预览口径（退出码仍为 1）。")
        for extra, dep in info["optional_dependencies"].items():
            state = "可用" if dep["available"] else "不可用"
            print("可选依赖 [%s] %s: %s%s"
                  % (extra, dep["module"], state, (" — " + dep["hint"]) if dep["hint"] else ""))
        if not gate_probe_ok:
            print("零字面量门禁 selftest 失败: %s" % gate_probe_msg)

    if gate.hits or not gate_probe_ok:
        return ExitCode.DEGRADED.value
    return ExitCode.OK.value


def cmd_rules_list(args: argparse.Namespace, library: RuleLibrary) -> int:
    payload: Dict[str, Any] = {"rulesets": []}
    for rs in sorted(library.rulesets.values(), key=lambda r: r.id):
        counts = rs.status_counts()
        payload["rulesets"].append(
            {
                "id": rs.id,
                "version": rs.version,
                "title": rs.title,
                "doc_no": rs.doc_no,
                "anchor_from": rs.anchor_from,
                "anchor_to": rs.anchor_to,
                "entries": len(rs.entries),
                "status_counts": counts,
            }
        )
    if getattr(args, "json", False):
        print(_dump(payload))
        return ExitCode.OK.value
    print("规则集清单（按 依据文件 × 版本 组织）:")
    for item in payload["rulesets"]:
        c = item["status_counts"]
        print("  %s@%s  %s" % (item["id"], item["version"], item["title"]))
        print("      文号: %s" % item["doc_no"])
        print("      锚点: %s ~ %s" % (item["anchor_from"], item["anchor_to"] or "（现行）"))
        print("      条目: %d（verified=%d pending=%d input_required=%d）"
              % (item["entries"], c.get("verified", 0), c.get("pending", 0), c.get("input_required", 0)))
    return ExitCode.OK.value


def cmd_rules_show(args: argparse.Namespace, library: RuleLibrary) -> int:
    rs = library.ruleset(args.ruleset)
    if getattr(args, "json", False):
        print(_dump({"id": rs.id, "version": rs.version, "entries":
                     [rs.entries[k].as_dict() for k in sorted(rs.entries)]}))
        return ExitCode.OK.value
    print("规则集 %s@%s  %s" % (rs.id, rs.version, rs.title))
    print("文号: %s" % rs.doc_no)
    src = rs.source or {}
    if src:
        print("来源: %s" % src.get("url", ""))
        print("抓取: %s 核验: %s" % (src.get("retrieved", ""), src.get("verification", "")))
    for key in sorted(rs.entries):
        entry = rs.entries[key]
        print("  [%s] %s  %s" % (entry.status, key, entry.label))
        if entry.kind == "ladder":
            for tier in entry.ladder:
                print("        第 %s-%s 年: %s 元"
                      % (tier.get("from_year"), tier.get("to_year"), tier.get("amount")))
        else:
            print("        值: %s %s" % (entry.value, entry.basis.get("unit", "")))
        basis = entry.basis or {}
        print("        依据: %s · %s" % (basis.get("doc_no", ""), basis.get("clause", "")))
    counts = rs.status_counts()
    print("合计: verified=%d pending=%d input_required=%d"
          % (counts.get("verified", 0), counts.get("pending", 0), counts.get("input_required", 0)))
    return ExitCode.OK.value


def cmd_rules_diff(args: argparse.Namespace, library: RuleLibrary) -> int:
    from .rules.diff import diff_ruleset, render_text

    payload = diff_ruleset(library, args.ruleset)
    if getattr(args, "json", False):
        print(_dump(payload))
        return ExitCode.OK.value
    for line in render_text(payload):
        print(line)
    return ExitCode.OK.value


def cmd_calc(args: argparse.Namespace, library: RuleLibrary) -> int:
    from .calc import pipeline

    payload = _load_json_file(Path(args.input))
    request = pipeline.build_request(payload, preview=args.preview)
    result = pipeline.compute_full_calc(request, library)
    exit_code = pipeline.exit_code_for(result, preview=args.preview)

    if getattr(args, "with_late", False):
        # 滞纳金扩展：due_on/paid_on 取自输入 JSON；缺字段不阻断年费结论本身，
        # 由滞纳金路径按"未判定"降级呈现（风险提示 ≠ 法律判定）。
        late_result = None
        try:
            late_request = pipeline.build_late_request(payload, preview=args.preview)
            late_result = pipeline.compute_full_late(late_request, library)
            late_code = pipeline.late_exit_code_for(late_result, preview=args.preview)
            exit_code = max(exit_code, late_code)
        except UsageError as exc:
            late_result = None
            late_usage_note = str(exc)
    else:
        late_usage_note = ""

    if getattr(args, "json", False):
        payload_out: Dict[str, Any] = {
            "result": result.as_dict(),
            "disclaimer": pipeline.DISCLAIMER,
        }
        if getattr(args, "with_late", False):
            payload_out["late"] = (
                late_result.as_dict() if late_result is not None
                else {"computed": False, "reasons": ["bad_format"], "note": late_usage_note}
            )
        print(_dump(payload_out))
    else:
        for line in pipeline.result_lines(result, library):
            print(line)
        if getattr(args, "with_late", False):
            if late_result is not None:
                print("")
                for line in pipeline.late_lines(late_result):
                    print(line)
            else:
                print("")
                print("== 滞纳金测算 ==")
                print("滞纳金: 未判定")
                print("原因码: bad_format")
                print("说明: %s" % late_usage_note)
        if args.preview:
            print("注意: --preview 仅用于预览口径，不得作为缴费依据。")
    return exit_code


def cmd_reduction(args: argparse.Namespace, library: RuleLibrary) -> int:
    from .calc import pipeline

    payload = _load_json_file(Path(args.input))
    request = pipeline.build_reduction_request(payload, preview=args.preview)
    result = pipeline.compute_full_reduction(request, library)

    if getattr(args, "json", False):
        print(_dump({"result": result.as_dict(), "disclaimer": pipeline.DISCLAIMER}))
    else:
        for line in pipeline.reduction_lines(result):
            print(line)
        if args.preview:
            print("注意: --preview 仅用于预览口径，不得作为缴费依据。")
    return pipeline.reduction_exit_code_for(result, preview=args.preview)


def cmd_scan(args: argparse.Namespace, library: RuleLibrary) -> int:
    """组合批量排期 + 到期预警 + 跨轮对账（M3）。

    * 失败件隔离：单件坏格式不中断整批、**不改变退出码**——退出码由
      "是否检出问题"决定（未缴清 / 未判定 / 窗口内到期 / 失败件）；
    * ``--out`` 指定输出目录时落盘报告（Markdown）+ 证据 JSON；
      未给出时只打印 stdout。
    * **未启用章节显式写出**：本次导出未覆盖的能力（滞纳金/费减判定）
      在报告里显式声明"未启用"，不留空（"没查"≠"查了没问题"）。
    """
    from .calc import pipeline
    from .calc.portfolio import compare_rounds

    payload = _load_json_file(Path(args.input))
    window_months = getattr(args, "window_months", None)
    if window_months is not None:
        payload = dict(payload)
        payload["window_months"] = window_months
    request = pipeline.build_portfolio_request(payload, preview=args.preview)
    result = pipeline.compute_full_portfolio(request, library)
    baseline, current = pipeline.portfolio_rounds(request)
    reconciliation = compare_rounds(baseline, current)
    exit_code = pipeline.portfolio_exit_code_for(result, preview=args.preview)

    if getattr(args, "json", False):
        print(_dump({
            "result": result.as_dict(),
            "reconciliation": reconciliation.as_dict(),
            "disclaimer": pipeline.DISCLAIMER,
            "not_enabled_sections": _scan_not_enabled_sections(),
        }))
    else:
        for line in pipeline.portfolio_lines(result, reconciliation):
            print(line)
        for line in _scan_not_enabled_lines():
            print(line)
        if args.preview:
            print("注意: --preview 仅用于预览口径，不得作为缴费依据。")

    out_dir = getattr(args, "out", None)
    if out_dir:
        written = _write_scan_report(
            Path(out_dir), result, reconciliation, library, args.preview
        )
        if not getattr(args, "json", False):
            for line in written:
                print(line)
    return exit_code


def _scan_not_enabled_sections() -> Dict[str, str]:
    """本次 scan 导出**未启用**的能力清单（显式写出，不留空）。"""
    return {
        "late": "本次组合排期未启用逐件滞纳金测算（对已逾期件用 `patfee calc <件.json> --with-late` 启用）",
        "reduction": "本次组合排期未启用费减资格判定（对单件用 `patfee reduction <主体.json>` 启用）",
    }


def _scan_not_enabled_lines() -> List[str]:
    lines = ["== 未启用章节（没查 ≠ 查了没问题）=="]
    for key, text in _scan_not_enabled_sections().items():
        lines.append("  - %s" % text)
    return lines


def _write_scan_report(
    out_dir: Path,
    result: Any,
    reconciliation: Any,
    library: RuleLibrary,
    preview: bool,
) -> List[str]:
    """报告落盘：Markdown（人类读）+ evidence JSON（机读指纹）。

    M3 只做 Markdown 单一渲染源；XLSX 双格式与逐字节可复现导出在 M5
    （plan/04 §七切分）。无外链纪律从 M3 起守：报告正文不写 URL。
    """
    from .calc.pipeline import DISCLAIMER, portfolio_lines
    import hashlib

    out_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# 专利组合费用排期报告")
    lines.append("")
    lines.append("- 基准日: %s" % result.today)
    lines.append("- 预警窗口: 未来 %d 个月" % result.window_months)
    coord = library.coordinate()
    lines.append("- 规则包: %s" % ", ".join(
        "%s@%s" % (rs["id"], rs["version"]) for rs in coord.get("rulesets", [])
    ))
    if preview:
        lines.append("- 口径: **预览（--preview），结论不得作为缴费依据**")
    lines.append("")
    lines.append("## 一、输入事实")
    lines.append("")
    lines.append("逐件输入与排期结论（含失败隔离件）：")
    lines.append("")
    lines.append("| 件 | 专利号 | 类型 | 年度 | 到期日 | 缴费日 | 结论 | 应缴年费 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for e in result.entries:
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                e.id, e.patent_no or "—", e.patent_type or "—",
                "" if e.year is None else e.year, e.due_on or "—", e.paid_on or "—",
                e.kind,
                "" if e.amount is None else "%s 元" % e.amount,
            )
        )
    lines.append("")
    lines.append("## 二、逐项结论与计算过程")
    lines.append("")
    for line in portfolio_lines(result, reconciliation):
        lines.append(line)
    lines.append("")
    lines.append("## 三、未启用章节")
    lines.append("")
    for key, text in _scan_not_enabled_sections().items():
        lines.append("- **%s**: %s" % (key, text))
    lines.append("")
    lines.append("## 四、适用依据与免责声明")
    lines.append("")
    for rs in coord.get("rulesets", []):
        lines.append("- %s@%s %s（锚点 %s ~ %s）" % (
            rs["id"], rs["version"], rs.get("doc_no") or "",
            rs.get("anchor_from") or "?", rs.get("anchor_to") or "现行"))
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")

    md_bytes = ("\n".join(lines)).encode("utf-8")
    md_path = out_dir / "scan-report.md"
    md_path.write_bytes(md_bytes)

    evidence = {
        "today": result.today,
        "window_months": result.window_months,
        "counts": {
            "entries": len(result.entries),
            "failed": len(result.failed),
            "due_soon": len(result.due_soon),
        },
        "reconciliation": reconciliation.as_dict(),
        "coordinate": coord,
        "disclaimer": DISCLAIMER,
        "not_enabled_sections": _scan_not_enabled_sections(),
        "report": {
            "name": md_path.name,
            "bytes": len(md_bytes),
            "sha256": hashlib.sha256(md_bytes).hexdigest(),
        },
        "preview": bool(preview),
    }
    evidence_path = out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return [
        "报告已写出: %s" % md_path,
        "证据已写出: %s（含报告 sha256 指纹）" % evidence_path,
    ]


def cmd_bench(args: argparse.Namespace, library: RuleLibrary) -> int:
    from .benchmark import suites

    only = list(args.only or [])
    results, verdicts, implemented = suites.run_suites(library, only=only)

    if getattr(args, "json", False):
        print(_dump({
            "results": {k: v.as_dict() for k, v in results.items()},
            "verdicts": verdicts,
            "implemented": implemented,
        }))
    else:
        print("== patfee bench ==")
        for name, res in results.items():
            if not res.implemented:
                print("  %-14s 未实装（%s）" % (name, "; ".join(res.notes) or "后续里程碑"))
                continue
            print("  %-14s 通过 %d/%d  达标率=%s  耗时=%ss" % (
                name, res.passed, res.total, res.pass_rate, res.elapsed_seconds))
            for note in res.notes:
                print("      注: %s" % note)
            for failure in res.failures[:5]:
                print("      失败: %s" % failure)
        print("  判定: %s" % (", ".join(verdicts) if verdicts else "无可判定套件"))

    ok = all(v.endswith("=达标") for v in verdicts) if verdicts else False
    return ExitCode.OK.value if ok else ExitCode.DEGRADED.value


def cmd_gui(args: argparse.Namespace, library: Optional[RuleLibrary]) -> int:
    """桌面界面入口（M5 实装）。惰性导入的 try 包住"从 import 到调用完成"整段。"""
    try:
        from .gui import main_window  # type: ignore

        return int(main_window.main())
    except ImportError as exc:
        # 关键：真正的缺依赖异常可能在 build_app() 这类函数体内才抛，
        # 所以 try 必须覆盖到调用完成，而不是只覆盖 import 这一行。
        print("桌面界面需要可选依赖 PySide6。")
        print(dependency_hint("gui", is_frozen()))
        print("（原始错误: %s）" % exc)
        return ExitCode.MISSING_DEP.value
    except FileNotFoundError as exc:
        print("桌面界面尚未实装（M5 里程碑）: %s" % exc)
        return ExitCode.USAGE.value


# ---------------------------------------------------------------- 装配

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="专利年费与费减合规计算工作台（全本地处理、零上传、零 API 依赖）",
    )
    parser.add_argument("--version", action="version", version="%s %s" % (PROG, __version__))
    sub = parser.add_subparsers(dest="command")

    p_ver = sub.add_parser("version", help="打印版本与规则包坐标")
    p_ver.add_argument("--json", action="store_true", help="输出 JSON")
    p_ver.set_defaults(func=cmd_version)

    p_self = sub.add_parser("selfcheck", help="数据目录 + 规则加载 + 门控计数 + 依赖可用性")
    p_self.add_argument("--json", action="store_true", help="输出 JSON")
    p_self.set_defaults(func=cmd_selfcheck)

    p_rules = sub.add_parser("rules", help="规则集浏览")
    rules_sub = p_rules.add_subparsers(dest="rules_command")
    p_rl = rules_sub.add_parser("list", help="列出全部规则集")
    p_rl.add_argument("--json", action="store_true")
    p_rl.set_defaults(func=cmd_rules_list)
    p_rs = rules_sub.add_parser("show", help="查看某规则集条目")
    p_rs.add_argument("ruleset", help="规则集 id，如 fee_schedule")
    p_rs.add_argument("--json", action="store_true")
    p_rs.set_defaults(func=cmd_rules_show)
    p_rd = rules_sub.add_parser("diff", help="规则版本差异报告（阈值前后对照 + 新增条目）")
    p_rd.add_argument("ruleset", help="规则集 id，如 reduction_316 / reduction_594")
    p_rd.add_argument("--json", action="store_true")
    p_rd.set_defaults(func=cmd_rules_diff)
    p_rules.set_defaults(func=None)

    p_calc = sub.add_parser("calc", help="单件年费测算")
    p_calc.add_argument("input", help="专利输入 JSON 文件")
    p_calc.add_argument("--preview", action="store_true",
                        help="预览口径：允许未核对条目参与，但退出码仍为 1")
    p_calc.add_argument("--with-late", action="store_true",
                        help="同件追加滞纳金测算（输入须含 due_on/paid_on；超上限为 warning）")
    p_calc.add_argument("--json", action="store_true")
    p_calc.set_defaults(func=cmd_calc)

    p_red = sub.add_parser("reduction", help="费减资格与减免额判定")
    p_red.add_argument("input", help="主体输入 JSON 文件（applicants + as_of_year + year）")
    p_red.add_argument("--preview", action="store_true",
                       help="预览口径：允许未核对条目参与，但退出码仍为 1")
    p_red.add_argument("--json", action="store_true")
    p_red.set_defaults(func=cmd_reduction)

    p_scan = sub.add_parser("scan", help="组合批量排期 + 到期预警 + 跨轮对账")
    p_scan.add_argument("input", help="组合输入 JSON 文件（items 或 baseline/current 两轮台账）")
    p_scan.add_argument("--out", default=None,
                        help="报告输出目录（Markdown + evidence.json；缺省只打印）")
    p_scan.add_argument("--window-months", type=int, default=None,
                        help="到期预警窗口（月数；缺省取输入的 window_months 或 3）")
    p_scan.add_argument("--preview", action="store_true",
                        help="预览口径：退出码仍为 1，绝不返回 0")
    p_scan.add_argument("--json", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_bench = sub.add_parser("bench", help="内置评测基准")
    p_bench.add_argument("--only", action="append", default=[],
                         help="只跑指定套件（可重复）；未知套件名 exit 2")
    p_bench.add_argument("--json", action="store_true")
    p_bench.set_defaults(func=cmd_bench)

    p_gui = sub.add_parser("gui", help="桌面界面（M5）")
    p_gui.set_defaults(func=cmd_gui)

    return parser


def _library_or_none(need_library: bool) -> Optional[RuleLibrary]:
    """加载规则库；仅在确实需要时加载（version/gui 允许缺失）。"""
    try:
        return load_library()
    except FileNotFoundError as exc:
        if need_library:
            raise UsageError(str(exc), reason_code="ruleset_error")
        return None
    except PatfeeError:
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not getattr(args, "command", None):
        parser.print_help()
        return ExitCode.USAGE.value

    func = getattr(args, "func", None)
    if func is None:
        # 例如 `patfee rules` 不带子命令
        parser.parse_args([args.command, "--help"])
        return ExitCode.USAGE.value

    needs_library = args.command in ("selfcheck", "rules", "calc", "reduction", "scan", "bench")
    try:
        library = _library_or_none(needs_library)
        if needs_library and library is None:
            raise UsageError("规则库不可用", reason_code="ruleset_error")
        return int(func(args, library))
    except UsageError as exc:
        print("参数错误 [%s]: %s" % (exc.reason_code, exc.message), file=sys.stderr)
        return ExitCode.USAGE.value
    except PatfeeError as exc:
        code = ExitCode.USAGE.value if exc.reason_code in ("usage_error", "ruleset_error") \
            else ExitCode.DEGRADED.value
        print("错误 [%s]: %s" % (exc.reason_code, exc.message), file=sys.stderr)
        return code
    except FileNotFoundError as exc:
        print("错误 [ruleset_error]: %s" % exc, file=sys.stderr)
        return ExitCode.USAGE.value


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
