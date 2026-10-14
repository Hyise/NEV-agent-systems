import json
import sqlite3

import pytest

from backend.collection.asset_domain import (
    AssetConflict,
    AssetGone,
    DeleteAssetBody,
    MetadataPatchBody,
)
from backend.collection.asset_repository import ReviewAssetRepository
from backend.collection.asset_service import ReviewAssetService
from backend.collection.domain import CollectedReview, CreateJobBody, VehicleSeries
from backend.collection.repository import CollectionRepository
from backend.review_analysis.domain import (
    CreateJobCommand,
    PromptManifest,
    ReviewSnapshot,
)
from backend.review_analysis.repository import ReviewAnalysisRepository
from backend.review_analysis.text import extract_analysis_text
from backend.store import Store
from backend.tests.test_review_asset_repository import seed_asset_database


def prepare_deletable(tmp_path):
    path = tmp_path / "delete.sqlite3"
    repository = seed_asset_database(path)
    with repository.connect() as connection:
        connection.execute(
            "UPDATE collection_jobs SET status='stopped', finished_at=updated_at"
        )
    return path, repository, ReviewAssetService(repository)


def delete_body(detail, **updates):
    values = {
        "expected_content_hash": detail["content_hash"],
        "confirmed_review_id": detail["review_id"],
        "reason": "该评论不再进入研究样本",
        "confirm": True,
    }
    values.update(updates)
    return DeleteAssetBody(**values)


def test_delete_writes_minimal_audit_and_removes_raw_asset(tmp_path):
    _, repository, service = prepare_deletable(tmp_path)
    detail = repository.get_asset("autohome:review-1")
    repository.update_metadata(
        "autohome:review-1",
        command=MetadataPatchBody(
            revision=1,
            tags=["敏感标签"],
            note="不得进入删除审计",
            analysis_enabled=True,
        ),
    )

    audit = service.delete_asset("autohome:review-1", delete_body(detail))

    with pytest.raises(AssetGone):
        repository.get_asset("autohome:review-1")
    assert set(audit) == {
        "audit_id",
        "asset_id",
        "source_kind",
        "platform",
        "review_id",
        "series_id",
        "series_name_snapshot",
        "content_hash",
        "reason",
        "deleted_at",
        "recollection_allowed_at",
    }
    serialized = json.dumps(audit, ensure_ascii=False)
    assert "空间宽敞" not in serialized
    assert "https://" not in serialized
    assert "敏感标签" not in serialized
    assert "不得进入删除审计" not in serialized
    assert repository.list_deletions(page=1, page_size=20)["rows"] == [audit]


@pytest.mark.parametrize("status", ["queued", "discovering", "collecting", "paused"])
def test_active_job_blocks_delete_without_partial_audit(tmp_path, status):
    path = tmp_path / f"active-{status}.sqlite3"
    repository = seed_asset_database(path)
    with repository.connect() as connection:
        connection.execute("UPDATE collection_jobs SET status=?", (status,))
    detail = repository.get_asset("autohome:review-1")

    with pytest.raises(AssetConflict, match="采集任务"):
        repository.delete_asset(
            "autohome:review-1",
            expected_content_hash=detail["content_hash"],
            confirmed_review_id="review-1",
            reason="测试并发保护",
        )

    assert repository.get_asset("autohome:review-1")["review_id"] == "review-1"
    assert repository.list_deletions(page=1, page_size=20)["total"] == 0


def test_delete_rejects_confirmation_and_hash_conflicts(tmp_path):
    _, repository, _ = prepare_deletable(tmp_path)
    detail = repository.get_asset("autohome:review-1")

    with pytest.raises(AssetConflict, match="评论ID"):
        repository.delete_asset(
            "autohome:review-1",
            expected_content_hash=detail["content_hash"],
            confirmed_review_id="wrong",
            reason="测试确认",
        )
    with pytest.raises(AssetConflict, match="内容已变化"):
        repository.delete_asset(
            "autohome:review-1",
            expected_content_hash="f" * 64,
            confirmed_review_id="review-1",
            reason="测试哈希",
        )
    assert repository.list_deletions(page=1, page_size=20)["total"] == 0


def test_deleted_asset_is_gone_and_can_only_allow_future_recollection(tmp_path):
    _, repository, service = prepare_deletable(tmp_path)
    detail = repository.get_asset("autohome:review-1")
    service.delete_asset("autohome:review-1", delete_body(detail))

    with pytest.raises(AssetGone):
        service.delete_asset("autohome:review-1", delete_body(detail))
    released = service.allow_recollection("autohome:review-1")

    assert released["recollection_allowed_at"] is not None
    with pytest.raises(AssetGone):
        repository.get_asset("autohome:review-1")


def test_analysis_snapshot_and_results_survive_source_deletion(tmp_path):
    path, repository, service = prepare_deletable(tmp_path)
    store = Store(path)
    with store.connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO projects VALUES ('p1','项目','custom','now')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schemas VALUES ('s1','p1',1,'draft',1,'[]','now')"
        )
    analysis = ReviewAnalysisRepository(path)
    command = CreateJobCommand(
        project_id="p1",
        schema_id="s1",
        schema_revision=1,
        job_type="criteria_discovery",
        selected_series_ids=["5769"],
        limit=1,
        model="deepseek-flash",
        prompt_manifests=[PromptManifest(version="v1", sha256="a" * 64)],
    )

    def snapshot(assets):
        item = assets[0]
        return [
            ReviewSnapshot(
                review_id=item.review_id,
                series_id=item.series_id,
                series_name=item.series_name,
                content_hash=item.content_hash,
                analysis_text=extract_analysis_text(item.original_review),
                ordinal=0,
            )
        ]

    job = analysis.create_job_with_snapshot(command, snapshot)
    analysis.save_proposal(
        job["id"],
        {"criteria": [{"name": "空间", "labels": ["好", "差"]}]},
        source_review_count=1,
        sample_review_count=1,
    )
    detail = repository.get_asset("autohome:review-1")

    service.delete_asset("autohome:review-1", delete_body(detail))

    assert analysis.pending_review_snapshots(job["id"])[0]["analysis_text"]
    assert analysis.get_proposal(job["id"])["proposal"]["criteria"][0]["name"] == "空间"


def test_allow_recollection_unblocks_future_collection_not_recovery(tmp_path):
    path, repository, service = prepare_deletable(tmp_path)
    detail = repository.get_asset("autohome:review-1")
    service.delete_asset("autohome:review-1", delete_body(detail))
    collection = CollectionRepository(path)
    series = VehicleSeries(
        series_id="5769",
        series_name="Model Y",
        series_url="https://www.autohome.com.cn/5769/",
        review_url="https://k.autohome.com.cn/5769/",
        discovery_rank=1,
    )
    review = CollectedReview(
        review_id="review-1",
        series_id="5769",
        series_name="Model Y",
        source_url="https://k.autohome.com.cn/5769/#review-1",
        original_review={"feeling_summary": "重新采集后的当前原文"},
    )
    collection.create_job(
        "job-recollect",
        CreateJobBody(mode="verification", selected_series_ids=["5769"]).to_config(),
        "2026-10-14T09:00:00+00:00",
    )
    collection.save_discovery(
        "job-recollect", [series], "2026-10-14T09:01:00+00:00"
    )
    blocked = collection.save_review_page(
        "job-recollect", series, [review], 2, "2026-10-14T09:02:00+00:00"
    )
    service.allow_recollection("autohome:review-1")
    stored = collection.save_review_page(
        "job-recollect", series, [review], 2, "2026-10-14T09:03:00+00:00"
    )

    assert blocked["deleted_skipped"] == 1
    assert stored["saved"] == 1
    assert repository.get_asset("autohome:review-1")["original_review"] == {
        "feeling_summary": "重新采集后的当前原文"
    }
