from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event

import pytest

from backend.collection.autohome import (
    AutohomeStructureError,
    BrowserSession,
    CatalogDiscoveryCancelled,
    CatalogDiscoveryResult,
)
from backend.collection.catalog_repository import SeriesCatalogRepository
from backend.collection.catalog_service import SeriesCatalogService
from backend.collection.coordination import ExternalAccessCoordinator
from backend.collection.domain import TaskControlError, VehicleSeries
from backend.collection.repository import CollectionRepository

NOW = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)


def make_dependencies(tmp_path):
    path = tmp_path / "catalog-service.sqlite3"
    CollectionRepository(path)
    return SeriesCatalogRepository(path), ExternalAccessCoordinator()


def make_series(index: int) -> VehicleSeries:
    series_id = str(5000 + index)
    return VehicleSeries(
        series_id=series_id,
        series_name=f"测试车系 {index}",
        series_url=f"https://www.autohome.com.cn/{series_id}/",
        review_url=f"https://k.autohome.com.cn/{series_id}/",
        discovery_rank=index,
    )


class BatchAdapter:
    def __init__(self, series, *, source_exhausted=False, error=None):
        self.series = series
        self.source_exhausted = source_exhausted
        self.error = error

    def discover_series(self, max_series, on_batch, should_cancel):
        if self.error is not None:
            raise self.error
        scanned = 0
        for page, start in enumerate(range(0, len(self.series), 500), start=1):
            batch = self.series[start : start + 500]
            scanned += len(batch)
            on_batch(batch, scanned, 0, page)
        return CatalogDiscoveryResult(
            self.series,
            BrowserSession({}, "test-agent"),
            scanned_count=scanned,
            skipped_count=0,
            source_exhausted=self.source_exhausted,
        )


def test_exactly_one_external_operation_wins_a_start_race():
    coordinator = ExternalAccessCoordinator()
    barrier = Barrier(2)

    def reserve(kind):
        barrier.wait(timeout=5)
        return coordinator.try_reserve(kind, f"{kind}-1")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, ("catalog", "collection")))

    assert sorted(results) == [False, True]
    assert coordinator.current() is not None


def test_only_the_owner_can_release_a_reservation():
    coordinator = ExternalAccessCoordinator()
    assert coordinator.try_reserve("catalog", "run-1") is True

    with pytest.raises(TaskControlError, match="预约"):
        coordinator.release("collection", "run-1")

    assert coordinator.current().operation_id == "run-1"
    coordinator.release("catalog", "run-1")
    assert coordinator.current() is None


def test_failed_executor_submission_releases_reservation(tmp_path):
    class RejectingExecutor:
        def submit(self, *args, **kwargs):
            raise RuntimeError("executor unavailable")

        def shutdown(self, wait=True):
            return None

    repository, coordinator = make_dependencies(tmp_path)
    service = SeriesCatalogService(
        repository,
        coordinator,
        clock=lambda: NOW,
        executor=RejectingExecutor(),
    )

    with pytest.raises(RuntimeError, match="executor unavailable"):
        service.start("run-1", "batch-1")

    assert coordinator.current() is None
    assert repository.get_run("run-1")["status"] == "failed"


def test_discovery_stages_progress_and_publishes_1000_unique_series(tmp_path):
    repository, coordinator = make_dependencies(tmp_path)
    series = [make_series(index) for index in range(1, 1001)]
    service = SeriesCatalogService(
        repository,
        coordinator,
        adapter_factory=lambda: BatchAdapter(series),
        clock=lambda: NOW,
    )

    future = service.start("run-1", "batch-1")
    future.result(timeout=5)

    run = repository.get_run("run-1")
    assert run["status"] == "completed"
    assert run["unique_count"] == 1000
    assert run["current_page"] == 2
    assert repository.catalog_status()["active_batch_id"] == "batch-1"
    assert repository.list_catalog(page_size=100)["total"] == 1000
    assert coordinator.current() is None
    service.shutdown()


def test_exhausted_source_completes_short(tmp_path):
    repository, coordinator = make_dependencies(tmp_path)
    series = [make_series(1), make_series(2)]
    service = SeriesCatalogService(
        repository,
        coordinator,
        adapter_factory=lambda: BatchAdapter(series, source_exhausted=True),
        clock=lambda: NOW,
    )

    service.start("run-1", "batch-1").result(timeout=5)

    assert repository.get_run("run-1")["status"] == "completed_short"
    assert repository.selection_ids() == ["5001", "5002"]
    assert coordinator.current() is None
    service.shutdown()


def test_source_failure_keeps_old_catalog(tmp_path):
    repository, coordinator = make_dependencies(tmp_path)
    repository.create_run("old-run", "old-batch", NOW.isoformat())
    repository.append_entries(
        "old-run",
        [make_series(1)],
        scanned_count=1,
        skipped_count=0,
        current_page=1,
        updated_at=NOW.isoformat(),
    )
    repository.publish_run("old-run", NOW.isoformat(), source_exhausted=True)
    service = SeriesCatalogService(
        repository,
        coordinator,
        adapter_factory=lambda: BatchAdapter(
            [], error=AutohomeStructureError("private selector details")
        ),
        clock=lambda: NOW,
    )

    service.start("run-1", "batch-1").result(timeout=5)

    run = repository.get_run("run-1")
    assert run["status"] == "failed"
    assert run["error_code"] == "source_error"
    assert run["error_message"] == "汽车之家车系目录发现失败，请检查网络和页面结构"
    assert repository.catalog_status()["active_batch_id"] == "old-batch"
    assert repository.selection_ids() == ["5001"]
    assert coordinator.current() is None
    service.shutdown()


def test_cancel_during_request_stops_before_next_batch_and_does_not_publish(tmp_path):
    entered = Event()
    release_request = Event()
    second_batch_written = Event()

    class BlockingAdapter:
        def discover_series(self, max_series, on_batch, should_cancel):
            on_batch([make_series(1)], 1, 0, 1)
            entered.set()
            assert release_request.wait(timeout=5)
            if should_cancel():
                raise CatalogDiscoveryCancelled("cancelled")
            second_batch_written.set()
            on_batch([make_series(2)], 2, 0, 2)
            return CatalogDiscoveryResult(
                [make_series(1), make_series(2)],
                BrowserSession({}, "test-agent"),
                scanned_count=2,
                source_exhausted=True,
            )

    repository, coordinator = make_dependencies(tmp_path)
    service = SeriesCatalogService(
        repository,
        coordinator,
        adapter_factory=BlockingAdapter,
        clock=lambda: NOW,
    )

    future = service.start("run-1", "batch-1")
    assert entered.wait(timeout=5)
    service.cancel("run-1")
    release_request.set()
    future.result(timeout=5)

    assert repository.get_run("run-1")["status"] == "cancelled"
    assert repository.catalog_status()["active_batch_id"] is None
    assert second_batch_written.is_set() is False
    assert coordinator.current() is None
    service.shutdown()


def test_shutdown_marks_running_catalog_interrupted(tmp_path):
    entered = Event()

    class ShutdownAwareAdapter:
        def discover_series(self, max_series, on_batch, should_cancel):
            on_batch([make_series(1)], 1, 0, 1)
            entered.set()
            while not should_cancel():
                entered.wait(0.01)
            raise CatalogDiscoveryCancelled("shutdown")

    repository, coordinator = make_dependencies(tmp_path)
    service = SeriesCatalogService(
        repository,
        coordinator,
        adapter_factory=ShutdownAwareAdapter,
        clock=lambda: NOW,
    )
    service.start("run-1", "batch-1")
    assert entered.wait(timeout=5)

    service.shutdown()

    assert repository.get_run("run-1")["status"] == "cancelled"
    assert repository.active_run() is None
    assert coordinator.current() is None
