from backend.collection.coordination import ExternalAccessCoordinator
from backend.sales_collection.domain import (
    CreateSalesJobBody,
    SalesAccessVerificationRequired,
    SalesMonthResult,
    SalesRecord,
)
from backend.sales_collection.repository import SalesCollectionRepository
from backend.sales_collection.service import SalesCollectionService


NOW = "2026-10-19T12:00:00+00:00"


class SuccessfulAdapter:
    def __init__(self, platform: str):
        self.platform = platform

    def fetch_month(self, month: str) -> SalesMonthResult:
        return SalesMonthResult(
            records=[
                SalesRecord(
                    platform=self.platform,
                    month=month,
                    series_id=f"{self.platform}-1",
                    series_name="Model Y",
                    sales_volume=100,
                    rank=1,
                    source_url=f"https://example.test/{self.platform}/{month}",
                )
            ],
            snapshot_hash=f"{self.platform}-{month}",
        )


class BlockedAdapter:
    def fetch_month(self, month: str) -> SalesMonthResult:
        raise SalesAccessVerificationRequired("平台要求人工验证")


def test_service_keeps_successful_steps_when_another_platform_is_blocked(tmp_path):
    repository = SalesCollectionRepository(tmp_path / "platform.sqlite3")
    repository.create_job(
        "job",
        CreateSalesJobBody(
            start_month="2026-01",
            end_month="2026-02",
            platforms=["autohome", "dongchedi"],
        ),
        NOW,
    )
    coordinator = ExternalAccessCoordinator()
    service = SalesCollectionService(
        repository,
        coordinator,
        adapter_factory=lambda platform: (
            SuccessfulAdapter(platform)
            if platform == "autohome"
            else BlockedAdapter()
        ),
        clock=lambda: NOW,
    )

    service.start("job").result(timeout=5)
    detail = repository.get_job("job")
    service.shutdown()

    assert detail["status"] == "partial_failed"
    assert detail["completed_steps"] == 2
    assert detail["failed_steps"] == 2
    assert detail["record_count"] == 2
    assert {step["error_code"] for step in detail["steps"] if step["status"] == "failed"} == {
        "access_verification_required"
    }
    assert coordinator.current() is None


def test_service_marks_all_successful_steps_completed(tmp_path):
    repository = SalesCollectionRepository(tmp_path / "platform.sqlite3")
    repository.create_job(
        "job",
        CreateSalesJobBody(
            start_month="2026-01", end_month="2026-01", platforms=["autohome"]
        ),
        NOW,
    )
    service = SalesCollectionService(
        repository,
        ExternalAccessCoordinator(),
        adapter_factory=SuccessfulAdapter,
        clock=lambda: NOW,
    )

    service.start("job").result(timeout=5)
    detail = repository.get_job("job")
    service.shutdown()

    assert detail["status"] == "completed"
    assert detail["completed_steps"] == 1
    assert detail["failed_steps"] == 0
