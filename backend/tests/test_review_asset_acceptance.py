import json

from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.review_analysis.domain import (
    CreateJobCommand,
    PromptManifest,
    ReviewSnapshot,
)
from backend.review_analysis.text import extract_analysis_text


def test_temporary_database_review_asset_research_lifecycle(tmp_path):
    """Exercise the documented flow without touching the local runtime database."""

    fixture = ROOT / "backend/tests/fixtures/import/reviews-valid.jsonl"
    text = fixture.read_text(encoding="utf-8")
    items = [json.loads(line) for line in text.splitlines() if line.strip()]
    app = create_app(tmp_path / "acceptance.sqlite3", ROOT / "backend/data/research")

    with TestClient(app) as client:
        preview = client.post(
            "/api/collection/review-assets/import/validate",
            json={"items": items, "payload_bytes": len(text.encode("utf-8"))},
        )
        assert preview.status_code == 200
        assert len(preview.json()["importable"]) == 2

        imported = client.post(
            "/api/collection/review-assets/import",
            json={
                "items": items,
                "payload_bytes": len(text.encode("utf-8")),
                "validation_fingerprint": preview.json()[
                    "validation_fingerprint"
                ],
            },
        )
        assert imported.status_code == 201
        asset_id = imported.json()["asset_ids"][0]

        detail = client.get(
            f"/api/collection/review-assets/{asset_id}"
        ).json()
        updated = client.patch(
            f"/api/collection/review-assets/{asset_id}/metadata",
            json={
                "revision": detail["revision"],
                "tags": ["验收夹具"],
                "note": "临时数据库闭环",
                "analysis_enabled": True,
            },
        )
        assert updated.status_code == 200

        with app.state.store.connect() as connection:
            connection.execute(
                "INSERT INTO projects VALUES ('acceptance','验收','custom','now')"
            )
            connection.execute(
                "INSERT INTO schemas VALUES "
                "('acceptance-schema','acceptance',1,'draft',1,'[]','now')"
            )

        def snapshots(assets):
            return [
                ReviewSnapshot(
                    source_asset_id=item.asset_id,
                    review_id=item.review_id,
                    series_id=item.series_id,
                    series_name=item.series_name,
                    content_hash=item.content_hash,
                    analysis_text=extract_analysis_text(item.original_review),
                    ordinal=index,
                )
                for index, item in enumerate(assets)
            ]

        job = app.state.review_analysis_repository.create_job_with_snapshot(
            CreateJobCommand(
                project_id="acceptance",
                schema_id="acceptance-schema",
                schema_revision=1,
                job_type="criteria_discovery",
                selected_series_ids=[detail["series_id"]],
                limit=10,
                model="acceptance-no-call",
                prompt_manifests=[
                    PromptManifest(version="acceptance", sha256="a" * 64)
                ],
            ),
            snapshots,
        )

        deleted = client.request(
            "DELETE",
            f"/api/collection/review-assets/{asset_id}",
            json={
                "expected_content_hash": detail["content_hash"],
                "confirmed_review_id": detail["review_id"],
                "reason": "临时数据库验收删除",
                "confirm": True,
            },
        )
        assert deleted.status_code == 200
        assert client.get(
            f"/api/collection/review-assets/{asset_id}"
        ).status_code == 410

        preserved = app.state.review_analysis_repository.pending_review_snapshots(
            job["id"]
        )
        deleted_snapshot = next(
            row for row in preserved if row["source_asset_id"] == asset_id
        )
        assert deleted_snapshot["analysis_text"]
        assert deleted_snapshot["source_deleted"] is True

        released = client.post(
            f"/api/collection/deletions/{asset_id}/allow-recollection"
        )
        assert released.status_code == 200
        assert released.json()["recollection_allowed_at"] is not None
