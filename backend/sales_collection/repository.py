"""SQLite persistence for sales collection jobs and source records."""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .domain import CreateSalesJobBody, SalesRecord, SalesStepStatus


def _normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("+", "plus")
    return "".join(character for character in normalized if character.isalnum())


class SalesCollectionRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sales_collection_jobs (
                    id TEXT PRIMARY KEY,
                    start_month TEXT NOT NULL,
                    end_month TEXT NOT NULL,
                    platforms_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_steps INTEGER NOT NULL,
                    completed_steps INTEGER NOT NULL DEFAULT 0,
                    failed_steps INTEGER NOT NULL DEFAULT 0,
                    record_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sales_collection_steps (
                    job_id TEXT NOT NULL REFERENCES sales_collection_jobs(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL,
                    month TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_count INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, platform, month)
                );
                CREATE TABLE IF NOT EXISTS sales_records (
                    platform TEXT NOT NULL,
                    month TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    series_name TEXT NOT NULL,
                    sales_volume INTEGER NOT NULL CHECK (sales_volume >= 0),
                    rank INTEGER NOT NULL CHECK (rank >= 1),
                    metric TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_snapshot_hash TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    job_id TEXT NOT NULL REFERENCES sales_collection_jobs(id),
                    PRIMARY KEY (platform, month, series_id)
                );
                CREATE TABLE IF NOT EXISTS sales_series_matches (
                    platform TEXT NOT NULL,
                    month TEXT NOT NULL,
                    platform_series_id TEXT NOT NULL,
                    review_series_id TEXT,
                    review_series_name TEXT,
                    match_method TEXT,
                    match_status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (platform, month, platform_series_id),
                    FOREIGN KEY (platform, month, platform_series_id)
                        REFERENCES sales_records(platform, month, series_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_sales_records_month
                    ON sales_records(month, platform, rank);
                CREATE INDEX IF NOT EXISTS ix_sales_matches_status
                    ON sales_series_matches(match_status, month, platform);
                """
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _job(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["platforms"] = json.loads(result.pop("platforms_json"))
        return result

    def create_job(
        self, job_id: str, body: CreateSalesJobBody, created_at: str
    ) -> dict[str, Any]:
        months = body.months()
        total_steps = len(months) * len(body.platforms)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM sales_collection_jobs WHERE status IN ('queued','running')"
            ).fetchone():
                raise RuntimeError("已有活动销量采集任务")
            connection.execute(
                """
                INSERT INTO sales_collection_jobs (
                    id,start_month,end_month,platforms_json,status,total_steps,
                    created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    body.start_month,
                    body.end_month,
                    json.dumps(body.platforms, ensure_ascii=False),
                    "queued",
                    total_steps,
                    created_at,
                    created_at,
                ),
            )
            for platform in body.platforms:
                for month in months:
                    connection.execute(
                        """
                        INSERT INTO sales_collection_steps (
                            job_id,platform,month,status,updated_at
                        ) VALUES (?,?,?,?,?)
                        """,
                        (job_id, platform, month, "queued", created_at),
                    )
            row = connection.execute(
                "SELECT * FROM sales_collection_jobs WHERE id=?", (job_id,)
            ).fetchone()
        result = self._job(row)
        assert result is not None
        return result

    def active_job(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            return self._job(
                connection.execute(
                    """
                    SELECT * FROM sales_collection_jobs
                    WHERE status IN ('queued','running')
                    ORDER BY created_at DESC LIMIT 1
                    """
                ).fetchone()
            )

    def overview(self) -> dict[str, Any]:
        with self.connect() as connection:
            record_count = connection.execute(
                "SELECT COUNT(*) FROM sales_records"
            ).fetchone()[0]
            matched_count = connection.execute(
                "SELECT COUNT(*) FROM sales_series_matches WHERE match_status='matched'"
            ).fetchone()[0]
            months = [
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT month FROM sales_records ORDER BY month"
                )
            ]
            latest = self._job(
                connection.execute(
                    """
                    SELECT * FROM sales_collection_jobs
                    ORDER BY created_at DESC,id DESC LIMIT 1
                    """
                ).fetchone()
            )
            active = self._job(
                connection.execute(
                    """
                    SELECT * FROM sales_collection_jobs
                    WHERE status IN ('queued','running')
                    ORDER BY created_at DESC LIMIT 1
                    """
                ).fetchone()
            )
        return {
            "record_count": record_count,
            "matched_count": matched_count,
            "unmatched_count": record_count - matched_count,
            "months": months,
            "active_job": active,
            "latest_job": latest,
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            job = self._job(
                connection.execute(
                    "SELECT * FROM sales_collection_jobs WHERE id=?", (job_id,)
                ).fetchone()
            )
            if job is None:
                return None
            job["steps"] = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM sales_collection_steps
                    WHERE job_id=? ORDER BY platform,month
                    """,
                    (job_id,),
                )
            ]
            return job

    def list_jobs(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        offset = (page - 1) * page_size
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM sales_collection_jobs"
            ).fetchone()[0]
            rows = [
                self._job(row)
                for row in connection.execute(
                    """
                    SELECT * FROM sales_collection_jobs
                    ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?
                    """,
                    (page_size, offset),
                )
            ]
        return {"rows": rows, "total": total, "page": page, "page_size": page_size}

    def get_step(self, job_id: str, platform: str, month: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM sales_collection_steps
                WHERE job_id=? AND platform=? AND month=?
                """,
                (job_id, platform, month),
            ).fetchone()
            return dict(row) if row is not None else None

    def pending_steps(self, job_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM sales_collection_steps
                    WHERE job_id=? AND status='queued'
                    ORDER BY platform,month
                    """,
                    (job_id,),
                )
            ]

    def mark_job_running(self, job_id: str, updated_at: str) -> None:
        with self.connect() as connection:
            changed = connection.execute(
                """
                UPDATE sales_collection_jobs
                SET status='running',started_at=COALESCE(started_at,?),updated_at=?
                WHERE id=? AND status='queued'
                """,
                (updated_at, updated_at, job_id),
            ).rowcount
            if changed != 1:
                raise RuntimeError("销量采集任务当前不能启动")

    def mark_step_running(
        self, job_id: str, platform: str, month: str, updated_at: str
    ) -> None:
        with self.connect() as connection:
            changed = connection.execute(
                """
                UPDATE sales_collection_steps
                SET status='running',started_at=?,error_code=NULL,error_message=NULL,
                    updated_at=?
                WHERE job_id=? AND platform=? AND month=? AND status='queued'
                """,
                (updated_at, updated_at, job_id, platform, month),
            ).rowcount
            if changed != 1:
                raise RuntimeError("销量采集步骤当前不能启动")

    def mark_step_failed(
        self,
        job_id: str,
        platform: str,
        month: str,
        error_code: str,
        error_message: str,
        updated_at: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                """
                UPDATE sales_collection_steps
                SET status='failed',record_count=0,error_code=?,error_message=?,
                    finished_at=?,updated_at=?
                WHERE job_id=? AND platform=? AND month=? AND status='running'
                """,
                (
                    error_code,
                    error_message[:1000],
                    updated_at,
                    updated_at,
                    job_id,
                    platform,
                    month,
                ),
            ).rowcount
            if changed != 1:
                raise RuntimeError("销量采集步骤当前不能标记失败")
            self._refresh_job_counts(connection, job_id, updated_at)

    def finish_job(self, job_id: str, updated_at: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            counts = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status IN ('queued','running') THEN 1 ELSE 0 END)
                FROM sales_collection_steps WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
            completed, failed, pending = (int(value or 0) for value in counts)
            if pending:
                raise RuntimeError("销量采集仍有未完成步骤")
            status = (
                "completed"
                if failed == 0
                else ("partial_failed" if completed else "failed")
            )
            last_error_row = connection.execute(
                """
                SELECT error_message FROM sales_collection_steps
                WHERE job_id=? AND status='failed'
                ORDER BY platform,month LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE sales_collection_jobs
                SET status=?,last_error=?,finished_at=?,updated_at=? WHERE id=?
                """,
                (
                    status,
                    last_error_row[0] if last_error_row else None,
                    updated_at,
                    updated_at,
                    job_id,
                ),
            )
        result = self.get_job(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    def fail_interrupted_jobs(self, updated_at: str) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            jobs = [
                str(row[0])
                for row in connection.execute(
                    "SELECT id FROM sales_collection_jobs WHERE status IN ('queued','running')"
                )
            ]
            for job_id in jobs:
                connection.execute(
                    """
                    UPDATE sales_collection_steps
                    SET status='failed',error_code='process_interrupted',
                        error_message='应用退出时任务尚未完成，请重新创建任务',
                        finished_at=?,updated_at=?
                    WHERE job_id=? AND status IN ('queued','running')
                    """,
                    (updated_at, updated_at, job_id),
                )
                self._refresh_job_counts(connection, job_id, updated_at)
                connection.execute(
                    """
                    UPDATE sales_collection_jobs
                    SET status='failed',last_error='应用退出时任务尚未完成，请重新创建任务',
                        finished_at=?,updated_at=? WHERE id=?
                    """,
                    (updated_at, updated_at, job_id),
                )

    def fail_job_start(self, job_id: str, message: str, updated_at: str) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE sales_collection_steps
                SET status='failed',error_code='schedule_failed',error_message=?,
                    finished_at=?,updated_at=?
                WHERE job_id=? AND status='queued'
                """,
                (message[:1000], updated_at, updated_at, job_id),
            )
            self._refresh_job_counts(connection, job_id, updated_at)
            connection.execute(
                """
                UPDATE sales_collection_jobs
                SET status='failed',last_error=?,finished_at=?,updated_at=?
                WHERE id=? AND status='queued'
                """,
                (message[:1000], updated_at, updated_at, job_id),
            )

    @staticmethod
    def _review_series(
        connection: sqlite3.Connection, month: str
    ) -> dict[str, list[tuple[str, str]]]:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reviews'"
        ).fetchone()
        if exists is None:
            return {}
        rows = connection.execute(
            """
            SELECT DISTINCT series_id,series_name_snapshot
            FROM reviews
            WHERE substr(COALESCE(
                json_extract(original_review_json, '$.posttime'),
                json_extract(original_review_json, '$.发表日期')
            ), 1, 7) = ?
            """,
            (month,),
        )
        by_name: dict[str, list[tuple[str, str]]] = {}
        for row in rows:
            key = _normalized_name(str(row["series_name_snapshot"]))
            item = (str(row["series_id"]), str(row["series_name_snapshot"]))
            if item not in by_name.setdefault(key, []):
                by_name[key].append(item)
        return by_name

    def save_month_records(
        self,
        job_id: str,
        platform: str,
        month: str,
        records: list[SalesRecord],
        snapshot_hash: str,
        collected_at: str,
    ) -> None:
        if not records:
            raise ValueError("销量月榜不能为空")
        if any(record.platform != platform or record.month != month for record in records):
            raise ValueError("销量记录平台或月份与任务步骤不一致")
        if len({record.series_id for record in records}) != len(records):
            raise ValueError("销量月榜包含重复车系")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT * FROM sales_collection_jobs WHERE id=?", (job_id,)
            ).fetchone()
            step = connection.execute(
                """
                SELECT 1 FROM sales_collection_steps
                WHERE job_id=? AND platform=? AND month=?
                """,
                (job_id, platform, month),
            ).fetchone()
            if job is None or step is None:
                raise KeyError((job_id, platform, month))
            matches = self._review_series(connection, month)
            connection.execute(
                "DELETE FROM sales_records WHERE platform=? AND month=?",
                (platform, month),
            )
            for record in records:
                connection.execute(
                    """
                    INSERT INTO sales_records (
                        platform,month,series_id,series_name,sales_volume,rank,
                        metric,source_url,source_snapshot_hash,collected_at,job_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.platform,
                        record.month,
                        record.series_id,
                        record.series_name,
                        record.sales_volume,
                        record.rank,
                        record.metric,
                        record.source_url,
                        snapshot_hash,
                        collected_at,
                        job_id,
                    ),
                )
                candidates = matches.get(_normalized_name(record.series_name), [])
                matched = len(candidates) == 1
                ambiguous = len(candidates) > 1
                review_id, review_name = candidates[0] if matched else (None, None)
                connection.execute(
                    """
                    INSERT INTO sales_series_matches (
                        platform,month,platform_series_id,review_series_id,
                        review_series_name,match_method,match_status,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        platform,
                        month,
                        record.series_id,
                        review_id,
                        review_name,
                        "normalized_exact" if matched else None,
                        "matched" if matched else ("ambiguous" if ambiguous else "unmatched"),
                        collected_at,
                    ),
                )
            connection.execute(
                """
                UPDATE sales_collection_steps
                SET status=?,record_count=?,error_code=NULL,error_message=NULL,
                    finished_at=?,updated_at=?
                WHERE job_id=? AND platform=? AND month=?
                """,
                (
                    SalesStepStatus.COMPLETED.value,
                    len(records),
                    collected_at,
                    collected_at,
                    job_id,
                    platform,
                    month,
                ),
            )
            self._refresh_job_counts(connection, job_id, collected_at)

    @staticmethod
    def _refresh_job_counts(
        connection: sqlite3.Connection, job_id: str, updated_at: str
    ) -> None:
        counts = connection.execute(
            """
            SELECT
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),
                SUM(record_count)
            FROM sales_collection_steps WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE sales_collection_jobs
            SET completed_steps=?,failed_steps=?,record_count=?,updated_at=?
            WHERE id=?
            """,
            (counts[0] or 0, counts[1] or 0, counts[2] or 0, updated_at, job_id),
        )

    def list_records(
        self,
        *,
        platform: str | None = None,
        month: str | None = None,
        search: str = "",
        match_status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        values: list[Any] = []
        if platform:
            clauses.append("record.platform=?")
            values.append(platform)
        if month:
            clauses.append("record.month=?")
            values.append(month)
        if search.strip():
            clauses.append(
                "(lower(record.series_name) LIKE ? OR record.series_id LIKE ? "
                "OR lower(COALESCE(match.review_series_name,'')) LIKE ? "
                "OR COALESCE(match.review_series_id,'') LIKE ?)"
            )
            pattern = f"%{search.strip().casefold()}%"
            values.extend((pattern, pattern, pattern, pattern))
        if match_status:
            clauses.append("match.match_status=?")
            values.append(match_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        base = """
            FROM sales_records AS record
            JOIN sales_series_matches AS match
              ON match.platform=record.platform AND match.month=record.month
             AND match.platform_series_id=record.series_id
        """
        offset = (page - 1) * page_size
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) " + base + where, values
            ).fetchone()[0]
            rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT record.*,match.review_series_id,match.review_series_name,
                           match.match_method,match.match_status
                    """
                    + base
                    + where
                    + " ORDER BY record.month DESC,record.platform,record.rank LIMIT ? OFFSET ?",
                    (*values, page_size, offset),
                )
            ]
        return {"rows": rows, "total": total, "page": page, "page_size": page_size}
