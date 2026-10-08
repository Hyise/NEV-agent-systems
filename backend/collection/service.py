"""Single-worker orchestration for resumable comment collection jobs."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from random import Random
from threading import Lock
from time import sleep
from typing import Any, Callable

from .autohome import AutohomeAccessPaused, AutohomeCatalogAdapter, AutohomeReviewAdapter
from .domain import JobStatus, ReviewPage, TaskControlError, VehicleSeries
from .repository import CollectionRepository


RETRY_DELAYS = (5, 15, 45)


class _JobInterrupted(RuntimeError):
    """Internal signal that a persisted pause or stop request took effect."""


class CollectionService:
    def __init__(
        self,
        repository: CollectionRepository,
        catalog_adapter_factory: Callable[[], Any] = AutohomeCatalogAdapter,
        review_adapter_factory: Callable[[Any], Any] = AutohomeReviewAdapter,
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], Any] | None = None,
        rng: Any | None = None,
    ):
        self.repository = repository
        self.catalog_adapter_factory = catalog_adapter_factory
        self.review_adapter_factory = review_adapter_factory
        self.sleeper = sleeper
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.rng = rng or Random()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="collection")
        self._future: Future[None] | None = None
        self._lock = Lock()

    def _now(self) -> str:
        value = self.clock()
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def _submit(self, job_id: str) -> Future[None]:
        with self._lock:
            if self._future is not None and not self._future.done():
                raise TaskControlError("已有活动采集任务")
            self._future = self._executor.submit(self.run_job, job_id)
            return self._future

    def start(self, job_id: str) -> Future[None]:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if JobStatus(job["status"]) is not JobStatus.QUEUED:
            raise TaskControlError("只有排队中的任务可以启动")
        active = self.repository.active_job()
        if active is not None and active["id"] != job_id:
            raise TaskControlError("已有活动采集任务")
        return self._submit(job_id)

    def pause(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if JobStatus(job["status"]) not in (JobStatus.DISCOVERING, JobStatus.COLLECTING):
            raise TaskControlError("当前任务不能暂停")
        self.repository.request_control(job_id, "pause", self._now())

    def resume(self, job_id: str) -> Future[None]:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if JobStatus(job["status"]) is not JobStatus.PAUSED:
            raise TaskControlError("只有暂停任务可以继续")
        active = self.repository.active_job()
        if active is not None and active["id"] != job_id:
            raise TaskControlError("已有活动采集任务")
        target = JobStatus(job["resume_status"] or JobStatus.COLLECTING.value)
        self.repository.clear_control(job_id, self._now())
        self.repository.set_status(job_id, target, self._now())
        return self._submit(job_id)

    def stop(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        status = JobStatus(job["status"])
        if status is JobStatus.QUEUED:
            self.repository.set_status(
                job_id, JobStatus.STOPPED, self._now(), finished=True
            )
            return
        if status not in (JobStatus.DISCOVERING, JobStatus.COLLECTING, JobStatus.PAUSED):
            raise TaskControlError("当前任务不能停止")
        if status is JobStatus.PAUSED:
            self.repository.clear_control(job_id, self._now())
            self.repository.set_status(
                job_id, JobStatus.STOPPED, self._now(), finished=True
            )
            return
        self.repository.request_control(job_id, "stop", self._now())

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    def _apply_control(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        action = job["control_requested"]
        if action is None:
            return
        current = JobStatus(job["status"])
        self.repository.clear_control(job_id, self._now())
        if action == "pause":
            self.repository.set_status(
                job_id,
                JobStatus.PAUSED,
                self._now(),
                resume_status=current,
            )
        else:
            self.repository.set_status(
                job_id, JobStatus.STOPPED, self._now(), finished=True
            )
        raise _JobInterrupted

    def _pause_for_source(self, job_id: str, error: Exception, resume: JobStatus) -> None:
        message = str(error)
        self.repository.record_event(
            job_id,
            "source_paused",
            message,
            self._now(),
            error_class=type(error).__name__,
        )
        self.repository.set_status(
            job_id,
            JobStatus.PAUSED,
            self._now(),
            resume_status=resume,
            last_error=message,
        )

    def _fetch_page(self, job_id: str, adapter: Any, series: VehicleSeries, page: int):
        for attempt in range(len(RETRY_DELAYS) + 1):
            self._apply_control(job_id)
            try:
                return adapter.fetch_page(series, page)
            except AutohomeAccessPaused:
                raise
            except Exception as error:
                if attempt == len(RETRY_DELAYS):
                    raise
                delay = RETRY_DELAYS[attempt]
                self.repository.record_event(
                    job_id,
                    "request_retry",
                    str(error),
                    self._now(),
                    series_id=series.series_id,
                    error_class=type(error).__name__,
                    retryable=True,
                    details={"page": page, "attempt": attempt + 1, "delay_seconds": delay},
                )
                self.sleeper(delay)

    @staticmethod
    def _is_last_page(page: ReviewPage) -> bool:
        return not page.reviews or (
            page.total is not None and page.page_index * 20 >= page.total
        )

    def _collect(self, job_id: str, session: Any) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        series_list = [VehicleSeries(**item) for item in job["series_manifest"]]
        adapter = self.review_adapter_factory(session)
        try:
            for index in range(job["current_series_index"], len(series_list)):
                series = series_list[index]
                current = self.repository.get_job(job_id)
                if current is None:
                    raise KeyError(job_id)
                page_index = current["current_page"] if index == current["current_series_index"] else 1
                previous_ids: tuple[str, ...] | None = None
                series_failed = False
                while True:
                    try:
                        page = self._fetch_page(job_id, adapter, series, page_index)
                    except _JobInterrupted:
                        return
                    except AutohomeAccessPaused as error:
                        self._pause_for_source(job_id, error, JobStatus.COLLECTING)
                        return
                    except Exception as error:
                        message = f"车系 {series.series_name} 第 {page_index} 页采集失败：{error}"
                        self.repository.record_event(
                            job_id,
                            "series_failed",
                            message,
                            self._now(),
                            series_id=series.series_id,
                            error_class=type(error).__name__,
                        )
                        self.repository.advance_series(
                            job_id,
                            index + 1,
                            self._now(),
                            failed=True,
                            last_error=message,
                        )
                        series_failed = True
                        break

                    review_ids = tuple(review.review_id for review in page.reviews)
                    if review_ids and review_ids == previous_ids:
                        message = f"车系 {series.series_name} 连续分页返回相同评论，已停止该车系"
                        self.repository.record_event(
                            job_id,
                            "repeated_page",
                            message,
                            self._now(),
                            series_id=series.series_id,
                            error_class="RepeatedPage",
                        )
                        self.repository.advance_series(
                            job_id,
                            index + 1,
                            self._now(),
                            failed=True,
                            last_error=message,
                        )
                        series_failed = True
                        break

                    self.repository.save_review_page(
                        job_id, series, page.reviews, page_index + 1, self._now()
                    )
                    previous_ids = review_ids
                    reached_cap = (
                        job["max_pages_per_series"] is not None
                        and page_index >= job["max_pages_per_series"]
                    )
                    if reached_cap or self._is_last_page(page):
                        self.repository.advance_series(job_id, index + 1, self._now())
                        break
                    delay = self.rng.uniform(
                        job["request_delay_min_seconds"],
                        job["request_delay_max_seconds"],
                    )
                    self.sleeper(delay)
                    page_index += 1

                if index + 1 < len(series_list):
                    delay = self.rng.uniform(
                        job["series_delay_min_seconds"],
                        job["series_delay_max_seconds"],
                    )
                    self.sleeper(delay)
                if series_failed:
                    continue
        finally:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()

        final = self.repository.get_job(job_id)
        if final is None or JobStatus(final["status"]) is not JobStatus.COLLECTING:
            return
        status = JobStatus.PARTIAL_FAILED if final["failed_count"] else JobStatus.COMPLETED
        self.repository.set_status(job_id, status, self._now(), finished=True)

    def run_job(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        status = JobStatus(job["status"])
        catalog = self.catalog_adapter_factory()
        session = None
        if status is JobStatus.QUEUED:
            self.repository.set_status(job_id, JobStatus.DISCOVERING, self._now())
            status = JobStatus.DISCOVERING
        if status is JobStatus.DISCOVERING:
            try:
                self._apply_control(job_id)
                result = catalog.discover(job["max_series"])
                self.repository.save_discovery(job_id, result.series, self._now())
                session = result.session
            except _JobInterrupted:
                return
            except Exception as error:
                self._pause_for_source(job_id, error, JobStatus.DISCOVERING)
                return
        elif status is JobStatus.COLLECTING:
            try:
                self._apply_control(job_id)
                session = catalog.open_session()
            except _JobInterrupted:
                return
            except Exception as error:
                self._pause_for_source(job_id, error, JobStatus.COLLECTING)
                return
        else:
            raise TaskControlError("当前任务不能运行")
        self._collect(job_id, session)
