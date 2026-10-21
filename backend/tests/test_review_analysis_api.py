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


def test_sources_and_missing_key_degradation(tmp_path):
    client, repo, service = client_for(tmp_path, configured=False)
    assert client.get('/api/projects/p/review-analysis/sources').json()['total'] == 1
    response = client.post('/api/projects/p/review-analysis/discovery-jobs', json={'schema_id':'draft','selected_series_ids':['1'],'sample_limit':10})
    assert response.status_code == 503
    assert repo.list_jobs('p')['total'] == 0


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
