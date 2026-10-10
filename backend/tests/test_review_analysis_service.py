import threading

import pytest

from backend.review_analysis.deepseek import LlmAuthenticationError
from backend.review_analysis.service import ReviewAnalysisService


class Repo:
    def __init__(self):
        self.jobs = {"a": {"id": "a", "job_type": "review_annotation", "status": "paused"}, "d": {"id": "d", "job_type": "criteria_discovery", "status": "paused"}}
        self.controls = {}; self.states = []; self.paused_interrupted = 0
    def pause_interrupted_jobs(self): self.paused_interrupted += 1; return 0
    def get_job(self, job_id): return self.jobs.get(job_id)
    def set_job_state(self, job_id, status, **kwargs): self.jobs[job_id]["status"] = status; self.controls.pop(job_id, None); self.states.append((job_id, status, kwargs)); return self.jobs[job_id]
    def request_control(self, job_id, action): self.controls[job_id] = action
    def requested_control(self, job_id): return self.controls.get(job_id)
    def create_retry_job(self, job_id): return {"id": "retry", "source_job_id": job_id}


class Pipeline:
    def __init__(self, called, gate=None, error=None): self.called = called; self.gate = gate; self.error = error
    def run(self, job_id, control):
        self.called.append(job_id)
        if self.gate: self.gate.wait(2)
        if self.error: raise self.error


def test_dispatches_by_type_and_allows_only_one_running_future():
    repo = Repo(); called = []; gate = threading.Event()
    service = ReviewAnalysisService(repo, Pipeline(called, gate), Pipeline(called))
    first = service.start("a")
    with pytest.raises(ValueError, match="正在执行"):
        service.start("d")
    gate.set(); first.result(timeout=2)
    service.start("d").result(timeout=2)
    assert called == ["a", "d"]
    service.shutdown()


def test_authentication_failure_pauses_with_sanitized_error():
    repo = Repo(); secret = "sk-private"
    service = ReviewAnalysisService(repo, Pipeline([], error=LlmAuthenticationError(secret)), Pipeline([]))
    service.start("a").result(timeout=2)
    _, status, details = repo.states[-1]
    assert status == "paused" and details["error_code"] == "authentication"
    assert secret not in details["error_message"]
    service.shutdown()


def test_controls_recovery_and_retry_delegate_to_repository():
    repo = Repo(); service = ReviewAnalysisService(repo, Pipeline([]), Pipeline([]))
    assert repo.paused_interrupted == 1
    service.pause("a"); assert repo.controls["a"] == "pause"
    service.cancel("a"); assert repo.controls["a"] == "cancel"
    assert service.retry_failures("a")["source_job_id"] == "a"
    service.shutdown()
