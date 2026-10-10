"""Single-worker orchestration for resumable local LLM jobs."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor

from .config import LlmConfigurationError
from .deepseek import LlmAuthenticationError
from .domain import ControlAction


class ReviewAnalysisService:
    def __init__(self, repository, annotation_pipeline, discovery_pipeline):
        self.repository = repository
        self.annotation_pipeline = annotation_pipeline
        self.discovery_pipeline = discovery_pipeline
        self.repository.pause_interrupted_jobs()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="review-analysis")
        self._lock = threading.Lock()
        self._future: Future[None] | None = None
        self._job_id: str | None = None

    def _control(self, job_id: str):
        value = self.repository.requested_control(job_id)
        return ControlAction(value) if value else None

    def _run(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        pipeline = self.discovery_pipeline if job["job_type"] == "criteria_discovery" else self.annotation_pipeline
        try:
            pipeline.run(job_id, lambda: self._control(job_id))
        except LlmAuthenticationError:
            self.repository.set_job_state(job_id, "paused", error_code="authentication", error_message="DeepSeek 认证或账户状态异常，请检查本机配置后继续")
        except LlmConfigurationError:
            self.repository.set_job_state(job_id, "paused", error_code="configuration", error_message="DeepSeek 本机配置不完整，请修复后继续")
        except Exception as exc:
            self.repository.set_job_state(job_id, "failed", error_code="internal", error_message=f"任务执行失败：{type(exc).__name__}")

    def start(self, job_id: str) -> Future[None]:
        with self._lock:
            if self._future is not None and not self._future.done():
                raise ValueError("已有大模型任务正在执行")
            job = self.repository.get_job(job_id)
            if job is None:
                raise KeyError(job_id)
            if job["status"] not in {"queued", "paused"}:
                raise ValueError("当前任务状态不能启动")
            self.repository.set_job_state(job_id, "queued")
            self._job_id = job_id
            self._future = self._executor.submit(self._run, job_id)
            return self._future

    def pause(self, job_id: str) -> None:
        self.repository.request_control(job_id, "pause")

    def cancel(self, job_id: str) -> None:
        self.repository.request_control(job_id, "cancel")

    def resume(self, job_id: str) -> Future[None]:
        return self.start(job_id)

    def retry_failures(self, job_id: str):
        job = self.repository.create_retry_job(job_id)
        self.start(job["id"])
        return job

    def shutdown(self) -> None:
        with self._lock:
            if self._future is not None and not self._future.done() and self._job_id:
                self.repository.request_control(self._job_id, "pause")
        self._executor.shutdown(wait=True, cancel_futures=False)

