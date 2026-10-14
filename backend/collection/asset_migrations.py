"""Idempotent SQLite migrations for review assets and analysis references."""

from __future__ import annotations

import sqlite3


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_column(
    connection: sqlite3.Connection, table: str, column: str, declaration: str
) -> None:
    if (
        table in {"reviews", "collection_jobs", "review_analysis_job_reviews"}
        and _table_exists(connection, table)
        and column not in _columns(connection, table)
    ):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _rebuild_analysis_snapshots_with_stable_identity(
    connection: sqlite3.Connection,
) -> None:
    table = "review_analysis_job_reviews"
    columns = _columns(connection, table)
    if not columns or "snapshot_id" in columns:
        return

    connection.execute("DROP INDEX IF EXISTS ix_review_analysis_job_reviews_pending")
    connection.execute(
        f"ALTER TABLE {table} RENAME TO review_analysis_job_reviews_legacy"
    )
    connection.execute(
        """
        CREATE TABLE review_analysis_job_reviews (
            job_id TEXT NOT NULL
                REFERENCES review_analysis_jobs(id) ON DELETE CASCADE,
            snapshot_id TEXT NOT NULL,
            source_asset_id TEXT,
            review_id TEXT NOT NULL,
            series_id TEXT NOT NULL,
            series_name_snapshot TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            analysis_text TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            annotation_id TEXT,
            error_code TEXT,
            error_message TEXT,
            PRIMARY KEY(job_id, snapshot_id),
            UNIQUE(job_id, ordinal)
        )
        """
    )

    def existing(name: str, fallback: str) -> str:
        return name if name in columns else fallback

    connection.execute(
        f"""
        INSERT INTO review_analysis_job_reviews (
            job_id, snapshot_id, source_asset_id, review_id, series_id,
            series_name_snapshot, content_hash, analysis_text, ordinal,
            status, attempt_count, annotation_id, error_code, error_message
        )
        SELECT job_id, review_id, source_asset_id, review_id, series_id,
               series_name_snapshot, content_hash, analysis_text, ordinal,
               {existing('status', "'pending'")},
               {existing('attempt_count', '0')},
               {existing('annotation_id', 'NULL')},
               {existing('error_code', 'NULL')},
               {existing('error_message', 'NULL')}
        FROM review_analysis_job_reviews_legacy
        """
    )
    connection.execute("DROP TABLE review_analysis_job_reviews_legacy")
    connection.execute(
        """CREATE INDEX ix_review_analysis_job_reviews_pending
           ON review_analysis_job_reviews(job_id, status, ordinal)"""
    )


def ensure_review_asset_schema(connection: sqlite3.Connection) -> None:
    """Migrate review asset storage atomically without rewriting source payloads."""

    if connection.in_transaction:
        connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    try:
        _add_column(connection, "reviews", "asset_id", "TEXT")
        _add_column(connection, "reviews", "source_kind", "TEXT")
        _add_column(
            connection,
            "collection_jobs",
            "deleted_review_skip_count",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _add_column(
            connection,
            "review_analysis_job_reviews",
            "source_asset_id",
            "TEXT",
        )
        _rebuild_analysis_snapshots_with_stable_identity(connection)

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS review_asset_metadata (
                asset_id TEXT PRIMARY KEY,
                analysis_enabled INTEGER NOT NULL DEFAULT 1
                    CHECK (analysis_enabled IN (0, 1)),
                tags_json TEXT NOT NULL DEFAULT '[]',
                note TEXT NOT NULL DEFAULT '',
                revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS review_deletion_audits (
                audit_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                platform TEXT NOT NULL,
                review_id TEXT NOT NULL,
                series_id TEXT NOT NULL,
                series_name_snapshot TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                reason TEXT NOT NULL,
                deleted_at TEXT NOT NULL,
                recollection_allowed_at TEXT
            )
            """
        )

        if _table_exists(connection, "reviews"):
            connection.execute(
                """
                UPDATE reviews
                SET asset_id = CASE
                        WHEN platform='autohome' THEN 'autohome:' || review_id
                        ELSE platform || ':' || review_id
                    END,
                    source_kind = CASE
                        WHEN platform='manual' THEN 'manual_import'
                        ELSE platform
                    END
                WHERE asset_id IS NULL OR source_kind IS NULL
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_reviews_asset_id ON reviews(asset_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_reviews_series_asset "
                "ON reviews(series_id, first_collected_at)"
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO review_asset_metadata (
                    asset_id, analysis_enabled, tags_json, note, revision,
                    created_at, updated_at
                )
                SELECT asset_id, 1, '[]', '', 1,
                       first_collected_at, last_confirmed_at
                FROM reviews
                WHERE asset_id IS NOT NULL
                """
            )

        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_review_deletions_asset "
            "ON review_deletion_audits(asset_id, deleted_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_review_deletions_source "
            "ON review_deletion_audits(platform, review_id, deleted_at DESC)"
        )

        if (
            _table_exists(connection, "review_analysis_job_reviews")
            and _table_exists(connection, "reviews")
        ):
            connection.execute(
                """
                UPDATE review_analysis_job_reviews AS snapshot
                SET source_asset_id = (
                    SELECT review.asset_id
                    FROM reviews AS review
                    WHERE review.review_id = snapshot.review_id
                      AND review.series_id = snapshot.series_id
                      AND review.content_hash = snapshot.content_hash
                    ORDER BY CASE WHEN review.platform='autohome' THEN 0 ELSE 1 END,
                             review.asset_id
                    LIMIT 1
                )
                WHERE source_asset_id IS NULL
                """
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
