"""SQLite repository for review asset queries and mutable management metadata."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.review_analysis.text import extract_analysis_text

from .asset_domain import (
    AssetConflict,
    AssetGone,
    AssetNotFound,
    BatchMetadataPatchBody,
    MetadataPatchBody,
)
from .asset_migrations import ensure_review_asset_schema


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


class ReviewAssetRepository:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as connection:
            ensure_review_asset_schema(connection)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _metadata(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "asset_id": row["asset_id"],
            "analysis_enabled": bool(row["analysis_enabled"]),
            "tags": json.loads(row["tags_json"]),
            "note": row["note"],
            "revision": row["revision"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _summary_row(row: sqlite3.Row) -> dict[str, Any]:
        original = json.loads(row["original_review_json"])
        try:
            analysis_text = extract_analysis_text(original)
        except ValueError:
            analysis_text = ""
        return {
            "asset_id": row["asset_id"],
            "review_id": row["review_id"],
            "series_id": row["series_id"],
            "series_name": row["series_name_snapshot"],
            "source_kind": row["source_kind"],
            "platform": row["platform"],
            "source_url": row["source_url"] or None,
            "content_hash": row["content_hash"],
            "excerpt": analysis_text[:180],
            "first_collected_at": row["first_collected_at"],
            "last_confirmed_at": row["last_confirmed_at"],
            "analysis_enabled": bool(row["analysis_enabled"]),
            "tags": json.loads(row["tags_json"]),
            "note": row["note"],
            "revision": row["revision"],
            "metadata_updated_at": row["updated_at"],
        }

    def _latest_deletion(
        self, connection: sqlite3.Connection, asset_id: str
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT asset_id, source_kind, platform, review_id, series_id,
                   series_name_snapshot, content_hash, reason, deleted_at,
                   recollection_allowed_at
            FROM review_deletion_audits
            WHERE asset_id=?
            ORDER BY deleted_at DESC, audit_id DESC LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _raise_missing(self, connection: sqlite3.Connection, asset_id: str) -> None:
        deletion = self._latest_deletion(connection, asset_id)
        if deletion is not None:
            raise AssetGone(deletion)
        raise AssetNotFound(asset_id)

    def list_assets(
        self,
        *,
        keyword: str = "",
        series_id: str | None = None,
        source_kind: str | None = None,
        tag: str | None = None,
        analysis_enabled: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("分页参数无效")
        clauses: list[str] = []
        params: list[Any] = []
        if keyword.strip():
            pattern = f"%{keyword.strip().casefold()}%"
            clauses.append(
                "(lower(r.review_id) LIKE ? OR lower(r.series_name_snapshot) LIKE ? "
                "OR lower(r.original_review_json) LIKE ?)"
            )
            params.extend([pattern, pattern, pattern])
        if series_id:
            clauses.append("r.series_id=?")
            params.append(series_id)
        if source_kind:
            clauses.append("r.source_kind=?")
            params.append(source_kind)
        if tag:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(m.tags_json) WHERE value=?)"
            )
            params.append(tag)
        if analysis_enabled is not None:
            clauses.append("m.analysis_enabled=?")
            params.append(int(analysis_enabled))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        base = (
            "FROM reviews r JOIN review_asset_metadata m ON m.asset_id=r.asset_id "
            + where
        )
        offset = (page - 1) * page_size
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) {base}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT r.*, m.analysis_enabled, m.tags_json, m.note,
                       m.revision, m.updated_at
                {base}
                ORDER BY r.first_collected_at DESC, r.asset_id
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        return {
            "rows": [self._summary_row(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, m.analysis_enabled, m.tags_json, m.note,
                       m.revision, m.updated_at
                FROM reviews r JOIN review_asset_metadata m ON m.asset_id=r.asset_id
                WHERE r.asset_id=?
                """,
                (asset_id,),
            ).fetchone()
            if row is None:
                self._raise_missing(connection, asset_id)
            reference_count = 0
            if _table_exists(connection, "review_analysis_job_reviews"):
                reference_count = connection.execute(
                    "SELECT COUNT(*) FROM review_analysis_job_reviews "
                    "WHERE source_asset_id=?",
                    (asset_id,),
                ).fetchone()[0]
        result = self._summary_row(row)
        result["original_review"] = json.loads(row["original_review_json"])
        result["reference_count"] = reference_count
        return result

    def update_metadata(
        self, asset_id: str, command: MetadataPatchBody
    ) -> dict[str, Any]:
        timestamp = _now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM reviews WHERE asset_id=?", (asset_id,)
            ).fetchone() is None:
                self._raise_missing(connection, asset_id)
            changed = connection.execute(
                """
                UPDATE review_asset_metadata
                SET analysis_enabled=?, tags_json=?, note=?,
                    revision=revision+1, updated_at=?
                WHERE asset_id=? AND revision=?
                """,
                (
                    int(command.analysis_enabled),
                    json.dumps(command.tags, ensure_ascii=False, separators=(",", ":")),
                    command.note,
                    timestamp,
                    asset_id,
                    command.revision,
                ),
            ).rowcount
            if changed != 1:
                raise AssetConflict("资产管理信息已被其他操作更新，请刷新后重试")
            row = connection.execute(
                "SELECT * FROM review_asset_metadata WHERE asset_id=?", (asset_id,)
            ).fetchone()
        return self._metadata(row)

    def batch_update_metadata(
        self, command: BatchMetadataPatchBody
    ) -> dict[str, int]:
        timestamp = _now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"SELECT * FROM review_asset_metadata WHERE asset_id IN "
                f"({','.join('?' for _ in command.asset_ids)})",
                command.asset_ids,
            ).fetchall()
            by_id = {row["asset_id"]: row for row in rows}
            missing = [asset_id for asset_id in command.asset_ids if asset_id not in by_id]
            if missing:
                self._raise_missing(connection, missing[0])
            for asset_id in command.asset_ids:
                row = by_id[asset_id]
                tags = [
                    value
                    for value in json.loads(row["tags_json"])
                    if value not in command.remove_tags
                ]
                for value in command.add_tags:
                    if value not in tags:
                        tags.append(value)
                if len(tags) > 20:
                    raise AssetConflict("批量操作后标签数量不能超过20个")
                enabled = (
                    int(command.analysis_enabled)
                    if command.analysis_enabled is not None
                    else row["analysis_enabled"]
                )
                connection.execute(
                    """
                    UPDATE review_asset_metadata
                    SET analysis_enabled=?, tags_json=?, revision=revision+1,
                        updated_at=? WHERE asset_id=?
                    """,
                    (
                        enabled,
                        json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                        timestamp,
                        asset_id,
                    ),
                )
        return {"updated_count": len(command.asset_ids)}

    def summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            counts = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN m.analysis_enabled=1 THEN 1 ELSE 0 END) AS enabled,
                       SUM(CASE WHEN m.analysis_enabled=0 THEN 1 ELSE 0 END) AS disabled
                FROM reviews r JOIN review_asset_metadata m ON m.asset_id=r.asset_id
                """
            ).fetchone()
            sources = connection.execute(
                """
                SELECT r.source_kind, COUNT(*) AS count
                FROM reviews r GROUP BY r.source_kind ORDER BY r.source_kind
                """
            ).fetchall()
            series = connection.execute(
                """
                SELECT r.series_id, MAX(r.series_name_snapshot) AS series_name,
                       COUNT(*) AS count,
                       SUM(CASE WHEN m.analysis_enabled=1 THEN 1 ELSE 0 END)
                           AS analysis_enabled
                FROM reviews r JOIN review_asset_metadata m ON m.asset_id=r.asset_id
                GROUP BY r.series_id ORDER BY count DESC, r.series_id
                """
            ).fetchall()
        return {
            "total": counts["total"],
            "analysis_enabled": counts["enabled"] or 0,
            "analysis_disabled": counts["disabled"] or 0,
            "by_source": [dict(row) for row in sources],
            "by_series": [dict(row) for row in series],
        }
