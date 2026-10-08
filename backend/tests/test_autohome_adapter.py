import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from backend.collection.autohome import (
    AutohomeAccessPaused,
    AutohomeCatalogAdapter,
    AutohomeReviewAdapter,
    AutohomeStructureError,
    BrowserSession,
    CatalogLink,
    ensure_allowed_url,
    extract_catalog_series,
    parse_review_page,
)
from backend.collection.domain import VehicleSeries

FIXTURES = Path(__file__).parent / "fixtures/autohome"


def fixture_json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FixtureLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            values = dict(attrs)
            self.current = {"href": values.get("href", ""), "name": values.get("title", "")}

    def handle_data(self, data):
        if self.current is not None and not self.current["name"]:
            self.current["name"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.current["name"] = self.current["name"].strip()
            self.links.append(self.current)
            self.current = None


def model_y():
    return VehicleSeries(
        series_id="5769",
        series_name="Model Y",
        series_url="https://www.autohome.com.cn/5769/",
        review_url="https://k.autohome.com.cn/5769/",
        discovery_rank=1,
    )


def test_catalog_deduplicates_years_and_requires_name():
    links = [
        CatalogLink("https://www.autohome.com.cn/5769/", "Model Y"),
        CatalogLink("https://www.autohome.com.cn/5769/", "Model Y 2025款"),
        CatalogLink("https://k.autohome.com.cn/5769/", "Model Y 长续航版"),
        CatalogLink("/6762/", "海鸥"),
        CatalogLink("/7806/", ""),
    ]

    series = extract_catalog_series(links, max_series=500)

    assert [(item.series_id, item.series_name) for item in series] == [
        ("5769", "Model Y"),
        ("6762", "海鸥"),
    ]


def test_catalog_keeps_discovery_order_and_stops_at_limit():
    links = [
        CatalogLink("/8584/", "ID.AURA T6"),
        CatalogLink("/8627/", "传祺向往S7"),
        CatalogLink("/8283/", "华境S"),
    ]

    series = extract_catalog_series(links, max_series=2)

    assert [(item.series_id, item.discovery_rank) for item in series] == [
        ("8584", 1),
        ("8627", 2),
    ]


def test_catalog_fixture_exercises_scoped_dom_extraction():
    parser = FixtureLinkParser()
    parser.feed((FIXTURES / "ev-catalog.html").read_text(encoding="utf-8"))

    class FixturePage:
        def eval_on_selector_all(self, selector, script):
            assert selector != "a[href]"
            assert "main" in selector or "article" in selector
            assert "data-series-name" in script
            return parser.links

    links = AutohomeCatalogAdapter._read_links(FixturePage())
    series = extract_catalog_series(links, max_series=500)

    assert [(item.series_id, item.series_name) for item in series] == [
        ("5769", "Model Y"),
        ("6762", "海鸥"),
    ]


def test_catalog_page_identity_rejects_redirects_and_verification_pages():
    class Body:
        def __init__(self, text):
            self.text = text

        def inner_text(self, timeout):
            assert timeout == 5_000
            return self.text

    class Page:
        def __init__(self, url, text):
            self.url = url
            self.text = text

        def locator(self, selector):
            assert selector == "body"
            return Body(self.text)

    response = type("Response", (), {"status": 200})()
    AutohomeCatalogAdapter._validate_catalog_page(
        Page("https://www.autohome.com.cn/price/ev#pvareaid=3311257", "新能源汽车"),
        response,
    )

    with pytest.raises(AutohomeAccessPaused, match="非预期"):
        AutohomeCatalogAdapter._validate_catalog_page(
            Page("https://www.autohome.com.cn/login/", "新能源汽车"), response
        )
    with pytest.raises(AutohomeAccessPaused, match="验证"):
        AutohomeCatalogAdapter._validate_catalog_page(
            Page("https://www.autohome.com.cn/price/ev", "请完成安全检查"), response
        )


def test_review_request_uses_series_id_yearid_zero_and_page_size_twenty():
    observed = {}

    def handler(request):
        observed["host"] = request.url.host
        observed["query"] = parse_qs(request.url.query.decode())
        return httpx.Response(200, json=fixture_json("reviews-page-1.json"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AutohomeReviewAdapter(BrowserSession({}, "test-agent"), client=client)

    page = adapter.fetch_page(model_y(), page_index=1)

    assert observed == {
        "host": "koubeiipv6.app.autohome.com.cn",
        "query": {
            "pm": ["3"],
            "seriesId": ["5769"],
            "pageIndex": ["1"],
            "pageSize": ["20"],
            "yearid": ["0"],
            "ge": ["0"],
            "seriesSummaryKey": ["0"],
            "order": ["0"],
        },
    }
    assert len(page.reviews) == 2


def test_review_page_keeps_complete_original_objects():
    payload = fixture_json("reviews-page-1.json")

    page = parse_review_page(model_y(), payload, page_index=1)

    assert page.total == 2
    assert page.reviews[0].original_review == payload["result"]["list"][0]
    assert page.reviews[0].original_review["unknownField"] == {
        "keep": [1, "中文", None]
    }
    assert {review.series_id for review in page.reviews} == {"5769"}
    assert {review.series_name for review in page.reviews} == {"Model Y"}
    assert page.page_size == 20
    assert page.page_count == 1


def test_review_page_validates_server_pagination_and_series_identity():
    payload = fixture_json("reviews-page-1.json")
    payload["result"]["seriesid"] = 9999
    with pytest.raises(AutohomeStructureError, match="车系"):
        parse_review_page(model_y(), payload, page_index=1)

    payload = fixture_json("reviews-page-1.json")
    payload["result"]["pageindex"] = 2
    with pytest.raises(AutohomeStructureError, match="页码"):
        parse_review_page(model_y(), payload, page_index=1)


def test_missing_source_id_fallback_is_scoped_to_series():
    payload = fixture_json("reviews-page-1.json")
    item = payload["result"]["list"][0]
    item.pop("Koubeiid")
    item.pop("showId")
    payload["result"]["list"] = [item]
    payload["result"]["rowcount"] = 1

    first = parse_review_page(model_y(), payload, page_index=1).reviews[0]
    other = model_y().model_copy(
        update={
            "series_id": "6762",
            "series_name": "海鸥",
            "series_url": "https://www.autohome.com.cn/6762/",
            "review_url": "https://k.autohome.com.cn/6762/",
        }
    )
    other_payload = json.loads(json.dumps(payload, ensure_ascii=False))
    other_payload["result"]["seriesid"] = 6762
    second = parse_review_page(other, other_payload, page_index=1).reviews[0]

    assert first.review_id != second.review_id
    assert first.review_id.startswith("sha256-5769-")
    assert second.review_id.startswith("sha256-6762-")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"returncode": 1, "message": "failed", "result": {}},
        {"returncode": 0, "result": {"rowcount": 1}},
        {"returncode": 0, "result": {"rowcount": 1, "list": "not-a-list"}},
        {"returncode": 0, "result": {"rowcount": 1, "list": [{}]}},
    ],
)
def test_unknown_or_missing_review_shape_fails_explicitly(payload):
    with pytest.raises(AutohomeStructureError):
        parse_review_page(model_y(), payload, page_index=1)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.autohome.com.cn/5769/",
        "https://k.autohome.com.cn/5769/",
        "https://koubeiipv6.app.autohome.com.cn/pc/series/list",
    ],
)
def test_only_autohome_hosts_are_allowed(url):
    assert ensure_allowed_url(url) == url

    with pytest.raises(ValueError):
        ensure_allowed_url("https://example.com/5769/")
    with pytest.raises(ValueError):
        ensure_allowed_url("http://www.autohome.com.cn/5769/")
