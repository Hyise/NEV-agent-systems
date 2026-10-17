"""Parse user-supplied review files without changing their source rows."""

from __future__ import annotations

import csv
import io
import json
import posixpath
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree


COMMENT_SHEET = "评论"
FULL_REVIEW_COLUMN = "分项评论全文"
REQUIRED_TABULAR_COLUMNS = {
    "series_id",
    "series_name",
    "show_id",
    FULL_REVIEW_COLUMN,
    "详情URL",
}

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_PACKAGE_REL_NS = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
_CELL_REFERENCE = re.compile(r"^([A-Z]+)\d+$")


class ReviewImportFileError(ValueError):
    """A user-facing review file parsing error."""


def _decode_csv(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ReviewImportFileError("CSV 文件必须使用 UTF-8 或 GB18030 编码")


def _required_headers(headers: list[str]) -> None:
    if len(set(headers)) != len(headers):
        raise ReviewImportFileError("表格包含重复列名")
    missing = sorted(REQUIRED_TABULAR_COLUMNS - set(headers))
    if missing:
        raise ReviewImportFileError(f"表格缺少必要列：{'、'.join(missing)}")


def _clean_identifier(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _import_item(headers: list[str], values: list[Any], line: int) -> dict[str, Any]:
    original = {
        header: values[index] if index < len(values) else None
        for index, header in enumerate(headers)
    }
    series_id = _clean_identifier(original.get("series_id"))
    series_name = _clean_identifier(original.get("series_name"))
    show_id = _clean_identifier(original.get("show_id"))
    koubei_id = _clean_identifier(original.get("koubei_id"))
    full_review = original.get(FULL_REVIEW_COLUMN)
    source_url = _clean_identifier(original.get("详情URL"))

    if not series_id or not series_name or not show_id:
        raise ReviewImportFileError(f"第 {line} 行缺少车系或评论标识")
    if not isinstance(full_review, str) or not full_review.strip():
        raise ReviewImportFileError(f"第 {line} 行的“{FULL_REVIEW_COLUMN}”为空")

    return {
        "series_id": series_id,
        "series_name": series_name,
        "review_id": koubei_id or show_id,
        "source_url": source_url or None,
        "original_review": original,
    }


def _parse_csv(payload: bytes) -> list[dict[str, Any]]:
    reader = csv.reader(io.StringIO(_decode_csv(payload), newline=""))
    try:
        raw_headers = next(reader)
    except StopIteration as error:
        raise ReviewImportFileError("文件内容为空") from error
    headers = [header.strip() for header in raw_headers]
    _required_headers(headers)
    items: list[dict[str, Any]] = []
    for line, row in enumerate(reader, start=2):
        if not any(value != "" for value in row):
            continue
        if len(row) > len(headers):
            raise ReviewImportFileError(f"第 {line} 行的列数超过表头")
        values: list[Any] = row + [None] * (len(headers) - len(row))
        items.append(_import_item(headers, values, line))
    if not items:
        raise ReviewImportFileError("文件没有可导入的评论")
    return items


def _column_index(reference: str) -> int:
    matched = _CELL_REFERENCE.match(reference)
    if not matched:
        raise ReviewImportFileError("XLSX 单元格地址无效")
    index = 0
    for character in matched.group(1):
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def _xml(archive: zipfile.ZipFile, path: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(archive.read(path))
    except KeyError as error:
        raise ReviewImportFileError("XLSX 文件结构不完整") from error
    except ElementTree.ParseError as error:
        raise ReviewImportFileError("XLSX 文件 XML 无法解析") from error


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _xml(archive, "xl/sharedStrings.xml")
    return [
        "".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    ]


def _sheet_path(archive: zipfile.ZipFile) -> tuple[str, bool]:
    workbook = _xml(archive, "xl/workbook.xml")
    workbook_properties = workbook.find(f"{{{_MAIN_NS}}}workbookPr")
    uses_1904_epoch = (
        workbook_properties is not None
        and workbook_properties.attrib.get("date1904") in {"1", "true", "True"}
    )
    target_relationship = None
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == COMMENT_SHEET:
            target_relationship = sheet.attrib.get(f"{{{_OFFICE_REL_NS}}}id")
            break
    if not target_relationship:
        raise ReviewImportFileError("XLSX 文件缺少“评论”工作表")

    relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
    for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        if relationship.attrib.get("Id") != target_relationship:
            continue
        target = relationship.attrib.get("Target", "")
        if not target:
            break
        normalized = posixpath.normpath(
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.join("xl", target)
        )
        if PurePosixPath(normalized).parts[:1] != ("xl",):
            raise ReviewImportFileError("XLSX 工作表路径无效")
        return normalized, uses_1904_epoch
    raise ReviewImportFileError("XLSX 文件缺少“评论”工作表关系")


def _cell_value(
    cell: ElementTree.Element, shared_strings: list[str]
) -> str | int | float | bool | None:
    cell_type = cell.attrib.get("t", "n")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t")
        )
    value = cell.find(f"{{{_MAIN_NS}}}v")
    raw = value.text if value is not None else None
    if raw is None:
        return None
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (IndexError, ValueError) as error:
            raise ReviewImportFileError("XLSX 共享字符串索引无效") from error
    if cell_type in {"str", "e"}:
        return raw
    if cell_type == "b":
        return raw == "1"
    try:
        number = float(raw)
    except ValueError:
        return raw
    return int(number) if number.is_integer() else number


def _excel_date(value: Any, uses_1904_epoch: bool) -> Any:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    epoch = datetime(1904, 1, 1) if uses_1904_epoch else datetime(1899, 12, 30)
    converted = epoch + timedelta(days=float(value))
    if converted.time() == datetime.min.time():
        return converted.date().isoformat()
    return converted.isoformat(timespec="seconds")


def _xlsx_rows(payload: bytes) -> list[list[Any]]:
    try:
        archive_context = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise ReviewImportFileError("XLSX 文件已损坏或格式不正确") from error
    with archive_context as archive:
        path, uses_1904_epoch = _sheet_path(archive)
        shared = _shared_strings(archive)
        sheet = _xml(archive, path)
        rows: list[list[Any]] = []
        for row in sheet.findall(f".//{{{_MAIN_NS}}}row"):
            indexed: dict[int, Any] = {}
            for cell in row.findall(f"{{{_MAIN_NS}}}c"):
                reference = cell.attrib.get("r", "")
                indexed[_column_index(reference)] = _cell_value(cell, shared)
            if not indexed:
                rows.append([])
                continue
            rows.append([indexed.get(index) for index in range(max(indexed) + 1)])
    if not rows:
        raise ReviewImportFileError("“评论”工作表为空")
    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    _required_headers(headers)
    date_index = headers.index("发表日期") if "发表日期" in headers else None
    if date_index is not None:
        for row in rows[1:]:
            if date_index < len(row):
                row[date_index] = _excel_date(row[date_index], uses_1904_epoch)
    return rows


def _parse_xlsx(payload: bytes) -> list[dict[str, Any]]:
    rows = _xlsx_rows(payload)
    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    items = [
        _import_item(headers, row + [None] * (len(headers) - len(row)), line)
        for line, row in enumerate(rows[1:], start=2)
        if any(value not in (None, "") for value in row)
    ]
    if not items:
        raise ReviewImportFileError("文件没有可导入的评论")
    return items


def _parse_json(payload: bytes, *, lines: bool) -> list[Any]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ReviewImportFileError("JSON 文件必须使用 UTF-8 编码") from error
    if not text.strip():
        raise ReviewImportFileError("文件内容为空")
    try:
        if lines:
            items = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            value = json.loads(text)
            items = value if isinstance(value, list) else [value]
    except json.JSONDecodeError as error:
        raise ReviewImportFileError(f"JSON 格式错误：第 {error.lineno} 行") from error
    if not items:
        raise ReviewImportFileError("文件没有可导入的评论")
    return items


def parse_review_import_file(filename: str, payload: bytes) -> list[Any]:
    """Convert one supported tabular file into the existing import contract."""

    extension = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if extension == ".csv":
        return _parse_csv(payload)
    if extension == ".xlsx":
        return _parse_xlsx(payload)
    if extension == ".json":
        return _parse_json(payload, lines=False)
    if extension == ".jsonl":
        return _parse_json(payload, lines=True)
    raise ReviewImportFileError("仅支持 JSON、JSONL、CSV 或 XLSX 文件")

