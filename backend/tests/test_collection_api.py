from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.collection.domain import (
    CollectedReview,
    CreateJobBody,
    JobStatus,
    TaskControlError,
    VehicleSeries,
)


class RecordingService:
    def __init__(self, repository):
        self.repository = repository
        self.started = []
        self.shutdown_called = False

    def start(self, job_id):
        self.started.append(job_id)

    def pause(self, job_id):
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] not in {"discovering", "collecting"}:
            raise TaskControlError("当前任务不能暂停")

    def resume(self, job_id):
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] != "paused":
            raise TaskControlError("只有暂停任务可以继续")

    def stop(self, job_id):
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] not in {"queued", "discovering", "collecting", "paused"}:
            raise TaskControlError("当前任务不能停止")

    def shutdown(self):
        self.shutdown_called = True


@pytest.fixture
def client(tmp_path):
    services = []

    def factory(repository):
        service = RecordingService(repository)
        services.append(service)
        return service

    app = create_app(
        tmp_path / "test.sqlite3",
        ROOT / "backend/data/research",
        collection_service_factory=factory,
    )
    with TestClient(app) as test_client:
        yield test_client
    assert services[0].shutdown_called is True


def make_series(index=1):
    series_id = str(5700 + index)
    return VehicleSeries(
        series_id=series_id,
        series_name=f"测试车系 {index}",
        series_url=f"https://www.autohome.com.cn/{series_id}/",
        review_url=f"https://k.autohome.com.cn/{series_id}/",
        discovery_rank=index,
    )


def seed_job(repository, job_id="job-1"):
    return repository.create_job(
        job_id,
        CreateJobBody(mode="verification").to_config(),
        f"2026-10-08T08:00:0{job_id[-1]}+00:00",
    )


def seed_review(repository):
    seed_job(repository)
    series = make_series()
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")
    original = {
        "Koubeiid": "review-1",
        "specname": "2025款 长续航版",
        "contents": [{"structuredname": "满意", "content": "空间充足"}],
        "unknown": {"nested": [1, "中文", None]},
    }
    review = CollectedReview(
        review_id="review-1",
        series_id=series.series_id,
        series_name=series.series_name,
        source_url=f"{series.review_url}#review-1",
        original_review=original,
    )
    repository.save_review_page(
        "job-1", series, [review], 2, "2026-10-08T08:02:00+00:00"
    )
    return series, original


def test_create_job_applies_verification_defaults(client):
    response = client.post("/api/collection/jobs", json={"mode": "verification"})

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "verification"
    assert body["max_series"] == 3
    assert body["max_pages_per_series"] == 2
    assert body["status"] == "queued"
    assert client.app.state.collection_service.started == [body["id"]]


def test_second_active_job_returns_409(client):
    assert client.post("/api/collection/jobs", json={"mode": "verification"}).status_code == 201

    response = client.post("/api/collection/jobs", json={"mode": "verification"})

    assert response.status_code == 409
    assert client.get("/api/collection/jobs").json()["total"] == 1


def test_scheduler_failure_does_not_leave_queued_job(tmp_path):
    class FailingService(RecordingService):
        def start(self, job_id):
            raise RuntimeError("executor unavailable")

    app = create_app(
        tmp_path / "scheduler.sqlite3",
        ROOT / "backend/data/research",
        collection_service_factory=FailingService,
    )

    with TestClient(app) as failing_client:
        response = failing_client.post(
            "/api/collection/jobs", json={"mode": "verification"}
        )
        jobs = failing_client.get("/api/collection/jobs").json()["rows"]

    assert response.status_code == 503
    assert jobs[0]["status"] == "stopped"
    assert jobs[0]["last_error"] == "任务未能启动，请重试"


def test_pause_resume_stop_validate_current_state(client):
    repository = client.app.state.collection_repository
    seed_job(repository)

    assert client.post("/api/collection/jobs/job-1/pause").status_code == 409
    assert client.post("/api/collection/jobs/job-1/resume").status_code == 409
    repository.set_status(
        "job-1", JobStatus.STOPPED, "2026-10-08T08:01:00+00:00", finished=True
    )
    assert client.post("/api/collection/jobs/job-1/stop").status_code == 409
    assert client.post("/api/collection/jobs/missing/pause").status_code == 404


def test_paused_job_remains_visible_and_resumable_from_overview(client):
    repository = client.app.state.collection_repository
    seed_job(repository)
    repository.set_status(
        "job-1",
        JobStatus.PAUSED,
        "2026-10-08T08:01:00+00:00",
        resume_status=JobStatus.DISCOVERING,
    )

    overview = client.get("/api/collection/overview")
    resumed = client.post("/api/collection/jobs/job-1/resume")

    assert overview.status_code == 200
    assert overview.json()["active_job"]["status"] == "paused"
    assert resumed.status_code == 200


def test_overview_jobs_and_series_are_paginated(client):
    repository = client.app.state.collection_repository
    seed_job(repository, "job-1")
    repository.save_discovery(
        "job-1", [make_series(1), make_series(2)], "2026-10-08T08:01:00+00:00"
    )
    repository.set_status(
        "job-1", JobStatus.STOPPED, "2026-10-08T08:00:10+00:00", finished=True
    )
    seed_job(repository, "job-2")

    overview = client.get("/api/collection/overview").json()
    jobs = client.get("/api/collection/jobs", params={"page": 2, "page_size": 1}).json()
    series = client.get("/api/collection/series", params={"page": 2, "page_size": 1}).json()

    assert overview["series_count"] == 2
    assert jobs["total"] == 2 and len(jobs["rows"]) == 1 and jobs["page"] == 2
    assert series["total"] == 2 and len(series["rows"]) == 1 and series["page"] == 2


def test_job_detail_returns_latest_events(client):
    repository = client.app.state.collection_repository
    seed_job(repository)
    repository.record_event(
        "job-1",
        "source_paused",
        "结构变化后暂停",
        "2026-10-08T08:01:00+00:00",
        error_class="AutohomeStructureError",
    )

    response = client.get("/api/collection/jobs/job-1")

    assert response.status_code == 200
    assert response.json()["events"][0]["event_type"] == "source_paused"


def test_review_list_omits_original_payload(client):
    series, _original = seed_review(client.app.state.collection_repository)

    response = client.get("/api/collection/reviews", params={"series_id": series.series_id})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert "original_review" not in body["rows"][0]


def test_review_detail_and_jsonl_are_lossless(client):
    series, original = seed_review(client.app.state.collection_repository)

    detail = client.get("/api/collection/reviews/review-1")
    exported = client.get("/api/collection/export", params={"series_id": series.series_id})

    assert detail.status_code == 200
    assert detail.json()["original_review"] == original
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/x-ndjson; charset=utf-8"
    rows = [json.loads(line) for line in exported.text.splitlines()]
    assert rows == [detail.json()]


def test_export_requires_known_series(client):
    response = client.get("/api/collection/export", params={"series_id": "999999"})

    assert response.status_code == 404


def test_restart_pauses_interrupted_job(tmp_path):
    db_path = tmp_path / "restart.sqlite3"

    def factory(repository):
        return RecordingService(repository)

    first = create_app(
        db_path,
        ROOT / "backend/data/research",
        collection_service_factory=factory,
    )
    repository = first.state.collection_repository
    seed_job(repository)
    repository.set_status(
        "job-1", JobStatus.COLLECTING, "2026-10-08T08:01:00+00:00"
    )

    restarted = create_app(
        db_path,
        ROOT / "backend/data/research",
        collection_service_factory=factory,
    )
    with TestClient(restarted):
        job = restarted.state.collection_repository.get_job("job-1")
        assert job["status"] == "paused"
        assert job["resume_status"] == "collecting"
        assert restarted.state.collection_repository.list_events("job-1")[0][
            "event_type"
        ] == "interrupted"
