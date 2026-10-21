import pytest
from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.collection.asset_domain import MetadataPatchBody
from backend.collection.domain import JobStatus
from backend.tests.test_review_asset_repository import seed_asset_database


@pytest.fixture
def asset_client(tmp_path):
    path = tmp_path / "asset-api.sqlite3"
    seed_asset_database(path)
    app = create_app(path, ROOT / "backend/data/research")
    with TestClient(app) as client:
        yield client


def test_asset_list_detail_summary_and_metadata_routes(asset_client):
    listed = asset_client.get(
        "/api/collection/review-assets",
        params={"keyword": "续航", "page": 1, "page_size": 20},
    )
    detail = asset_client.get("/api/collection/review-assets/autohome%3Areview-1")
    updated = asset_client.patch(
        "/api/collection/review-assets/autohome%3Areview-1/metadata",
        json={
            "revision": 1,
            "tags": ["重点"],
            "note": "API 修改元数据",
            "analysis_enabled": False,
        },
    )
    summary = asset_client.get("/api/collection/review-assets/summary")

    assert listed.status_code == 200
    assert listed.json()["rows"][0]["asset_id"] == "autohome:review-1"
    assert "original_review" not in listed.json()["rows"][0]
    assert detail.status_code == 200
    assert detail.json()["original_review"]["feeling_summary"] == "空间宽敞"
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert summary.status_code == 200
    assert summary.json()["analysis_disabled"] == 1


def test_asset_list_filters_by_original_review_date_and_rejects_reversed_range(
    asset_client,
):
    filtered = asset_client.get(
        "/api/collection/review-assets",
        params={
            "review_date_from": "2026-01-01",
            "review_date_to": "2026-12-31",
        },
    )
    reversed_range = asset_client.get(
        "/api/collection/review-assets",
        params={
            "review_date_from": "2026-12-31",
            "review_date_to": "2026-01-01",
        },
    )

    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["rows"][0]["review_date"] == "2026-05-03"
    assert reversed_range.status_code == 422
    assert reversed_range.json()["detail"] == "评论开始日期不能晚于结束日期"


@pytest.mark.parametrize(
    "field,value",
    [
        ("tags", [f"标签{i}" for i in range(21)]),
        ("tags", ["三" * 31]),
        ("note", "注" * 1001),
    ],
)
def test_metadata_limits_return_422(asset_client, field, value):
    body = {
        "revision": 1,
        "tags": [],
        "note": "",
        "analysis_enabled": True,
    }
    body[field] = value

    response = asset_client.patch(
        "/api/collection/review-assets/autohome%3Areview-1/metadata", json=body
    )

    assert response.status_code == 422


def test_stale_metadata_revision_returns_409(asset_client):
    path = "/api/collection/review-assets/autohome%3Areview-1/metadata"
    body = {
        "revision": 1,
        "tags": ["首轮"],
        "note": "",
        "analysis_enabled": True,
    }
    assert asset_client.patch(path, json=body).status_code == 200

    response = asset_client.patch(path, json=body)

    assert response.status_code == 409
    assert response.json()["detail"] == "资产管理信息已被其他操作更新，请刷新后重试"


def test_unknown_asset_returns_404_and_raw_fields_are_forbidden(asset_client):
    missing = asset_client.get("/api/collection/review-assets/autohome%3Amissing")
    invalid = asset_client.patch(
        "/api/collection/review-assets/autohome%3Areview-1/metadata",
        json={
            "revision": 1,
            "tags": [],
            "note": "",
            "analysis_enabled": True,
            "original_review": {"contents": []},
        },
    )

    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert "original_review" not in MetadataPatchBody.model_fields


def test_import_validate_and_confirm_routes_are_two_step(asset_client):
    item = {
        "series_id": "5769",
        "series_name": "Model Y",
        "review_id": "api-manual-1",
        "original_review": {
            "feeling_summary": "导入测试",
            "contents": [{"structuredname": "满意", "content": "空间充足"}],
        },
    }
    preview = asset_client.post(
        "/api/collection/review-assets/import/validate",
        json={"items": [item], "payload_bytes": 512},
    )

    confirmed = asset_client.post(
        "/api/collection/review-assets/import",
        json={
            "items": [item],
            "payload_bytes": 512,
            "validation_fingerprint": preview.json()["validation_fingerprint"],
        },
    )

    assert preview.status_code == 200
    assert preview.json()["importable"][0]["line"] == 1
    assert confirmed.status_code == 201
    assert confirmed.json()["imported_count"] == 1


def test_import_confirm_with_stale_fingerprint_returns_409(asset_client):
    item = {
        "series_id": "5769",
        "series_name": "Model Y",
        "review_id": "stale-api",
        "original_review": {"feeling_summary": "导入测试"},
    }

    response = asset_client.post(
        "/api/collection/review-assets/import",
        json={
            "items": [item],
            "payload_bytes": 256,
            "validation_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 409


def test_tabular_file_import_routes_validate_then_preserve_full_text(asset_client):
    full_text = "最满意：空间宽敞。\n续航：高速续航稳定，完整结尾。"
    payload = (
        "series_id,series_name,koubei_id,show_id,分项评论全文,详情URL\n"
        f'5769,Model Y,,show-file-1,"{full_text}",https://example.test/1\n'
    ).encode("utf-8")

    preview = asset_client.post(
        "/api/collection/review-assets/import-file/validate",
        params={"filename": "reviews.csv"},
        content=payload,
        headers={"content-type": "application/octet-stream"},
    )
    confirmed = asset_client.post(
        "/api/collection/review-assets/import-file",
        params={"filename": "reviews.csv"},
        content=payload,
        headers={
            "content-type": "application/octet-stream",
            "x-validation-fingerprint": preview.json()["validation_fingerprint"],
        },
    )

    assert preview.status_code == 200
    assert preview.json()["importable"][0]["review_id"] == "show-file-1"
    assert confirmed.status_code == 201
    detail = asset_client.get(
        f"/api/collection/review-assets/{confirmed.json()['asset_ids'][0]}"
    )
    assert detail.json()["original_review"]["分项评论全文"] == full_text


def test_delete_audit_and_allow_recollection_routes(asset_client):
    asset_client.app.state.collection_repository.set_status(
        "job-1",
        JobStatus.STOPPED,
        "2026-10-14T08:00:00+00:00",
        finished=True,
    )
    detail = asset_client.get(
        "/api/collection/review-assets/autohome%3Areview-1"
    ).json()

    deleted = asset_client.request(
        "DELETE",
        "/api/collection/review-assets/autohome%3Areview-1",
        json={
            "expected_content_hash": detail["content_hash"],
            "confirmed_review_id": "review-1",
            "reason": "API删除测试",
            "confirm": True,
        },
    )
    gone = asset_client.get("/api/collection/review-assets/autohome%3Areview-1")
    audits = asset_client.get("/api/collection/deletions")
    released = asset_client.post(
        "/api/collection/deletions/autohome%3Areview-1/allow-recollection"
    )

    assert deleted.status_code == 200
    assert gone.status_code == 410
    assert audits.json()["total"] == 1
    assert "original_review" not in audits.text
    assert released.status_code == 200
    assert released.json()["recollection_allowed_at"] is not None


def test_delete_validation_and_conflict_statuses(asset_client):
    detail = asset_client.get(
        "/api/collection/review-assets/autohome%3Areview-1"
    ).json()
    invalid = asset_client.request(
        "DELETE",
        "/api/collection/review-assets/autohome%3Areview-1",
        json={
            "expected_content_hash": detail["content_hash"],
            "confirmed_review_id": "review-1",
            "reason": "",
            "confirm": False,
        },
    )
    conflict = asset_client.request(
        "DELETE",
        "/api/collection/review-assets/autohome%3Areview-1",
        json={
            "expected_content_hash": detail["content_hash"],
            "confirmed_review_id": "review-1",
            "reason": "活动任务冲突",
            "confirm": True,
        },
    )

    assert invalid.status_code == 422
    assert conflict.status_code == 409
