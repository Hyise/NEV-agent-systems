import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.model_experiments.dataset import DatasetSnapshot
from backend.model_experiments.repository import ModelExperimentRepository


def wait_for_terminal(client, path):
    for _ in range(100):
        run = client.get(path).json()
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.02)
    raise AssertionError("模型实验未在测试时限内结束")


def database_path(name):
    return Path(".runtime/tests") / f"{name}-{uuid4().hex}.sqlite3"


def test_capabilities_create_run_and_persist_result():
    database = database_path("models")
    base = "/api/projects/research-archive/model-experiments"
    with TestClient(create_app(database, ROOT / "backend/data/research")) as client:
        capabilities = client.get(base + "/capabilities")
        assert capabilities.status_code == 200
        assert {item["key"] for item in capabilities.json()} == {
            "ridge",
            "random_forest",
            "xgboost",
            "lightgbm",
            "beast_mcdm",
        }
        response = client.post(
            base,
            json={
                "schema_id": "preset-v1",
                "model_keys": ["ridge"],
                "validation_months": 2,
                "test_months": 2,
                "seed": 19,
                "simulations": 64,
            },
        )
        assert response.status_code == 201, response.text
        run_id = response.json()["id"]
        completed = wait_for_terminal(client, base + "/" + run_id)
        assert completed["status"] == "completed", completed
        assert completed["progress"] == 1.0
        assert completed["result"]["split"]["test"] == ["2025-11", "2025-12"]
        assert completed["result"]["models"][0]["key"] == "ridge"
        assert completed["dataset"]["records"] == 1609
        assert len(completed["dataset"]["snapshot_sha256"]) == 64
        assert completed["result"]["models"][0]["predictions"]

        listed = client.get(base).json()["rows"][0]
        assert listed["result"]["models"][0]["predictions"] == []

    with TestClient(create_app(database, ROOT / "backend/data/research")) as restarted:
        rows = restarted.get(base).json()["rows"]
        assert rows[0]["id"] == run_id
        assert rows[0]["status"] == "completed"


def test_model_run_rejects_draft_and_unknown_or_unavailable_model():
    with TestClient(
        create_app(database_path("guard"), ROOT / "backend/data/research")
    ) as client:
        project = client.post(
            "/api/projects", json={"name": "草稿", "mode": "custom"}
        ).json()
        schema = client.get(f"/api/projects/{project['id']}/schemas").json()[0]
        base = f"/api/projects/{project['id']}/model-experiments"
        draft = client.post(
            base, json={"schema_id": schema["id"], "model_keys": ["ridge"]}
        )
        assert draft.status_code == 409
        unknown = client.post(
            "/api/projects/research-archive/model-experiments",
            json={"schema_id": "preset-v1", "model_keys": ["not-a-model"]},
        )
        assert unknown.status_code == 422


def test_run_list_is_filtered_by_schema_before_pagination():
    database = database_path("schema-filter")
    repository = ModelExperimentRepository(database)
    for index, schema_id in enumerate(("preset-v1", "preset-v2"), start=1):
        run = repository.create(
            "research-archive",
            schema_id,
            DatasetSnapshot(
                records=(),
                criteria=(),
                levels=(),
                source={"id": f"dataset-{index}"},
                sha256=str(index) * 64,
            ),
            {"model_keys": []},
        )
        repository.finish(run["id"], "completed", result={"models": []})

    with TestClient(create_app(database, ROOT / "backend/data/research")) as client:
        response = client.get(
            "/api/projects/research-archive/model-experiments",
            params={"schema_id": "preset-v1", "page_size": 1},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [row["schema_id"] for row in body["rows"]] == ["preset-v1"]
