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
    CatalogDiscoveryCancelled,
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


class FakeBody:
    def inner_text(self, timeout):
        assert timeout == 5_000
        return "新能源汽车"


class FakePage:
    def __init__(self, rounds):
        self.rounds = rounds
        self.round_index = 0
        self.scroll_calls = 0
        self.goto_calls = 0
        self.url = "https://www.autohome.com.cn/price/ev#pvareaid=3311257"

    def goto(self, url, wait_until, timeout):
        self.goto_calls += 1
        assert url == self.url
        assert wait_until == "domcontentloaded"
        assert timeout == 20_000
        return type("Response", (), {"status": 200})()

    def locator(self, selector):
        assert selector == "body"
        return FakeBody()

    def eval_on_selector_all(self, selector, script):
        assert selector != "a[href]"
        assert "data-series-name" in script
        return self.rounds[min(self.round_index, len(self.rounds) - 1)]

    def evaluate(self, script):
        if "navigator.userAgent" in script:
            return "test-agent"
        assert "scrollTo" in script
        self.scroll_calls += 1
        self.round_index += 1

    def wait_for_timeout(self, milliseconds):
        assert milliseconds == 800


class FakeContext:
    def __init__(self, page):
        self.page = page

    def route(self, pattern, handler):
        assert pattern == "**/*"
        assert callable(handler)

    def new_page(self):
        return self.page

    def cookies(self):
        return [{"name": "session", "value": "fixture"}]


class FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.closed = False

    def new_context(self, locale):
        assert locale == "zh-CN"
        return FakeContext(self.page)

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, page):
        self.chromium = self
        self.page = page

    def launch(self, headless):
        assert headless is True
        return FakeBrowser(self.page)


class FakePlaywrightManager:
    def __init__(self, page):
        self.playwright = FakePlaywright(page)

    def __enter__(self):
        return self.playwright

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def discovery_adapter(rounds):
    page = FakePage(rounds)
    adapter = AutohomeCatalogAdapter(
        playwright_factory=lambda: FakePlaywrightManager(page)
    )
    return adapter, page


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
        ("8627", "传祺越7"),
        ("5769", "Model Y"),
        ("6762", "海鸥"),
    ]


def test_catalog_dom_extraction_ignores_non_series_links_before_quality_metrics():
    class CurrentPage:
        def eval_on_selector_all(self, selector, script):
            return [
                {"href": "/8627/#pvareaid=6861421", "name": "传祺越7"},
                {"href": "/price/ev#filters", "name": "筛选"},
                {"href": "https://www.autohome.com.cn/news/", "name": "资讯"},
                {"href": "/8584/#pvareaid=6861421", "name": "ID.AURA T6"},
            ]

    links = AutohomeCatalogAdapter._read_links(CurrentPage())

    assert [(link.href, link.name) for link in links] == [
        ("/8627/#pvareaid=6861421", "传祺越7"),
        ("/8584/#pvareaid=6861421", "ID.AURA T6"),
    ]


def test_discovery_cancelled_before_start_does_not_launch_browser():
    factory_called = False

    def factory():
        nonlocal factory_called
        factory_called = True
        raise AssertionError("browser must not launch")

    adapter = AutohomeCatalogAdapter(playwright_factory=factory)

    with pytest.raises(CatalogDiscoveryCancelled):
        adapter.discover_series(1000, should_cancel=lambda: True)

    assert factory_called is False


def test_discovery_cancelled_after_page_creation_does_not_navigate():
    adapter, page = discovery_adapter([[{"href": "/5769/", "name": "Model Y"}]])
    checks = iter((False, True))

    with pytest.raises(CatalogDiscoveryCancelled):
        adapter.discover_series(1000, should_cancel=lambda: next(checks))

    assert page.goto_calls == 0


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


def test_discovery_reports_new_unique_series_in_first_seen_order():
    adapter, _ = discovery_adapter(
        [
            [
                {"href": "/5769/", "name": "Model Y"},
                {"href": "/5769/", "name": "Model Y 2025款"},
            ],
            [
                {"href": "/5769/", "name": "Model Y"},
                {"href": "/5769/", "name": "Model Y 2025款"},
                {"href": "/6762/", "name": "海鸥"},
            ],
        ]
    )
    batches = []

    result = adapter.discover_series(
        2,
        on_batch=lambda items, scanned, skipped, page: batches.append(
            ([item.series_id for item in items], scanned, skipped, page)
        ),
    )

    assert [(item.series_id, item.discovery_rank) for item in result.series] == [
        ("5769", 1),
        ("6762", 2),
    ]
    assert batches == [(["5769"], 2, 0, 1), (["6762"], 3, 0, 2)]
    assert result.scanned_count == 3
    assert result.skipped_count == 0
    assert result.source_exhausted is False


def test_discovery_scans_past_duplicates_until_1000_unique_series():
    first = [
        {"href": f"/{5000 + index}/", "name": f"车系 {index}"}
        for index in range(500)
    ]
    second = [
        *first,
        {"href": "/5000/", "name": "车系 0 另一个年款"},
        *[
            {"href": f"/{5500 + index}/", "name": f"车系 {500 + index}"}
            for index in range(500)
        ],
    ]
    adapter, page = discovery_adapter([first, second])

    result = adapter.discover_series(1000)

    assert len(result.series) == 1000
    assert result.series[-1].discovery_rank == 1000
    assert result.series[-1].series_id == "5999"
    assert result.scanned_count == 1001
    assert page.scroll_calls == 1
    assert result.source_exhausted is False


def test_discovery_marks_normal_source_exhaustion():
    adapter, page = discovery_adapter(
        [[{"href": "/5769/", "name": "Model Y"}]]
    )

    result = adapter.discover_series(1000)

    assert [item.series_id for item in result.series] == ["5769"]
    assert result.source_exhausted is True
    assert page.scroll_calls == 5


def test_discovery_cancels_before_the_next_scroll():
    adapter, page = discovery_adapter(
        [
            [{"href": "/5769/", "name": "Model Y"}],
            [
                {"href": "/5769/", "name": "Model Y"},
                {"href": "/6762/", "name": "海鸥"},
            ],
        ]
    )
    cancelled = False

    def on_batch(items, scanned, skipped, load_round):
        nonlocal cancelled
        assert [item.series_id for item in items] == ["5769"]
        assert (scanned, skipped, load_round) == (1, 0, 1)
        cancelled = True

    with pytest.raises(CatalogDiscoveryCancelled):
        adapter.discover_series(
            1000, on_batch=on_batch, should_cancel=lambda: cancelled
        )

    assert page.scroll_calls == 0


def test_nonempty_round_with_zero_valid_entries_fails():
    adapter, page = discovery_adapter(
        [
            [{"href": "/5769/", "name": ""}],
            [{"href": "/5769/", "name": "Model Y"}],
        ]
    )

    with pytest.raises(AutohomeStructureError, match="没有有效车系"):
        adapter.discover_series(1000)

    assert page.scroll_calls == 0


def test_required_field_failure_rate_over_five_percent_after_one_hundred_items_fails():
    candidates = [
        {"href": f"/{5000 + index}/", "name": f"车系 {index}"}
        for index in range(94)
    ]
    candidates.extend(
        {"href": f"/{6000 + index}/", "name": ""}
        for index in range(6)
    )
    adapter, page = discovery_adapter([candidates])

    with pytest.raises(AutohomeStructureError, match="缺失率"):
        adapter.discover_series(1000)

    assert page.scroll_calls == 0


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


def test_review_detail_html_replaces_truncated_contents_with_complete_text():
    payload = fixture_json("reviews-page-1.json")
    item = payload["result"]["list"][0]
    item["contents"] = [
        {"structuredid": 1, "structuredname": "满意", "content": "第一段完整..."},
        {"structuredid": 2, "structuredname": "不满意", "content": "完整的不..."},
    ]
    review = parse_review_page(model_y(), payload, page_index=1).reviews[0]

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/detail/view_show-2024.html"
        return httpx.Response(
            200,
            text=(FIXTURES / "review-detail.html").read_text(encoding="utf-8"),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AutohomeReviewAdapter(BrowserSession({}, "test-agent"), client=client)

    complete = adapter.fetch_detail(review)

    assert complete.source_url == (
        "https://k.autohome.com.cn/detail/view_show-2024.html"
    )
    assert complete.original_review["contents"][:2] == [
        {
            "structuredid": 1,
            "structuredname": "满意",
            "content": "第一段完整内容。\n第二段 & 后续内容。",
        },
        {
            "structuredid": 2,
            "structuredname": "不满意",
            "content": "完整的不满意内容。",
        },
    ]
    assert complete.content_hash != review.content_hash


def test_review_detail_html_appends_every_nonempty_section_in_dom_order():
    payload = fixture_json("reviews-page-1.json")
    item = payload["result"]["list"][0]
    item["contents"] = [
        {
            "structuredid": 1,
            "structuredname": "满意",
            "content": "第一段完整...",
            "sourceField": "kept",
        },
        {"structuredid": 2, "structuredname": "不满意", "content": "完整的不..."},
    ]
    review = parse_review_page(model_y(), payload, page_index=1).reviews[0]
    detail_html = (FIXTURES / "review-detail.html").read_text(encoding="utf-8")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=detail_html,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        )
    )
    adapter = AutohomeReviewAdapter(BrowserSession({}, "test-agent"), client=client)

    complete = adapter.fetch_detail(review)

    assert [section["structuredname"] for section in complete.original_review["contents"]] == [
        "满意",
        "不满意",
        "空间",
        "驾驶感受",
        "续航",
        "外观",
        "内饰",
        "性价比",
        "智能化",
    ]
    assert complete.original_review["contents"][0] == {
        "structuredid": 1,
        "structuredname": "满意",
        "content": "第一段完整内容。\n第二段 & 后续内容。",
        "sourceField": "kept",
    }
    assert complete.original_review["contents"][2:] == [
        {"structuredname": "空间", "content": "后排空间宽敞，储物位置充足。"},
        {"structuredname": "驾驶感受", "content": "底盘稳定，转向轻盈。"},
        {"structuredname": "续航", "content": "日常通勤续航表现稳定。"},
        {"structuredname": "外观", "content": "车身线条简洁，造型耐看。"},
        {"structuredname": "内饰", "content": "座椅舒适，储物设计合理。"},
        {"structuredname": "性价比", "content": "同价位配置完整，用车成本较低。"},
        {"structuredname": "智能化", "content": "车机流畅，辅助功能容易使用。"},
    ]


def test_review_detail_requires_a_valid_show_id():
    payload = fixture_json("reviews-page-1.json")
    payload["result"]["list"][0].pop("showId")
    review = parse_review_page(model_y(), payload, page_index=1).reviews[0]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=(FIXTURES / "review-detail.html").read_text(encoding="utf-8"),
                headers={"content-type": "text/html"},
            )
        )
    )
    adapter = AutohomeReviewAdapter(BrowserSession({}, "test-agent"), client=client)

    with pytest.raises(AutohomeStructureError, match="showId"):
        adapter.fetch_detail(review)


def test_truncated_section_missing_from_detail_html_fails_explicitly():
    payload = fixture_json("reviews-page-1.json")
    item = payload["result"]["list"][0]
    item["contents"] = [
        {"structuredid": 3, "structuredname": "动力", "content": "加速很..."}
    ]
    review = parse_review_page(model_y(), payload, page_index=1).reviews[0]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=(FIXTURES / "review-detail.html").read_text(encoding="utf-8"),
                headers={"content-type": "text/html"},
            )
        )
    )
    adapter = AutohomeReviewAdapter(BrowserSession({}, "test-agent"), client=client)

    with pytest.raises(AutohomeStructureError, match="动力"):
        adapter.fetch_detail(review)


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
