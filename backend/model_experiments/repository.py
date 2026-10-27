from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .dataset import DatasetSnapshot


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class ModelExperimentRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS model_experiment_snapshots (
                    sha256 TEXT PRIMARY KEY, source_json TEXT NOT NULL,
                    criteria_json TEXT NOT NULL, levels_json TEXT NOT NULL,
                    records_json TEXT NOT NULL, record_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_experiment_runs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    schema_id TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL
                        REFERENCES model_experiment_snapshots(sha256),
                    status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
                    current_model TEXT, config_json TEXT NOT NULL,
                    result_json TEXT, error_message TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, started_at TEXT,
                    updated_at TEXT NOT NULL, finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_model_experiment_project
                    ON model_experiment_runs(project_id,created_at);
                """
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _run(row):
        if row is None:
            return None
        value = dict(row)
        value["config"] = json.loads(value.pop("config_json"))
        value["result"] = (
            json.loads(value.pop("result_json")) if value["result_json"] else None
        )
        value.pop("result_json", None)
        value["cancel_requested"] = bool(value["cancel_requested"])
        return value

    def create(
        self, project_id: str, schema_id: str, snapshot: DatasetSnapshot, config: dict
    ):
        timestamp, run_id = _now(), uuid4().hex
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                "SELECT 1 FROM model_experiment_runs WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone()
            if active:
                raise ValueError("已有模型实验正在排队或运行")
            connection.execute(
                """INSERT OR IGNORE INTO model_experiment_snapshots
                   (sha256,source_json,criteria_json,levels_json,records_json,record_count,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    snapshot.sha256,
                    _json(snapshot.source),
                    _json(snapshot.criteria),
                    _json(snapshot.levels),
                    _json(snapshot.records),
                    len(snapshot.records),
                    timestamp,
                ),
            )
            connection.execute(
                """INSERT INTO model_experiment_runs
                   (id,project_id,schema_id,snapshot_sha256,status,config_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    project_id,
                    schema_id,
                    snapshot.sha256,
                    "queued",
                    _json(config),
                    timestamp,
                    timestamp,
                ),
            )
        return self.get(run_id)

    def get(self, run_id: str):
        with self.connect() as connection:
            row = connection.execute(
                """SELECT r.*,s.source_json,s.record_count
                   FROM model_experiment_runs r JOIN model_experiment_snapshots s
                     ON s.sha256=r.snapshot_sha256 WHERE r.id=?""",
                (run_id,),
            ).fetchone()
        value = self._run(row)
        if value:
            value["dataset"] = {
                "snapshot_sha256": value["snapshot_sha256"],
                "records": value.pop("record_count"),
                "source": json.loads(value.pop("source_json")),
            }
        return value

    def snapshot(self, sha256: str):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM model_experiment_snapshots WHERE sha256=?", (sha256,)
            ).fetchone()
        if row is None:
            raise KeyError(sha256)
        return DatasetSnapshot(
            tuple(json.loads(row["records_json"])),
            tuple(json.loads(row["criteria_json"])),
            tuple(json.loads(row["levels_json"])),
            json.loads(row["source_json"]),
            row["sha256"],
        )

    def list(
        self,
        project_id: str,
        page=1,
        page_size=20,
        schema_id: str | None = None,
    ):
        where = "WHERE project_id=?"
        filter_params: tuple[str, ...] = (project_id,)
        if schema_id is not None:
            where += " AND schema_id=?"
            filter_params += (schema_id,)
        with self.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM model_experiment_runs {where}",
                filter_params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT r.*,s.source_json,s.record_count
                   FROM model_experiment_runs r JOIN model_experiment_snapshots s
                     ON s.sha256=r.snapshot_sha256
                   {where.replace('project_id', 'r.project_id').replace('schema_id', 'r.schema_id')}
                   ORDER BY r.created_at DESC LIMIT ? OFFSET ?""",
                (*filter_params, page_size, (page - 1) * page_size),
            ).fetchall()
        values = []
        for row in rows:
            value = self._run(row)
            if value["result"]:
                for model in value["result"].get("models", []):
                    model["predictions"] = []
            value["dataset"] = {
                "snapshot_sha256": value["snapshot_sha256"],
                "records": value.pop("record_count"),
                "source": json.loads(value.pop("source_json")),
            }
            values.append(value)
        return {"rows": values, "total": total, "page": page, "page_size": page_size}

    def claim(self, run_id: str):
        timestamp = _now()
        with self.connect() as connection:
            count = connection.execute(
                """UPDATE model_experiment_runs SET status='running',started_at=?,updated_at=?
                   WHERE id=? AND status='queued'""",
                (timestamp, timestamp, run_id),
            ).rowcount
        return bool(count)

    def progress(self, run_id: str, progress: float, current_model: str | None):
        with self.connect() as connection:
            connection.execute(
                "UPDATE model_experiment_runs SET progress=?,current_model=?,updated_at=? WHERE id=? AND status='running'",
                (max(0.0, min(1.0, progress)), current_model, _now(), run_id),
            )

    def finish(self, run_id: str, status: str, result=None, error_message=None):
        timestamp = _now()
        with self.connect() as connection:
            connection.execute(
                """UPDATE model_experiment_runs SET status=?,progress=?,current_model=NULL,
                   result_json=?,error_message=?,cancel_requested=0,updated_at=?,finished_at=? WHERE id=?""",
                (
                    status,
                    1.0 if status == "completed" else 0.0,
                    _json(result) if result is not None else None,
                    error_message,
                    timestamp,
                    timestamp,
                    run_id,
                ),
            )

    def request_cancel(self, run_id: str):
        timestamp = _now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM model_experiment_runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["status"] == "queued":
                connection.execute(
                    "UPDATE model_experiment_runs SET status='cancelled',finished_at=?,updated_at=? WHERE id=?",
                    (timestamp, timestamp, run_id),
                )
            elif row["status"] == "running":
                connection.execute(
                    "UPDATE model_experiment_runs SET cancel_requested=1,updated_at=? WHERE id=?",
                    (timestamp, run_id),
                )
            else:
                raise ValueError("当前实验状态不能取消")
        return self.get(run_id)

    def cancellation_requested(self, run_id: str):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM model_experiment_runs WHERE id=?",
                (run_id,),
            ).fetchone()
        return bool(row and row[0])

    def fail_interrupted(self):
        timestamp = _now()
        with self.connect() as connection:
            connection.execute(
                """UPDATE model_experiment_runs SET status='failed',error_message='服务重启导致实验中断，请重新发起',
                   updated_at=?,finished_at=? WHERE status IN ('queued','running')""",
                (timestamp, timestamp),
            )
