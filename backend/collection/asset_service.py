"""Validation and orchestration for two-step manual review import."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from backend.review_analysis.text import extract_analysis_text

from .asset_domain import (
    AssetConflict,
    DeleteAssetBody,
    ImportReviewItem,
    ImportValidationError,
)
from .asset_repository import ReviewAssetRepository
from .import_file import ReviewImportFileError, parse_review_import_file
from .domain import canonical_review_hash

MAX_IMPORT_FILE_BYTES = 32 * 1024 * 1024
MAX_IMPORT_BYTES = 128 * 1024 * 1024
MAX_IMPORT_ITEMS = 20_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialized_item_bytes(items: list[Any]) -> int:
    try:
        canonical = json.dumps(
            items,
            ensure_ascii=False,
            allow_nan=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return 0
    return len(canonical.encode("utf-8"))


class ReviewAssetService:
    def __init__(self, repository: ReviewAssetRepository):
        self.repository = repository

    @staticmethod
    def _fingerprint(
        items: list[Any], payload_bytes: int, duplicate_state: dict[str, set[str]]
    ) -> str:
        canonical = json.dumps(
            {
                "items": items,
                "payload_bytes": payload_bytes,
                "existing_review_ids": sorted(duplicate_state["review_ids"]),
                "existing_content_hashes": sorted(
                    duplicate_state["content_hashes"]
                ),
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _validated_records(
        self, items: list[Any], payload_bytes: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, set[str]]]:
        errors: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        if (
            payload_bytes > MAX_IMPORT_BYTES
            or _serialized_item_bytes(items) > MAX_IMPORT_BYTES
        ):
            return [], [
                {
                    "line": 0,
                    "type": "payload_too_large",
                    "message": "规范化导入内容不能超过 128 MB",
                }
            ], {"review_ids": set(), "content_hashes": set()}
        if len(items) > MAX_IMPORT_ITEMS:
            return [], [
                {
                    "line": 0,
                    "type": "too_many_items",
                    "message": "单个文件最多导入 20000 条评论",
                }
            ], {"review_ids": set(), "content_hashes": set()}

        for line, raw in enumerate(items, start=1):
            try:
                item = ImportReviewItem.model_validate(raw)
                json.dumps(item.original_review, allow_nan=False)
                extract_analysis_text(item.original_review)
                content_hash = canonical_review_hash(item.original_review)
            except (ValidationError, TypeError, ValueError):
                errors.append(
                    {
                        "line": line,
                        "type": "invalid_item",
                        "message": "该行结构或可分析正文不合法",
                    }
                )
                continue
            records.append(
                {"line": line, "item": item, "content_hash": content_hash}
            )

        state = self.repository.import_duplicate_state(
            [record["item"].review_id for record in records if record["item"].review_id],
            [record["content_hash"] for record in records],
        )
        return records, errors, state

    def _validation_details(
        self, items: list[Any], payload_bytes: int
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, set[str]]]:
        records, errors, state = self._validated_records(items, payload_bytes)
        importable: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_hashes: set[str] = set()
        for record in records:
            item = record["item"]
            reason: str | None = None
            if item.review_id and item.review_id in state["review_ids"]:
                reason = "人工来源评论ID已存在"
            elif record["content_hash"] in state["content_hashes"]:
                reason = "内容已存在"
            elif item.review_id and item.review_id in seen_ids:
                reason = "同一批次存在重复评论ID"
            elif record["content_hash"] in seen_hashes:
                reason = "同一批次存在重复内容"
            if reason:
                duplicates.append({"line": record["line"], "reason": reason})
            else:
                importable.append(
                    {
                        "line": record["line"],
                        "series_id": item.series_id,
                        "series_name": item.series_name,
                        "review_id": item.review_id,
                        "content_hash": record["content_hash"],
                    }
                )
                if item.review_id:
                    seen_ids.add(item.review_id)
                seen_hashes.add(record["content_hash"])
        try:
            fingerprint = self._fingerprint(items, payload_bytes, state)
        except (TypeError, ValueError):
            fingerprint = hashlib.sha256(repr(items).encode("utf-8")).hexdigest()
        result = {
            "importable": importable,
            "duplicates": duplicates,
            "errors": errors,
            "validation_fingerprint": fingerprint,
        }
        return result, records, state

    def validate_import(
        self, items: list[Any], payload_bytes: int
    ) -> dict[str, Any]:
        result, _, _ = self._validation_details(items, payload_bytes)
        return result

    @staticmethod
    def _file_error(
        filename: str, payload: bytes, error_type: str, message: str
    ) -> dict[str, Any]:
        fingerprint = hashlib.sha256(
            filename.encode("utf-8") + b"\0" + payload
        ).hexdigest()
        return {
            "importable": [],
            "duplicates": [],
            "errors": [{"line": 0, "type": error_type, "message": message}],
            "validation_fingerprint": fingerprint,
        }

    def _file_items(
        self, filename: str, payload: bytes
    ) -> tuple[list[Any] | None, dict[str, Any] | None]:
        if len(payload) > MAX_IMPORT_FILE_BYTES:
            return None, self._file_error(
                filename,
                payload,
                "payload_too_large",
                "单个导入文件不能超过 32 MB",
            )
        try:
            return parse_review_import_file(filename, payload), None
        except ReviewImportFileError as error:
            return None, self._file_error(
                filename, payload, "file_parse_error", str(error)
            )

    def validate_import_file(
        self, filename: str, payload: bytes
    ) -> dict[str, Any]:
        items, error = self._file_items(filename, payload)
        if error is not None:
            return error
        assert items is not None
        return self.validate_import(items, len(payload))

    def import_validated_file(
        self, filename: str, payload: bytes, validation_fingerprint: str
    ) -> dict[str, Any]:
        items, error = self._file_items(filename, payload)
        if error is not None:
            raise ImportValidationError(error)
        assert items is not None
        return self.import_validated(items, len(payload), validation_fingerprint)

    def import_validated(
        self,
        items: list[Any],
        payload_bytes: int,
        validation_fingerprint: str,
    ) -> dict[str, Any]:
        validation, records, state = self._validation_details(items, payload_bytes)
        if validation["validation_fingerprint"] != validation_fingerprint:
            raise AssetConflict("导入校验结果已变化，请重新校验")
        if validation["errors"]:
            raise ImportValidationError(validation)
        importable_lines = {row["line"] for row in validation["importable"]}
        records_to_import = [
            record for record in records if record["line"] in importable_lines
        ]
        duplicate_guard = {
            "candidate_review_ids": [
                record["item"].review_id
                for record in records
                if record["item"].review_id
            ],
            "candidate_content_hashes": [
                record["content_hash"] for record in records
            ],
            "expected_state": state,
        }
        asset_ids = self.repository.import_assets(
            records_to_import, _now(), duplicate_guard
        )
        return {
            "imported_count": len(asset_ids),
            "duplicate_count": len(validation["duplicates"]),
            "asset_ids": asset_ids,
        }

    def delete_asset(
        self, asset_id: str, command: DeleteAssetBody
    ) -> dict[str, Any]:
        return self.repository.delete_asset(
            asset_id,
            expected_content_hash=command.expected_content_hash,
            confirmed_review_id=command.confirmed_review_id,
            reason=command.reason,
        )

    def allow_recollection(self, asset_id: str) -> dict[str, Any]:
        return self.repository.allow_recollection(asset_id)
