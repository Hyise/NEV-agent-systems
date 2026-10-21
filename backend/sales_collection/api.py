"""FastAPI boundary for monthly vehicle-series sales collection."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.collection.coordination import ExternalAccessCoordinator

from .domain import CreateSalesJobBody, SalesPlatform
from .repository import SalesCollectionRepository
from .service import SalesCollectionService

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
MonthQuery = Annotated[str | None, Query(pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")]
MatchStatus = Literal["matched", "unmatched", "ambiguous"]

SOURCES = [
    {
        "platform": "autohome",
        "label": "汽车之家",
        "availability": "live",
        "description": "公开车系月销榜分页接口，可直接运行低频采集。",
    },
    {
        "platform": "dongchedi",
        "label": "懂车帝",
        "availability": "verification_required",
        "description": "当前自动化环境只返回应用空壳，任务会保留受阻记录。",
    },
    {
        "platform": "yiche",
        "label": "易车",
        "availability": "verification_required",
        "description": "当前自动化环境返回验证码，系统不会绕过验证。",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_csv_text(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def create_sales_collection_router(
    repository: SalesCollectionRepository,
    service: SalesCollectionService,
    coordinator: ExternalAccessCoordinator,
) -> APIRouter:
    router = APIRouter(prefix="/api/sales-collection", tags=["sales-collection"])

    @router.get("/overview")
    def overview():
        return {**repository.overview(), "sources": SOURCES}

    @router.get("/jobs")
    def list_jobs(page: Page = 1, page_size: PageSize = 20):
        return repository.list_jobs(page, page_size)

    @router.post("/jobs", status_code=201)
    def create_job(body: CreateSalesJobBody):
        if coordinator.current() is not None:
            raise HTTPException(status_code=409, detail="外部数据源正被其他采集任务使用")
        if repository.active_job() is not None:
            raise HTTPException(status_code=409, detail="已有活动销量采集任务")
        job_id = str(uuid4())
        try:
            job = repository.create_job(job_id, body, _now())
            service.start(job_id)
            return job
        except RuntimeError as error:
            if repository.get_job(job_id) is not None:
                repository.fail_job_start(job_id, str(error), _now())
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str):
        job = repository.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="销量采集任务不存在")
        return job

    @router.get("/records")
    def records(
        platform: SalesPlatform | None = None,
        month: MonthQuery = None,
        search: Annotated[str, Query(max_length=200)] = "",
        match_status: MatchStatus | None = None,
        page: Page = 1,
        page_size: PageSize = 20,
    ):
        return repository.list_records(
            platform=platform,
            month=month,
            search=search,
            match_status=match_status,
            page=page,
            page_size=page_size,
        )

    @router.get("/export")
    def export(
        platform: SalesPlatform | None = None,
        month: MonthQuery = None,
        search: Annotated[str, Query(max_length=200)] = "",
        match_status: MatchStatus | None = None,
    ):
        result = repository.list_records(
            platform=platform,
            month=month,
            search=search,
            match_status=match_status,
            page=1,
            page_size=1_000_000,
        )
        output = io.StringIO(newline="")
        fields = [
            "来源平台",
            "月份",
            "平台车系ID",
            "平台车系名称",
            "销量",
            "排名",
            "指标口径",
            "评论车系ID",
            "评论车系名称",
            "匹配状态",
            "来源地址",
            "采集时间",
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow(
                {
                    "来源平台": row["platform"],
                    "月份": row["month"],
                    "平台车系ID": _safe_csv_text(row["series_id"]),
                    "平台车系名称": _safe_csv_text(row["series_name"]),
                    "销量": row["sales_volume"],
                    "排名": row["rank"],
                    "指标口径": row["metric"],
                    "评论车系ID": _safe_csv_text(row["review_series_id"] or ""),
                    "评论车系名称": _safe_csv_text(row["review_series_name"] or ""),
                    "匹配状态": row["match_status"],
                    "来源地址": _safe_csv_text(row["source_url"]),
                    "采集时间": row["collected_at"],
                }
            )
        return Response(
            "\ufeff" + output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="sales-records.csv"'},
        )

    return router
