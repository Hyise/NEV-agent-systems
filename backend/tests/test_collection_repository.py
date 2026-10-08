import json
import sqlite3

import pytest

from backend.collection.domain import CollectedReview, CreateJobBody, JobStatus, VehicleSeries
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
        CreateJobBody(mode="verification").to_config(),
        "2026-10-08T08:00:00+00:00",
    )


def test_repository_creates_four_collection_tables(tmp_path):
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
