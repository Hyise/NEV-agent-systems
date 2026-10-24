import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.review_analysis.api import AnnotationBody, create_review_analysis_router
from backend.review_analysis.config import DeepSeekSettings
from backend.review_analysis.repository import ReviewAnalysisRepository
from backend.sales_collection.repository import SalesCollectionRepository


class Service:
    def __init__(self): self.started = []; self.actions = []
    def start(self, job_id): self.started.append(job_id)
    def pause(self, job_id): self.actions.append((job_id, "pause"))
    def resume(self, job_id): self.actions.append((job_id, "resume"))
    def cancel(self, job_id): self.actions.append((job_id, "cancel"))
    def retry_failures(self, job_id): return {"id": "retry"}


def client_for(tmp_path, *, configured=True):
    path = tmp_path / "app.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
      CREATE TABLE projects (id TEXT PRIMARY KEY,name TEXT,mode TEXT,created_at TEXT);
      CREATE TABLE schemas (id TEXT PRIMARY KEY,project_id TEXT,version INTEGER,status TEXT,revision INTEGER,criteria TEXT,created_at TEXT);
      CREATE TABLE vehicle_series (platform TEXT,series_id TEXT,series_name TEXT,series_url TEXT,review_url TEXT,discovery_rank INTEGER,first_discovered_at TEXT,last_confirmed_at TEXT,PRIMARY KEY(platform,series_id));
      CREATE TABLE reviews (platform TEXT,review_id TEXT,series_id TEXT,series_name_snapshot TEXT,source_url TEXT,original_review_json TEXT,content_hash TEXT,first_collected_at TEXT,last_confirmed_at TEXT,PRIMARY KEY(platform,review_id));
      CREATE TABLE datasets (id TEXT PRIMARY KEY,project_id TEXT,schema_id TEXT,name TEXT,sha256 TEXT,records TEXT,created_at TEXT);
      INSERT INTO projects VALUES ('p','项目','custom','now');
      INSERT INTO projects VALUES ('other','其他项目','custom','now');
      INSERT INTO schemas VALUES ('draft','p',1,'draft',1,'[{"name":"空间","labels":["宽敞","局促"]}]','now');
      INSERT INTO schemas VALUES ('frozen','p',2,'frozen',2,'[{"name":"空间","labels":["宽敞","局促"]}]','now');
      INSERT INTO vehicle_series VALUES ('autohome','1','车系一','https://a','https://a',1,'now','now');
    """)
    connection.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?)", ('autohome','r1','1','车系一','https://x',json.dumps({'posttime':'2026-01-05','feeling_summary':'后排宽敞'},ensure_ascii=False),'1'*64,'now','now'))
    connection.commit(); connection.close()
    repo = ReviewAnalysisRepository(path); service = Service()
    settings = DeepSeekSettings.from_environ({'DEEPSEEK_API_KEY':'fake'}) if configured else None
    app = FastAPI(); app.include_router(create_review_analysis_router(repo, service, settings))
    return TestClient(app), repo, service


def add_frozen_schema(repo, schema_id, version, criteria=None):
    criteria = criteria or [{"name": "空间", "labels": ["宽敞", "局促"]}]
    with repo.connect() as connection:
        connection.execute(
            "INSERT INTO schemas VALUES (?,?,?,?,?,?,?)",
            (schema_id, "p", version, "frozen", 1, json.dumps(criteria, ensure_ascii=False), "now"),
        )


def complete_single_annotation(client, repo, schema_id="frozen"):
    created = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={"schema_id": schema_id, "selected_series_ids": ["1"], "limit": 1},
    ).json()
    job = repo.get_job(created["id"])
    snapshot = repo.pending_review_snapshots(job["id"])[0]
    result = repo.save_result(
        content_hash=snapshot["content_hash"],
        schema_fingerprint=job["schema_fingerprint"],
        model=job["model"],
        prompt_version=job["prompt_manifests"][0]["version"],
        prompt_sha256=job["prompt_manifests"][0]["sha256"],
        result={
            "annotations": [
                {
                    "criterion": "空间",
                    "label": "宽敞",
                    "evidence": ["后排宽敞"],
                    "basis": "原文明确描述空间",
                }
            ],
            "unmatched_evidence": [],
        },
        input_tokens=10,
        output_tokens=5,
        cached_tokens=0,
    )
    repo.mark_review_succeeded(
        job["id"], snapshot["snapshot_id"], result["id"], cached=False
    )
    repo.set_job_state(job["id"], "completed")
    return repo.get_job(job["id"])


def complete_two_series_annotation(client, repo, schema_id="frozen"):
    timestamp = "2026-10-23T00:00:00+00:00"
    with repo.connect() as connection:
        connection.execute(
            "INSERT INTO vehicle_series VALUES (?,?,?,?,?,?,?,?)",
            ("autohome", "2", "车系二", "https://b", "https://b", 2, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO reviews (
                platform,review_id,series_id,series_name_snapshot,source_url,
                original_review_json,content_hash,first_collected_at,last_confirmed_at,
                asset_id,source_kind
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "autohome",
                "r2",
                "2",
                "车系二",
                "https://y",
                json.dumps(
                    {"posttime": "2026-01-06", "feeling_summary": "车内空间宽敞"},
                    ensure_ascii=False,
                ),
                "2" * 64,
                timestamp,
                timestamp,
                "autohome:r2",
                "crawler",
            ),
        )
        connection.execute(
            "INSERT INTO review_asset_metadata VALUES (?,?,?,?,?,?,?)",
            ("autohome:r2", 1, "[]", "", 1, timestamp, timestamp),
        )
    created = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={
            "schema_id": schema_id,
            "selected_series_ids": ["1", "2"],
            "limit": 2,
        },
    ).json()
    job = repo.get_job(created["id"])
    for snapshot in repo.pending_review_snapshots(job["id"]):
        result = repo.save_result(
            content_hash=snapshot["content_hash"],
            schema_fingerprint=job["schema_fingerprint"],
            model=job["model"],
            prompt_version=job["prompt_manifests"][0]["version"],
            prompt_sha256=job["prompt_manifests"][0]["sha256"],
            result={
                "annotations": [
                    {
                        "criterion": "空间",
                        "label": "宽敞",
                        "evidence": ["空间宽敞"],
                        "basis": "评论明确描述空间",
                    }
                ],
                "unmatched_evidence": [],
            },
            input_tokens=10,
            output_tokens=5,
            cached_tokens=0,
        )
        repo.mark_review_succeeded(
            job["id"], snapshot["snapshot_id"], result["id"], cached=False
        )
    repo.set_job_state(job["id"], "completed")
    return repo.get_job(job["id"])


def add_matching_sales(repo):
    SalesCollectionRepository(repo.path)
    with repo.connect() as connection:
        connection.execute(
            "INSERT INTO sales_collection_jobs (id,start_month,end_month,platforms_json,status,total_steps,created_at,updated_at) VALUES ('sales-handoff','2026-01','2026-01','[\"autohome\"]','completed',1,'now','now')"
        )
        connection.execute(
            "INSERT INTO sales_records VALUES ('autohome','2026-01','platform-handoff','车系一',120,1,'retail','https://sales','hash-handoff','now','sales-handoff')"
        )
        connection.execute(
            "INSERT INTO sales_series_matches VALUES ('autohome','2026-01','platform-handoff','1','车系一','normalized_exact','matched','now')"
        )


def test_sources_and_missing_key_degradation(tmp_path):
    client, repo, service = client_for(tmp_path, configured=False)
    assert client.get('/api/projects/p/review-analysis/sources').json()['total'] == 1
    response = client.post('/api/projects/p/review-analysis/discovery-jobs', json={'schema_id':'draft','selected_series_ids':['1'],'sample_limit':10})
    assert response.status_code == 503
    assert repo.list_jobs('p')['total'] == 0


def test_jobs_endpoint_filters_history_to_the_current_schema(tmp_path):
    client, repo, _ = client_for(tmp_path)
    add_frozen_schema(repo, "same", 3)
    old = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={"schema_id": "frozen", "selected_series_ids": ["1"], "limit": 1},
    ).json()
    repo.set_job_state(old["id"], "completed")
    current = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={"schema_id": "same", "selected_series_ids": ["1"], "limit": 1},
    ).json()

    response = client.get(
        "/api/projects/p/review-analysis/jobs", params={"schema_id": "same"}
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["rows"]] == [current["id"]]


def test_handoff_exposes_compatible_annotation_without_hiding_blockers(tmp_path):
    client, repo, _ = client_for(tmp_path)
    add_frozen_schema(repo, "same", 3)
    job = complete_single_annotation(client, repo)

    response = client.get(
        "/api/projects/p/review-analysis/handoff", params={"schema_id": "same"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "blocked"
    assert body["compatibility"] == "fingerprint"
    assert body["job"]["id"] == job["id"]
    assert body["job"]["source_schema_id"] == "frozen"
    assert body["job"]["source_schema_version"] == 2
    assert body["target_schema_version"] == 3
    assert body["matrix"]["stats"] == {
        "source_reviews": 1,
        "groups": 1,
        "records": 0,
        "blocked_groups": 1,
        "missing_date_reviews": 0,
        "unmentioned_criterion_groups": 0,
    }
    assert body["matrix"]["blocker_counts"] == {"missing_sales": 1}


def test_handoff_rejects_incompatible_cross_version_materialization(tmp_path):
    client, repo, _ = client_for(tmp_path)
    add_frozen_schema(
        repo,
        "different",
        3,
        [{"name": "驾驶", "labels": ["稳定", "松散"]}],
    )
    job = complete_single_annotation(client, repo)
    add_matching_sales(repo)

    handoff = client.get(
        "/api/projects/p/review-analysis/handoff",
        params={"schema_id": "different"},
    )
    materialized = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={"target_schema_id": "different"},
    )

    assert handoff.status_code == 200
    assert handoff.json()["state"] == "no_job"
    assert materialized.status_code == 409
    assert "准则内容不一致" in materialized.text


def test_compatible_materialization_targets_current_schema_and_records_lineage(tmp_path):
    client, repo, _ = client_for(tmp_path)
    add_frozen_schema(repo, "same", 3)
    job = complete_single_annotation(client, repo)
    add_matching_sales(repo)

    response = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={"target_schema_id": "same"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["schema_id"] == "same"
    assert response.json()["source_schema_id"] == "frozen"
    with repo.connect() as connection:
        dataset = connection.execute(
            "SELECT id,schema_id FROM datasets WHERE project_id='p'"
        ).fetchone()
        lineage = connection.execute(
            "SELECT * FROM review_matrix_dataset_lineage WHERE dataset_id=?",
            (dataset["id"],),
        ).fetchone()
    assert dataset["schema_id"] == "same"
    assert lineage["source_job_id"] == job["id"]
    assert lineage["source_schema_id"] == "frozen"
    assert lineage["target_schema_id"] == "same"


def test_materialization_preserves_an_existing_authoritative_dataset(tmp_path):
    client, repo, _ = client_for(tmp_path)
    job = complete_single_annotation(client, repo)
    add_matching_sales(repo)
    with repo.connect() as connection:
        connection.execute(
            "INSERT INTO datasets VALUES (?,?,?,?,?,?,?)",
            (
                "manual-dataset",
                "p",
                "frozen",
                "人工导入矩阵",
                "f" * 64,
                '[{"month":"2026-01","model":"人工车型"}]',
                "2026-10-23T00:00:00+00:00",
            ),
        )

    response = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={"target_schema_id": "frozen"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["id"] == "manual-dataset"
    with repo.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM datasets WHERE project_id='p' AND schema_id='frozen'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM review_matrix_dataset_lineage"
        ).fetchone()[0] == 0


def test_handoff_uses_only_frozen_predecessor_schemas(tmp_path):
    client, repo, _ = client_for(tmp_path)
    add_frozen_schema(repo, "future", 4)
    future_job = complete_single_annotation(client, repo, "future")

    older = client.get(
        "/api/projects/p/review-analysis/handoff", params={"schema_id": "frozen"}
    )
    with repo.connect() as connection:
        connection.execute("UPDATE schemas SET status='draft' WHERE id='future'")
    draft = client.get(
        "/api/projects/p/review-analysis/handoff", params={"schema_id": "future"}
    )

    assert future_job["schema_id"] == "future"
    assert older.status_code == 200
    assert older.json()["state"] == "no_job"
    assert draft.status_code == 200
    assert draft.json()["state"] == "not_frozen"
    assert draft.json()["job"] is None


def test_handoff_prefers_usable_exact_job_over_newer_terminal_failure(tmp_path):
    client, repo, _ = client_for(tmp_path)
    usable = complete_single_annotation(client, repo)
    failed = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={"schema_id": "frozen", "selected_series_ids": ["1"], "limit": 1},
    ).json()
    repo.set_job_state(
        failed["id"],
        "failed",
        error_code="LLM_ERROR",
        error_message="boom",
    )
    add_matching_sales(repo)

    response = client.get(
        "/api/projects/p/review-analysis/handoff", params={"schema_id": "frozen"}
    )

    assert response.status_code == 200
    assert response.json()["state"] == "ready"
    assert response.json()["job"]["id"] == usable["id"]


def test_explicit_missing_sales_exclusion_persists_an_auditable_snapshot(tmp_path):
    client, repo, _ = client_for(tmp_path)
    job = complete_two_series_annotation(client, repo)
    add_matching_sales(repo)

    strict = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={"target_schema_id": "frozen"},
    )
    excluded = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={
            "target_schema_id": "frozen",
            "exclusion_policy": "exclude_missing_sales",
        },
    )
    repeated = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={
            "target_schema_id": "frozen",
            "exclusion_policy": "exclude_missing_sales",
        },
    )

    assert strict.status_code == 409
    assert excluded.status_code == 201, excluded.text
    assert excluded.json()["included_count"] == 1
    assert excluded.json()["excluded_count"] == 1
    assert excluded.json()["source_group_count"] == 2
    assert excluded.json()["coverage_rate"] == 0.5
    assert excluded.json()["exclusions"] == [
        {
            "month": "2026-01",
            "series_id": "2",
            "series_name": "车系二",
            "issues": [{"code": "missing_sales", "message": "没有匹配到销量"}],
        }
    ]
    assert repeated.json() == excluded.json()
    with repo.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM datasets WHERE project_id='p' AND schema_id='frozen'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM review_matrix_dataset_exclusions"
        ).fetchone()[0] == 1


def test_missing_sales_exclusion_rejects_mixed_or_empty_snapshots(tmp_path):
    client, repo, _ = client_for(tmp_path)
    job = complete_single_annotation(client, repo)

    empty = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={"exclusion_policy": "exclude_missing_sales"},
    )
    with repo.connect() as connection:
        connection.execute(
            "UPDATE review_analysis_job_reviews SET review_date='2025-12-05' WHERE job_id=?",
            (job["id"],),
        )
    mixed = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets",
        json={"exclusion_policy": "exclude_missing_sales"},
    )

    assert empty.status_code == 409
    assert "没有可保存" in empty.text
    assert mixed.status_code == 409
    assert "不可排除" in mixed.text


def test_sources_endpoint_aggregates_manual_and_autohome_by_series(tmp_path):
    client, repo, _ = client_for(tmp_path, configured=False)
    timestamp = "2026-10-14T08:00:00+00:00"
    with repo.connect() as connection:
        connection.execute(
            "INSERT INTO vehicle_series VALUES ('manual','1','车系一','','',1000000,?,?)",
            (timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO reviews (
                platform,review_id,series_id,series_name_snapshot,source_url,
                original_review_json,content_hash,first_collected_at,
                last_confirmed_at,asset_id,source_kind
            ) VALUES ('manual','m1','1','车系一','',?,?,?, ?,
                      'manual:m1','manual_import')
            """,
            (
                json.dumps({"feeling_summary": "人工评论"}, ensure_ascii=False),
                "2" * 64,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO review_asset_metadata VALUES "
            "('manual:m1',1,'[]','',1,?,?)",
            (timestamp, timestamp),
        )

    response = client.get('/api/projects/p/review-analysis/sources')

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["rows"][0]["review_count"] == 2


def test_discovery_requires_draft_and_annotation_requires_frozen(tmp_path):
    client, repo, service = client_for(tmp_path)
    wrong = client.post('/api/projects/p/review-analysis/discovery-jobs', json={'schema_id':'frozen','selected_series_ids':['1'],'sample_limit':10})
    assert wrong.status_code == 409
    created = client.post('/api/projects/p/review-analysis/discovery-jobs', json={'schema_id':'draft','selected_series_ids':['1'],'sample_limit':10})
    assert created.status_code == 201 and service.started


def test_duplicate_selection_is_422(tmp_path):
    client, _, _ = client_for(tmp_path)
    response = client.post('/api/projects/p/review-analysis/discovery-jobs', json={'schema_id':'draft','selected_series_ids':['1','1'],'sample_limit':10})
    assert response.status_code == 422


def test_annotation_date_range_is_validated_and_persisted(tmp_path):
    client, repo, service = client_for(tmp_path)
    timestamp = "2026-10-14T08:00:00+00:00"
    with repo.connect() as connection:
        for review_id, posttime, content_hash in (
            ("jan", "2026-01-05", "2" * 64),
            ("feb", "2026-02-05", "3" * 64),
            ("may", "2026-05-05", "4" * 64),
        ):
            connection.execute(
                """
                INSERT INTO reviews (
                    platform,review_id,series_id,series_name_snapshot,source_url,
                    original_review_json,content_hash,first_collected_at,
                    last_confirmed_at,asset_id,source_kind
                ) VALUES ('manual',?,'1','车系一','',?,?,?, ?,?,
                          'manual_import')
                """,
                (
                    review_id,
                    json.dumps(
                        {"posttime": posttime, "feeling_summary": f"{posttime} 评论"},
                        ensure_ascii=False,
                    ),
                    content_hash,
                    timestamp,
                    timestamp,
                    f"manual:{review_id}",
                ),
            )
            connection.execute(
                "INSERT INTO review_asset_metadata VALUES (?,?, '[]','',1,?,?)",
                (f"manual:{review_id}", 1, timestamp, timestamp),
            )

    invalid = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={
            "schema_id": "frozen",
            "selected_series_ids": ["1"],
            "limit": 2,
            "review_date_from": "2026-04-30",
            "review_date_to": "2026-01-01",
            "sampling": "month_series",
        },
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={
            "schema_id": "frozen",
            "selected_series_ids": ["1"],
            "limit": 2,
            "review_date_from": "2026-01-01",
            "review_date_to": "2026-02-28",
            "sampling": "month_series",
        },
    )

    assert created.status_code == 201
    job = repo.get_job(created.json()["id"])
    assert job["total_count"] == 2
    assert job["source_config"] == {
        "selected_series_ids": ["1"],
        "limit": 2,
        "review_date_from": "2026-01-01",
        "review_date_to": "2026-02-28",
        "sampling": "month-series-sha256-round-robin",
    }
    snapshots = repo.pending_review_snapshots(job["id"])
    assert {row["review_id"] for row in snapshots} == {"jan", "feb"}
    assert {row["review_date"] for row in snapshots} == {
        "2026-01-05",
        "2026-02-05",
    }
    assert service.started == [job["id"]]


def test_annotation_rejects_nonexistent_calendar_date():
    with pytest.raises(ValidationError, match="无效日期"):
        AnnotationBody(
            schema_id="frozen",
            selected_series_ids=["1"],
            review_date_from="2026-02-31",
        )


def test_completed_annotation_can_preview_and_materialize_dataset(tmp_path):
    client, repo, _ = client_for(tmp_path)
    SalesCollectionRepository(repo.path)
    created = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={"schema_id": "frozen", "selected_series_ids": ["1"], "limit": 1},
    ).json()
    job = repo.get_job(created["id"])
    snapshot = repo.pending_review_snapshots(job["id"])[0]
    result = repo.save_result(
        content_hash=snapshot["content_hash"],
        schema_fingerprint=job["schema_fingerprint"],
        model=job["model"],
        prompt_version=job["prompt_manifests"][0]["version"],
        prompt_sha256=job["prompt_manifests"][0]["sha256"],
        result={
            "annotations": [
                {
                    "criterion": "空间",
                    "label": "宽敞",
                    "evidence": ["后排宽敞"],
                    "basis": "原文明确描述空间",
                }
            ],
            "unmatched_evidence": [],
        },
        input_tokens=10,
        output_tokens=5,
        cached_tokens=0,
    )
    repo.mark_review_succeeded(
        job["id"], snapshot["snapshot_id"], result["id"], cached=False
    )
    repo.set_job_state(job["id"], "completed")
    with repo.connect() as connection:
        connection.execute(
            "INSERT INTO sales_collection_jobs (id,start_month,end_month,platforms_json,status,total_steps,created_at,updated_at) VALUES ('sales','2026-01','2026-01','[\"autohome\"]','completed',1,'now','now')"
        )
        connection.execute(
            "INSERT INTO sales_records VALUES ('autohome','2026-01','platform-1','车系一',120,1,'retail','https://sales','hash','now','sales')"
        )
        connection.execute(
            "INSERT INTO sales_series_matches VALUES ('autohome','2026-01','platform-1','1','车系一','normalized_exact','matched','now')"
        )

    preview = client.get(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/matrix-preview"
    )
    assert preview.status_code == 200
    assert preview.json()["stats"]["records"] == 1
    assert preview.json()["blockers"] == []

    materialized = client.post(
        f"/api/projects/p/review-analysis/jobs/{job['id']}/datasets"
    )
    assert materialized.status_code == 201, materialized.text
    assert materialized.json()["records"] == 1
    with repo.connect() as connection:
        stored = connection.execute(
            "SELECT project_id,schema_id,name,records FROM datasets"
        ).fetchone()
    assert stored["project_id"] == "p"
    assert stored["schema_id"] == "frozen"
    assert json.loads(stored["records"])[0]["model"] == "车系一"


def test_partial_failure_must_be_retried_before_materializing_dataset(tmp_path):
    client, repo, _ = client_for(tmp_path)
    created = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={"schema_id": "frozen", "selected_series_ids": ["1"], "limit": 1},
    ).json()
    snapshot = repo.pending_review_snapshots(created["id"])[0]
    repo.mark_review_failed(created["id"], snapshot["snapshot_id"], "x", "x")
    repo.set_job_state(created["id"], "partial_failed")

    response = client.post(
        f"/api/projects/p/review-analysis/jobs/{created['id']}/datasets"
    )

    assert response.status_code == 409
    assert "失败评论" in response.text


def test_retry_job_preview_uses_the_whole_root_job_family(tmp_path):
    client, repo, _ = client_for(tmp_path)
    SalesCollectionRepository(repo.path)
    with repo.connect() as connection:
        connection.execute(
            """
            INSERT INTO reviews (
                platform,review_id,series_id,series_name_snapshot,source_url,
                original_review_json,content_hash,first_collected_at,last_confirmed_at,
                asset_id,source_kind
            ) VALUES ('manual','r2','1','车系一','',?,?,'now','now','manual:r2','manual_import')
            """,
            (
                json.dumps(
                    {"posttime": "2026-01-06", "feeling_summary": "空间也很宽敞"},
                    ensure_ascii=False,
                ),
                "2" * 64,
            ),
        )
        connection.execute(
            "INSERT INTO review_asset_metadata VALUES ('manual:r2',1,'[]','',1,'now','now')"
        )
    root = client.post(
        "/api/projects/p/review-analysis/annotation-jobs",
        json={"schema_id": "frozen", "selected_series_ids": ["1"], "limit": 2},
    ).json()
    root_job = repo.get_job(root["id"])
    snapshots = {row["review_id"]: row for row in repo.pending_review_snapshots(root["id"])}

    def save_success(job, snapshot):
        result = repo.save_result(
            content_hash=snapshot["content_hash"],
            schema_fingerprint=job["schema_fingerprint"],
            model=job["model"],
            prompt_version=job["prompt_manifests"][0]["version"],
            prompt_sha256=job["prompt_manifests"][0]["sha256"],
            result={
                "annotations": [
                    {
                        "criterion": "空间",
                        "label": "宽敞",
                        "evidence": ["宽敞"],
                        "basis": "评论明确描述空间",
                    }
                ],
                "unmatched_evidence": [],
            },
            input_tokens=1,
            output_tokens=1,
            cached_tokens=0,
        )
        repo.mark_review_succeeded(
            job["id"], snapshot["snapshot_id"], result["id"], cached=False
        )

    save_success(root_job, snapshots["r1"])
    repo.mark_review_failed(root["id"], snapshots["r2"]["snapshot_id"], "x", "x")
    repo.set_job_state(root["id"], "partial_failed")
    retry = repo.create_retry_job(root["id"])
    retry_snapshot = repo.pending_review_snapshots(retry["id"])[0]
    save_success(retry, retry_snapshot)
    repo.set_job_state(retry["id"], "completed")
    with repo.connect() as connection:
        connection.execute(
            "INSERT INTO sales_collection_jobs (id,start_month,end_month,platforms_json,status,total_steps,created_at,updated_at) VALUES ('sales-family','2026-01','2026-01','[\"autohome\"]','completed',1,'now','now')"
        )
        connection.execute(
            "INSERT INTO sales_records VALUES ('autohome','2026-01','platform-1','车系一',120,1,'retail','https://sales','hash','now','sales-family')"
        )
        connection.execute(
            "INSERT INTO sales_series_matches VALUES ('autohome','2026-01','platform-1','1','车系一','normalized_exact','matched','now')"
        )

    preview = client.get(
        f"/api/projects/p/review-analysis/jobs/{retry['id']}/matrix-preview"
    )

    assert preview.status_code == 200
    assert preview.json()["stats"]["source_reviews"] == 2
    assert preview.json()["stats"]["records"] == 1
    annotations = client.get(
        "/api/projects/p/review-analysis/annotations",
        params={"job_id": retry["id"]},
    ).json()
    assert annotations["total"] == 2
    assert {row["status"] for row in annotations["rows"]} == {"succeeded"}
    summary = client.get(
        "/api/projects/p/review-analysis/summary",
        params={"job_id": retry["id"]},
    ).json()
    assert summary["annotated_reviews"] == 2


def test_job_mutations_are_scoped_to_project(tmp_path):
    client, _, _ = client_for(tmp_path)
    created = client.post(
        '/api/projects/p/review-analysis/discovery-jobs',
        json={'schema_id':'draft','selected_series_ids':['1'],'sample_limit':10},
    ).json()

    assert client.get(f"/api/projects/other/review-analysis/jobs/{created['id']}").status_code == 404
    assert client.post(f"/api/projects/other/review-analysis/jobs/{created['id']}/cancel").status_code == 404
    assert client.get(f"/api/projects/other/review-analysis/jobs/{created['id']}/proposal").status_code == 404
