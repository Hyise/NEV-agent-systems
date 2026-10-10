"""SQLite persistence for review-analysis jobs and immutable inputs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .domain import CreateJobCommand, ReviewAsset, ReviewSnapshot


ACTIVE_STATUSES = ("queued", "running", "paused")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class ReviewAnalysisRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_analysis_jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, schema_id TEXT,
                    job_type TEXT NOT NULL, status TEXT NOT NULL, phase TEXT NOT NULL,
                    model TEXT NOT NULL, prompt_manifest_json TEXT NOT NULL,
                    schema_fingerprint TEXT, criteria_json TEXT NOT NULL DEFAULT '[]',
                    source_config_json TEXT NOT NULL,
                    total_count INTEGER NOT NULL DEFAULT 0,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    cache_hit_count INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_tokens INTEGER NOT NULL DEFAULT 0,
                    control_requested TEXT, last_error_code TEXT, last_error_message TEXT,
                    created_at TEXT NOT NULL, started_at TEXT, updated_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS review_analysis_job_reviews (
                    job_id TEXT NOT NULL REFERENCES review_analysis_jobs(id) ON DELETE CASCADE,
                    review_id TEXT NOT NULL, series_id TEXT NOT NULL,
                    series_name_snapshot TEXT NOT NULL, content_hash TEXT NOT NULL,
                    analysis_text TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', attempt_count INTEGER NOT NULL DEFAULT 0,
                    annotation_id TEXT, error_code TEXT, error_message TEXT,
                    PRIMARY KEY(job_id,review_id), UNIQUE(job_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS criteria_proposals (
                    job_id TEXT PRIMARY KEY REFERENCES review_analysis_jobs(id) ON DELETE CASCADE,
                    proposal_json TEXT NOT NULL, proposal_fingerprint TEXT NOT NULL,
                    source_review_count INTEGER NOT NULL, sample_review_count INTEGER NOT NULL,
                    applied_schema_id TEXT, applied_revision INTEGER,
                    created_at TEXT NOT NULL, applied_at TEXT
                );
                CREATE TABLE IF NOT EXISTS review_annotation_results (
                    id TEXT PRIMARY KEY, content_hash TEXT NOT NULL,
                    schema_fingerprint TEXT NOT NULL, model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL, prompt_sha256 TEXT NOT NULL,
                    result_json TEXT NOT NULL, input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL, cached_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(content_hash,schema_fingerprint,model,prompt_sha256)
                );
                CREATE INDEX IF NOT EXISTS ix_review_analysis_jobs_project
                    ON review_analysis_jobs(project_id,created_at);
                CREATE INDEX IF NOT EXISTS ix_review_analysis_job_reviews_pending
                    ON review_analysis_job_reviews(job_id,status,ordinal);
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
    def _job(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["prompt_manifests"] = json.loads(result.pop("prompt_manifest_json"))
        result["source_config"] = json.loads(result.pop("source_config_json"))
        result["criteria"] = json.loads(result.pop("criteria_json"))
        return result

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["series_name"] = result.pop("series_name_snapshot")
        return result

    def list_sources(self, query: str = "", page: int = 1, page_size: int = 20):
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("分页参数无效")
        pattern = f"%{query.casefold()}%"
        params = (pattern, pattern)
        offset = (page - 1) * page_size
        with self.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM vehicle_series s WHERE EXISTS "
                "(SELECT 1 FROM reviews r WHERE r.platform=s.platform AND r.series_id=s.series_id) "
                "AND (lower(s.series_name) LIKE ? OR s.series_id LIKE ?)",
                params,
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT s.platform,s.series_id,s.series_name,s.discovery_rank,
                       COUNT(r.review_id) AS review_count
                FROM vehicle_series s JOIN reviews r
                  ON r.platform=s.platform AND r.series_id=s.series_id
                WHERE lower(s.series_name) LIKE ? OR s.series_id LIKE ?
                GROUP BY s.platform,s.series_id
                ORDER BY s.discovery_rank,s.series_id LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        return {"rows": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}

    def get_project_schema(self, project_id: str, schema_id: str):
        with self.connect() as connection:
            project = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            schema = connection.execute("SELECT * FROM schemas WHERE id=? AND project_id=?", (schema_id, project_id)).fetchone()
        if project is None or schema is None: return None
        schema_value = dict(schema); schema_value["criteria"] = json.loads(schema_value["criteria"])
        return dict(project), schema_value

    def create_job_with_snapshot(
        self,
        command: CreateJobCommand,
        build_snapshot: Callable[[list[ReviewAsset]], list[ReviewSnapshot]],
    ) -> dict[str, Any]:
        if len(command.selected_series_ids) != len(set(command.selected_series_ids)):
            raise ValueError("车系不能重复")
        job_id, timestamp = uuid.uuid4().hex, _now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            marks = ",".join("?" for _ in ACTIVE_STATUSES)
            if connection.execute(
                f"SELECT 1 FROM review_analysis_jobs WHERE status IN ({marks}) LIMIT 1",
                ACTIVE_STATUSES,
            ).fetchone():
                raise ValueError("已有活动大模型任务")
            series_marks = ",".join("?" for _ in command.selected_series_ids)
            rows = connection.execute(
                f"""
                SELECT review_id,series_id,series_name_snapshot,content_hash,original_review_json
                FROM reviews WHERE platform='autohome' AND series_id IN ({series_marks})
                ORDER BY series_id,review_id
                """,
                command.selected_series_ids,
            ).fetchall()
            if not rows:
                raise ValueError("所选车系没有已采集评论")
            assets = [
                ReviewAsset(
                    review_id=row["review_id"], series_id=row["series_id"],
                    series_name=row["series_name_snapshot"], content_hash=row["content_hash"],
                    original_review=json.loads(row["original_review_json"]),
                )
                for row in rows
            ]
            snapshots = build_snapshot(assets)
            if not snapshots:
                raise ValueError("任务评论快照不能为空")
            selected = set(command.selected_series_ids)
            if any(item.series_id not in selected for item in snapshots):
                raise ValueError("快照包含未选择车系")
            phase = "sampling" if command.job_type == "criteria_discovery" else "annotating"
            connection.execute(
                """INSERT INTO review_analysis_jobs (
                    id,project_id,schema_id,job_type,status,phase,model,prompt_manifest_json,
                    schema_fingerprint,criteria_json,source_config_json,total_count,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id, command.project_id, command.schema_id, command.job_type, "queued", phase,
                 command.model, _json([item.model_dump() for item in command.prompt_manifests]),
                 command.schema_fingerprint, _json([item.model_dump() for item in command.criteria]),
                 _json({"selected_series_ids": command.selected_series_ids, "limit": command.limit,
                        "sampling": "sha256-stratified-round-robin"}), len(snapshots), timestamp, timestamp),
            )
            for snapshot in snapshots:
                connection.execute(
                    """INSERT INTO review_analysis_job_reviews (
                        job_id,review_id,series_id,series_name_snapshot,content_hash,analysis_text,ordinal
                    ) VALUES (?,?,?,?,?,?,?)""",
                    (job_id, snapshot.review_id, snapshot.series_id, snapshot.series_name,
                     snapshot.content_hash, snapshot.analysis_text, snapshot.ordinal),
                )
            row = connection.execute("SELECT * FROM review_analysis_jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row)

    def get_job(self, job_id: str):
        with self.connect() as connection:
            return self._job(connection.execute("SELECT * FROM review_analysis_jobs WHERE id=?", (job_id,)).fetchone())

    def list_jobs(self, project_id: str, page: int = 1, page_size: int = 20):
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM review_analysis_jobs WHERE project_id=?", (project_id,)).fetchone()[0]
            rows = connection.execute("SELECT * FROM review_analysis_jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?", (project_id, page_size, (page - 1) * page_size)).fetchall()
        return {"rows": [self._job(row) for row in rows], "total": total, "page": page, "page_size": page_size}

    def active_job(self):
        marks = ",".join("?" for _ in ACTIVE_STATUSES)
        with self.connect() as connection:
            return self._job(connection.execute(f"SELECT * FROM review_analysis_jobs WHERE status IN ({marks}) ORDER BY created_at LIMIT 1", ACTIVE_STATUSES).fetchone())

    def request_control(self, job_id: str, action: str):
        if action not in {"pause", "cancel"}:
            raise ValueError("不支持的控制动作")
        with self.connect() as connection:
            count = connection.execute("UPDATE review_analysis_jobs SET control_requested=?,updated_at=? WHERE id=? AND status IN ('queued','running','paused')", (action, _now(), job_id)).rowcount
            if count != 1:
                raise ValueError("任务状态不允许控制")
        return self.get_job(job_id)

    def requested_control(self, job_id: str):
        with self.connect() as connection:
            row = connection.execute("SELECT control_requested FROM review_analysis_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return row["control_requested"]

    def pause_interrupted_jobs(self):
        timestamp = _now()
        with self.connect() as connection:
            count = connection.execute("UPDATE review_analysis_jobs SET status='paused',control_requested=NULL,last_error_code='interrupted',last_error_message='应用重启，任务已暂停',updated_at=? WHERE status IN ('queued','running')", (timestamp,)).rowcount
        return count

    def pending_review_snapshots(self, job_id: str, *, include_failed: bool = False):
        statuses = ("pending", "failed") if include_failed else ("pending",)
        marks = ",".join("?" for _ in statuses)
        with self.connect() as connection:
            rows = connection.execute(f"SELECT * FROM review_analysis_job_reviews WHERE job_id=? AND status IN ({marks}) ORDER BY ordinal", (job_id, *statuses)).fetchall()
        return [self._snapshot(row) for row in rows]

    def set_job_state(self, job_id: str, status: str, *, phase: str | None = None, error_code: str | None = None, error_message: str | None = None):
        timestamp = _now()
        terminal = status in {"completed", "partial_failed", "failed", "cancelled"}
        with self.connect() as connection:
            count = connection.execute(
                """UPDATE review_analysis_jobs SET status=?,phase=COALESCE(?,phase),control_requested=NULL,
                   last_error_code=?,last_error_message=?,started_at=COALESCE(started_at,?),updated_at=?,
                   finished_at=CASE WHEN ? THEN ? ELSE finished_at END WHERE id=?""",
                (status, phase, error_code, error_message, timestamp if status == "running" else None,
                 timestamp, int(terminal), timestamp, job_id),
            ).rowcount
            if count != 1:
                raise KeyError(job_id)
        return self.get_job(job_id)

    def add_usage(self, job_id: str, completion):
        with self.connect() as connection:
            connection.execute(
                "UPDATE review_analysis_jobs SET input_tokens=input_tokens+?,output_tokens=output_tokens+?,cached_tokens=cached_tokens+?,updated_at=? WHERE id=?",
                (completion.input_tokens, completion.output_tokens, completion.cached_tokens, _now(), job_id),
            )

    def mark_review_succeeded(self, job_id: str, review_id: str, annotation_id: str, *, cached: bool, input_tokens: int = 0, output_tokens: int = 0, cached_tokens: int = 0):
        status = "cached" if cached else "succeeded"
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("UPDATE review_analysis_job_reviews SET status=?,annotation_id=?,attempt_count=attempt_count+1,error_code=NULL,error_message=NULL WHERE job_id=? AND review_id=?", (status, annotation_id, job_id, review_id)).rowcount
            if count != 1: raise KeyError(review_id)
            connection.execute("UPDATE review_analysis_jobs SET processed_count=processed_count+1,success_count=success_count+1,cache_hit_count=cache_hit_count+?,input_tokens=input_tokens+?,output_tokens=output_tokens+?,cached_tokens=cached_tokens+?,updated_at=? WHERE id=?", (int(cached), input_tokens, output_tokens, cached_tokens, _now(), job_id))

    def mark_review_failed(self, job_id: str, review_id: str, error_code: str, error_message: str):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("UPDATE review_analysis_job_reviews SET status='failed',attempt_count=attempt_count+1,error_code=?,error_message=? WHERE job_id=? AND review_id=?", (error_code, error_message[:500], job_id, review_id)).rowcount
            if count != 1: raise KeyError(review_id)
            connection.execute("UPDATE review_analysis_jobs SET processed_count=processed_count+1,failed_count=failed_count+1,updated_at=? WHERE id=?", (_now(), job_id))

    def save_proposal(self, job_id: str, proposal: dict[str, Any], *, source_review_count: int, sample_review_count: int):
        canonical = _json(proposal)
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        with self.connect() as connection:
            connection.execute("INSERT INTO criteria_proposals (job_id,proposal_json,proposal_fingerprint,source_review_count,sample_review_count,created_at) VALUES (?,?,?,?,?,?)", (job_id, canonical, fingerprint, source_review_count, sample_review_count, _now()))
        return self.get_proposal(job_id)

    def get_proposal(self, job_id: str):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM criteria_proposals WHERE job_id=?", (job_id,)).fetchone()
        if row is None: return None
        result = dict(row); result["proposal"] = json.loads(result.pop("proposal_json")); return result

    def apply_proposal(self, job_id: str, expected_revision: int):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT p.*,j.schema_id,j.project_id FROM criteria_proposals p JOIN review_analysis_jobs j ON j.id=p.job_id WHERE p.job_id=?", (job_id,)).fetchone()
            if row is None: raise KeyError(job_id)
            if row["applied_at"] is not None: raise ValueError("候选方案已经应用")
            proposal = json.loads(row["proposal_json"])
            criteria = [{"name": item["name"], "labels": item["labels"]} for item in proposal["criteria"]]
            count = connection.execute("UPDATE schemas SET criteria=?,revision=revision+1 WHERE id=? AND project_id=? AND status='draft' AND revision=?", (_json(criteria), row["schema_id"], row["project_id"], expected_revision)).rowcount
            if count != 1: raise ValueError("准则草稿 revision 冲突或不可编辑")
            schema = connection.execute("SELECT * FROM schemas WHERE id=?", (row["schema_id"],)).fetchone()
            connection.execute("UPDATE criteria_proposals SET applied_schema_id=?,applied_revision=?,applied_at=? WHERE job_id=?", (row["schema_id"], schema["revision"], _now(), job_id))
        result = dict(schema); result["criteria"] = json.loads(result["criteria"]); return result

    def find_cached_result(self, content_hash: str, schema_fingerprint: str, model: str, prompt_sha256: str):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM review_annotation_results WHERE content_hash=? AND schema_fingerprint=? AND model=? AND prompt_sha256=?", (content_hash, schema_fingerprint, model, prompt_sha256)).fetchone()
        if row is None: return None
        result = dict(row); result["result"] = json.loads(result.pop("result_json")); return result

    def save_result(self, *, content_hash: str, schema_fingerprint: str, model: str, prompt_version: str, prompt_sha256: str, result: dict[str, Any], input_tokens: int, output_tokens: int, cached_tokens: int):
        result_id = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO review_annotation_results VALUES (?,?,?,?,?,?,?,?,?,?,?)", (result_id, content_hash, schema_fingerprint, model, prompt_version, prompt_sha256, _json(result), input_tokens, output_tokens, cached_tokens, _now()))
        return self.find_cached_result(content_hash, schema_fingerprint, model, prompt_sha256)

    def create_retry_job(self, source_job_id: str):
        new_id, timestamp = uuid.uuid4().hex, _now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute("SELECT * FROM review_analysis_jobs WHERE id=? AND job_type='review_annotation'", (source_job_id,)).fetchone()
            if source is None:
                raise KeyError(source_job_id)
            failed = connection.execute("SELECT * FROM review_analysis_job_reviews WHERE job_id=? AND status='failed' ORDER BY ordinal", (source_job_id,)).fetchall()
            if not failed:
                raise ValueError("原任务没有可重试失败项")
            marks = ",".join("?" for _ in ACTIVE_STATUSES)
            if connection.execute(f"SELECT 1 FROM review_analysis_jobs WHERE status IN ({marks}) LIMIT 1", ACTIVE_STATUSES).fetchone():
                raise ValueError("已有活动大模型任务")
            connection.execute(
                """INSERT INTO review_analysis_jobs (
                    id,project_id,schema_id,job_type,status,phase,model,prompt_manifest_json,
                    schema_fingerprint,criteria_json,source_config_json,total_count,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (new_id, source["project_id"], source["schema_id"], source["job_type"], "queued", "annotating",
                 source["model"], source["prompt_manifest_json"], source["schema_fingerprint"], source["criteria_json"],
                 _json({"retry_of": source_job_id}), len(failed), timestamp, timestamp),
            )
            for ordinal, row in enumerate(failed):
                connection.execute("INSERT INTO review_analysis_job_reviews (job_id,review_id,series_id,series_name_snapshot,content_hash,analysis_text,ordinal) VALUES (?,?,?,?,?,?,?)", (new_id,row["review_id"],row["series_id"],row["series_name_snapshot"],row["content_hash"],row["analysis_text"],ordinal))
            job = connection.execute("SELECT * FROM review_analysis_jobs WHERE id=?", (new_id,)).fetchone()
        return self._job(job)

    def list_annotations(self, project_id: str, *, job_id=None, series_id=None, criterion=None, label=None, status=None, page=1, page_size=20):
        clauses, params = ["j.project_id=?"], [project_id]
        for column, value in (("r.job_id", job_id), ("r.series_id", series_id), ("r.status", status)):
            if value: clauses.append(f"{column}=?"); params.append(value)
        where = " AND ".join(clauses)
        with self.connect() as connection:
            rows = connection.execute(f"""SELECT r.*,a.result_json,a.created_at AS annotated_at
                FROM review_analysis_job_reviews r JOIN review_analysis_jobs j ON j.id=r.job_id
                LEFT JOIN review_annotation_results a ON a.id=r.annotation_id WHERE {where}
                ORDER BY r.ordinal LIMIT ? OFFSET ?""", (*params,page_size,(page-1)*page_size)).fetchall()
        result=[]
        for row in rows:
            item=self._snapshot(row); payload=json.loads(item.pop("result_json")) if item.get("result_json") else None
            if criterion and not any(x["criterion"]==criterion for x in (payload or {}).get("annotations",[])): continue
            if label and not any(x["label"]==label for x in (payload or {}).get("annotations",[])): continue
            item["result"]=payload; item["annotation_count"]=len((payload or {}).get("annotations",[])); result.append(item)
        return {"rows":result,"total":len(result),"page":page,"page_size":page_size}

    def get_annotation(self, project_id: str, annotation_id: str):
        with self.connect() as connection:
            row=connection.execute("""SELECT a.*,r.review_id,r.series_id,r.series_name_snapshot,r.analysis_text,r.job_id
                FROM review_annotation_results a JOIN review_analysis_job_reviews r ON r.annotation_id=a.id
                JOIN review_analysis_jobs j ON j.id=r.job_id WHERE a.id=? AND j.project_id=? LIMIT 1""",(annotation_id,project_id)).fetchone()
        if row is None:return None
        result=dict(row);result["series_name"]=result.pop("series_name_snapshot");result["result"]=json.loads(result.pop("result_json"));return result

    def annotation_summary(self, project_id: str, job_id: str | None = None):
        with self.connect() as connection:
            params=[project_id]; extra=""
            if job_id: extra=" AND j.id=?";params.append(job_id)
            rows=connection.execute("SELECT a.result_json FROM review_annotation_results a JOIN review_analysis_job_reviews r ON r.annotation_id=a.id JOIN review_analysis_jobs j ON j.id=r.job_id WHERE j.project_id=?"+extra,params).fetchall()
        criteria={};labels={}
        for row in rows:
            for item in json.loads(row[0]).get("annotations",[]):
                criteria[item["criterion"]]=criteria.get(item["criterion"],0)+1
                key=f'{item["criterion"]}/{item["label"]}';labels[key]=labels.get(key,0)+1
        return {"annotated_reviews":len(rows),"criteria":criteria,"labels":labels}

