from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.collection.autohome import AutohomeAccessPaused, BrowserSession, CatalogDiscoveryResult
from backend.collection.domain import (
    CollectedReview,
    CreateJobBody,
    JobStatus,
    ReviewPage,
    TaskControlError,
    VehicleSeries,
)
from backend.collection.repository import CollectionRepository
from backend.collection.service import CollectionService


NOW = datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)


def make_series(index: int) -> VehicleSeries:
    series_id = str(5000 + index)
    return VehicleSeries(
        series_id=series_id,
        series_name=f"测试车系 {index}",
        series_url=f"https://www.autohome.com.cn/{series_id}/",
        review_url=f"https://k.autohome.com.cn/{series_id}/",
        discovery_rank=index,
    )


def make_page(series: VehicleSeries, page_index: int, *, total: int = 999, ids=None):
    ids = ids if ids is not None else [f"{series.series_id}-{page_index}"]
    reviews = [
        CollectedReview(
            review_id=review_id,
            series_id=series.series_id,
            series_name=series.series_name,
            source_url=f"{series.review_url}#{review_id}",
            original_review={"Koubeiid": review_id, "contents": [{"content": "原始评论"}]},
        )
        for review_id in ids
    ]
    return ReviewPage(series=series, page_index=page_index, total=total, reviews=reviews)


class FakeCatalogAdapter:
    def __init__(self, series):
        self.series = series
        self.discover_limits = []
        self.open_count = 0

    def discover(self, max_series):
        self.discover_limits.append(max_series)
        return CatalogDiscoveryResult(self.series[:max_series], BrowserSession({}, "test-agent"))

    def open_session(self):
        self.open_count += 1
        return BrowserSession({}, "test-agent")


class FakeReviewAdapter:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []
        self.closed = False

    def fetch_page(self, series, page_index, page_size=20):
        self.calls.append((series.series_id, page_index))
        return self.responder(series, page_index, len(self.calls))

    def close(self):
        self.closed = True


def make_service(tmp_path, config, series, responder, *, sleeper=None, rng=None):
    repository = CollectionRepository(tmp_path / "collection.sqlite3")
    repository.create_job("job-1", config, NOW.isoformat())
    catalog = FakeCatalogAdapter(series)
    review = FakeReviewAdapter(responder)
    service = CollectionService(
        repository,
        catalog_adapter_factory=lambda: catalog,
        review_adapter_factory=lambda session: review,
        sleeper=sleeper or (lambda seconds: None),
        clock=lambda: NOW,
        rng=rng or SimpleNamespace(uniform=lambda low, high: low),
    )
    return repository, catalog, review, service


def test_verification_job_stops_at_three_series_and_two_pages(tmp_path):
    config = CreateJobBody(mode="verification").to_config()
    repository, catalog, review, service = make_service(
        tmp_path,
        config,
        [make_series(index) for index in range(1, 6)],
        lambda series, page, call: make_page(series, page),
    )

    service.run_job("job-1")

    assert catalog.discover_limits == [3]
    assert review.calls == [
        (str(5000 + series_index), page)
        for series_index in range(1, 4)
        for page in (1, 2)
    ]
    assert repository.get_job("job-1")["status"] == "completed"
    service.shutdown()


def test_production_job_has_500_series_and_no_page_cap(tmp_path):
    config = CreateJobBody(mode="production").to_config()
    series = [make_series(index) for index in range(1, 501)]

    def responder(item, page, call):
        total = 41 if item.discovery_rank == 1 else 1
        return make_page(item, page, total=total)

    repository, catalog, review, service = make_service(
        tmp_path, config, series, responder
    )

    service.run_job("job-1")

    assert catalog.discover_limits == [500]
    assert [page for series_id, page in review.calls if series_id == "5001"] == [1, 2, 3]
    assert len({series_id for series_id, page in review.calls}) == 500
    assert repository.get_job("job-1")["status"] == "completed"
    service.shutdown()


def test_repeated_page_stops_series_without_looping(tmp_path):
    item = make_series(1)
    repository, catalog, review, service = make_service(
        tmp_path,
        CreateJobBody(mode="production").to_config(),
        [item],
        lambda series, page, call: make_page(series, page, ids=["same-review"]),
    )

    service.run_job("job-1")

    assert review.calls == [(item.series_id, 1), (item.series_id, 2)]
    assert repository.get_job("job-1")["status"] == "partial_failed"
    assert repository.list_events("job-1")[0]["event_type"] == "repeated_page"
    service.shutdown()


def test_page_commit_advances_resume_cursor(tmp_path):
    item = make_series(1)
    repository = CollectionRepository(tmp_path / "collection.sqlite3")
    config = CreateJobBody(mode="production").to_config()
    repository.create_job("job-1", config, NOW.isoformat())
    repository.save_discovery("job-1", [item], NOW.isoformat())

    def responder(series, page, call):
        repository.request_control("job-1", "pause", NOW.isoformat())
        return make_page(series, page, total=100)

    catalog = FakeCatalogAdapter([item])
    review = FakeReviewAdapter(responder)
    service = CollectionService(
        repository,
        catalog_adapter_factory=lambda: catalog,
        review_adapter_factory=lambda session: review,
        sleeper=lambda seconds: None,
        clock=lambda: NOW,
        rng=SimpleNamespace(uniform=lambda low, high: low),
    )

    service.run_job("job-1")

    job = repository.get_job("job-1")
    assert job["status"] == "paused"
    assert job["current_page"] == 2
    assert job["saved_count"] == 1
    assert catalog.open_count == 1
    service.shutdown()


def test_pause_and_stop_take_effect_before_next_request(tmp_path):
    for action, expected_status in (("pause", "paused"), ("stop", "stopped")):
        case_dir = tmp_path / action
        case_dir.mkdir()
        item = make_series(1)
        repository = CollectionRepository(case_dir / "collection.sqlite3")
        repository.create_job(
            "job-1", CreateJobBody(mode="production").to_config(), NOW.isoformat()
        )
        catalog = FakeCatalogAdapter([item])

        def responder(series, page, call, *, action=action, repository=repository):
            repository.request_control("job-1", action, NOW.isoformat())
            return make_page(series, page, total=100)

        review = FakeReviewAdapter(responder)
        service = CollectionService(
            repository,
            catalog_adapter_factory=lambda catalog=catalog: catalog,
            review_adapter_factory=lambda session, review=review: review,
            sleeper=lambda seconds: None,
            clock=lambda: NOW,
            rng=SimpleNamespace(uniform=lambda low, high: low),
        )

        service.run_job("job-1")

        assert review.calls == [(item.series_id, 1)]
        assert repository.get_job("job-1")["status"] == expected_status
        service.shutdown()


def test_page_and_series_delays_use_configured_ranges(tmp_path):
    sleeps = []
    ranges = []

    class RecordingRng:
        def uniform(self, low, high):
            ranges.append((low, high))
            return (low + high) / 2

    config = CreateJobBody(
        mode="verification",
        max_series=2,
        max_pages_per_series=2,
        request_delay_min_seconds=2,
        request_delay_max_seconds=4,
        series_delay_min_seconds=5,
        series_delay_max_seconds=10,
    ).to_config()
    repository, catalog, review, service = make_service(
        tmp_path,
        config,
        [make_series(1), make_series(2)],
        lambda series, page, call: make_page(series, page),
        sleeper=sleeps.append,
        rng=RecordingRng(),
    )

    service.run_job("job-1")

    assert ranges == [(2, 4), (5, 10), (2, 4)]
    assert sleeps == [3, 7.5, 3]
    service.shutdown()


def test_transient_error_retries_after_5_15_45_seconds(tmp_path):
    sleeps = []

    def responder(series, page, call):
        if call <= 3:
            raise TimeoutError("temporary timeout")
        return make_page(series, page, total=1)

    repository, catalog, review, service = make_service(
        tmp_path,
        CreateJobBody(mode="verification", max_series=1, max_pages_per_series=1).to_config(),
        [make_series(1)],
        responder,
        sleeper=sleeps.append,
    )

    service.run_job("job-1")

    assert sleeps == [5, 15, 45]
    assert len(review.calls) == 4
    assert repository.get_job("job-1")["status"] == "completed"
    service.shutdown()


def test_403_429_and_verification_pause_immediately(tmp_path):
    for index, message in enumerate(("HTTP 403", "HTTP 429", "verification page"), start=1):
        case_dir = tmp_path / str(index)
        case_dir.mkdir()

        def responder(series, page, call, *, message=message):
            raise AutohomeAccessPaused(message)

        repository, catalog, review, service = make_service(
            case_dir,
            CreateJobBody(mode="verification").to_config(),
            [make_series(1)],
            responder,
        )

        service.run_job("job-1")

        job = repository.get_job("job-1")
        assert job["status"] == "paused"
        assert message in job["last_error"]
        assert len(review.calls) == 1
        service.shutdown()


def test_single_series_failure_continues_and_finishes_partial_failed(tmp_path):
    first, second = make_series(1), make_series(2)

    def responder(series, page, call):
        if series.series_id == first.series_id:
            raise TimeoutError("series unavailable")
        return make_page(series, page, total=1)

    repository, catalog, review, service = make_service(
        tmp_path,
        CreateJobBody(mode="verification", max_series=2, max_pages_per_series=1).to_config(),
        [first, second],
        responder,
    )

    service.run_job("job-1")

    job = repository.get_job("job-1")
    assert review.calls == [(first.series_id, 1)] * 4 + [(second.series_id, 1)]
    assert job["status"] == "partial_failed"
    assert job["failed_count"] == 1
    assert repository.list_reviews(series_id=second.series_id)["total"] == 1
    service.shutdown()


def test_second_active_job_is_rejected(tmp_path):
    repository = CollectionRepository(tmp_path / "collection.sqlite3")
    config = CreateJobBody(mode="verification").to_config()
    repository.create_job("job-1", config, NOW.isoformat())
    repository.create_job("job-2", config, NOW.isoformat())
    service = CollectionService(
        repository,
        catalog_adapter_factory=lambda: FakeCatalogAdapter([]),
        review_adapter_factory=lambda session: FakeReviewAdapter(lambda *_: None),
        sleeper=lambda seconds: None,
        clock=lambda: NOW,
        rng=SimpleNamespace(uniform=lambda low, high: low),
    )

    with pytest.raises(TaskControlError, match="已有活动采集任务"):
        service.start("job-2")

    service.shutdown()


def test_discovery_failure_pauses_without_exposing_adapter_internals(tmp_path):
    repository = CollectionRepository(tmp_path / "collection.sqlite3")
    repository.create_job(
        "job-1", CreateJobBody(mode="verification").to_config(), NOW.isoformat()
    )

    class BrokenCatalog:
        def discover(self, max_series):
            raise RuntimeError(r"BrowserType.launch failed at C:\Users\secret\chrome.exe")

    service = CollectionService(
        repository,
        catalog_adapter_factory=BrokenCatalog,
        review_adapter_factory=lambda session: None,
        sleeper=lambda seconds: None,
        clock=lambda: NOW,
        rng=SimpleNamespace(uniform=lambda low, high: low),
    )

    service.run_job("job-1")

    job = repository.get_job("job-1")
    assert job["status"] == "paused"
    assert job["last_error"] == "汽车之家车系目录访问失败，请检查浏览器安装、网络和页面结构后重试"
    assert "secret" not in repository.list_events("job-1")[0]["message"]
    service.shutdown()
