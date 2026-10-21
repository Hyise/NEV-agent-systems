import sqlite3

import pytest

import backend.collection.asset_service as asset_service_module
from backend.collection.asset_domain import AssetConflict, ImportValidationError
from backend.collection.asset_repository import ReviewAssetRepository
from backend.collection.asset_service import ReviewAssetService
from backend.tests.test_review_asset_repository import seed_asset_database


def valid_item(review_id="manual-1", content="乘坐舒适"):
    return {
        "series_id": "5769",
        "series_name": "Model Y",
        "review_id": review_id,
        "source_url": "https://example.test/reviews/1",
        "original_review": {
            "feeling_summary": "日常使用",
            "contents": [{"structuredname": "满意", "content": content}],
            "unknown": {"nested": [1, "保留", None]},
        },
    }


def service_for(tmp_path):
    path = tmp_path / "import.sqlite3"
    repository = seed_asset_database(path)
    return ReviewAssetService(repository), repository


def test_validate_import_reports_line_errors_and_duplicates(tmp_path):
    service, _ = service_for(tmp_path)
    items = [
        valid_item(),
        valid_item(review_id="manual-2"),
        {**valid_item(review_id="bad-url"), "source_url": "http://example.test/1"},
        {**valid_item(review_id="empty"), "original_review": {"contents": []}},
        "not-an-object",
    ]

    result = service.validate_import(items, payload_bytes=1024)

    assert [row["line"] for row in result["importable"]] == [1]
    assert result["duplicates"] == [
        {"line": 2, "reason": "同一批次存在重复内容"}
    ]
    assert [row["line"] for row in result["errors"]] == [3, 4, 5]
    assert len(result["validation_fingerprint"]) == 64
    assert "乘坐舒适" not in str(result)


@pytest.mark.parametrize(
    "items,payload_bytes,error_type",
    [
        (
            [valid_item()],
            asset_service_module.MAX_IMPORT_BYTES + 1,
            "payload_too_large",
        ),
        (
            [valid_item()] * (asset_service_module.MAX_IMPORT_ITEMS + 1),
            1024,
            "too_many_items",
        ),
        (
            [
                {
                    **valid_item(),
                    "original_review": {"feeling_summary": "ok", "score": float("nan")},
                }
            ],
            1024,
            "invalid_item",
        ),
    ],
)
def test_validate_import_enforces_batch_and_json_limits(
    tmp_path, items, payload_bytes, error_type
):
    service, _ = service_for(tmp_path)

    result = service.validate_import(items, payload_bytes=payload_bytes)

    assert result["importable"] == []
    assert result["errors"][0]["type"] == error_type


def test_validate_import_file_supports_real_csv_contract(tmp_path):
    service, _ = service_for(tmp_path)
    full_text = "最满意：空间宽敞。\n续航：高速续航稳定，完整结尾。"
    payload = (
        "series_id,series_name,koubei_id,show_id,分项评论全文,详情URL\n"
        f'5769,Model Y,,show-1,"{full_text}",https://example.test/1\n'
    ).encode("utf-8")

    validation = service.validate_import_file("reviews.csv", payload)
    result = service.import_validated_file(
        "reviews.csv", payload, validation["validation_fingerprint"]
    )

    assert validation["importable"][0]["review_id"] == "show-1"
    assert result["imported_count"] == 1


def test_validate_import_file_reports_parse_and_file_size_errors(tmp_path, monkeypatch):
    service, _ = service_for(tmp_path)
    invalid = service.validate_import_file("reviews.csv", b"series_id\n1\n")
    assert invalid["errors"] == [
        {
            "line": 0,
            "type": "file_parse_error",
            "message": "表格缺少必要列：series_name、show_id、分项评论全文、详情URL",
        }
    ]

    monkeypatch.setattr(asset_service_module, "MAX_IMPORT_FILE_BYTES", 4)
    oversized = service.validate_import_file("reviews.csv", b"12345")
    assert oversized["errors"][0]["type"] == "payload_too_large"
    assert "32 MB" in oversized["errors"][0]["message"]


def test_validate_import_file_marks_files_without_reviews_as_skippable(tmp_path):
    service, _ = service_for(tmp_path)
    header_only = (
        "series_id,series_name,koubei_id,show_id,分项评论全文,详情URL\n"
    ).encode("utf-8")

    validation = service.validate_import_file("empty.csv", header_only)

    assert validation["importable"] == []
    assert validation["errors"] == [
        {
            "line": 0,
            "type": "empty_file",
            "message": "文件没有可导入的评论",
        }
    ]


def test_expanded_limits_cover_verified_source_shape(tmp_path):
    service, _ = service_for(tmp_path)
    items = [valid_item(review_id=f"source-{index}", content=f"内容{index}") for index in range(10_001)]

    result = service.validate_import(items, payload_bytes=16 * 1024 * 1024)

    assert len(result["importable"]) == 10_001
    assert result["errors"] == []


def test_validate_import_measures_items_instead_of_trusting_declared_size(
    tmp_path, monkeypatch
):
    service, repository = service_for(tmp_path)
    items = [valid_item(content="大" * 1024)]

    monkeypatch.setattr(asset_service_module, "MAX_IMPORT_BYTES", 100)
    validation = service.validate_import(items, payload_bytes=1)

    assert validation["importable"] == []
    assert validation["errors"][0]["type"] == "payload_too_large"
    with pytest.raises(ImportValidationError):
        service.import_validated(
            items,
            payload_bytes=1,
            validation_fingerprint=validation["validation_fingerprint"],
        )
    assert repository.list_assets(
        source_kind="manual_import", page=1, page_size=20
    )["total"] == 0


@pytest.mark.parametrize(
    "source_url",
    ["https://", "https:// bad-host/review", "https://example.test/has space"],
)
def test_validate_import_rejects_malformed_https_urls(tmp_path, source_url):
    service, _ = service_for(tmp_path)

    result = service.validate_import(
        [{**valid_item(), "source_url": source_url}], payload_bytes=1024
    )

    assert result["importable"] == []
    assert result["errors"][0]["type"] == "invalid_item"


def test_confirm_import_preserves_structure_and_isolates_manual_ids(tmp_path):
    service, repository = service_for(tmp_path)
    items = [valid_item(), valid_item(review_id=None, content="储物空间丰富")]
    validation = service.validate_import(items, payload_bytes=2048)

    result = service.import_validated(
        items,
        payload_bytes=2048,
        validation_fingerprint=validation["validation_fingerprint"],
    )

    assert result["imported_count"] == 2
    assert result["duplicate_count"] == 0
    imported = repository.list_assets(
        source_kind="manual_import", page=1, page_size=20
    )
    assert imported["total"] == 2
    assert all(row["asset_id"].startswith("manual:") for row in imported["rows"])
    detail = repository.get_asset(imported["rows"][0]["asset_id"])
    assert detail["platform"] == "manual"
    assert detail["source_kind"] == "manual_import"
    assert detail["original_review"]["unknown"] == {"nested": [1, "保留", None]}


def test_import_rejects_stale_fingerprint_without_partial_write(tmp_path):
    service, repository = service_for(tmp_path)
    items = [valid_item(), valid_item(review_id="manual-2", content="动力平顺")]
    validation = service.validate_import(items, payload_bytes=2048)
    timestamp = "2026-10-14T08:00:00+00:00"
    with repository.connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO vehicle_series VALUES (?,?,?,?,?,?,?,?)",
            ("manual", "5769", "Model Y", "", "", 1000000, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO reviews (
                platform, review_id, series_id, series_name_snapshot, source_url,
                original_review_json, content_hash, first_collected_at,
                last_confirmed_at, asset_id, source_kind
            ) VALUES ('manual','manual-1','5769','Model Y','',
                      '{"feeling_summary":"竞争写入"}',?, ?, ?,
                      'manual:competition','manual_import')
            """,
            ("b" * 64, timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO review_asset_metadata VALUES "
            "('manual:competition',1,'[]','',1,?,?)",
            (timestamp, timestamp),
        )

    with pytest.raises(AssetConflict, match="校验结果已变化"):
        service.import_validated(
            items,
            payload_bytes=2048,
            validation_fingerprint=validation["validation_fingerprint"],
        )

    assert repository.list_assets(
        keyword="manual-2", page=1, page_size=20
    )["total"] == 0


def test_import_rechecks_duplicate_state_inside_write_transaction(tmp_path):
    path = tmp_path / "race.sqlite3"
    seed_asset_database(path)

    class RacingRepository(ReviewAssetRepository):
        def import_assets(self, records, imported_at, duplicate_guard):
            content_hash = records[0]["content_hash"]
            with self.connect() as connection:
                connection.execute(
                    "INSERT OR IGNORE INTO vehicle_series VALUES (?,?,?,?,?,?,?,?)",
                    (
                        "manual",
                        "5769",
                        "Model Y",
                        "",
                        "",
                        1000000,
                        imported_at,
                        imported_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO reviews (
                        platform, review_id, series_id, series_name_snapshot,
                        source_url, original_review_json, content_hash,
                        first_collected_at, last_confirmed_at, asset_id, source_kind
                    ) VALUES ('manual','race-other','5769','Model Y','',
                              '{"feeling_summary":"竞争内容"}',?,?,?,
                              'manual:race-other','manual_import')
                    """,
                    (content_hash, imported_at, imported_at),
                )
                connection.execute(
                    "INSERT INTO review_asset_metadata VALUES "
                    "('manual:race-other',1,'[]','',1,?,?)",
                    (imported_at, imported_at),
                )
            return super().import_assets(records, imported_at, duplicate_guard)

    repository = RacingRepository(path)
    service = ReviewAssetService(repository)
    items = [valid_item()]
    validation = service.validate_import(items, payload_bytes=1024)

    with pytest.raises(AssetConflict, match="校验结果已变化"):
        service.import_validated(
            items,
            payload_bytes=1024,
            validation_fingerprint=validation["validation_fingerprint"],
        )


def test_import_transaction_rolls_back_when_one_insert_fails(tmp_path):
    service, repository = service_for(tmp_path)
    items = [valid_item(), valid_item(review_id="fail", content="第二条")]
    validation = service.validate_import(items, payload_bytes=2048)
    with repository.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_manual_row BEFORE INSERT ON reviews
            WHEN NEW.review_id='fail'
            BEGIN SELECT RAISE(ABORT, 'forced failure'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced failure"):
        service.import_validated(
            items,
            payload_bytes=2048,
            validation_fingerprint=validation["validation_fingerprint"],
        )

    assert repository.list_assets(
        source_kind="manual_import", page=1, page_size=20
    )["total"] == 0
