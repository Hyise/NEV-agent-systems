"""SQLite persistence for staged and published vehicle-series catalogs."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .catalog_domain import CatalogRunConflict, CatalogRunStatus
from .domain import VehicleSeries
from .repository import AUTOHOME_CATALOG_URL


class SeriesCatalogRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS series_catalog_runs (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    target_unique_series INTEGER NOT NULL,
                    scanned_count INTEGER NOT NULL DEFAULT 0,
                    unique_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    current_page INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    source_exhausted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS series_catalog_entries (
                    batch_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    series_id TEXT NOT NULL,
                    series_name TEXT NOT NULL,
                    series_url TEXT NOT NULL,
                    review_url TEXT NOT NULL,
                    discovery_rank INTEGER NOT NULL,
                    discovered_at TEXT NOT NULL,
                    PRIMARY KEY (batch_id, platform, series_id),
                    FOREIGN KEY (batch_id) REFERENCES series_catalog_runs(batch_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_series_catalog_entries_rank
                    ON series_catalog_entries(batch_id, discovery_rank, series_id);
                CREATE TABLE IF NOT EXISTS series_catalog_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    active_batch_id TEXT,
                    series_count INTEGER NOT NULL DEFAULT 0,
                    published_at TEXT,
                    source_url TEXT NOT NULL,
                    source_exhausted INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO series_catalog_state (
                    singleton,active_batch_id,series_count,published_at,
                    source_url,source_exhausted
                ) VALUES (1,NULL,0,NULL,'https://www.autohome.com.cn/price/ev#pvareaid=3311257',0);
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
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        if "source_exhausted" in result:
            result["source_exhausted"] = bool(result["source_exhausted"])
        return result

    def create_run(
        self,
        run_id: str,
        batch_id: str,
        created_at: str,
        target_unique_series: int = 1000,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            active = connection.execute(
                """
                SELECT 1 FROM series_catalog_runs
                WHERE status IN ('queued','discovering','publishing','cancelling')
                """
            ).fetchone()
            if active is not None:
                raise CatalogRunConflict("已有车系发现任务正在运行")
            connection.execute(
                """
                INSERT INTO series_catalog_runs (
                    id,batch_id,status,target_unique_series,created_at,updated_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    run_id,
                    batch_id,
                    CatalogRunStatus.QUEUED.value,
                    target_unique_series,
                    created_at,
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._row(row)  # type: ignore[return-value]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._row(row)

    def active_run(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM series_catalog_runs
                WHERE status IN ('queued','discovering','publishing','cancelling')
                ORDER BY created_at,id LIMIT 1
                """
            ).fetchone()
        return self._row(row)

    def request_cancel(self, run_id: str, updated_at: str) -> dict[str, Any]:
        with self.connect() as connection:
            count = connection.execute(
                """
                UPDATE series_catalog_runs SET status=?,updated_at=?
                WHERE id=? AND status IN ('queued','discovering')
                """,
                (CatalogRunStatus.CANCELLING.value, updated_at, run_id),
            ).rowcount
            if count != 1:
                exists = connection.execute(
                    "SELECT 1 FROM series_catalog_runs WHERE id=?", (run_id,)
                ).fetchone()
                if exists is None:
                    raise KeyError(run_id)
                raise CatalogRunConflict("当前发现任务不能取消")
            row = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._row(row)  # type: ignore[return-value]

    def is_cancel_requested(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run["status"] == CatalogRunStatus.CANCELLING.value

    def append_entries(
        self,
        run_id: str,
        entries: list[VehicleSeries],
        *,
        scanned_count: int,
        skipped_count: int,
        current_page: int,
        updated_at: str,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            run = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            if run["status"] not in {
                CatalogRunStatus.QUEUED.value,
                CatalogRunStatus.DISCOVERING.value,
            }:
                raise CatalogRunConflict("当前发现任务不能写入目录")
            for entry in entries:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO series_catalog_entries (
                        batch_id,platform,series_id,series_name,series_url,
                        review_url,discovery_rank,discovered_at
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        run["batch_id"],
                        entry.platform,
                        entry.series_id,
                        entry.series_name,
                        entry.series_url,
                        entry.review_url,
                        entry.discovery_rank,
                        updated_at,
                    ),
                )
            unique_count = connection.execute(
                "SELECT COUNT(*) FROM series_catalog_entries WHERE batch_id=?",
                (run["batch_id"],),
            ).fetchone()[0]
            connection.execute(
                """
                UPDATE series_catalog_runs
                SET status=?,scanned_count=?,unique_count=?,skipped_count=?,
                    current_page=?,started_at=COALESCE(started_at,?),updated_at=?
                WHERE id=?
                """,
                (
                    CatalogRunStatus.DISCOVERING.value,
                    scanned_count,
                    unique_count,
                    skipped_count,
                    current_page,
                    updated_at,
                    updated_at,
                    run_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._row(row)  # type: ignore[return-value]

    @staticmethod
    def _search(query: str) -> tuple[str, str]:
        pattern = f"%{query.casefold()}%"
        return pattern, pattern

    def list_catalog(
        self, query: str = "", page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        params = self._search(query)
        where = "lower(e.series_name) LIKE ? OR e.series_id LIKE ?"
        with self.connect() as connection:
            connection.execute("BEGIN")
            state = connection.execute(
                "SELECT * FROM series_catalog_state WHERE singleton=1"
            ).fetchone()
            if state is None or state["active_batch_id"] is None:
                return {"rows": [], "total": 0, "page": page, "page_size": page_size}
            batch_id = state["active_batch_id"]
            total = connection.execute(
                f"SELECT COUNT(*) FROM series_catalog_entries e "
                f"WHERE e.batch_id=? AND ({where})",
                (batch_id, *params),
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT e.*,? AS published_at
                FROM series_catalog_entries e
                WHERE e.batch_id=? AND ({where})
                ORDER BY e.discovery_rank,e.series_id
                LIMIT ? OFFSET ?
                """,
                (state["published_at"], batch_id, *params, page_size, offset),
            ).fetchall()
        return {
            "rows": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def selection_result(self, query: str = "") -> dict[str, Any]:
        params = self._search(query)
        where = "lower(e.series_name) LIKE ? OR e.series_id LIKE ?"
        with self.connect() as connection:
            connection.execute("BEGIN")
            state = connection.execute(
                "SELECT active_batch_id FROM series_catalog_state WHERE singleton=1"
            ).fetchone()
            if state is None or state["active_batch_id"] is None:
                return {"batch_id": None, "series_ids": [], "total": 0}
            batch_id = str(state["active_batch_id"])
            rows = connection.execute(
                f"""
                SELECT e.series_id FROM series_catalog_entries e
                WHERE e.batch_id=? AND ({where})
                ORDER BY e.discovery_rank,e.series_id
                """,
                (batch_id, *params),
            ).fetchall()
        series_ids = [str(row["series_id"]) for row in rows]
        return {
            "batch_id": batch_id,
            "series_ids": series_ids,
            "total": len(series_ids),
        }

    def selection_ids(self, query: str = "") -> list[str]:
        return self.selection_result(query)["series_ids"]

    def publish_run(
        self, run_id: str, published_at: str, source_exhausted: bool
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            if run["status"] not in {
                CatalogRunStatus.QUEUED.value,
                CatalogRunStatus.DISCOVERING.value,
            }:
                raise CatalogRunConflict("当前发现任务不能发布目录")
            unique_count = connection.execute(
                "SELECT COUNT(*) FROM series_catalog_entries WHERE batch_id=?",
                (run["batch_id"],),
            ).fetchone()[0]
            if unique_count < run["target_unique_series"] and not source_exhausted:
                raise CatalogRunConflict("目录未达到目标数量且数据源尚未耗尽")
            terminal = (
                CatalogRunStatus.COMPLETED
                if unique_count >= run["target_unique_series"]
                else CatalogRunStatus.COMPLETED_SHORT
            )
            connection.execute(
                "UPDATE series_catalog_runs SET status=?,updated_at=? WHERE id=?",
                (CatalogRunStatus.PUBLISHING.value, published_at, run_id),
            )
            connection.execute(
                """
                UPDATE series_catalog_state
                SET active_batch_id=?,series_count=?,published_at=?,
                    source_url=?,source_exhausted=?
                WHERE singleton=1
                """,
                (
                    run["batch_id"],
                    unique_count,
                    published_at,
                    AUTOHOME_CATALOG_URL,
                    int(source_exhausted),
                ),
            )
            connection.execute(
                """
                UPDATE series_catalog_runs
                SET status=?,unique_count=?,source_exhausted=?,finished_at=?,updated_at=?
                WHERE id=?
                """,
                (
                    terminal.value,
                    unique_count,
                    int(source_exhausted),
                    published_at,
                    published_at,
                    run_id,
                ),
            )
            successful = connection.execute(
                """
                SELECT batch_id FROM series_catalog_runs
                WHERE status IN ('completed','completed_short')
                ORDER BY finished_at DESC,id DESC
                """
            ).fetchall()
            for old in successful[3:]:
                referenced = connection.execute(
                    "SELECT 1 FROM collection_job_series WHERE catalog_batch_id=? LIMIT 1",
                    (old["batch_id"],),
                ).fetchone()
                if referenced is None:
                    connection.execute(
                        "DELETE FROM series_catalog_entries WHERE batch_id=?",
                        (old["batch_id"],),
                    )
            row = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._row(row)  # type: ignore[return-value]

    def fail_run(
        self,
        run_id: str,
        error_code: str,
        error_message: str,
        finished_at: str,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            if run["status"] in {
                CatalogRunStatus.COMPLETED.value,
                CatalogRunStatus.COMPLETED_SHORT.value,
                CatalogRunStatus.CANCELLED.value,
                CatalogRunStatus.FAILED.value,
            }:
                raise CatalogRunConflict("发现任务已经结束")
            connection.execute(
                "DELETE FROM series_catalog_entries WHERE batch_id=?",
                (run["batch_id"],),
            )
            connection.execute(
                """
                UPDATE series_catalog_runs
                SET status=?,error_code=?,error_message=?,finished_at=?,updated_at=?
                WHERE id=?
                """,
                (
                    CatalogRunStatus.FAILED.value,
                    error_code,
                    error_message,
                    finished_at,
                    finished_at,
                    run_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._row(row)  # type: ignore[return-value]

    def cancel_run(self, run_id: str, finished_at: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            if run["status"] not in {
                CatalogRunStatus.QUEUED.value,
                CatalogRunStatus.DISCOVERING.value,
                CatalogRunStatus.CANCELLING.value,
            }:
                raise CatalogRunConflict("当前发现任务不能取消")
            connection.execute(
                "DELETE FROM series_catalog_entries WHERE batch_id=?",
                (run["batch_id"],),
            )
            connection.execute(
                """
                UPDATE series_catalog_runs
                SET status=?,finished_at=?,updated_at=? WHERE id=?
                """,
                (
                    CatalogRunStatus.CANCELLED.value,
                    finished_at,
                    finished_at,
                    run_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM series_catalog_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._row(row)  # type: ignore[return-value]

    def catalog_status(self) -> dict[str, Any]:
        with self.connect() as connection:
            state = connection.execute(
                "SELECT * FROM series_catalog_state WHERE singleton=1"
            ).fetchone()
        result = self._row(state) or {
            "active_batch_id": None,
            "series_count": 0,
            "published_at": None,
            "source_url": AUTOHOME_CATALOG_URL,
            "source_exhausted": False,
        }
        result.pop("singleton", None)
        result["active_run"] = self.active_run()
        return result

    def fail_interrupted_runs(self, failed_at: str) -> int:
        active_statuses = (
            CatalogRunStatus.QUEUED.value,
            CatalogRunStatus.DISCOVERING.value,
            CatalogRunStatus.PUBLISHING.value,
            CatalogRunStatus.CANCELLING.value,
        )
        placeholders = ",".join("?" for _ in active_statuses)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"SELECT id,batch_id FROM series_catalog_runs "
                f"WHERE status IN ({placeholders})",
                active_statuses,
            ).fetchall()
            for row in rows:
                connection.execute(
                    "DELETE FROM series_catalog_entries WHERE batch_id=?",
                    (row["batch_id"],),
                )
                connection.execute(
                    """
                    UPDATE series_catalog_runs
                    SET status=?,error_code=?,error_message=?,finished_at=?,updated_at=?
                    WHERE id=?
                    """,
                    (
                        CatalogRunStatus.FAILED.value,
                        "interrupted",
                        "应用上次运行期间中断，请重新发现车系",
                        failed_at,
                        failed_at,
                        row["id"],
                    ),
                )
        return len(rows)
