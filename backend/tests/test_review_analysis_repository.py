import json
import sqlite3
from pathlib import Path

import pytest

from backend.collection.asset_domain import DeleteAssetBody, MetadataPatchBody
from backend.collection.asset_repository import ReviewAssetRepository
from backend.collection.asset_service import ReviewAssetService
from backend.collection.repository import CollectionRepository
from backend.review_analysis.deepseek import JsonCompletion
from backend.review_analysis.domain import (
    CreateJobCommand,
    CriterionSnapshot,
    PromptManifest,
    ReviewSnapshot,
    schema_fingerprint,
    stable_stratified_sample,
)
from backend.review_analysis.repository import ReviewAnalysisRepository
from backend.review_analysis.text import extract_analysis_text


def seed(path: Path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE projects (id TEXT PRIMARY KEY,name TEXT,mode TEXT,created_at TEXT);
        CREATE TABLE schemas (id TEXT PRIMARY KEY,project_id TEXT,version INTEGER,status TEXT,revision INTEGER,criteria TEXT,created_at TEXT);
        CREATE TABLE vehicle_series (platform TEXT,series_id TEXT,series_name TEXT,series_url TEXT,review_url TEXT,discovery_rank INTEGER,first_discovered_at TEXT,last_confirmed_at TEXT,PRIMARY KEY(platform,series_id));
        CREATE TABLE reviews (platform TEXT,review_id TEXT,series_id TEXT,series_name_snapshot TEXT,source_url TEXT,original_review_json TEXT,content_hash TEXT,first_collected_at TEXT,last_confirmed_at TEXT,PRIMARY KEY(platform,review_id));
        INSERT INTO projects VALUES ('p1','项目','custom','now');
        INSERT INTO schemas VALUES ('s1','p1',1,'draft',1,'[]','now');
        INSERT INTO vehicle_series VALUES ('autohome','1','车系一','https://a','https://a','1','now','now');
        INSERT INTO vehicle_series VALUES ('autohome','2','车系二','https://b','https://b','2','now','now');
        """
    )
    for series, review_id, text, content_hash in (
        ("1", "r1", "空间宽敞", "1" * 64),
        ("1", "r2", "动力充足", "2" * 64),
        ("2", "r3", "续航扎实", "3" * 64),
    ):
        connection.execute(
            "INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?)",
            ("autohome", review_id, series, f"车系{series}", "https://x", json.dumps({"feeling_summary": text}, ensure_ascii=False), content_hash, "now", "now"),
        )
    connection.commit()
    connection.close()
    CollectionRepository(path)


def command(**updates):
    values = dict(
        project_id="p1",
        schema_id="s1",
        job_type="criteria_discovery",
        schema_revision=1,
        selected_series_ids=["1", "2"],
        limit=2,
        model="deepseek-flash",
        prompt_manifests=[PromptManifest(version="v1", sha256="a" * 64)],
    )
    values.update(updates)
    return CreateJobCommand(**values)


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
        for index, item in enumerate(stable_stratified_sample(assets, 2))
    ]


def test_sources_aggregate_providers_and_snapshots_use_enabled_assets_only(tmp_path):
    path = tmp_path / "mixed.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    assets = ReviewAssetRepository(path)
    timestamp = "2026-10-14T08:00:00+00:00"
    with assets.connect() as connection:
        connection.execute(
            "INSERT INTO vehicle_series VALUES (?,?,?,?,?,?,?,?)",
            ("manual", "1", "车系一", "", "", 1000000, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO reviews (
                platform,review_id,series_id,series_name_snapshot,source_url,
                original_review_json,content_hash,first_collected_at,
                last_confirmed_at,asset_id,source_kind
            ) VALUES ('manual','r1','1','车系一','',?,?,?, ?,
                      'manual:asset-r4','manual_import')
            """,
            (
                json.dumps({"feeling_summary": "人工补充"}, ensure_ascii=False),
                "4" * 64,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO review_asset_metadata VALUES "
            "('manual:asset-r4',1,'[]','',1,?,?)",
            (timestamp, timestamp),
        )
    assets.update_metadata(
        "autohome:r2",
        MetadataPatchBody(
            revision=1, tags=[], note="", analysis_enabled=False
        ),
    )
    detail = assets.get_asset("autohome:r3")
    ReviewAssetService(assets).delete_asset(
        "autohome:r3",
        DeleteAssetBody(
            expected_content_hash=detail["content_hash"],
            confirmed_review_id="r3",
            reason="删除车系二样本",
            confirm=True,
        ),
    )

    sources = repository.list_sources(query="车系", page=1, page_size=20)
    job = repository.create_job_with_snapshot(
        command(selected_series_ids=["1"], limit=10), snapshots
    )
    rows = repository.pending_review_snapshots(job["id"])

    assert sources["total"] == 1
    assert sources["rows"] == [
        {
            "series_id": "1",
            "series_name": "车系一",
            "discovery_rank": 1,
            "review_count": 2,
        }
    ]
    assert {row["source_asset_id"] for row in rows} == {
        "autohome:r1",
        "manual:asset-r4",
    }
    assert {row["snapshot_id"] for row in rows} == {
        "autohome:r1",
        "manual:asset-r4",
    }
    checkpoint = repository.ensure_discovery_batches(job["id"], [rows])[0]
    assert set(checkpoint["review_ids"]) == {
        "autohome:r1",
        "manual:asset-r4",
    }


def test_snapshot_source_deleted_status_is_stable_for_current_and_historical_rows(
    tmp_path,
):
    path = tmp_path / "source-status.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    assets = ReviewAssetRepository(path)
    job = repository.create_job_with_snapshot(
        command(selected_series_ids=["1"], limit=2), snapshots
    )
    rows = repository.pending_review_snapshots(job["id"])
    assert all(row["source_deleted"] is False for row in rows)

    deleted_asset_id = rows[0]["source_asset_id"]
    detail = assets.get_asset(deleted_asset_id)
    ReviewAssetService(assets).delete_asset(
        deleted_asset_id,
        DeleteAssetBody(
            expected_content_hash=detail["content_hash"],
            confirmed_review_id=detail["review_id"],
            reason="验证研究快照保留",
            confirm=True,
        ),
    )
    with repository.connect() as connection:
        connection.execute(
            "UPDATE review_analysis_job_reviews SET source_asset_id=NULL "
            "WHERE job_id=? AND review_id=?",
            (job["id"], rows[1]["review_id"]),
        )

    after = repository.pending_review_snapshots(job["id"])

    deleted = next(row for row in after if row["source_asset_id"] == deleted_asset_id)
    historical = next(row for row in after if row["source_asset_id"] is None)
    assert deleted["source_deleted"] is True
    assert deleted["analysis_text"]
    assert historical["source_deleted"] is False


def test_migrates_old_database_and_lists_sources(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)

    sources = repository.list_sources(query="车系", page=1, page_size=20)
    assert sources["total"] == 2
    assert [row["review_count"] for row in sources["rows"]] == [2, 1]
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"review_analysis_jobs", "review_analysis_job_reviews", "criteria_proposals", "review_annotation_results"} <= tables


def test_job_and_immutable_text_snapshot_are_created_atomically(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    rows = repository.pending_review_snapshots(job["id"])
    assert len(rows) == 2
    original = rows[0]["analysis_text"]

    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE reviews SET original_review_json=? WHERE review_id=?", (json.dumps({"feeling_summary": "已变化"}), rows[0]["review_id"]))
        connection.commit()
    assert repository.pending_review_snapshots(job["id"])[0]["analysis_text"] == original

    with pytest.raises(ValueError, match="活动"):
        repository.create_job_with_snapshot(command(selected_series_ids=["1"]), snapshots)


def test_rejects_duplicate_empty_and_unknown_source_selections(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    with pytest.raises(ValueError):
        repository.create_job_with_snapshot(command(selected_series_ids=["1", "1"]), snapshots)
    with pytest.raises(ValueError, match="没有已采集评论"):
        repository.create_job_with_snapshot(command(selected_series_ids=["999"]), snapshots)


def test_cache_key_uses_all_four_lineage_dimensions(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    result = repository.save_result(
        content_hash="1" * 64,
        schema_fingerprint="b" * 64,
        model="deepseek-flash",
        prompt_version="v1",
        prompt_sha256="c" * 64,
        result={"annotations": [], "unmatched_evidence": []},
        input_tokens=1,
        output_tokens=2,
        cached_tokens=0,
    )
    assert repository.find_cached_result("1" * 64, "b" * 64, "deepseek-flash", "c" * 64)["id"] == result["id"]
    assert repository.find_cached_result("2" * 64, "b" * 64, "deepseek-flash", "c" * 64) is None
    assert repository.find_cached_result("1" * 64, "d" * 64, "deepseek-flash", "c" * 64) is None
    assert repository.find_cached_result("1" * 64, "b" * 64, "other", "c" * 64) is None
    assert repository.find_cached_result("1" * 64, "b" * 64, "deepseek-flash", "d" * 64) is None


def test_proposal_application_uses_revision_lock_and_applies_once(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    proposal = {"criteria": [{"name": "空间", "labels": ["宽敞", "局促"], "similar_terms": [], "basis": "空间评价", "evidence": []}]}
    repository.save_proposal(job["id"], proposal, source_review_count=3, sample_review_count=2)
    applied = repository.apply_proposal(job["id"], expected_revision=1)
    assert applied["revision"] == 2
    assert applied["criteria"] == [{"name": "空间", "labels": ["宽敞", "局促"]}]
    with pytest.raises(ValueError, match="已经应用"):
        repository.apply_proposal(job["id"], expected_revision=1)


def test_proposal_reports_deleted_source_snapshots(tmp_path):
    path = tmp_path / "proposal-source-status.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    assets = ReviewAssetRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    repository.save_proposal(
        job["id"],
        {
            "criteria": [
                {
                    "name": "空间",
                    "labels": ["宽敞", "局促"],
                    "similar_terms": [],
                    "basis": "空间评价",
                    "evidence": ["空间宽敞"],
                }
            ]
        },
        source_review_count=2,
        sample_review_count=2,
    )
    repository.set_job_state(job["id"], "completed")
    snapshot = repository.pending_review_snapshots(job["id"])[0]
    detail = assets.get_asset(snapshot["source_asset_id"])

    ReviewAssetService(assets).delete_asset(
        snapshot["source_asset_id"],
        DeleteAssetBody(
            expected_content_hash=detail["content_hash"],
            confirmed_review_id=detail["review_id"],
            reason="验证准则发现历史来源状态",
            confirm=True,
        ),
    )

    assert repository.get_proposal(job["id"])["source_deleted_count"] == 1


def test_proposal_rejects_schema_changed_after_discovery(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    proposal = {"criteria": [{"name": "空间", "labels": ["宽敞", "局促"], "similar_terms": [], "basis": "空间评价", "evidence": []}]}
    repository.save_proposal(job["id"], proposal, source_review_count=3, sample_review_count=2)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE schemas SET revision=2,criteria=? WHERE id='s1'", (json.dumps([{"name": "续航", "labels": ["充足", "不足"]}], ensure_ascii=False),))
        connection.commit()

    with pytest.raises(ValueError, match="revision 已变化"):
        repository.apply_proposal(job["id"], expected_revision=2)

    with sqlite3.connect(path) as connection:
        criteria = json.loads(connection.execute("SELECT criteria FROM schemas WHERE id='s1'").fetchone()[0])
    assert criteria == [{"name": "续航", "labels": ["充足", "不足"]}]


def test_cancel_paused_job_finishes_immediately(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    repository.set_job_state(job["id"], "paused")

    cancelled = repository.request_control(job["id"], "cancel")

    assert cancelled["status"] == "cancelled"
    assert cancelled["control_requested"] is None


def test_pause_queued_job_prevents_worker_claim(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)

    paused = repository.request_control(job["id"], "pause")

    assert paused["status"] == "paused"
    assert paused["control_requested"] is None
    assert not repository.claim_job(job["id"], "extracting")


def test_cancel_request_is_not_downgraded_by_later_pause(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    assert repository.claim_job(job["id"], "extracting")

    repository.request_control(job["id"], "cancel")
    repository.request_control(job["id"], "pause")

    assert repository.requested_control(job["id"]) == "cancel"
    assert repository.consume_control(job["id"]) == "cancel"
    assert repository.get_job(job["id"])["status"] == "cancelled"


def test_paused_job_can_still_be_cancelled(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    assert repository.claim_job(job["id"], "extracting")

    repository.request_control(job["id"], "pause")
    assert repository.consume_control(job["id"]) == "pause"
    assert repository.get_job(job["id"])["status"] == "paused"

    cancelled = repository.request_control(job["id"], "cancel")

    assert cancelled["status"] == "cancelled"
    assert cancelled["control_requested"] is None


@pytest.mark.parametrize(
    ("action", "expected"),
    [("pause", "paused"), ("cancel", "cancelled")],
)
def test_finish_job_honors_control_requested_during_last_call(
    tmp_path, action, expected
):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    assert repository.claim_job(job["id"], "extracting")
    repository.request_control(job["id"], action)

    finished = repository.finish_job(
        job["id"], "failed", error_code="internal", error_message="boom"
    )

    assert finished["status"] == expected
    assert finished["control_requested"] is None


def test_discovery_batch_progress_is_idempotent(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    job = repository.create_job_with_snapshot(command(), snapshots)
    rows = repository.pending_review_snapshots(job["id"])
    batch = repository.ensure_discovery_batches(job["id"], [rows])[0]
    completion = JsonCompletion({}, 10, 5, 15, 0, "stop")

    assert repository.save_discovery_batch(job["id"], batch["batch_index"], [], completion)
    assert not repository.save_discovery_batch(job["id"], batch["batch_index"], [], completion)
    updated = repository.get_job(job["id"])
    assert updated["processed_count"] == len(rows)
    assert updated["success_count"] == len(rows)
    assert updated["input_tokens"] == 10


def test_combined_criterion_and_label_filter_matches_same_annotation(tmp_path):
    path = tmp_path / "app.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    criteria = [
        CriterionSnapshot(name="空间", labels=["好", "差"]),
        CriterionSnapshot(name="续航", labels=["好", "差"]),
    ]
    job = repository.create_job_with_snapshot(
        command(
            job_type="review_annotation",
            criteria=criteria,
            schema_fingerprint=schema_fingerprint(criteria),
        ),
        snapshots,
    )
    row = repository.pending_review_snapshots(job["id"])[0]
    result = repository.save_result(
        content_hash=row["content_hash"],
        schema_fingerprint=job["schema_fingerprint"],
        model=job["model"],
        prompt_version="v1",
        prompt_sha256="a" * 64,
        result={
            "annotations": [
                {"criterion": "空间", "label": "好", "evidence": ["空间"], "basis": "依据"},
                {"criterion": "续航", "label": "差", "evidence": ["续航"], "basis": "依据"},
            ],
            "unmatched_evidence": [],
        },
        input_tokens=1,
        output_tokens=1,
        cached_tokens=0,
    )
    repository.mark_review_succeeded(
        job["id"], row["snapshot_id"], result["id"], cached=False
    )

    filtered = repository.list_annotations(
        "p1", job_id=job["id"], criterion="空间", label="差"
    )

    assert filtered["total"] == 0


def test_shared_cached_annotation_detail_uses_snapshot_identity(tmp_path):
    path = tmp_path / "annotation-detail.db"
    seed(path)
    repository = ReviewAnalysisRepository(path)
    criteria = [CriterionSnapshot(name="空间", labels=["好", "差"])]
    job = repository.create_job_with_snapshot(
        command(
            job_type="review_annotation",
            criteria=criteria,
            schema_fingerprint=schema_fingerprint(criteria),
        ),
        snapshots,
    )
    rows = repository.pending_review_snapshots(job["id"])
    result = repository.save_result(
        content_hash=rows[0]["content_hash"],
        schema_fingerprint=job["schema_fingerprint"],
        model=job["model"],
        prompt_version="v1",
        prompt_sha256="a" * 64,
        result={"annotations": [], "unmatched_evidence": []},
        input_tokens=1,
        output_tokens=1,
        cached_tokens=0,
    )
    for row in rows:
        repository.mark_review_succeeded(
            job["id"], row["snapshot_id"], result["id"], cached=True
        )

    selected = repository.get_annotation(
        "p1", result["id"], rows[1]["snapshot_id"]
    )

    assert selected["snapshot_id"] == rows[1]["snapshot_id"]
    assert selected["review_id"] == rows[1]["review_id"]
    assert selected["analysis_text"] == rows[1]["analysis_text"]
