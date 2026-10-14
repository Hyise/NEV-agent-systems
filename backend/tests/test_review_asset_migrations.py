import sqlite3

import pytest

from backend.collection.asset_migrations import ensure_review_asset_schema


LEGACY_COLLECTION_SCHEMA = """
CREATE TABLE collection_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    skipped_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE reviews (
    platform TEXT NOT NULL,
    review_id TEXT NOT NULL,
    series_id TEXT NOT NULL,
    series_name_snapshot TEXT NOT NULL,
    source_url TEXT NOT NULL,
    original_review_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    first_collected_at TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL,
    PRIMARY KEY (platform, review_id)
);
CREATE TABLE review_analysis_job_reviews (
    job_id TEXT NOT NULL,
    review_id TEXT NOT NULL,
    series_id TEXT NOT NULL,
    series_name_snapshot TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    analysis_text TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(job_id, review_id)
);
"""


def legacy_connection(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(LEGACY_COLLECTION_SCHEMA)
    connection.execute(
        "INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "autohome",
            "review-1",
            "5769",
            "Model Y",
            "https://k.autohome.com.cn/5769/#review-1",
            '{"contents":[{"content":"空间充足"}]}',
            "a" * 64,
            "2026-10-01T00:00:00+00:00",
            "2026-10-01T00:00:00+00:00",
        ),
    )
    connection.execute(
        "INSERT INTO review_analysis_job_reviews VALUES (?,?,?,?,?,?,?)",
        ("job-1", "review-1", "5769", "Model Y", "a" * 64, "空间充足", 0),
    )
    connection.commit()
    return connection


def test_migration_backfills_legacy_reviews_without_changing_raw_content(tmp_path):
    connection = legacy_connection(tmp_path / "legacy.sqlite3")
    before = connection.execute(
        "SELECT original_review_json, content_hash FROM reviews"
    ).fetchone()

    ensure_review_asset_schema(connection)

    review = connection.execute(
        "SELECT asset_id, source_kind, original_review_json, content_hash FROM reviews"
    ).fetchone()
    metadata = connection.execute(
        "SELECT analysis_enabled, tags_json, note, revision FROM review_asset_metadata"
    ).fetchone()
    snapshot = connection.execute(
        "SELECT source_asset_id FROM review_analysis_job_reviews"
    ).fetchone()
    job_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(collection_jobs)")
    }

    assert dict(review) == {
        "asset_id": "autohome:review-1",
        "source_kind": "autohome",
        "original_review_json": before["original_review_json"],
        "content_hash": before["content_hash"],
    }
    assert dict(metadata) == {
        "analysis_enabled": 1,
        "tags_json": "[]",
        "note": "",
        "revision": 1,
    }
    assert snapshot["source_asset_id"] == "autohome:review-1"
    assert "deleted_review_skip_count" in job_columns
    connection.close()


def test_migration_is_idempotent(tmp_path):
    connection = legacy_connection(tmp_path / "repeat.sqlite3")

    ensure_review_asset_schema(connection)
    ensure_review_asset_schema(connection)

    assert connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
    assert (
        connection.execute("SELECT COUNT(*) FROM review_asset_metadata").fetchone()[0]
        == 1
    )
    indexes = {
        row[1] for row in connection.execute("PRAGMA index_list(reviews)").fetchall()
    }
    assert "ux_reviews_asset_id" in indexes
    connection.close()


def test_migration_rolls_back_as_one_transaction(tmp_path):
    connection = legacy_connection(tmp_path / "broken.sqlite3")
    connection.execute("CREATE TABLE review_asset_metadata (asset_id TEXT PRIMARY KEY)")
    connection.commit()

    with pytest.raises(sqlite3.OperationalError):
        ensure_review_asset_schema(connection)

    review_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(reviews)")
    }
    job_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(collection_jobs)")
    }
    analysis_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(review_analysis_job_reviews)")
    }
    assert "asset_id" not in review_columns
    assert "deleted_review_skip_count" not in job_columns
    assert "source_asset_id" not in analysis_columns
    connection.close()
