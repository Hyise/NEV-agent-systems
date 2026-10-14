import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from backend.collection.catalog_domain import CatalogSelectionError
from backend.collection.catalog_repository import SeriesCatalogRepository
from backend.collection.domain import (
    CollectedReview,
    CreateJobBody,
    JobStatus,
    TaskControlError,
    VehicleSeries,
)
from backend.collection.repository import CollectionRepository


def make_repository(tmp_path):
    return CollectionRepository(tmp_path / "collection.sqlite3")


def make_series(name="Model Y", rank=1):
    return VehicleSeries(
        series_id="5769",
        series_name=name,
        series_url="https://www.autohome.com.cn/5769/",
        review_url="https://k.autohome.com.cn/5769/",
        discovery_rank=rank,
    )


def make_review(content="空间充足"):
    original = {
        "Koubeiid": "review-1",
        "specname": "2025款 长续航版",
        "contents": [{"structuredname": "满意", "content": content}],
        "unknown": {"nested": [1, "中文", None]},
    }
    return CollectedReview(
        review_id="review-1",
        series_id="5769",
        series_name="Model Y",
        source_url="https://k.autohome.com.cn/5769/#review-1",
        original_review=original,
    )


def create_job(repository, job_id="job-1"):
    return repository.create_job(
        job_id,
        CreateJobBody(mode="verification", selected_series_ids=["5769"]).to_config(),
        "2026-10-08T08:00:00+00:00",
    )


def publish_catalog(repository, batch_id, series, minute=0):
    catalog = SeriesCatalogRepository(repository.path)
    run_id = f"run-{batch_id}"
    created_at = f"2026-10-09T09:{minute:02d}:00+00:00"
    catalog.create_run(run_id, batch_id, created_at)
    catalog.append_entries(
        run_id,
        series,
        scanned_count=len(series),
        skipped_count=0,
        current_page=1,
        updated_at=created_at,
    )
    catalog.publish_run(run_id, created_at, source_exhausted=True)
    return catalog


def test_create_job_snapshots_selected_active_catalog_in_submitted_order(tmp_path):
    repository = make_repository(tmp_path)
    first = make_series(name="Model Y", rank=1)
    second = VehicleSeries(
        series_id="526",
        series_name="汉",
        series_url="https://www.autohome.com.cn/526/",
        review_url="https://k.autohome.com.cn/526/",
        discovery_rank=2,
    )
    publish_catalog(repository, "batch-1", [first, second])
    config = CreateJobBody(
        mode="verification", selected_series_ids=["526", "5769"]
    ).to_config()

    job = repository.create_job_from_catalog(
        "job-selected",
        config,
        ["526", "5769"],
        "2026-10-09T10:00:00+00:00",
    )

    assert job["series_manifest"] == []
    assert job["discovered_count"] == 2
    assert [item.series_id for item in repository.job_series("job-selected")] == [
        "526",
        "5769",
    ]
    assert [item.series_name for item in repository.job_series("job-selected")] == [
        "汉",
        "Model Y",
    ]


def test_stale_batch_ids_return_all_invalid_ids_and_create_no_job(tmp_path):
    repository = make_repository(tmp_path)
    publish_catalog(repository, "batch-1", [make_series()], minute=1)
    newer = VehicleSeries(
        series_id="999",
        series_name="新目录车系",
        series_url="https://www.autohome.com.cn/999/",
        review_url="https://k.autohome.com.cn/999/",
        discovery_rank=1,
    )
    publish_catalog(repository, "batch-2", [newer], minute=2)
    config = CreateJobBody(
        mode="verification", selected_series_ids=["5769", "123"]
    ).to_config()

    with pytest.raises(CatalogSelectionError) as error:
        repository.create_job_from_catalog(
            "job-stale",
            config,
            ["5769", "123"],
            "2026-10-09T10:00:00+00:00",
        )

    assert error.value.invalid_series_ids == ["5769", "123"]
    assert repository.get_job("job-stale") is None


@pytest.mark.parametrize("selected", [[], ["5769", "5769"]])
def test_empty_or_duplicate_selection_creates_no_job(tmp_path, selected):
    repository = make_repository(tmp_path)
    publish_catalog(repository, "batch-1", [make_series()])
    config = CreateJobBody(
        mode="verification", selected_series_ids=["5769"]
    ).to_config()

    with pytest.raises(CatalogSelectionError):
        repository.create_job_from_catalog(
            "job-invalid", config, selected, "2026-10-09T10:00:00+00:00"
        )

    assert repository.get_job("job-invalid") is None


def test_legacy_json_manifest_remains_readable(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    repository.save_discovery(
        "job-1", [make_series()], "2026-10-08T08:01:00+00:00"
    )

    assert repository.job_series("job-1") == [make_series()]


def test_repository_creates_collection_tables(tmp_path):
    repository = make_repository(tmp_path)

    with sqlite3.connect(repository.path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'collection_%'"
            )
        }
        names.add(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='vehicle_series'"
            ).fetchone()[0]
        )
        names.add(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'"
            ).fetchone()[0]
        )

    assert names == {
        "collection_jobs",
        "vehicle_series",
        "reviews",
        "collection_events",
        "collection_job_series",
    }


def test_series_upsert_keeps_one_id_and_updates_current_name(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    repository.save_discovery("job-1", [make_series()], "2026-10-08T08:01:00+00:00")
    repository.save_discovery(
        "job-1", [make_series("Model Y 焕新版", rank=2)], "2026-10-08T08:02:00+00:00"
    )

    page = repository.list_series(page=1, page_size=20)

    assert page["total"] == 1
    assert page["rows"][0]["series_name"] == "Model Y 焕新版"
    assert page["rows"][0]["discovery_rank"] == 1
    assert repository.get_job("job-1")["series_manifest"] == [
        {
            "platform": "autohome",
            "series_id": "5769",
            "series_name": "Model Y 焕新版",
            "series_url": "https://www.autohome.com.cn/5769/",
            "review_url": "https://k.autohome.com.cn/5769/",
            "discovery_rank": 2,
        }
    ]


def test_review_page_saves_reviews_and_cursor_in_one_transaction(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    series = make_series()
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")

    with sqlite3.connect(repository.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_cursor_update
            BEFORE UPDATE OF current_page ON collection_jobs
            BEGIN SELECT RAISE(ABORT, 'cursor rejected'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="cursor rejected"):
        repository.save_review_page(
            "job-1", series, [make_review()], 2, "2026-10-08T08:02:00+00:00"
        )

    assert repository.list_reviews(page=1, page_size=20)["total"] == 0
    assert repository.get_job("job-1")["current_page"] == 1


def test_duplicate_review_updates_last_confirmed_without_new_row(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    series = make_series()
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")
    repository.save_review_page(
        "job-1", series, [make_review()], 2, "2026-10-08T08:02:00+00:00"
    )
    repository.save_review_page(
        "job-1", series, [make_review()], 3, "2026-10-08T08:03:00+00:00"
    )

    page = repository.list_reviews(page=1, page_size=20)
    job = repository.get_job("job-1")

    assert page["total"] == 1
    assert page["rows"][0]["last_confirmed_at"] == "2026-10-08T08:03:00+00:00"
    assert job["saved_count"] == 1
    assert job["duplicate_count"] == 1


def test_review_content_change_is_audited(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    series = make_series()
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")
    repository.save_review_page(
        "job-1", series, [make_review()], 2, "2026-10-08T08:02:00+00:00"
    )
    repository.save_review_page(
        "job-1", series, [make_review("空间一般")], 3, "2026-10-08T08:03:00+00:00"
    )

    detail = repository.get_review("review-1")
    events = repository.list_events("job-1")

    assert detail["original_review"]["contents"][0]["content"] == "空间一般"
    assert [event["event_type"] for event in events] == ["review_changed"]
    assert json.loads(events[0]["details"])["previous_hash"] != detail["content_hash"]


def test_dynamic_review_metadata_is_updated_without_content_change_event(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    series = make_series()
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")
    original = make_review()
    first_payload = {
        **original.original_review,
        "commentcount": 1,
        "viewcount": 10,
        "posttimeV2": "昨天",
        "piclist": ["https://img.example/2.jpg", "https://img.example/1.jpg"],
    }
    second_payload = {
        **first_payload,
        "commentcount": 2,
        "viewcount": 20,
        "posttimeV2": "2天前",
        "piclist": ["https://cdn.example/new-2.jpg", "https://cdn.example/new-1.jpg"],
    }
    first = CollectedReview(
        review_id=original.review_id,
        series_id=original.series_id,
        series_name=original.series_name,
        source_url=original.source_url,
        original_review=first_payload,
    )
    second = CollectedReview(
        review_id=original.review_id,
        series_id=original.series_id,
        series_name=original.series_name,
        source_url=original.source_url,
        original_review=second_payload,
    )

    repository.save_review_page(
        "job-1", series, [first], 2, "2026-10-08T08:02:00+00:00"
    )
    result = repository.save_review_page(
        "job-1", series, [second], 3, "2026-10-08T08:03:00+00:00"
    )

    assert result == {
        "saved": 0,
        "duplicates": 1,
        "changed": 0,
        "deleted_skipped": 0,
    }
    assert repository.list_events("job-1") == []
    assert repository.get_review("review-1")["original_review"]["viewcount"] == 20


def test_interrupted_active_job_becomes_paused_and_resumable(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    repository.set_status(
        "job-1", JobStatus.DISCOVERING, "2026-10-08T08:01:00+00:00"
    )

    affected = repository.pause_interrupted_jobs("2026-10-08T08:02:00+00:00")
    job = repository.get_job("job-1")

    assert affected == 1
    assert job["status"] == "paused"
    assert job["resume_status"] == "discovering"
    assert repository.list_events("job-1")[0]["event_type"] == "interrupted"


def test_paused_job_remains_controllable_and_blocks_a_second_job(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    repository.set_status(
        "job-1",
        JobStatus.PAUSED,
        "2026-10-08T08:01:00+00:00",
        resume_status=JobStatus.DISCOVERING,
    )

    assert repository.overview()["active_job"]["status"] == "paused"
    with pytest.raises(TaskControlError, match="已有活动采集任务"):
        repository.create_job(
            "job-2",
            CreateJobBody(mode="verification", selected_series_ids=["5769"]).to_config(),
            "2026-10-08T08:02:00+00:00",
        )


def test_concurrent_job_creation_preserves_single_controllable_job(tmp_path):
    repository = make_repository(tmp_path)
    barrier = Barrier(2)

    def create(job_id):
        barrier.wait(timeout=5)
        try:
            repository.create_job(
                job_id,
                CreateJobBody(
                    mode="verification", selected_series_ids=["5769"]
                ).to_config(),
                "2026-10-08T08:00:00+00:00",
            )
            return "created"
        except TaskControlError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, ("job-1", "job-2")))

    assert sorted(results) == ["created", "rejected"]
    assert repository.list_jobs()["total"] == 1


def test_list_events_returns_latest_hundred_in_chronological_order(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    for index in range(105):
        repository.record_event(
            "job-1", "sample", f"event-{index}", f"2026-10-08T08:00:{index:02d}+00:00"
        )

    events = repository.list_events("job-1")

    assert len(events) == 100
    assert events[0]["message"] == "event-5"
    assert events[-1]["message"] == "event-104"


def test_detail_and_export_return_lossless_original_review(tmp_path):
    repository = make_repository(tmp_path)
    create_job(repository)
    series = make_series()
    review = make_review()
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")
    repository.save_review_page(
        "job-1", series, [review], 2, "2026-10-08T08:02:00+00:00"
    )

    summary = repository.list_reviews(page=1, page_size=20)["rows"][0]
    detail = repository.get_review("review-1")
    exported = list(repository.iter_reviews_for_export("5769"))

    assert "original_review" not in summary
    assert detail["original_review"] == review.original_review
    assert exported == [detail]


def test_new_review_gets_stable_asset_identity_and_default_metadata(tmp_path):
    repository = make_repository(tmp_path)
    series = make_series()
    create_job(repository)
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")

    repository.save_review_page(
        "job-1", series, [make_review()], 2, "2026-10-08T08:02:00+00:00"
    )

    with repository.connect() as connection:
        review = connection.execute(
            "SELECT asset_id, source_kind FROM reviews WHERE review_id='review-1'"
        ).fetchone()
        metadata = connection.execute(
            "SELECT analysis_enabled, revision FROM review_asset_metadata "
            "WHERE asset_id='autohome:review-1'"
        ).fetchone()
    assert dict(review) == {
        "asset_id": "autohome:review-1",
        "source_kind": "autohome",
    }
    assert dict(metadata) == {"analysis_enabled": 1, "revision": 1}


def test_unreleased_deletion_tombstone_blocks_silent_recollection(tmp_path):
    repository = make_repository(tmp_path)
    series = make_series()
    create_job(repository)
    repository.save_discovery("job-1", [series], "2026-10-08T08:01:00+00:00")
    with repository.connect() as connection:
        connection.execute(
            """
            INSERT INTO review_deletion_audits (
                audit_id, asset_id, source_kind, platform, review_id, series_id,
                series_name_snapshot, content_hash, reason, deleted_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "audit-1",
                "autohome:review-1",
                "autohome",
                "autohome",
                "review-1",
                "5769",
                "Model Y",
                "a" * 64,
                "用户删除",
                "2026-10-08T08:01:30+00:00",
            ),
        )

    result = repository.save_review_page(
        "job-1", series, [make_review()], 2, "2026-10-08T08:02:00+00:00"
    )

    assert result == {
        "saved": 0,
        "duplicates": 0,
        "changed": 0,
        "deleted_skipped": 1,
    }
    assert repository.get_review("review-1") is None
    assert repository.get_job("job-1")["deleted_review_skip_count"] == 1
