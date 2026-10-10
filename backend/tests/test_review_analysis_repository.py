import json
import sqlite3
from pathlib import Path

import pytest

from backend.review_analysis.domain import (
    CreateJobCommand,
    PromptManifest,
    ReviewSnapshot,
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
            review_id=item.review_id,
            series_id=item.series_id,
            series_name=item.series_name,
            content_hash=item.content_hash,
            analysis_text=extract_analysis_text(item.original_review),
            ordinal=index,
        )
        for index, item in enumerate(stable_stratified_sample(assets, 2))
    ]


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
