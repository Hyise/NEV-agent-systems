from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.collection.domain import VehicleSeries

NOW = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)


def make_series(index: int, name: str | None = None) -> VehicleSeries:
    series_id = str(5000 + index)
    return VehicleSeries(
        series_id=series_id,
        series_name=name or f"测试车系 {index}",
        series_url=f"https://www.autohome.com.cn/{series_id}/",
        review_url=f"https://k.autohome.com.cn/{series_id}/",
        discovery_rank=index,
    )


class RecordingCatalogService:
    def __init__(self, repository, coordinator):
        self.repository = repository
        self.coordinator = coordinator
        self.started = []
        self.cancelled = []
        self.shutdown_called = False

    def start(self, run_id, batch_id):
        self.repository.create_run(run_id, batch_id, NOW.isoformat())
        self.started.append((run_id, batch_id))

    def cancel(self, run_id):
        self.repository.request_cancel(run_id, NOW.isoformat())
        self.cancelled.append(run_id)

    def shutdown(self):
        self.shutdown_called = True


@pytest.fixture
def catalog_client(tmp_path):
    services = []

    def factory(repository, coordinator):
        service = RecordingCatalogService(repository, coordinator)
        services.append(service)
        return service

    app = create_app(
        tmp_path / "catalog-api.sqlite3",
        ROOT / "backend/data/research",
        catalog_service_factory=factory,
    )
    with TestClient(app) as client:
        yield client, app, services[0]
    assert services[0].shutdown_called is True


def publish(repository, run_id, batch_id, series, minute=1):
    repository.create_run(run_id, batch_id, NOW.isoformat())
    repository.append_entries(
        run_id,
        series,
        scanned_count=len(series),
        skipped_count=0,
        current_page=1,
        updated_at=f"2026-10-09T08:{minute:02d}:00+00:00",
    )
    return repository.publish_run(
        run_id,
        f"2026-10-09T08:{minute + 1:02d}:00+00:00",
        source_exhausted=True,
    )


def test_empty_catalog_status_and_discovery_start(catalog_client):
    client, _, service = catalog_client

    status = client.get("/api/collection/catalog/status")
    started = client.post("/api/collection/catalog/discover")

    assert status.status_code == 200
    assert status.json() == {
        "active_batch_id": None,
        "series_count": 0,
        "published_at": None,
        "source_url": "https://www.autohome.com.cn/price/ev#pvareaid=3311257",
        "source_exhausted": False,
        "active_run": None,
    }
    assert started.status_code == 202
    assert started.json()["status"] == "queued"
    assert started.json()["target_unique_series"] == 1000
    assert len(service.started) == 1


def test_second_active_catalog_run_returns_409(catalog_client):
    client, _, _ = catalog_client
    assert client.post("/api/collection/catalog/discover").status_code == 202

    response = client.post("/api/collection/catalog/discover")

    assert response.status_code == 409
    assert "已有" in response.json()["detail"]


def test_catalog_query_and_selection_share_the_same_filter(catalog_client):
    client, app, _ = catalog_client
    repository = app.state.catalog_repository
    publish(
        repository,
        "run-old",
        "batch-old",
        [
            make_series(1, "星海 A"),
            make_series(2, "星海 B"),
            make_series(3, "远山 C"),
        ],
    )

    page = client.get(
        "/api/collection/catalog", params={"query": "星海", "page": 1, "page_size": 1}
    )
    selection = client.get(
        "/api/collection/catalog/selection", params={"query": "星海"}
    )

    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["rows"][0]["batch_id"] == "batch-old"
    assert page.json()["rows"][0]["published_at"] == "2026-10-09T08:02:00+00:00"
    assert selection.json() == {
        "batch_id": "batch-old",
        "series_ids": ["5001", "5002"],
        "total": 2,
    }


def test_catalog_run_detail_cancel_and_missing_run(catalog_client):
    client, _, service = catalog_client
    started = client.post("/api/collection/catalog/discover").json()
    run_id = started["id"]

    detail = client.get(f"/api/collection/catalog/discover/{run_id}")
    cancelled = client.post(f"/api/collection/catalog/discover/{run_id}/cancel")
    missing = client.get("/api/collection/catalog/discover/missing")

    assert detail.status_code == 200
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelling"
    assert service.cancelled == [run_id]
    assert missing.status_code == 404


def test_completed_short_status_is_serialized(catalog_client):
    client, app, _ = catalog_client
    run = publish(
        app.state.catalog_repository,
        "run-short",
        "batch-short",
        [make_series(1)],
    )

    response = client.get(f"/api/collection/catalog/discover/{run['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed_short"
    assert response.json()["source_exhausted"] is True
