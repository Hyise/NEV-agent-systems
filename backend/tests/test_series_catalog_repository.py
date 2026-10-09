import sqlite3

import pytest

from backend.collection.catalog_repository import SeriesCatalogRepository
from backend.collection.domain import VehicleSeries
from backend.collection.repository import CollectionRepository

CREATED_AT = "2026-10-09T08:00:00+00:00"


def make_series(series_id: str = "5769", name: str = "Model Y", rank: int = 1):
    return VehicleSeries(
        series_id=series_id,
        series_name=name,
        series_url=f"https://www.autohome.com.cn/{series_id}/",
        review_url=f"https://k.autohome.com.cn/{series_id}/",
        discovery_rank=rank,
    )


def make_repository(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    CollectionRepository(path)
    return SeriesCatalogRepository(path)


def test_catalog_repository_creates_versioned_tables(tmp_path):
    repository = make_repository(tmp_path)

    with sqlite3.connect(repository.path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert {
        "series_catalog_runs",
        "series_catalog_entries",
        "series_catalog_state",
        "collection_job_series",
    } <= names


def test_append_entries_deduplicates_within_batch_and_preserves_first_rank(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("run-1", "batch-1", CREATED_AT)

    repository.append_entries(
        "run-1",
        [make_series(rank=1), make_series(name="Model Y 焕新版", rank=9)],
        scanned_count=2,
        skipped_count=0,
        current_page=1,
        updated_at="2026-10-09T08:01:00+00:00",
    )

    with sqlite3.connect(repository.path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM series_catalog_entries WHERE batch_id='batch-1'"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["series_name"] == "Model Y"
    assert rows[0]["discovery_rank"] == 1
    assert repository.get_run("run-1")["unique_count"] == 1


def test_unpublished_batch_is_not_visible(tmp_path):
    repository = make_repository(tmp_path)
    repository.create_run("run-1", "batch-1", CREATED_AT)
    repository.append_entries(
        "run-1",
        [make_series()],
        scanned_count=1,
        skipped_count=0,
        current_page=1,
        updated_at="2026-10-09T08:01:00+00:00",
    )

    assert repository.list_catalog() == {
        "rows": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }
    assert repository.selection_ids() == []


def stage_one(repository, run_id: str, batch_id: str, series_id: str, minute: int):
    created_at = f"2026-10-09T08:{minute:02d}:00+00:00"
    repository.create_run(run_id, batch_id, created_at)
    repository.append_entries(
        run_id,
        [make_series(series_id=series_id, name=f"车系 {series_id}")],
        scanned_count=1,
        skipped_count=0,
        current_page=1,
        updated_at=created_at,
    )
    return created_at


def test_publish_switches_active_batch_in_one_transaction(tmp_path):
    repository = make_repository(tmp_path)
    stage_one(repository, "run-1", "batch-1", "5001", 1)

    run = repository.publish_run(
        "run-1", "2026-10-09T08:02:00+00:00", source_exhausted=True
    )

    assert run["status"] == "completed_short"
    assert run["source_exhausted"] is True
    assert repository.catalog_status()["active_batch_id"] == "batch-1"
    assert repository.list_catalog()["rows"][0]["series_id"] == "5001"


def test_publish_failure_keeps_previous_batch_active(tmp_path):
    repository = make_repository(tmp_path)
    stage_one(repository, "run-1", "batch-1", "5001", 1)
    repository.publish_run(
        "run-1", "2026-10-09T08:02:00+00:00", source_exhausted=True
    )
    stage_one(repository, "run-2", "batch-2", "5002", 3)
    with sqlite3.connect(repository.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_catalog_publish
            BEFORE UPDATE OF active_batch_id ON series_catalog_state
            BEGIN SELECT RAISE(ABORT, 'publish rejected'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="publish rejected"):
        repository.publish_run(
            "run-2", "2026-10-09T08:04:00+00:00", source_exhausted=True
        )

    assert repository.catalog_status()["active_batch_id"] == "batch-1"
    assert [row["series_id"] for row in repository.list_catalog()["rows"]] == [
        "5001"
    ]
    assert repository.get_run("run-2")["status"] == "discovering"


def test_failed_and_cancelled_runs_discard_staged_entries(tmp_path):
    repository = make_repository(tmp_path)
    stage_one(repository, "run-1", "batch-1", "5001", 1)
    repository.fail_run(
        "run-1",
        "source_error",
        "目录读取失败",
        "2026-10-09T08:02:00+00:00",
    )
    stage_one(repository, "run-2", "batch-2", "5002", 3)
    repository.cancel_run("run-2", "2026-10-09T08:04:00+00:00")

    with sqlite3.connect(repository.path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM series_catalog_entries"
        ).fetchone()[0]

    assert count == 0
    assert repository.get_run("run-1")["status"] == "failed"
    assert repository.get_run("run-2")["status"] == "cancelled"


def test_only_three_unreferenced_successful_batches_are_retained(tmp_path):
    repository = make_repository(tmp_path)
    for index in range(1, 5):
        stage_one(
            repository,
            f"run-{index}",
            f"batch-{index}",
            str(5000 + index),
            index,
        )
        repository.publish_run(
            f"run-{index}",
            f"2026-10-09T08:{index + 10:02d}:00+00:00",
            source_exhausted=True,
        )

    with sqlite3.connect(repository.path) as connection:
        batches = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT batch_id FROM series_catalog_entries ORDER BY batch_id"
            )
        ]

    assert batches == ["batch-2", "batch-3", "batch-4"]
    assert repository.get_run("run-1")["status"] == "completed_short"


def test_restart_fails_interrupted_run_without_changing_active_catalog(tmp_path):
    repository = make_repository(tmp_path)
    stage_one(repository, "run-1", "batch-1", "5001", 1)
    repository.publish_run(
        "run-1", "2026-10-09T08:02:00+00:00", source_exhausted=True
    )
    stage_one(repository, "run-2", "batch-2", "5002", 3)

    affected = repository.fail_interrupted_runs("2026-10-09T08:04:00+00:00")

    assert affected == 1
    assert repository.get_run("run-2")["status"] == "failed"
    assert repository.get_run("run-2")["error_code"] == "interrupted"
    assert repository.catalog_status()["active_batch_id"] == "batch-1"
    assert repository.selection_ids() == ["5001"]
