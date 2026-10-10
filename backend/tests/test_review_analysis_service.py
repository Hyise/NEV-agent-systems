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
    def finish_job(self, job_id, default_status, **kwargs):
        action = self.controls.pop(job_id, None)
        status = "cancelled" if action == "cancel" else "paused" if action == "pause" else default_status
        self.jobs[job_id]["status"] = status
        self.states.append((job_id, status, kwargs))
        return self.jobs[job_id]
    def request_control(self, job_id, action):
        if not (action == "pause" and self.controls.get(job_id) == "cancel"):
            self.controls[job_id] = action
        if action == "cancel" and self.jobs[job_id]["status"] in {"queued", "paused"}:
            self.jobs[job_id]["status"] = "cancelled"
        if action == "pause" and self.jobs[job_id]["status"] == "queued":
            self.jobs[job_id]["status"] = "paused"
    def requested_control(self, job_id): return self.controls.get(job_id)
    def consume_control(self, job_id):
        action = self.controls.pop(job_id, None)
        if action in {"pause", "cancel"} and self.jobs[job_id]["status"] == "running":
            self.jobs[job_id]["status"] = "cancelled" if action == "cancel" else "paused"
        return action
    def queue_job(self, job_id):
        if self.jobs[job_id]["status"] != "paused": return False
        self.jobs[job_id]["status"] = "queued"; self.controls.pop(job_id, None); return True
    def claim_job(self, job_id, phase):
        if self.jobs[job_id]["status"] != "queued": return False
        self.jobs[job_id]["status"] = "running"; return True
    def create_retry_job(self, job_id):
        job = {"id": "retry", "source_job_id": job_id, "job_type": "review_annotation", "status": "queued"}
        self.jobs[job["id"]] = job
        return job


class Pipeline:
    def __init__(self, called, gate=None, error=None, started=None, before_error=None): self.called = called; self.gate = gate; self.error = error; self.started = started; self.before_error = before_error
    def run(self, job_id, control):
        self.called.append(job_id)
        if self.started: self.started.set()
        if self.gate: self.gate.wait(2)
        if self.error:
            if self.before_error: self.before_error(job_id)
            raise self.error


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
    repo = Repo(); called = []; service = ReviewAnalysisService(repo, Pipeline(called), Pipeline([]))
    assert repo.paused_interrupted == 1
    repo.jobs["a"]["status"] = "running"
    service.pause("a"); assert repo.controls["a"] == "pause"
    service.cancel("a"); assert repo.controls["a"] == "cancel"
    repo.jobs["a"]["status"] = "partial_failed"
    assert service.retry_failures("a")["source_job_id"] == "a"
    service._future.result(timeout=2)
    assert called == ["retry"]
    service.shutdown()


def test_cancelled_queued_future_never_enters_pipeline():
    repo = Repo()
    repo.jobs["q"] = {"id": "q", "job_type": "review_annotation", "status": "queued"}
    called = []
    gate = threading.Event()
    started = threading.Event()
    service = ReviewAnalysisService(repo, Pipeline(called, gate, started=started), Pipeline([]))
    first = service.start("a")
    assert started.wait(1)
    repo.jobs["a"]["status"] = "partial_failed"
    queued = service.start("q")
    service.cancel("q")
    gate.set()
    first.result(timeout=2)
    queued.result(timeout=2)

    assert called == ["a"]
    assert repo.jobs["q"]["status"] == "cancelled"
    service.shutdown()


def test_retry_can_queue_after_terminal_state_before_old_future_returns():
    repo = Repo()
    called = []
    gate = threading.Event()
    started = threading.Event()
    service = ReviewAnalysisService(repo, Pipeline(called, gate, started=started), Pipeline([]))
    first = service.start("a")
    assert started.wait(1)
    repo.jobs["a"]["status"] = "partial_failed"

    retry = service.retry_failures("a")
    gate.set()
    first.result(timeout=2)
    service._future.result(timeout=2)

    assert retry["id"] == "retry"
    assert called == ["a", "retry"]
    service.shutdown()


@pytest.mark.parametrize(
    ("action", "expected"),
    [("pause", "paused"), ("cancel", "cancelled")],
)
def test_error_finish_honors_control_received_during_request(action, expected):
    repo = Repo()
    pipeline = Pipeline(
        [],
        error=RuntimeError("boom"),
        before_error=lambda job_id: repo.request_control(job_id, action),
    )
    service = ReviewAnalysisService(repo, pipeline, Pipeline([]))

    service.start("a").result(timeout=2)

    assert repo.jobs["a"]["status"] == expected
    service.shutdown()
