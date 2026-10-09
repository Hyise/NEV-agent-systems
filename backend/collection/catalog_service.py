"""Single-worker orchestration for versioned series-catalog discovery."""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from .autohome import (
    AutohomeCatalogAdapter,
    CatalogDiscoveryCancelled,
)
from .catalog_domain import CatalogRunConflict, CatalogRunStatus
from .catalog_repository import SeriesCatalogRepository
from .coordination import ExternalAccessCoordinator


class SeriesCatalogService:
    def __init__(
        self,
        repository: SeriesCatalogRepository,
        coordinator: ExternalAccessCoordinator,
        adapter_factory: Callable[[], Any] = AutohomeCatalogAdapter,
        clock: Callable[[], Any] | None = None,
        executor: Any | None = None,
    ):
        self.repository = repository
        self.coordinator = coordinator
        self.adapter_factory = adapter_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="series-catalog"
        )
        self._future: Future[None] | None = None

    def _now(self) -> str:
        value = self.clock()
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def start(self, run_id: str, batch_id: str) -> Future[None]:
        if not self.coordinator.try_reserve("catalog", run_id):
            raise CatalogRunConflict("汽车之家数据源正被其他任务使用")
        created = False
        try:
            self.repository.create_run(run_id, batch_id, self._now())
            created = True
            self._future = self._executor.submit(self.run_discovery, run_id)
            return self._future
        except Exception:
            if created:
                try:
                    self.repository.fail_run(
                        run_id,
                        "schedule_error",
                        "车系发现任务调度失败，请重试",
                        self._now(),
                    )
                except Exception:  # noqa: BLE001 - preserve scheduling failure
                    pass
            try:
                self.coordinator.release("catalog", run_id)
            except Exception:  # noqa: BLE001 - preserve scheduling failure
                pass
            raise

    def run_discovery(self, run_id: str) -> None:
        try:
            adapter = self.adapter_factory()

            def cancelled() -> bool:
                return self.repository.is_cancel_requested(run_id)

            def stage(entries, scanned, skipped, current_page) -> None:
                if cancelled():
                    raise CatalogDiscoveryCancelled("车系发现已取消")
                self.repository.append_entries(
                    run_id,
                    entries,
                    scanned_count=scanned,
                    skipped_count=skipped,
                    current_page=current_page,
                    updated_at=self._now(),
                )

            result = adapter.discover_series(
                1000,
                on_batch=stage,
                should_cancel=cancelled,
            )
            if cancelled():
                raise CatalogDiscoveryCancelled("车系发现已取消")
            self.repository.publish_run(
                run_id,
                self._now(),
                source_exhausted=result.source_exhausted,
            )
        except CatalogDiscoveryCancelled:
            run = self.repository.get_run(run_id)
            if run is not None and run["status"] in {
                CatalogRunStatus.QUEUED.value,
                CatalogRunStatus.DISCOVERING.value,
                CatalogRunStatus.CANCELLING.value,
            }:
                self.repository.cancel_run(run_id, self._now())
        except Exception:  # noqa: BLE001 - sanitize the external source boundary
            run = self.repository.get_run(run_id)
            if run is not None and run["status"] == CatalogRunStatus.CANCELLING.value:
                self.repository.cancel_run(run_id, self._now())
            elif run is not None and run["status"] in {
                CatalogRunStatus.QUEUED.value,
                CatalogRunStatus.DISCOVERING.value,
                CatalogRunStatus.PUBLISHING.value,
            }:
                self.repository.fail_run(
                    run_id,
                    "source_error",
                    "汽车之家车系目录发现失败，请检查网络和页面结构",
                    self._now(),
                )
        finally:
            self.coordinator.release("catalog", run_id)

    def cancel(self, run_id: str) -> None:
        self.repository.request_cancel(run_id, self._now())

    def shutdown(self) -> None:
        try:
            run = self.repository.active_run()
            if run is not None and run["status"] != CatalogRunStatus.CANCELLING.value:
                try:
                    self.repository.request_cancel(run["id"], self._now())
                except CatalogRunConflict:
                    latest = self.repository.get_run(run["id"])
                    terminal = {
                        CatalogRunStatus.COMPLETED.value,
                        CatalogRunStatus.COMPLETED_SHORT.value,
                        CatalogRunStatus.CANCELLED.value,
                        CatalogRunStatus.FAILED.value,
                    }
                    if latest is not None and latest["status"] not in terminal:
                        raise
        finally:
            self._executor.shutdown(wait=True)
