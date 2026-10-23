import json

import pytest
from pydantic import ValidationError

from backend.collection.repository import CollectionRepository
from backend.sales_collection.domain import (
    CreateSalesJobBody,
    SalesRecord,
    SalesStepStatus,
)
from backend.sales_collection.repository import SalesCollectionRepository


NOW = "2026-10-19T12:00:00+00:00"


def test_create_job_body_rejects_invalid_or_reversed_months():
    with pytest.raises(ValidationError):
        CreateSalesJobBody(
            start_month="2026-13", end_month="2026-04", platforms=["autohome"]
        )
    with pytest.raises(ValidationError):
        CreateSalesJobBody(
            start_month="2026-05", end_month="2026-04", platforms=["autohome"]
        )
    with pytest.raises(ValidationError):
        CreateSalesJobBody(
            start_month="2026-01",
            end_month="2026-04",
            platforms=["autohome", "autohome"],
        )


def test_create_job_builds_one_step_for_each_platform_and_month(tmp_path):
    repository = SalesCollectionRepository(tmp_path / "platform.sqlite3")
    body = CreateSalesJobBody(
        start_month="2026-01",
        end_month="2026-02",
        platforms=["autohome", "dongchedi"],
    )

    job = repository.create_job("sales-job", body, NOW)
    detail = repository.get_job("sales-job")

    assert job["status"] == "queued"
    assert job["total_steps"] == 4
    assert [(row["platform"], row["month"]) for row in detail["steps"]] == [
        ("autohome", "2026-01"),
        ("autohome", "2026-02"),
        ("dongchedi", "2026-01"),
        ("dongchedi", "2026-02"),
    ]


def test_month_records_are_idempotent_and_exact_names_match_review_series(tmp_path):
    database = tmp_path / "platform.sqlite3"
    CollectionRepository(database)
    repository = SalesCollectionRepository(database)
    body = CreateSalesJobBody(
        start_month="2026-01", end_month="2026-01", platforms=["autohome"]
    )
    repository.create_job("sales-job", body, NOW)
    with repository.connect() as connection:
        connection.execute(
            """
            INSERT INTO vehicle_series (
                platform,series_id,series_name,series_url,review_url,
                discovery_rank,first_discovered_at,last_confirmed_at
            ) VALUES ('autohome','5769','Model Y','series','reviews',1,?,?)
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO reviews (
                platform,review_id,series_id,series_name_snapshot,source_url,
                original_review_json,content_hash,first_collected_at,last_confirmed_at,
                asset_id,source_kind
            ) VALUES ('autohome','r-1','5769','Model Y','source',?,'hash',?,?,
                      'autohome:r-1','autohome')
            """,
            (json.dumps({"content": "review", "posttime": "2026-01-12"}), NOW, NOW),
        )

    first = SalesRecord(
        platform="autohome",
        month="2026-01",
        series_id="5769",
        series_name="Model Y",
        sales_volume=25000,
        rank=1,
        source_url="https://www.autohome.com.cn/rank/1",
    )
    repository.save_month_records(
        "sales-job", "autohome", "2026-01", [first], "snapshot-a", NOW
    )
    changed = first.model_copy(update={"sales_volume": 25123})
    repository.save_month_records(
        "sales-job", "autohome", "2026-01", [changed], "snapshot-b", NOW
    )

    page = repository.list_records(
        platform="autohome", month="2026-01", search="Model", match_status="matched"
    )
    assert page["total"] == 1
    assert page["rows"][0]["sales_volume"] == 25123
    assert page["rows"][0]["review_series_id"] == "5769"
    assert page["rows"][0]["match_status"] == "matched"
    assert page["rows"][0]["match_method"] == "normalized_exact"
    assert repository.get_step("sales-job", "autohome", "2026-01")[
        "status"
    ] == SalesStepStatus.COMPLETED.value

    mapped = repository.list_records(month="2026-01", search="5769")
    assert mapped["total"] == 1
    assert mapped["rows"][0]["review_series_name"] == "Model Y"


def test_list_records_keeps_unmatched_series_explicit(tmp_path):
    repository = SalesCollectionRepository(tmp_path / "platform.sqlite3")
    body = CreateSalesJobBody(
        start_month="2026-01", end_month="2026-01", platforms=["autohome"]
    )
    repository.create_job("sales-job", body, NOW)
    repository.save_month_records(
        "sales-job",
        "autohome",
        "2026-01",
        [
            SalesRecord(
                platform="autohome",
                month="2026-01",
                series_id="7806",
                series_name="星愿",
                sales_volume=28805,
                rank=1,
                source_url="https://www.autohome.com.cn/rank/1",
            )
        ],
        "snapshot-a",
        NOW,
    )

    page = repository.list_records(match_status="unmatched")

    assert page["total"] == 1
    assert page["rows"][0]["review_series_id"] is None
    assert page["rows"][0]["match_status"] == "unmatched"


def test_sales_series_only_matches_reviews_from_the_same_month(tmp_path):
    database = tmp_path / "platform.sqlite3"
    CollectionRepository(database)
    repository = SalesCollectionRepository(database)
    repository.create_job(
        "sales-job",
        CreateSalesJobBody(
            start_month="2026-01",
            end_month="2026-02",
            platforms=["autohome"],
        ),
        NOW,
    )
    with repository.connect() as connection:
        connection.execute(
            """
            INSERT INTO vehicle_series (
                platform,series_id,series_name,series_url,review_url,
                discovery_rank,first_discovered_at,last_confirmed_at
            ) VALUES ('autohome','5769','Model Y','series','reviews',1,?,?)
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO reviews (
                platform,review_id,series_id,series_name_snapshot,source_url,
                original_review_json,content_hash,first_collected_at,last_confirmed_at,
                asset_id,source_kind
            ) VALUES ('autohome','r-jan','5769','Model Y','source',?,'hash',?, ?,
                      'autohome:r-jan','autohome')
            """,
            (json.dumps({"content": "review", "posttime": "2026-01-12"}), NOW, NOW),
        )

    repository.save_month_records(
        "sales-job",
        "autohome",
        "2026-02",
        [
            SalesRecord(
                platform="autohome",
                month="2026-02",
                series_id="5769",
                series_name="Model Y",
                sales_volume=20000,
                rank=1,
                source_url="https://www.autohome.com.cn/rank/1",
            )
        ],
        "snapshot-february",
        NOW,
    )

    page = repository.list_records(month="2026-02")

    assert page["rows"][0]["match_status"] == "unmatched"
    assert page["rows"][0]["review_series_id"] is None
