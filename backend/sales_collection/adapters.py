"""Auditable platform adapters for monthly vehicle-series sales."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .domain import (
    SalesAccessVerificationRequired,
    SalesMonthResult,
    SalesRecord,
    SalesStructureError,
    validate_month,
)

AUTOHOME_SALES_API = "https://www.autohome.com.cn/web-main/car/rank/getList"
AUTOHOME_RANK_URL = "https://www.autohome.com.cn/rank/1"
MAX_PAGES = 100


@dataclass(frozen=True)
class AutohomeSalesPage:
    records: list[SalesRecord]
    page_index: int
    page_count: int


class SalesAdapter(Protocol):
    def fetch_month(self, month: str) -> SalesMonthResult: ...


def _integer(value: Any, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SalesStructureError(f"汽车之家销量响应缺少有效{field}")
    return value


def parse_autohome_sales_page(
    payload: dict[str, Any],
    *,
    month: str,
    source_url: str,
    expected_page: int,
) -> AutohomeSalesPage:
    validate_month(month)
    if payload.get("returncode") != 0:
        raise SalesStructureError("汽车之家销量接口返回失败状态")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise SalesStructureError("汽车之家销量响应缺少result对象")
    page_index = _integer(result.get("pageindex"), "页码", minimum=1)
    page_count = _integer(result.get("pagecount"), "总页数", minimum=1)
    if page_count > MAX_PAGES or page_index != expected_page:
        raise SalesStructureError("汽车之家销量响应分页与请求不一致")
    expected_subtitle = f"{int(month[-2:])}月"
    if result.get("scenesubtitle") != expected_subtitle:
        raise SalesStructureError("汽车之家销量响应月份与请求不一致")
    items = result.get("list")
    if not isinstance(items, list) or not items:
        raise SalesStructureError("汽车之家销量月榜为空或结构已变化")
    records: list[SalesRecord] = []
    for item in items:
        if not isinstance(item, dict):
            raise SalesStructureError("汽车之家销量榜包含无效记录")
        try:
            records.append(
                SalesRecord(
                    platform="autohome",
                    month=month,
                    series_id=str(item["seriesid"]),
                    series_name=str(item["seriesname"]),
                    sales_volume=_integer(item.get("salecount"), "销量", minimum=0),
                    rank=_integer(item.get("rankNum"), "排名", minimum=1),
                    source_url=source_url,
                )
            )
        except (KeyError, ValueError) as error:
            raise SalesStructureError("汽车之家销量榜必填字段无效") from error
    return AutohomeSalesPage(records, page_index, page_count)


class AutohomeSalesAdapter:
    def __init__(
        self,
        client: httpx.Client | None = None,
        sleeper=time.sleep,
        page_delay_seconds: float = 1.5,
    ):
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=30,
            follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
                "Referer": AUTOHOME_RANK_URL,
            },
        )
        self._sleeper = sleeper
        self._delay = page_delay_seconds

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_month(self, month: str) -> SalesMonthResult:
        validate_month(month)
        page_index = 1
        page_count = 1
        records: list[SalesRecord] = []
        payloads: list[dict[str, Any]] = []
        while page_index <= page_count:
            response = self._client.get(
                AUTOHOME_SALES_API,
                params={
                    "from": 28,
                    "pm": 2,
                    "pluginversion": "11.75.8",
                    "model": 1,
                    "channel": 0,
                    "pageindex": page_index,
                    "pagesize": 50,
                    "typeid": 1,
                    "subranktypeid": 1,
                    "levelid": 0,
                    "price": "0-9000",
                    "date": month,
                },
            )
            if response.status_code in {403, 429}:
                raise SalesAccessVerificationRequired(
                    f"汽车之家返回 HTTP {response.status_code}，请稍后重试"
                )
            try:
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise SalesStructureError("汽车之家销量响应不可读取") from error
            if not isinstance(payload, dict):
                raise SalesStructureError("汽车之家销量响应顶层必须是对象")
            page = parse_autohome_sales_page(
                payload,
                month=month,
                source_url=AUTOHOME_RANK_URL,
                expected_page=page_index,
            )
            payloads.append(payload)
            records.extend(page.records)
            page_count = page.page_count
            page_index += 1
            if page_index <= page_count:
                self._sleeper(self._delay)
        if len({record.series_id for record in records}) != len(records):
            raise SalesStructureError("汽车之家完整月榜包含重复车系")
        canonical = json.dumps(
            payloads, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return SalesMonthResult(records, hashlib.sha256(canonical).hexdigest())


class VerificationRequiredSalesAdapter:
    def __init__(self, platform_label: str):
        self.platform_label = platform_label

    def fetch_month(self, month: str) -> SalesMonthResult:
        validate_month(month)
        raise SalesAccessVerificationRequired(
            f"{self.platform_label}在当前自动化环境要求人工验证；系统未绕过验证，也未写入替代数据"
        )


def create_sales_adapter(platform: str) -> SalesAdapter:
    if platform == "autohome":
        return AutohomeSalesAdapter()
    labels = {"dongchedi": "懂车帝", "yiche": "易车"}
    try:
        return VerificationRequiredSalesAdapter(labels[platform])
    except KeyError as error:
        raise ValueError("不支持的销量来源平台") from error
