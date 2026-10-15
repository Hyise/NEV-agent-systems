"""Automotive Home source adapters with a fixed, auditable access boundary."""

import re
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from .domain import (
    CollectedReview,
    ReviewPage,
    VehicleSeries,
    canonical_review_hash,
)

AUTOHOME_CATALOG_URL = "https://www.autohome.com.cn/price/ev#pvareaid=3311257"
AUTOHOME_REVIEW_API_URL = "https://koubeiipv6.app.autohome.com.cn/pc/series/list"
AUTOHOME_REVIEW_DETAIL_URL = "https://k.autohome.com.cn/detail/view_{show_id}.html"
CATALOG_LINK_SELECTOR = (
    "main a[href], article a[href], [data-series-id] a[href], "
    "[class*='series'] a[href], [class*='car-list'] a[href]"
)
ALLOWED_HOSTS = frozenset(
    {
        "www.autohome.com.cn",
        "k.autohome.com.cn",
        "koubeiipv6.app.autohome.com.cn",
    }
)


class AutohomeSourceError(RuntimeError):
    """Base error for source access and structure failures."""


class AutohomeStructureError(AutohomeSourceError):
    """The source response no longer matches the verified contract."""


class AutohomeAccessPaused(AutohomeSourceError):
    """The source asked the collector to stop or verify access."""


class CatalogDiscoveryCancelled(AutohomeSourceError):
    """Catalog discovery was cancelled at a source-operation boundary."""


@dataclass(frozen=True)
class BrowserSession:
    cookies: dict[str, str]
    user_agent: str


@dataclass(frozen=True)
class CatalogLink:
    href: str
    name: str


@dataclass(frozen=True)
class CatalogDiscoveryResult:
    series: list[VehicleSeries]
    session: BrowserSession
    scanned_count: int = 0
    skipped_count: int = 0
    source_exhausted: bool = False


class _ReviewDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[tuple[str, str]] = []
        self._section_depth = 0
        self._title_parts: list[str] = []
        self._content_parts: list[str] = []
        self._in_title = False
        self._in_content = False

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        values = dict(attrs).get("class") or ""
        return set(values.split())

    @staticmethod
    def _section_name(value: str) -> str:
        compact = "".join(value.split())
        compact = re.sub(r"\d+(?:\.\d+)?$", "", compact)
        return {"最满意": "满意", "最不满意": "不满意"}.get(compact, compact)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if tag == "div":
            if self._section_depth:
                self._section_depth += 1
            elif {"space", "kb-item"}.issubset(classes):
                self._section_depth = 1
                self._title_parts = []
                self._content_parts = []
        if not self._section_depth:
            return
        if tag == "h1":
            self._in_title = True
        elif tag == "p" and "kb-item-msg" in classes:
            self._in_content = True
        elif tag == "br" and self._in_content:
            self._content_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self._section_depth:
            return
        if tag == "h1":
            self._in_title = False
        elif tag == "p":
            self._in_content = False
        if tag == "div":
            self._section_depth -= 1
            if self._section_depth == 0:
                name = self._section_name("".join(self._title_parts))
                content = "".join(self._content_parts).replace("\r\n", "\n").strip()
                if name and content:
                    self.sections.append((name, content))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_content:
            self._content_parts.append(data)


def _review_detail_url(review: CollectedReview) -> str:
    show_id = str(review.original_review.get("showId") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", show_id):
        raise AutohomeStructureError("汽车之家口碑记录缺少有效showId")
    return ensure_allowed_url(AUTOHOME_REVIEW_DETAIL_URL.format(show_id=show_id))


def _complete_review_from_html(
    review: CollectedReview, detail_url: str, html: str
) -> CollectedReview:
    parser = _ReviewDetailParser()
    parser.feed(html)
    original = deepcopy(review.original_review)
    contents = original.get("contents")
    if not isinstance(contents, list):
        raise AutohomeStructureError("汽车之家口碑记录缺少contents列表")
    remaining: list[dict[str, Any]] = []
    for section in contents:
        if not isinstance(section, dict):
            raise AutohomeStructureError("汽车之家口碑contents包含无效分区")
        remaining.append(section)

    merged: list[dict[str, Any]] = []
    for name, complete in parser.sections:
        match_index = next(
            (
                index
                for index, section in enumerate(remaining)
                if _ReviewDetailParser._section_name(
                    str(section.get("structuredname") or "")
                )
                == name
            ),
            None,
        )
        if match_index is None:
            merged.append({"structuredname": name, "content": complete})
            continue
        section = remaining.pop(match_index)
        section["content"] = complete
        merged.append(section)

    for section in remaining:
        name = str(section.get("structuredname") or "").strip()
        current = str(section.get("content") or "").rstrip()
        if current.endswith(("...", "…")):
            raise AutohomeStructureError(f"详情页缺少完整的{name or '评论'}正文")
        merged.append(section)
    original["contents"] = merged
    return CollectedReview(
        platform=review.platform,
        review_id=review.review_id,
        series_id=review.series_id,
        series_name=review.series_name,
        source_url=detail_url,
        original_review=original,
    )


def ensure_allowed_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("只允许访问已配置的汽车之家HTTPS地址")
    return url


def _series_id_from_href(href: str) -> str | None:
    if href.startswith("/"):
        path = urlparse("https://www.autohome.com.cn" + href).path
    else:
        try:
            ensure_allowed_url(href)
        except ValueError:
            return None
        path = urlparse(href).path
    parts = [part for part in path.split("/") if part]
    if len(parts) != 1 or not parts[0].isdigit():
        return None
    return parts[0]


def extract_catalog_series(
    links: Iterable[CatalogLink], max_series: int
) -> list[VehicleSeries]:
    result: list[VehicleSeries] = []
    seen: set[str] = set()
    for link in links:
        series_id = _series_id_from_href(link.href)
        name = " ".join(link.name.split())
        if not series_id or not name or series_id in seen:
            continue
        seen.add(series_id)
        result.append(
            VehicleSeries(
                series_id=series_id,
                series_name=name,
                series_url=f"https://www.autohome.com.cn/{series_id}/",
                review_url=f"https://k.autohome.com.cn/{series_id}/",
                discovery_rank=len(result) + 1,
            )
        )
        if len(result) >= max_series:
            break
    return result


def parse_review_page(
    series: VehicleSeries, payload: dict[str, Any], page_index: int
) -> ReviewPage:
    if payload.get("returncode") != 0:
        raise AutohomeStructureError("汽车之家口碑接口返回失败状态")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AutohomeStructureError("汽车之家口碑响应缺少result对象")
    items = result.get("list")
    total = result.get("rowcount")
    page_size = result.get("pagesize")
    page_count = result.get("pagecount")
    response_page = result.get("pageindex")
    response_series = result.get("seriesid")
    integers = (total, page_size, page_count, response_page)
    if (
        not isinstance(items, list)
        or any(isinstance(value, bool) or not isinstance(value, int) for value in integers)
        or total < 0
        or page_size < 1
        or page_count < 0
        or response_page < 1
    ):
        raise AutohomeStructureError("汽车之家口碑响应缺少有效的list或rowcount")
    if str(response_series) != series.series_id:
        raise AutohomeStructureError("汽车之家口碑响应车系与请求不一致")
    if response_page != page_index:
        raise AutohomeStructureError("汽车之家口碑响应页码与请求不一致")
    if total > 0 and page_count < 1:
        raise AutohomeStructureError("汽车之家口碑响应分页总数无效")
    reviews: list[CollectedReview] = []
    for item in items:
        if not isinstance(item, dict) or not item:
            raise AutohomeStructureError("汽车之家口碑列表包含无效记录")
        source_id = item.get("Koubeiid") or item.get("showId")
        review_id = str(source_id).strip() if source_id is not None else ""
        if not review_id:
            review_id = f"sha256-{series.series_id}-{canonical_review_hash(item)}"
        reviews.append(
            CollectedReview(
                review_id=review_id,
                series_id=series.series_id,
                series_name=series.series_name,
                source_url=f"{series.review_url}#{review_id}",
                original_review=item,
            )
        )
    return ReviewPage(
        series=series,
        page_index=page_index,
        page_size=page_size,
        page_count=page_count,
        total=total,
        reviews=reviews,
    )


class AutohomeCatalogAdapter:
    def __init__(self, playwright_factory: Callable[[], Any] | None = None):
        self._playwright_factory = playwright_factory

    def _factory(self):
        if self._playwright_factory is not None:
            return self._playwright_factory
        from playwright.sync_api import sync_playwright

        return sync_playwright

    @staticmethod
    def _read_links(page) -> list[CatalogLink]:
        values = page.eval_on_selector_all(
            CATALOG_LINK_SELECTOR,
            """
            elements => elements.map(anchor => {
              const image = anchor.querySelector('img');
              const card = anchor.closest('li, article, [class*="item"], [class*="card"]');
              const heading = card && card.querySelector('h2, h3, h4, [class*="name"], [class*="title"]');
              const name = anchor.getAttribute('data-series-name')
                || anchor.getAttribute('title')
                || (image && image.getAttribute('alt'))
                || anchor.textContent
                || (heading && heading.textContent)
                || '';
              return { href: anchor.getAttribute('href') || '', name: name.trim() };
            })
            """,
        )
        links = [
            CatalogLink(str(value["href"]), str(value["name"])) for value in values
        ]
        return [link for link in links if _series_id_from_href(link.href)]

    @staticmethod
    def _guard_browser_requests(context) -> None:
        def handle(route) -> None:
            request = route.request
            parsed = urlparse(request.url)
            host = (parsed.hostname or "").casefold()
            if request.resource_type == "document":
                allowed = parsed.scheme == "https" and host == "www.autohome.com.cn"
            else:
                allowed = parsed.scheme in {"data", "blob"} or (
                    parsed.scheme == "https"
                    and (
                        host in {"autohome.com.cn", "autoimg.cn"}
                        or host.endswith((".autohome.com.cn", ".autoimg.cn"))
                    )
                )
            route.continue_() if allowed else route.abort()

        context.route("**/*", handle)

    @staticmethod
    def _validate_catalog_page(page, response) -> None:
        if response is None or response.status >= 400:
            raise AutohomeAccessPaused("汽车之家新能源汽车目录访问失败，任务已暂停")
        final_url = ensure_allowed_url(page.url)
        parsed = urlparse(final_url)
        if parsed.hostname != "www.autohome.com.cn" or parsed.path.rstrip("/") != "/price/ev":
            raise AutohomeAccessPaused("汽车之家目录跳转到非预期页面，任务已暂停")
        body_text = str(page.locator("body").inner_text(timeout=5_000))
        if "新能源" not in body_text:
            raise AutohomeAccessPaused("汽车之家目录页面需要验证或结构发生变化，任务已暂停")

    @staticmethod
    def _session(context, page) -> BrowserSession:
        cookies = {
            str(cookie["name"]): str(cookie["value"])
            for cookie in context.cookies()
            if cookie.get("name")
        }
        user_agent = str(page.evaluate("() => navigator.userAgent"))
        return BrowserSession(cookies=cookies, user_agent=user_agent)

    def discover_series(
        self,
        max_series: int,
        on_batch: Callable[[list[VehicleSeries], int, int, int], None]
        | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> CatalogDiscoveryResult:
        ensure_allowed_url(AUTOHOME_CATALOG_URL)
        if should_cancel is not None and should_cancel():
            raise CatalogDiscoveryCancelled("车系发现已取消")
        with self._factory()() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(locale="zh-CN")
                self._guard_browser_requests(context)
                page = context.new_page()
                if should_cancel is not None and should_cancel():
                    raise CatalogDiscoveryCancelled("车系发现已取消")
                response = page.goto(
                    AUTOHOME_CATALOG_URL,
                    wait_until="domcontentloaded",
                    timeout=20_000,
                )
                self._validate_catalog_page(page, response)
                if should_cancel is not None and should_cancel():
                    raise CatalogDiscoveryCancelled("车系发现已取消")
                found: list[VehicleSeries] = []
                seen_series: set[str] = set()
                seen_candidates: set[tuple[str, str]] = set()
                scanned_count = 0
                skipped_count = 0
                unchanged_rounds = 0
                load_round = 1
                while len(found) < max_series and unchanged_rounds < 5:
                    if should_cancel is not None and should_cancel():
                        raise CatalogDiscoveryCancelled("车系发现已取消")
                    new_entries: list[VehicleSeries] = []
                    links = self._read_links(page)
                    structurally_valid = sum(
                        1
                        for link in links
                        if _series_id_from_href(link.href)
                        and " ".join(link.name.split())
                    )
                    if links and structurally_valid == 0:
                        raise AutohomeStructureError(
                            "新能源汽车目录非空但没有有效车系"
                        )
                    for link in links:
                        name = " ".join(link.name.split())
                        candidate_key = (link.href.strip(), name)
                        if candidate_key in seen_candidates:
                            continue
                        seen_candidates.add(candidate_key)
                        scanned_count += 1
                        series_id = _series_id_from_href(link.href)
                        if not series_id or not name:
                            skipped_count += 1
                            continue
                        if series_id in seen_series:
                            continue
                        seen_series.add(series_id)
                        item = VehicleSeries(
                            series_id=series_id,
                            series_name=name,
                            series_url=f"https://www.autohome.com.cn/{series_id}/",
                            review_url=f"https://k.autohome.com.cn/{series_id}/",
                            discovery_rank=len(found) + 1,
                        )
                        found.append(item)
                        new_entries.append(item)
                        if len(found) >= max_series:
                            break
                    if new_entries and on_batch is not None:
                        on_batch(
                            new_entries,
                            scanned_count,
                            skipped_count,
                            load_round,
                        )
                    if (
                        scanned_count >= 100
                        and skipped_count / scanned_count > 0.05
                    ):
                        raise AutohomeStructureError(
                            "新能源汽车目录必填字段缺失率超过5%"
                        )
                    if should_cancel is not None and should_cancel():
                        raise CatalogDiscoveryCancelled("车系发现已取消")
                    unchanged_rounds = 0 if new_entries else unchanged_rounds + 1
                    if len(found) >= max_series or unchanged_rounds >= 5:
                        break
                    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(800)
                    load_round += 1
                if not found:
                    raise AutohomeStructureError("新能源汽车目录中没有发现有效车系")
                return CatalogDiscoveryResult(
                    found,
                    self._session(context, page),
                    scanned_count=scanned_count,
                    skipped_count=skipped_count,
                    source_exhausted=len(found) < max_series,
                )
            finally:
                browser.close()

    def discover(self, max_series: int) -> CatalogDiscoveryResult:
        return self.discover_series(max_series)

    def open_session(self) -> BrowserSession:
        ensure_allowed_url(AUTOHOME_CATALOG_URL)
        with self._factory()() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(locale="zh-CN")
                self._guard_browser_requests(context)
                page = context.new_page()
                response = page.goto(
                    AUTOHOME_CATALOG_URL,
                    wait_until="domcontentloaded",
                    timeout=20_000,
                )
                self._validate_catalog_page(page, response)
                return self._session(context, page)
            finally:
                browser.close()


class AutohomeReviewAdapter:
    def __init__(self, session: BrowserSession, client: httpx.Client | None = None):
        ensure_allowed_url(AUTOHOME_REVIEW_API_URL)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            headers={"User-Agent": session.user_agent, "Accept": "application/json"},
            cookies=session.cookies,
            timeout=20,
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_detail(self, review: CollectedReview) -> CollectedReview:
        detail_url = _review_detail_url(review)
        response = self._client.get(detail_url)
        if response.status_code in (403, 429):
            raise AutohomeAccessPaused(
                f"汽车之家返回HTTP {response.status_code}，任务已暂停"
            )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.casefold():
            raise AutohomeAccessPaused("汽车之家口碑详情返回了非HTML验证页面，任务已暂停")
        return _complete_review_from_html(review, detail_url, response.text)

    def fetch_page(
        self, series: VehicleSeries, page_index: int, page_size: int = 20
    ) -> ReviewPage:
        ensure_allowed_url(series.review_url)
        response = self._client.get(
            AUTOHOME_REVIEW_API_URL,
            params={
                "pm": 3,
                "seriesId": series.series_id,
                "pageIndex": page_index,
                "pageSize": page_size,
                "yearid": 0,
                "ge": 0,
                "seriesSummaryKey": 0,
                "order": 0,
            },
        )
        if response.status_code in (403, 429):
            raise AutohomeAccessPaused(f"汽车之家返回HTTP {response.status_code}，任务已暂停")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.casefold():
            raise AutohomeAccessPaused("汽车之家返回了非JSON验证页面，任务已暂停")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AutohomeStructureError("汽车之家口碑响应不是有效JSON") from exc
        if not isinstance(payload, dict):
            raise AutohomeStructureError("汽车之家口碑响应顶层必须是对象")
        return parse_review_page(series, payload, page_index)
