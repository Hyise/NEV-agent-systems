import pytest
from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.collection.asset_domain import MetadataPatchBody
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
    detail = asset_client.get(
        "/api/collection/review-assets/autohome%3Areview-1"
    )
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
    missing = asset_client.get(
        "/api/collection/review-assets/autohome%3Amissing"
    )
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
