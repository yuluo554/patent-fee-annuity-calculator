"""XLSX 渲染器：openpyxl 惰性导入 + 逐字节可复现导出（M5）。

可复现口径（plan/04 §七）：

* zip 条目 ``ZIP_STORED`` + 固定 ``date_time``（1980-01-01）+ ``create_system=0``
* 文档属性（creator/created/modified）固定值
* 单元格一律字符串（金额保持两位小数文本，NFR-2 由引擎负责）

openpyxl 的 ``save`` 走内部 zipfile；本模块通过在其写入后**重打包**
（读取原 zip 条目、按固定时间戳与存储方式重写）实现可复现——这样不依赖
openpyxl 内部 API 的版本行为，两次导出的 sha256 逐字节一致可实测背书。
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import List, Optional

from .base import Section
from ..errors import UsageError

# 文档属性固定值（可复现：不许随导出时刻漂移）
_FIXED_CREATOR = "patfee"
_FIXED_TIMESTAMP = "1980-01-01T00:00:00Z"

# openpyxl save 时会用当前时刻重打 dcterms:modified 戳（不尊重 Workbook
# 属性赋值），重打包阶段统一替换为固定值。替换串必须保留原标签携带的
# xmlns:xsi 声明（它声明在该开标签上，被整体替换会留下未定义前缀，
# lxml 解析直接报错）。
_FIX_MODIFIED_RE = re.compile(
    rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>"
)
_FIXED_MODIFIED_XML = (
    '<dcterms:modified xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:type="dcterms:W3CDTF">%s</dcterms:modified>' % _FIXED_TIMESTAMP
).encode("utf-8")

# 重打包时固定的 zip 条目元数据
_EPOCH_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_EXTERNAL_ATTR = 0o600 << 16


def render_xlsx_bytes(sections: List[Section]) -> bytes:
    """把结构化章节渲染成 XLSX 字节串（确定性）。

    缺 openpyxl → ``UsageError``（exit 3 语义由 CLI 映射）。
    """
    try:
        import openpyxl  # noqa: F401
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - 本机已装，CI core-only 走此分支
        raise UsageError(
            "XLSX 导出需要可选依赖 openpyxl（pip install patfee[report]）",
            reason_code="missing_dependency",
        ) from exc

    wb = Workbook()
    wb.properties.creator = _FIXED_CREATOR
    wb.properties.lastModifiedBy = _FIXED_CREATOR
    try:
        import datetime as _datetime

        wb.properties.created = _datetime.datetime(1980, 1, 1, 0, 0, 0)
        wb.properties.modified = _datetime.datetime(1980, 1, 1, 0, 0, 0)
    except Exception:  # pragma: no cover - 属性赋值失败不影响数据行
        pass

    # 默认 sheet 用作目录（无章节时不留空表）
    summary = wb.active
    summary.title = "目录"
    summary.append(["章节", "工作表"])
    for idx, section in enumerate(sections):
        sheet_name = _sheet_name(section.title, idx)
        ws = wb.create_sheet(title=sheet_name)
        header = section.header()
        if header:
            ws.append([str(c) if c is not None else "" for c in header])
            for row in section.table_rows():
                ws.append([str(c) if c is not None else "" for c in row])
        for line in section.lines:
            ws.append([line])
        summary.append([section.title, sheet_name])

    buf = io.BytesIO()
    wb.save(buf)
    return _repack_deterministic(buf.getvalue())


def write_xlsx(sections: List[Section], path) -> bytes:
    """渲染并落盘（二进制写，返回字节串供指纹计算）。"""
    data = render_xlsx_bytes(sections)
    with open(path, "wb") as fh:
        fh.write(data)
    return data


def _sheet_name(title: str, idx: int) -> str:
    """XLSX 工作表名：去 Excel 非法字符、限 31 字节、带序号防重名。"""
    cleaned = "".join(ch for ch in title if ch not in '[]:*?/\\')
    cleaned = cleaned.strip() or "sheet"
    base = cleaned[:24]
    return "%d-%s" % (idx + 1, base)


def _repack_deterministic(xlsx: bytes) -> bytes:
    """把 openpyxl 产出的 zip 重打包为确定性 zip。

    逐条目读取原始字节，按固定 date_time / ZIP_STORED / create_system=0
    重写；core.xml 的 ``dcterms:modified`` 在 save 阶段被 openpyxl 用当前
    时刻重打戳（不尊重 Workbook 属性），在此统一替换为固定值。
    """
    src = zipfile.ZipFile(io.BytesIO(xlsx), "r")
    out_buf = io.BytesIO()
    with zipfile.ZipFile(
        out_buf, "w", compression=zipfile.ZIP_STORED
    ) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = _FIX_MODIFIED_RE.sub(_FIXED_MODIFIED_XML, data)
            fixed = zipfile.ZipInfo(info.filename, date_time=_EPOCH_DATE_TIME)
            fixed.compress_type = zipfile.ZIP_STORED
            fixed.create_system = 0
            fixed.external_attr = _EXTERNAL_ATTR
            dst.writestr(fixed, data)
    src.close()
    return out_buf.getvalue()
