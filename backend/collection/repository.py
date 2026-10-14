"""SQLite persistence for collection jobs and immutable source payloads."""

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .asset_migrations import ensure_review_asset_schema
from .catalog_domain import CatalogRunConflict, CatalogSelectionError
from .domain import (
    CollectedReview,
    JobConfig,
    JobStatus,
    TaskControlError,
    VehicleSeries,
    canonical_review_hash,
)

AUTOHOME_CATALOG_URL = "https://www.autohome.com.cn/price/ev#pvareaid=3311257"
RUNNING_STATUSES = (
    JobStatus.QUEUED.value,
    JobStatus.DISCOVERING.value,
    JobStatus.COLLECTING.value,
)
CONTROLLABLE_STATUSES = (*RUNNING_STATUSES, JobStatus.PAUSED.value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class CollectionRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS collection_jobs (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    max_series INTEGER NOT NULL,
                    max_pages_per_series INTEGER,
                    request_delay_min_seconds REAL NOT NULL,
                    request_delay_max_seconds REAL NOT NULL,
                    series_delay_min_seconds REAL NOT NULL,
                    series_delay_max_seconds REAL NOT NULL,
                    status TEXT NOT NULL,
                    resume_status TEXT,
                    control_requested TEXT,
                    series_manifest TEXT NOT NULL DEFAULT '[]',
                    current_series_index INTEGER NOT NULL DEFAULT 0,
                    current_series_id TEXT,
                    current_series_name TEXT,
                    current_page INTEGER NOT NULL DEFAULT 1,
                    discovered_count INTEGER NOT NULL DEFAULT 0,
                    saved_count INTEGER NOT NULL DEFAULT 0,
                    duplicate_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    last_success_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS vehicle_series (
                    platform TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    series_name TEXT NOT NULL,
                    series_url TEXT NOT NULL,
                    review_url TEXT NOT NULL,
                    discovery_rank INTEGER NOT NULL,
                    first_discovered_at TEXT NOT NULL,
                    last_confirmed_at TEXT NOT NULL,
                    PRIMARY KEY (platform, series_id)
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    platform TEXT NOT NULL,
                    review_id TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    series_name_snapshot TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    original_review_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    first_collected_at TEXT NOT NULL,
                    last_confirmed_at TEXT NOT NULL,
                    PRIMARY KEY (platform, review_id),
                    FOREIGN KEY (platform, series_id)
                        REFERENCES vehicle_series(platform, series_id)
                );
                CREATE TABLE IF NOT EXISTS collection_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES collection_jobs(id),
                    series_id TEXT,
                    event_type TEXT NOT NULL,
                    error_class TEXT,
                    message TEXT NOT NULL,
                    details TEXT,
                    retryable INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collection_job_series (
                    job_id TEXT NOT NULL REFERENCES collection_jobs(id),
                    platform TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    series_name_snapshot TEXT NOT NULL,
                    series_url_snapshot TEXT NOT NULL,
                    review_url_snapshot TEXT NOT NULL,
                    catalog_batch_id TEXT NOT NULL,
                    catalog_rank INTEGER NOT NULL,
                    selection_order INTEGER NOT NULL,
                    PRIMARY KEY (job_id, platform, series_id),
                    UNIQUE (job_id, selection_order)
                );
                CREATE INDEX IF NOT EXISTS ix_reviews_series
                    ON reviews(platform, series_id, first_collected_at);
                CREATE INDEX IF NOT EXISTS ix_collection_events_job
                    ON collection_events(job_id, id);
                """
            )
            ensure_review_asset_schema(connection)

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
    def _job(row: sqlite3.Row | None):
        if row is None:
            return None
        result = dict(row)
        result["series_manifest"] = json.loads(result["series_manifest"])
        return result

    @staticmethod
    def _review(row: sqlite3.Row | None):
        if row is None:
            return None
        result = dict(row)
        result["series_name"] = result.pop("series_name_snapshot")
        result["original_review"] = json.loads(result.pop("original_review_json"))
        return result

    def create_job(self, job_id: str, config: JobConfig, created_at: str):
        values = config.model_dump(mode="json")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in CONTROLLABLE_STATUSES)
            if connection.execute(
                f"SELECT 1 FROM collection_jobs WHERE status IN ({placeholders}) LIMIT 1",
                CONTROLLABLE_STATUSES,
            ).fetchone():
                raise TaskControlError("已有活动采集任务")
            connection.execute(
                """
                INSERT INTO collection_jobs (
                    id, mode, source_url, max_series, max_pages_per_series,
                    request_delay_min_seconds, request_delay_max_seconds,
                    series_delay_min_seconds, series_delay_max_seconds,
                    status, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    values["mode"],
                    AUTOHOME_CATALOG_URL,
                    values["max_series"],
                    values["max_pages_per_series"],
                    values["request_delay_min_seconds"],
                    values["request_delay_max_seconds"],
                    values["series_delay_min_seconds"],
                    values["series_delay_max_seconds"],
                    JobStatus.QUEUED.value,
                    created_at,
                    created_at,
                ),
            )
            return self._job(
                connection.execute(
                    "SELECT * FROM collection_jobs WHERE id=?", (job_id,)
                ).fetchone()
            )

    def create_job_from_catalog(
        self,
        job_id: str,
        config: JobConfig,
        selected_series_ids: list[str],
        created_at: str,
    ) -> dict[str, Any]:
        if not selected_series_ids:
            raise CatalogSelectionError("请至少选择一个车系")
        if len(selected_series_ids) != len(set(selected_series_ids)):
            raise CatalogSelectionError("车系 ID 不能重复")
        if config.max_series != len(selected_series_ids):
            raise CatalogSelectionError("任务范围与所选车系数量不一致")

        values = config.model_dump(mode="json")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in CONTROLLABLE_STATUSES)
            if connection.execute(
                f"SELECT 1 FROM collection_jobs WHERE status IN ({placeholders}) LIMIT 1",
                CONTROLLABLE_STATUSES,
            ).fetchone():
                raise TaskControlError("已有活动采集任务")

            state = connection.execute(
                "SELECT active_batch_id FROM series_catalog_state WHERE singleton=1"
            ).fetchone()
            if state is None or state["active_batch_id"] is None:
                raise CatalogRunConflict("尚未建立可用车系目录")
            batch_id = str(state["active_batch_id"])
            id_placeholders = ",".join("?" for _ in selected_series_ids)
            rows = connection.execute(
                f"""
                SELECT platform,series_id,series_name,series_url,review_url,
                       discovery_rank
                FROM series_catalog_entries
                WHERE batch_id=? AND series_id IN ({id_placeholders})
                """,
                (batch_id, *selected_series_ids),
            ).fetchall()
            by_id = {str(row["series_id"]): row for row in rows}
            invalid = [
                series_id
                for series_id in selected_series_ids
                if series_id not in by_id
            ]
            if invalid:
                raise CatalogSelectionError(
                    "所选车系已不在当前目录中，请刷新后重试", invalid
                )

            connection.execute(
                """
                INSERT INTO collection_jobs (
                    id, mode, source_url, max_series, max_pages_per_series,
                    request_delay_min_seconds, request_delay_max_seconds,
                    series_delay_min_seconds, series_delay_max_seconds,
                    status, series_manifest, discovered_count, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    values["mode"],
                    AUTOHOME_CATALOG_URL,
                    values["max_series"],
                    values["max_pages_per_series"],
                    values["request_delay_min_seconds"],
                    values["request_delay_max_seconds"],
                    values["series_delay_min_seconds"],
                    values["series_delay_max_seconds"],
                    JobStatus.QUEUED.value,
                    "[]",
                    len(selected_series_ids),
                    created_at,
                    created_at,
                ),
            )
            for selection_order, series_id in enumerate(selected_series_ids):
                row = by_id[series_id]
                connection.execute(
                    """
                    INSERT INTO collection_job_series (
                        job_id,platform,series_id,series_name_snapshot,
                        series_url_snapshot,review_url_snapshot,catalog_batch_id,
                        catalog_rank,selection_order
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        job_id,
                        row["platform"],
                        row["series_id"],
                        row["series_name"],
                        row["series_url"],
                        row["review_url"],
                        batch_id,
                        row["discovery_rank"],
                        selection_order,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO vehicle_series (
                        platform,series_id,series_name,series_url,review_url,
                        discovery_rank,first_discovered_at,last_confirmed_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(platform,series_id) DO UPDATE SET
                        series_name=excluded.series_name,
                        series_url=excluded.series_url,
                        review_url=excluded.review_url,
                        discovery_rank=MIN(vehicle_series.discovery_rank,excluded.discovery_rank),
                        last_confirmed_at=excluded.last_confirmed_at
                    """,
                    (
                        row["platform"],
                        row["series_id"],
                        row["series_name"],
                        row["series_url"],
                        row["review_url"],
                        row["discovery_rank"],
                        created_at,
                        created_at,
                    ),
                )
            job = connection.execute(
                "SELECT * FROM collection_jobs WHERE id=?", (job_id,)
            ).fetchone()
        return self._job(job)

    def job_series(self, job_id: str) -> list[VehicleSeries]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT platform,series_id,series_name_snapshot,
                       series_url_snapshot,review_url_snapshot,catalog_rank
                FROM collection_job_series
                WHERE job_id=?
                ORDER BY selection_order
                """,
                (job_id,),
            ).fetchall()
            if rows:
                return [
                    VehicleSeries(
                        platform=row["platform"],
                        series_id=row["series_id"],
                        series_name=row["series_name_snapshot"],
                        series_url=row["series_url_snapshot"],
                        review_url=row["review_url_snapshot"],
                        discovery_rank=row["catalog_rank"],
                    )
                    for row in rows
                ]
            job = connection.execute(
                "SELECT series_manifest FROM collection_jobs WHERE id=?", (job_id,)
            ).fetchone()
        if job is None:
            raise KeyError(job_id)
        return [VehicleSeries.model_validate(item) for item in json.loads(job[0])]

    def get_job(self, job_id: str):
        with self.connect() as connection:
            return self._job(
                connection.execute(
                    "SELECT * FROM collection_jobs WHERE id=?", (job_id,)
                ).fetchone()
            )

    def list_jobs(self, page: int = 1, page_size: int = 20):
        offset = (page - 1) * page_size
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM collection_jobs").fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM collection_jobs ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
        return {
            "rows": [self._job(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def active_job(self):
        placeholders = ",".join("?" for _ in CONTROLLABLE_STATUSES)
        with self.connect() as connection:
            return self._job(
                connection.execute(
                    f"SELECT * FROM collection_jobs WHERE status IN ({placeholders}) "
                    "ORDER BY created_at LIMIT 1",
                    CONTROLLABLE_STATUSES,
                ).fetchone()
            )

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        updated_at: str,
        *,
        resume_status: JobStatus | None = None,
        last_error: str | None = None,
        finished: bool = False,
    ):
        started_at = updated_at if status in (JobStatus.DISCOVERING, JobStatus.COLLECTING) else None
        with self.connect() as connection:
            count = connection.execute(
                """
                UPDATE collection_jobs
                SET status=?, resume_status=?, last_error=?, updated_at=?,
                    started_at=COALESCE(started_at,?),
                    finished_at=CASE WHEN ? THEN ? ELSE finished_at END
                WHERE id=?
                """,
                (
                    status.value,
                    resume_status.value if resume_status else None,
                    last_error,
                    updated_at,
                    started_at,
                    int(finished),
                    updated_at,
                    job_id,
                ),
            ).rowcount
            if count != 1:
                raise KeyError(job_id)
        return self.get_job(job_id)

    def request_control(self, job_id: str, action: str, updated_at: str):
        if action not in {"pause", "stop"}:
            raise ValueError("不支持的控制动作")
        allowed_statuses = (
            RUNNING_STATUSES
            if action == "pause"
            else (JobStatus.DISCOVERING.value, JobStatus.COLLECTING.value)
        )
        placeholders = ",".join("?" for _ in allowed_statuses)
        with self.connect() as connection:
            count = connection.execute(
                f"UPDATE collection_jobs SET control_requested=?,updated_at=? "
                f"WHERE id=? AND status IN ({placeholders})",
                (action, updated_at, job_id, *allowed_statuses),
            ).rowcount
            if count != 1:
                exists = connection.execute(
                    "SELECT 1 FROM collection_jobs WHERE id=?", (job_id,)
                ).fetchone()
                if exists is None:
                    raise KeyError(job_id)
                raise TaskControlError("任务状态已变化，请刷新后重试")

    def finalize_job(
        self, job_id: str, status: JobStatus, updated_at: str
    ) -> bool:
        if status not in (JobStatus.COMPLETED, JobStatus.PARTIAL_FAILED):
            raise ValueError("只允许通过终结操作写入完成状态")
        with self.connect() as connection:
            count = connection.execute(
                """
                UPDATE collection_jobs
                SET status=?,resume_status=NULL,control_requested=NULL,
                    updated_at=?,finished_at=?
                WHERE id=? AND status=? AND control_requested IS NULL
                """,
                (
                    status.value,
                    updated_at,
                    updated_at,
                    job_id,
                    JobStatus.COLLECTING.value,
                ),
            ).rowcount
            if count == 1:
                return True
            exists = connection.execute(
                "SELECT 1 FROM collection_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(job_id)
            return False

    def clear_control(self, job_id: str, updated_at: str):
        with self.connect() as connection:
            connection.execute(
                "UPDATE collection_jobs SET control_requested=NULL,updated_at=? WHERE id=?",
                (updated_at, job_id),
            )

    def save_discovery(
        self, job_id: str, series: list[VehicleSeries], saved_at: str
    ) -> None:
        manifest = [item.model_dump(mode="json") for item in series]
        with self.connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM collection_jobs WHERE id=?", (job_id,)
            ).fetchone():
                raise KeyError(job_id)
            for item in series:
                connection.execute(
                    """
                    INSERT INTO vehicle_series (
                        platform,series_id,series_name,series_url,review_url,
                        discovery_rank,first_discovered_at,last_confirmed_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(platform,series_id) DO UPDATE SET
                        series_name=excluded.series_name,
                        series_url=excluded.series_url,
                        review_url=excluded.review_url,
                        discovery_rank=MIN(vehicle_series.discovery_rank,excluded.discovery_rank),
                        last_confirmed_at=excluded.last_confirmed_at
                    """,
                    (
                        item.platform,
                        item.series_id,
                        item.series_name,
                        item.series_url,
                        item.review_url,
                        item.discovery_rank,
                        saved_at,
                        saved_at,
                    ),
                )
            connection.execute(
                """
                UPDATE collection_jobs
                SET series_manifest=?,discovered_count=?,status=?,resume_status=NULL,
                    current_series_index=0,current_series_id=NULL,current_series_name=NULL,
                    current_page=1,updated_at=?
                WHERE id=?
                """,
                (_json(manifest), len(series), JobStatus.COLLECTING.value, saved_at, job_id),
            )

    def save_review_page(
        self,
        job_id: str,
        series: VehicleSeries,
        reviews: list[CollectedReview],
        next_page: int,
        saved_at: str,
    ) -> dict[str, int]:
        saved = duplicates = changed = deleted_skipped = 0
        with self.connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM collection_jobs WHERE id=?", (job_id,)
            ).fetchone():
                raise KeyError(job_id)
            for review in reviews:
                deletion = connection.execute(
                    """
                    SELECT recollection_allowed_at
                    FROM review_deletion_audits
                    WHERE platform=? AND review_id=?
                    ORDER BY deleted_at DESC, audit_id DESC
                    LIMIT 1
                    """,
                    (review.platform, review.review_id),
                ).fetchone()
                if deletion is not None and deletion["recollection_allowed_at"] is None:
                    deleted_skipped += 1
                    connection.execute(
                        """
                        INSERT INTO collection_events (
                            job_id, series_id, event_type, message, details, created_at
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (
                            job_id,
                            review.series_id,
                            "review_deleted_skip",
                            "评论已由用户删除，本次未重新写入",
                            _json(
                                {
                                    "asset_id": f"autohome:{review.review_id}",
                                    "review_id": review.review_id,
                                }
                            ),
                            saved_at,
                        ),
                    )
                    continue
                existing = connection.execute(
                    "SELECT content_hash,original_review_json FROM reviews "
                    "WHERE platform=? AND review_id=?",
                    (review.platform, review.review_id),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO reviews (
                            platform, review_id, series_id, series_name_snapshot,
                            source_url, original_review_json, content_hash,
                            first_collected_at, last_confirmed_at, asset_id, source_kind
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            review.platform,
                            review.review_id,
                            review.series_id,
                            review.series_name,
                            review.source_url,
                            _json(review.original_review),
                            review.content_hash,
                            saved_at,
                            saved_at,
                            f"autohome:{review.review_id}",
                            "autohome",
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO review_asset_metadata (
                            asset_id, analysis_enabled, tags_json, note, revision,
                            created_at, updated_at
                        ) VALUES (?,1,'[]','',1,?,?)
                        """,
                        (f"autohome:{review.review_id}", saved_at, saved_at),
                    )
                    saved += 1
                    continue
                duplicates += 1
                previous_hash = canonical_review_hash(
                    json.loads(existing["original_review_json"])
                )
                if previous_hash != review.content_hash:
                    changed += 1
                    connection.execute(
                        """
                        INSERT INTO collection_events (
                            job_id,series_id,event_type,message,details,created_at
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (
                            job_id,
                            series.series_id,
                            "review_changed",
                            "同一评论ID的原始内容发生变化",
                            _json(
                                {
                                    "review_id": review.review_id,
                                    "previous_hash": previous_hash,
                                    "current_hash": review.content_hash,
                                }
                            ),
                            saved_at,
                        ),
                    )
                connection.execute(
                    """
                    UPDATE reviews SET
                        series_id=?,series_name_snapshot=?,source_url=?,
                        original_review_json=?,content_hash=?,last_confirmed_at=?
                    WHERE platform=? AND review_id=?
                    """,
                    (
                        review.series_id,
                        review.series_name,
                        review.source_url,
                        _json(review.original_review),
                        review.content_hash,
                        saved_at,
                        review.platform,
                        review.review_id,
                    ),
                )
            connection.execute(
                """
                UPDATE collection_jobs SET
                    current_series_id=?,current_series_name=?,current_page=?,
                    saved_count=saved_count+?,duplicate_count=duplicate_count+?,
                    deleted_review_skip_count=deleted_review_skip_count+?,
                    last_success_at=?,updated_at=?
                WHERE id=?
                """,
                (
                    series.series_id,
                    series.series_name,
                    next_page,
                    saved,
                    duplicates,
                    deleted_skipped,
                    saved_at,
                    saved_at,
                    job_id,
                ),
            )
        return {
            "saved": saved,
            "duplicates": duplicates,
            "changed": changed,
            "deleted_skipped": deleted_skipped,
        }

    def advance_series(
        self,
        job_id: str,
        next_series_index: int,
        updated_at: str,
        *,
        failed: bool = False,
        skipped: bool = False,
        last_error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            count = connection.execute(
                """
                UPDATE collection_jobs SET
                    current_series_index=?,current_series_id=NULL,
                    current_series_name=NULL,current_page=1,
                    failed_count=failed_count+?,skipped_count=skipped_count+?,
                    last_error=COALESCE(?,last_error),updated_at=?
                WHERE id=?
                """,
                (
                    next_series_index,
                    int(failed),
                    int(skipped),
                    last_error,
                    updated_at,
                    job_id,
                ),
            ).rowcount
            if count != 1:
                raise KeyError(job_id)

    def record_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        created_at: str,
        *,
        series_id: str | None = None,
        error_class: str | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO collection_events (
                    job_id,series_id,event_type,error_class,message,details,retryable,created_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    series_id,
                    event_type,
                    error_class,
                    message,
                    _json(details) if details is not None else None,
                    int(retryable),
                    created_at,
                ),
            )

    def list_events(self, job_id: str, limit: int = 100):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ("
                "SELECT * FROM collection_events WHERE job_id=? ORDER BY id DESC LIMIT ?"
                ") ORDER BY id",
                (job_id, limit),
            ).fetchall()
        events = [dict(row) for row in rows]
        for event in events:
            event["retryable"] = bool(event["retryable"])
        return events

    def list_series(
        self, *, search: str = "", page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        pattern = f"%{search.casefold()}%"
        where = "WHERE lower(s.series_name) LIKE ? OR s.series_id LIKE ?"
        params = (pattern, pattern)
        offset = (page - 1) * page_size
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM vehicle_series s {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT s.*,COUNT(r.review_id) AS comment_count
                FROM vehicle_series s
                LEFT JOIN reviews r
                    ON r.platform=s.platform AND r.series_id=s.series_id
                {where}
                GROUP BY s.platform,s.series_id
                ORDER BY s.discovery_rank,s.series_id
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        return {
            "rows": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_series(self, series_id: str):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM vehicle_series WHERE platform='autohome' AND series_id=?",
                (series_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_reviews(
        self,
        *,
        series_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        where = "WHERE series_id=?" if series_id else ""
        params: tuple[Any, ...] = (series_id,) if series_id else ()
        offset = (page - 1) * page_size
        summary_columns = (
            "platform,review_id,series_id,series_name_snapshot AS series_name,"
            "source_url,content_hash,first_collected_at,last_confirmed_at"
        )
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM reviews {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT {summary_columns} FROM reviews {where} "
                "ORDER BY first_collected_at,review_id LIMIT ? OFFSET ?",
                (*params, page_size, offset),
            ).fetchall()
        return {
            "rows": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_review(self, review_id: str):
        with self.connect() as connection:
            return self._review(
                connection.execute(
                    "SELECT * FROM reviews WHERE platform='autohome' AND review_id=?",
                    (review_id,),
                ).fetchone()
            )

    def iter_reviews_for_export(self, series_id: str) -> Iterable[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM reviews
                WHERE platform='autohome' AND series_id=?
                ORDER BY first_collected_at,review_id
                """,
                (series_id,),
            ).fetchall()
            payloads = [self._review(row) for row in rows]
        yield from payloads

    def overview(self):
        with self.connect() as connection:
            series_count = connection.execute(
                "SELECT COUNT(*) FROM vehicle_series"
            ).fetchone()[0]
            review_count = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            pending_errors = connection.execute(
                "SELECT COUNT(*) FROM collection_events WHERE error_class IS NOT NULL"
            ).fetchone()[0]
        return {
            "series_count": series_count,
            "review_count": review_count,
            "pending_errors": pending_errors,
            "active_job": self.active_job(),
        }

    def pause_interrupted_jobs(self, paused_at: str) -> int:
        placeholders = ",".join("?" for _ in RUNNING_STATUSES)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT id,status FROM collection_jobs WHERE status IN ({placeholders})",
                RUNNING_STATUSES,
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE collection_jobs
                    SET status=?,resume_status=?,control_requested=NULL,
                        last_error=?,updated_at=?
                    WHERE id=?
                    """,
                    (
                        JobStatus.PAUSED.value,
                        row["status"],
                        "应用上次运行期间中断，请检查后继续",
                        paused_at,
                        row["id"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO collection_events (
                        job_id,event_type,message,created_at
                    ) VALUES (?,?,?,?)
                    """,
                    (row["id"], "interrupted", "应用重启，任务已转为暂停", paused_at),
                )
        return len(rows)
