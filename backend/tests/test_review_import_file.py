from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

import pytest

from backend.collection.import_file import (
    ReviewImportFileError,
    parse_review_import_file,
)


HEADERS = [
    "series_id",
    "series_name",
    "koubei_id",
    "show_id",
    "specid",
    "specname",
    "用户名",
    "发表日期",
    "标题",
    "综合评分",
    "最满意",
    "最不满意",
    "分项评论全文",
    "详情URL",
]


def build_shared_string_xlsx(
    *, sheet_name: str = "评论", absolute_sheet_target: bool = False
) -> bytes:
    values = HEADERS + [
        "5769",
        "Model Y",
        "show-1",
        "spec-1",
        "后轮驱动版",
        "研究用户",
        "长期用车",
        "满意内容",
        "不满意内容",
        "最满意：空间宽敞\n续航：高速续航稳定，没有截断。",
        "https://k.autohome.com.cn/detail/view_01.html",
    ]
    shared = "".join(f"<si><t>{escape(value)}</t></si>" for value in values)
    header_cells = "".join(
        f'<c r="{chr(65 + index)}1" t="s"><v>{index}</v></c>'
        for index in range(len(HEADERS))
    )
    row_cells = [
        '<c r="A2" t="s"><v>14</v></c>',
        '<c r="B2" t="inlineStr"><is><t>Model Y</t></is></c>',
        # C2 (koubei_id) intentionally omitted to exercise sparse cells.
        '<c r="D2" t="s"><v>16</v></c>',
        '<c r="E2" t="s"><v>17</v></c>',
        '<c r="F2" t="s"><v>18</v></c>',
        '<c r="G2" t="s"><v>19</v></c>',
        '<c r="H2"><v>45292</v></c>',
        '<c r="I2" t="s"><v>20</v></c>',
        '<c r="J2"><v>4.5</v></c>',
        '<c r="K2" t="s"><v>21</v></c>',
        '<c r="L2" t="s"><v>22</v></c>',
        '<c r="M2" t="s"><v>23</v></c>',
        '<c r="N2" t="s"><v>24</v></c>',
    ]
    payload = io.BytesIO()
    sheet_target = (
        "/xl/worksheets/sheet1.xml"
        if absolute_sheet_target
        else "worksheets/sheet1.xml"
    )
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'''<?xml version="1.0" encoding="UTF-8"?>
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
            </workbook>''',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'''<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{sheet_target}"/>
            </Relationships>''',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f'''<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(values)}" uniqueCount="{len(values)}">{shared}</sst>''',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'''<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1">{header_cells}</row><row r="2">{"".join(row_cells)}</row></sheetData>
            </worksheet>''',
        )
    return payload.getvalue()


def test_csv_import_preserves_full_text_and_complete_source_row():
    full_text = "最满意：后排空间宽敞。\n续航：高速行驶仍然稳定，正文完整保留。"
    csv_text = (
        ",".join(HEADERS)
        + "\r\n"
        + '5769,Model Y,koubei-1,show-1,spec-1,后轮驱动版,研究用户,2026-07-19,长期用车,4.5,空间宽敞,车机一般,"'
        + full_text
        + '",https://k.autohome.com.cn/detail/view_01.html\r\n'
    )

    items = parse_review_import_file("reviews.csv", csv_text.encode("utf-8-sig"))

    assert items == [
        {
            "series_id": "5769",
            "series_name": "Model Y",
            "review_id": "koubei-1",
            "source_url": "https://k.autohome.com.cn/detail/view_01.html",
            "original_review": dict(
                zip(
                    HEADERS,
                    [
                        "5769",
                        "Model Y",
                        "koubei-1",
                        "show-1",
                        "spec-1",
                        "后轮驱动版",
                        "研究用户",
                        "2026-07-19",
                        "长期用车",
                        "4.5",
                        "空间宽敞",
                        "车机一般",
                        full_text,
                        "https://k.autohome.com.cn/detail/view_01.html",
                    ],
                )
            ),
        }
    ]


def test_xlsx_import_keeps_sparse_columns_and_uses_show_id_fallback():
    items = parse_review_import_file("reviews.xlsx", build_shared_string_xlsx())

    assert len(items) == 1
    item = items[0]
    assert item["review_id"] == "show-1"
    assert item["original_review"]["koubei_id"] is None
    assert item["original_review"]["发表日期"] == "2024-01-01"
    assert item["original_review"]["综合评分"] == 4.5
    assert item["original_review"]["分项评论全文"] == (
        "最满意：空间宽敞\n续航：高速续航稳定，没有截断。"
    )


def test_xlsx_import_accepts_absolute_workbook_relationship_target():
    items = parse_review_import_file(
        "reviews.xlsx", build_shared_string_xlsx(absolute_sheet_target=True)
    )

    assert items[0]["series_id"] == "5769"


def test_csv_import_accepts_gb18030_and_reports_missing_required_columns():
    csv_text = "series_id,series_name,show_id,分项评论全文,详情URL\n1,测试车,show-1,完整正文,https://example.test/1\n"
    items = parse_review_import_file("reviews.csv", csv_text.encode("gb18030"))
    assert items[0]["original_review"]["分项评论全文"] == "完整正文"

    invalid = "series_id,series_name\n1,测试车\n".encode("utf-8")
    with pytest.raises(ReviewImportFileError, match="缺少必要列"):
        parse_review_import_file("invalid.csv", invalid)


def test_xlsx_import_requires_comment_sheet():
    with pytest.raises(ReviewImportFileError, match="评论.*工作表"):
        parse_review_import_file(
            "reviews.xlsx", build_shared_string_xlsx(sheet_name="抓取信息")
        )


@pytest.mark.parametrize(
    "filename,payload",
    [
        (
            "reviews.json",
            b'[{"series_id":"1","series_name":"A","original_review":{"feeling_summary":"ok"}}]',
        ),
        (
            "reviews.jsonl",
            b'{"series_id":"1","series_name":"A","original_review":{"feeling_summary":"ok"}}\n',
        ),
    ],
)
def test_json_and_jsonl_file_imports_remain_compatible(filename, payload):
    items = parse_review_import_file(filename, payload)

    assert items[0]["series_id"] == "1"
    assert items[0]["original_review"] == {"feeling_summary": "ok"}

