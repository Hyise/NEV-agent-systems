import csv
import io

import pytest
from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.sales_collection.domain import CreateSalesJobBody, SalesRecord


NOW = "2026-10-19T12:00:00+00:00"


class RecordingSalesService:
    def __init__(self, repository, coordinator):
        self.repository = repository
        self.coordinator = coordinator
        self.started: list[str] = []
        self.shutdown_called = False

    def start(self, job_id: str):
        self.started.append(job_id)

    def shutdown(self):
        self.shutdown_called = True


@pytest.fixture
def sales_client(tmp_path):
    services: list[RecordingSalesService] = []

    def factory(repository, coordinator):
        service = RecordingSalesService(repository, coordinator)
        services.append(service)
        return service

    app = create_app(
        tmp_path / "sales-api.sqlite3",
        ROOT / "backend/data/research",
        sales_collection_service_factory=factory,
    )
    with TestClient(app) as client:
        yield client, services[0]
    assert services[0].shutdown_called is True


def test_create_sales_job_validates_months_and_starts_service(sales_client):
    client, service = sales_client

    invalid = client.post(
        "/api/sales-collection/jobs",
        json={
            "start_month": "2026-05",
            "end_month": "2026-04",
            "platforms": ["autohome"],
        },
    )
    created = client.post(
        "/api/sales-collection/jobs",
        json={
            "start_month": "2026-01",
            "end_month": "2026-04",
            "platforms": ["autohome", "dongchedi", "yiche"],
        },
    )

    assert invalid.status_code == 422
    assert created.status_code == 201
    assert created.json()["total_steps"] == 12
    assert service.started == [created.json()["id"]]
    detail = client.get(f"/api/sales-collection/jobs/{created.json()['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["steps"]) == 12


def test_create_sales_job_conflicts_with_other_external_collection(sales_client):
    client, _service = sales_client
    coordinator = client.app.state.external_access_coordinator
    assert coordinator.try_reserve("collection", "review-job") is True
    try:
        response = client.post(
            "/api/sales-collection/jobs",
            json={
                "start_month": "2026-01",
                "end_month": "2026-01",
                "platforms": ["autohome"],
            },
        )
    finally:
        coordinator.release("collection", "review-job")

    assert response.status_code == 409
    assert "其他采集任务" in response.json()["detail"]


def test_sales_records_filter_and_csv_export_escape_formula_text(sales_client):
    client, _service = sales_client
    repository = client.app.state.sales_collection_repository
    repository.create_job(
        "seed-job",
        CreateSalesJobBody(
            start_month="2026-01", end_month="2026-01", platforms=["autohome"]
        ),
        NOW,
    )
    repository.save_month_records(
        "seed-job",
        "autohome",
        "2026-01",
        [
            SalesRecord(
                platform="autohome",
                month="2026-01",
                series_id="danger",
                series_name="=危险公式",
                sales_volume=10,
                rank=1,
                source_url="https://www.autohome.com.cn/rank/1",
            )
        ],
        "snapshot",
        NOW,
    )

    listed = client.get(
        "/api/sales-collection/records",
        params={"platform": "autohome", "month": "2026-01", "search": "危险"},
    )
    exported = client.get(
        "/api/sales-collection/export",
        params={"platform": "autohome", "month": "2026-01"},
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    reader = csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig")))
    row = next(reader)
    assert row["平台车系名称"] == "'=危险公式"
    assert row["销量"] == "10"


def test_sales_overview_declares_live_and_verification_required_sources(sales_client):
    client, _service = sales_client

    response = client.get("/api/sales-collection/overview")

    assert response.status_code == 200
    sources = {item["platform"]: item["availability"] for item in response.json()["sources"]}
    assert sources == {
        "autohome": "live",
        "dongchedi": "verification_required",
        "yiche": "verification_required",
    }
