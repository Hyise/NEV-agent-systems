"""Single-worker orchestration for monthly sales collection."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from backend.collection.coordination import ExternalAccessCoordinator

from .adapters import SalesAdapter, create_sales_adapter
from .domain import SalesSourceError
from .repository import SalesCollectionRepository


class SalesCollectionService:
    def __init__(
        self,
        repository: SalesCollectionRepository,
        coordinator: ExternalAccessCoordinator,
        adapter_factory: Callable[[str], SalesAdapter] = create_sales_adapter,
        clock: Callable[[], Any] | None = None,
    ):
        self.repository = repository
        self.coordinator = coordinator
        self.adapter_factory = adapter_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sales")
        self._future: Future[None] | None = None
        self._lock = Lock()

    def _now(self) -> str:
        value = self.clock()
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def start(self, job_id: str) -> Future[None]:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] != "queued":
            raise RuntimeError("只有排队中的销量采集任务可以启动")
        with self._lock:
            if self._future is not None and not self._future.done():
                raise RuntimeError("已有活动销量采集任务")
            if not self.coordinator.try_reserve("sales", job_id):
                raise RuntimeError("外部数据源正被其他采集任务使用")
            try:
                self._future = self._executor.submit(self._run_reserved, job_id)
            except Exception:
                self.coordinator.release("sales", job_id)
                raise
            return self._future

    def _run_reserved(self, job_id: str) -> None:
        try:
            self.run_job(job_id)
        finally:
            self.coordinator.release("sales", job_id)

    def run_job(self, job_id: str) -> None:
        self.repository.mark_job_running(job_id, self._now())
        for step in self.repository.pending_steps(job_id):
            platform = str(step["platform"])
            month = str(step["month"])
            self.repository.mark_step_running(job_id, platform, month, self._now())
            adapter = self.adapter_factory(platform)
            try:
                result = adapter.fetch_month(month)
                self.repository.save_month_records(
                    job_id,
                    platform,
                    month,
                    result.records,
                    result.snapshot_hash,
                    self._now(),
                )
            except SalesSourceError as error:
                self.repository.mark_step_failed(
                    job_id,
                    platform,
                    month,
                    error.code,
                    str(error),
                    self._now(),
                )
            except Exception as error:
                self.repository.mark_step_failed(
                    job_id,
                    platform,
                    month,
                    "unexpected_error",
                    f"{type(error).__name__}: {error}",
                    self._now(),
                )
            finally:
                close = getattr(adapter, "close", None)
                if callable(close):
                    close()
        self.repository.finish_job(job_id, self._now())

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
