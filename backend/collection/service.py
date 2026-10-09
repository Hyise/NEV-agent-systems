"""Single-worker orchestration for resumable comment collection jobs."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from random import Random
from threading import Event, Lock
from typing import Any

from .autohome import (
    AutohomeAccessPaused,
    AutohomeCatalogAdapter,
    AutohomeReviewAdapter,
    AutohomeStructureError,
)
from .coordination import ExternalAccessCoordinator
from .domain import JobStatus, ReviewPage, TaskControlError, VehicleSeries
from .repository import CollectionRepository

RETRY_DELAYS = (5, 15, 45)
CONSECUTIVE_SERIES_FAILURE_LIMIT = 3


class _JobInterrupted(RuntimeError):
    """Internal signal that a persisted pause or stop request took effect."""


class CollectionService:
    def __init__(
        self,
        repository: CollectionRepository,
        coordinator: ExternalAccessCoordinator | None = None,
        catalog_adapter_factory: Callable[[], Any] = AutohomeCatalogAdapter,
        review_adapter_factory: Callable[[Any], Any] = AutohomeReviewAdapter,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], Any] | None = None,
        rng: Any | None = None,
    ):
        self.repository = repository
        self.coordinator = coordinator or ExternalAccessCoordinator()
        self.catalog_adapter_factory = catalog_adapter_factory
        self.review_adapter_factory = review_adapter_factory
        self.sleeper = sleeper
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.rng = rng or Random()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="collection")
        self._future: Future[None] | None = None
        self._lock = Lock()
        self._shutdown_requested = Event()

    def _now(self) -> str:
        value = self.clock()
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def _submit(self, job_id: str) -> Future[None]:
        with self._lock:
            if self._future is not None and not self._future.done():
                raise TaskControlError("已有活动采集任务")
            if not self.coordinator.try_reserve("collection", job_id):
                raise TaskControlError("汽车之家数据源正被其他任务使用")
            self._shutdown_requested.clear()
            try:
                self._future = self._executor.submit(self._run_reserved, job_id)
            except Exception:
                self.coordinator.release("collection", job_id)
                raise
            return self._future

    def _run_reserved(self, job_id: str) -> None:
        try:
            self.run_job(job_id)
        finally:
            self.coordinator.release("collection", job_id)

    def _wait(self, seconds: float) -> None:
        if self.sleeper is not None:
            self.sleeper(seconds)
        else:
            self._shutdown_requested.wait(seconds)

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
        with self._lock:
            if self._future is not None and not self._future.done():
                raise TaskControlError("已有活动采集任务")
            if not self.coordinator.try_reserve("collection", job_id):
                raise TaskControlError("汽车之家数据源正被其他任务使用")
            self._shutdown_requested.clear()
            try:
                self.repository.clear_control(job_id, self._now())
                self.repository.set_status(job_id, target, self._now())
                self._future = self._executor.submit(self._run_reserved, job_id)
            except Exception:
                try:
                    current = self.repository.get_job(job_id)
                    if current is not None and JobStatus(current["status"]) is target:
                        self.repository.set_status(
                            job_id,
                            JobStatus.PAUSED,
                            self._now(),
                            resume_status=target,
                            last_error="任务调度失败，请重试",
                        )
                except Exception:  # noqa: BLE001 - preserve preparation failure
                    pass
                try:
                    self.coordinator.release("collection", job_id)
                except Exception:  # noqa: BLE001 - preserve preparation failure
                    pass
                raise
            return self._future

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
        with self._lock:
            job = self.repository.active_job()
            if job is not None:
                status = JobStatus(job["status"])
                if status in (JobStatus.DISCOVERING, JobStatus.COLLECTING):
                    self.repository.request_control(job["id"], "pause", self._now())
                elif status is JobStatus.QUEUED:
                    if self._future is not None and not self._future.done():
                        self.repository.request_control(
                            job["id"], "pause", self._now()
                        )
                    else:
                        self.repository.set_status(
                            job["id"],
                            JobStatus.PAUSED,
                            self._now(),
                            resume_status=JobStatus.QUEUED,
                            last_error="应用正在关闭，任务已暂停",
                        )
            self._shutdown_requested.set()
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

    def _pause_for_source(
        self,
        job_id: str,
        error: Exception,
        resume: JobStatus,
        public_message: str | None = None,
    ) -> None:
        message = public_message or str(error)
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

    def _request_with_retry(
        self,
        job_id: str,
        series: VehicleSeries,
        request: Callable[[], Any],
        details: dict[str, Any],
    ) -> Any:
        for attempt in range(len(RETRY_DELAYS) + 1):
            self._apply_control(job_id)
            try:
                return request()
            except (AutohomeAccessPaused, AutohomeStructureError):
                raise
            except Exception as error:
                if attempt == len(RETRY_DELAYS):
                    raise
                delay = RETRY_DELAYS[attempt]
                self.repository.record_event(
                    job_id,
                    "request_retry",
                    f"临时请求失败，将在 {delay} 秒后重试",
                    self._now(),
                    series_id=series.series_id,
                    error_class=type(error).__name__,
                    retryable=True,
                    details={
                        **details,
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                    },
                )
                self._wait(delay)

    def _fetch_page(self, job_id: str, adapter: Any, series: VehicleSeries, page: int):
        return self._request_with_retry(
            job_id,
            series,
            lambda: adapter.fetch_page(series, page),
            {"page": page},
        )

    def _fetch_detail(
        self, job_id: str, adapter: Any, series: VehicleSeries, review: Any
    ):
        return self._request_with_retry(
            job_id,
            series,
            lambda: adapter.fetch_detail(review),
            {"review_id": review.review_id},
        )

    @staticmethod
    def _is_last_page(page: ReviewPage) -> bool:
        if not page.reviews:
            return True
        if page.page_count is not None:
            return page.page_index >= page.page_count
        return bool(
            page.total is not None
            and page.page_size is not None
            and page.page_index * page.page_size >= page.total
        )

    def _collect(self, job_id: str, session: Any) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        series_list = self.repository.job_series(job_id)
        adapter = self.review_adapter_factory(session)
        consecutive_failures = 0
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
                        complete_reviews = []
                        for review in page.reviews:
                            delay = self.rng.uniform(
                                job["request_delay_min_seconds"],
                                job["request_delay_max_seconds"],
                            )
                            self._wait(delay)
                            complete_reviews.append(
                                self._fetch_detail(job_id, adapter, series, review)
                            )
                        page = page.model_copy(update={"reviews": complete_reviews})
                    except _JobInterrupted:
                        return
                    except AutohomeAccessPaused as error:
                        self._pause_for_source(job_id, error, JobStatus.COLLECTING)
                        return
                    except AutohomeStructureError as error:
                        self._pause_for_source(
                            job_id,
                            error,
                            JobStatus.COLLECTING,
                            "汽车之家评论页面结构发生变化，请检查采集适配器后重试",
                        )
                        return
                    except Exception as error:  # noqa: BLE001 - adapter boundary
                        message = (
                            f"车系 {series.series_name} 第 {page_index} 页采集失败，"
                            "重试已用尽"
                        )
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
                        consecutive_failures += 1
                        if consecutive_failures >= CONSECUTIVE_SERIES_FAILURE_LIMIT:
                            self._pause_for_source(
                                job_id,
                                error,
                                JobStatus.COLLECTING,
                                "连续 3 个车系请求失败，任务已暂停，请检查网络后继续",
                            )
                            return
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
                    consecutive_failures = 0
                    try:
                        self._apply_control(job_id)
                    except _JobInterrupted:
                        return
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
                    self._wait(delay)
                    try:
                        self._apply_control(job_id)
                    except _JobInterrupted:
                        return
                    page_index += 1

                if index + 1 < len(series_list):
                    delay = self.rng.uniform(
                        job["series_delay_min_seconds"],
                        job["series_delay_max_seconds"],
                    )
                    self._wait(delay)
                    try:
                        self._apply_control(job_id)
                    except _JobInterrupted:
                        return
                if series_failed:
                    continue
        finally:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()

        final = self.repository.get_job(job_id)
        if final is None or JobStatus(final["status"]) is not JobStatus.COLLECTING:
            return
        try:
            self._apply_control(job_id)
        except _JobInterrupted:
            return
        status = JobStatus.PARTIAL_FAILED if final["failed_count"] else JobStatus.COMPLETED
        if self.repository.finalize_job(job_id, status, self._now()):
            return
        try:
            self._apply_control(job_id)
        except _JobInterrupted:
            return

    def run_job(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        status = JobStatus(job["status"])
        catalog = self.catalog_adapter_factory()
        session = None
        if status is JobStatus.QUEUED:
            has_snapshot = bool(self.repository.job_series(job_id)) and not job[
                "series_manifest"
            ]
            if has_snapshot:
                self.repository.set_status(job_id, JobStatus.COLLECTING, self._now())
                status = JobStatus.COLLECTING
            else:
                self.repository.set_status(job_id, JobStatus.DISCOVERING, self._now())
                status = JobStatus.DISCOVERING
        if status is JobStatus.DISCOVERING:
            try:
                self._apply_control(job_id)
                result = catalog.discover(job["max_series"])
                self.repository.save_discovery(job_id, result.series, self._now())
                session = result.session
                self._apply_control(job_id)
            except _JobInterrupted:
                return
            except Exception as error:  # noqa: BLE001 - source boundary
                self._pause_for_source(
                    job_id,
                    error,
                    JobStatus.DISCOVERING,
                    "汽车之家车系目录访问失败，请检查浏览器安装、网络和页面结构后重试",
                )
                return
        elif status is JobStatus.COLLECTING:
            try:
                self._apply_control(job_id)
                session = catalog.open_session()
                self._apply_control(job_id)
            except _JobInterrupted:
                return
            except Exception as error:  # noqa: BLE001 - source boundary
                self._pause_for_source(
                    job_id,
                    error,
                    JobStatus.COLLECTING,
                    "汽车之家评论访问失败，请检查网络或页面结构后重试",
                )
                return
        else:
            raise TaskControlError("当前任务不能运行")
        self._collect(job_id, session)
