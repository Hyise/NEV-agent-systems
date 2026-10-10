"""HTTP boundary for collection jobs and persisted source records."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from .catalog_domain import CatalogRunConflict, CatalogSelectionError
from .catalog_repository import SeriesCatalogRepository
from .coordination import ExternalAccessCoordinator
from .domain import CreateJobBody, JobStatus, TaskControlError
from .repository import CollectionRepository
from .service import CollectionService

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="资源不存在")


def _run_control(action, job_id: str) -> None:
    try:
        action(job_id)
    except KeyError as error:
        raise _not_found() from error
    except TaskControlError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def create_collection_router(
    repository: CollectionRepository,
    service: CollectionService,
    catalog_repository: SeriesCatalogRepository,
    coordinator: ExternalAccessCoordinator,
) -> APIRouter:
    router = APIRouter(prefix="/api/collection", tags=["collection"])

    @router.get("/overview")
    def overview():
        return repository.overview()

    @router.get("/jobs")
    def jobs(page: Page = 1, page_size: PageSize = 20):
        return repository.list_jobs(page=page, page_size=page_size)

    @router.post("/jobs", status_code=201)
    def create_job(body: CreateJobBody):
        if repository.active_job() is not None:
            raise HTTPException(status_code=409, detail="已有活动采集任务")
        if (
            catalog_repository.active_run() is not None
            or coordinator.current() is not None
        ):
            raise HTTPException(status_code=409, detail="汽车之家数据源正被其他任务使用")
        job_id = str(uuid4())
        try:
            job = repository.create_job_from_catalog(
                job_id,
                body.to_config(),
                body.selected_series_ids,
                _now(),
            )
            service.start(job_id)
        except CatalogSelectionError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": str(error),
                    "invalid_series_ids": error.invalid_series_ids,
                },
            ) from error
        except CatalogRunConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except TaskControlError as error:
            created = repository.get_job(job_id)
            if created is not None and created["status"] == "queued":
                repository.set_status(
                    job_id,
                    JobStatus.STOPPED,
                    _now(),
                    last_error="任务未能启动，请重试",
                    finished=True,
                )
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            created = repository.get_job(job_id)
            if created is not None and created["status"] == "queued":
                repository.set_status(
                    job_id,
                    JobStatus.STOPPED,
                    _now(),
                    last_error="任务未能启动，请重试",
                    finished=True,
                )
            raise HTTPException(status_code=503, detail="任务调度失败，请重试") from error
        return job

    @router.get("/jobs/{job_id}")
    def job_detail(job_id: str):
        job = repository.get_job(job_id)
        if job is None:
            raise _not_found()
        return {**job, "events": repository.list_events(job_id)}

    @router.post("/jobs/{job_id}/pause")
    def pause_job(job_id: str):
        _run_control(service.pause, job_id)
        return repository.get_job(job_id)

    @router.post("/jobs/{job_id}/resume")
    def resume_job(job_id: str):
        _run_control(service.resume, job_id)
        return repository.get_job(job_id)

    @router.post("/jobs/{job_id}/stop")
    def stop_job(job_id: str):
        _run_control(service.stop, job_id)
        return repository.get_job(job_id)

    @router.get("/series")
    def series(
        search: str = "",
        page: Page = 1,
        page_size: PageSize = 20,
    ):
        return repository.list_series(search=search, page=page, page_size=page_size)

    @router.get("/reviews")
    def reviews(
        series_id: str | None = None,
        page: Page = 1,
        page_size: PageSize = 20,
    ):
        return repository.list_reviews(
            series_id=series_id, page=page, page_size=page_size
        )

    @router.get("/reviews/{review_id}")
    def review_detail(review_id: str):
        review = repository.get_review(review_id)
        if review is None:
            raise _not_found()
        return review

    @router.get("/export")
    def export(series_id: Annotated[str, Query(min_length=1)]):
        if repository.get_series(series_id) is None:
            raise _not_found()

        def rows():
            for review in repository.iter_reviews_for_export(series_id):
                yield json.dumps(
                    review,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ) + "\n"

        return StreamingResponse(
            rows(),
            media_type="application/x-ndjson; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="autohome-{series_id}.jsonl"'
            },
        )

    return router
