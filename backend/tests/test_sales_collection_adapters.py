import json
from pathlib import Path

import httpx
import pytest

from backend.sales_collection.adapters import (
    AutohomeSalesAdapter,
    VerificationRequiredSalesAdapter,
    parse_autohome_sales_page,
)
from backend.sales_collection.domain import (
    SalesAccessVerificationRequired,
    SalesStructureError,
)


FIXTURES = Path(__file__).parent / "fixtures" / "sales"


def test_parse_autohome_sales_page_preserves_source_identity_and_values():
    payload = json.loads((FIXTURES / "autohome-page-1.json").read_text("utf-8"))

    page = parse_autohome_sales_page(
        payload,
        month="2026-01",
        source_url="https://www.autohome.com.cn/rank/1",
        expected_page=1,
    )

    assert page.page_index == 1
    assert page.page_count == 2
    assert [(row.series_id, row.series_name, row.sales_volume, row.rank) for row in page.records] == [
        ("5769", "Model Y", 25000, 1),
        ("5714", "宏光MINIEV", 18000, 2),
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["result"].update(list=[]),
        lambda payload: payload["result"].update(scenesubtitle="2月"),
        lambda payload: payload["result"].update(pageindex=2),
    ],
)
def test_parse_autohome_sales_page_rejects_empty_or_misaligned_payload(mutation):
    payload = json.loads((FIXTURES / "autohome-page-1.json").read_text("utf-8"))
    mutation(payload)

    with pytest.raises(SalesStructureError):
        parse_autohome_sales_page(
            payload,
            month="2026-01",
            source_url="https://www.autohome.com.cn/rank/1",
            expected_page=1,
        )


def test_autohome_adapter_reads_every_page_once_and_hashes_raw_payloads():
    first = json.loads((FIXTURES / "autohome-page-1.json").read_text("utf-8"))
    second = {
        "returncode": 0,
        "result": {
            "pagecount": 2,
            "pageindex": 2,
            "pagesize": 2,
            "scenesubtitle": "1月",
            "list": [
                {
                    "seriesid": "7806",
                    "seriesname": "星愿",
                    "salecount": 15000,
                    "rankNum": 3,
                }
            ],
        },
    }
    requested_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["pageindex"]
        requested_pages.append(page)
        return httpx.Response(200, json=first if page == "1" else second)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = AutohomeSalesAdapter(client=client, sleeper=lambda _seconds: None).fetch_month(
            "2026-01"
        )

    assert requested_pages == ["1", "2"]
    assert len(result.records) == 3
    assert len(result.snapshot_hash) == 64


def test_restricted_platform_adapter_reports_verification_instead_of_faking_data():
    adapter = VerificationRequiredSalesAdapter("易车")

    with pytest.raises(SalesAccessVerificationRequired, match="易车"):
        adapter.fetch_month("2026-01")
