import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.review_analysis.api import create_review_analysis_router
from backend.review_analysis.config import DeepSeekSettings
from backend.review_analysis.repository import ReviewAnalysisRepository


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
      INSERT INTO projects VALUES ('p','项目','custom','now');
      INSERT INTO projects VALUES ('other','其他项目','custom','now');
      INSERT INTO schemas VALUES ('draft','p',1,'draft',1,'[{"name":"空间","labels":["宽敞","局促"]}]','now');
      INSERT INTO schemas VALUES ('frozen','p',2,'frozen',2,'[{"name":"空间","labels":["宽敞","局促"]}]','now');
      INSERT INTO vehicle_series VALUES ('autohome','1','车系一','https://a','https://a',1,'now','now');
    """)
    connection.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?)", ('autohome','r1','1','车系一','https://x',json.dumps({'feeling_summary':'后排宽敞'},ensure_ascii=False),'1'*64,'now','now'))
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


def test_job_mutations_are_scoped_to_project(tmp_path):
    client, _, _ = client_for(tmp_path)
    created = client.post(
        '/api/projects/p/review-analysis/discovery-jobs',
        json={'schema_id':'draft','selected_series_ids':['1'],'sample_limit':10},
    ).json()

    assert client.get(f"/api/projects/other/review-analysis/jobs/{created['id']}").status_code == 404
    assert client.post(f"/api/projects/other/review-analysis/jobs/{created['id']}/cancel").status_code == 404
    assert client.get(f"/api/projects/other/review-analysis/jobs/{created['id']}/proposal").status_code == 404
