from collections import deque

import pytest

from backend.review_analysis.deepseek import JsonCompletion, LlmInvalidResponseError, LlmTransientError
from backend.review_analysis.discovery import CriteriaDiscoveryPipeline
from backend.review_analysis.domain import ControlAction
from backend.review_analysis.prompting import PromptRenderer
from backend.review_analysis.structured_calls import StructuredCallExecutor


class Client:
    def __init__(self, payloads): self.payloads = deque(payloads); self.calls = []
    def complete_json(self, prompt, *, max_tokens):
        self.calls.append(prompt)
        value = self.payloads.popleft()
        if isinstance(value, Exception): raise value
        return JsonCompletion(value, 10, 5, 15, 0, "stop")


class Repo:
    def __init__(self, texts):
        self.job = {"id": "j", "status": "queued"}; self.texts = texts; self.proposal = None; self.states = []; self.usage = []
    def get_job(self, job_id): return self.job
    def pending_review_snapshots(self, job_id): return [{"review_id": str(i), "analysis_text": text} for i, text in enumerate(self.texts)]
    def save_proposal(self, job_id, proposal, **counts): self.proposal = proposal; self.counts = counts
    def set_job_state(self, job_id, status, **kwargs): self.states.append(status); self.job["status"] = status
    def add_usage(self, job_id, completion): self.usage.append(completion.total_tokens)


def test_discovery_batches_whole_reviews_and_merges_all_clues():
    clues1 = {"clues": [{"name": "空间", "terms": ["宽敞"], "evidence": ["甲" * 12]}]}
    clues2 = {"clues": [{"name": "续航", "terms": ["里程"], "evidence": ["乙" * 12]}]}
    proposal = {"criteria": [{"name": "空间", "labels": ["宽敞", "局促"], "similar_terms": ["宽敞"], "basis": "空间线索", "evidence": ["甲" * 12]}]}
    repo = Repo(["甲" * 12, "乙" * 12])
    client = Client([clues1, clues2, proposal])
    pipeline = CriteriaDiscoveryPipeline(repo, PromptRenderer(), StructuredCallExecutor(client), character_budget=12, max_reviews_per_batch=100)
    pipeline.run("j", lambda: None)

    assert len(client.calls) == 3
    assert "甲" * 12 in client.calls[0].user_prompt and "乙" * 12 not in client.calls[0].user_prompt
    assert "空间" in client.calls[2].user_prompt and "续航" in client.calls[2].user_prompt
    assert repo.proposal == proposal
    assert repo.counts == {"source_review_count": 2, "sample_review_count": 2}
    assert sum(repo.usage) == 45
    assert repo.states[-1] == "completed"


def test_structured_executor_retries_transient_and_validation_errors():
    client = Client([LlmTransientError("later"), {"bad": True}, {"ok": True}])
    executor = StructuredCallExecutor(client, sleep=lambda _: None)
    value, _ = executor.call(PromptRenderer().discovery_batch(["x"]), lambda payload: payload if "ok" in payload else (_ for _ in ()).throw(ValueError("bad")), max_tokens=20, attempts=3)
    assert value == {"ok": True}
    assert len(client.calls) == 3


@pytest.mark.parametrize("action", [ControlAction.PAUSE, ControlAction.CANCEL])
def test_control_stops_before_next_model_call(action):
    repo = Repo(["甲", "乙"])
    client = Client([])
    CriteriaDiscoveryPipeline(repo, PromptRenderer(), StructuredCallExecutor(client), character_budget=1).run("j", lambda: action)
    assert client.calls == []
    assert repo.states[-1] == ("paused" if action is ControlAction.PAUSE else "cancelled")


def test_invalid_merge_does_not_save_partial_proposal():
    repo = Repo(["甲"])
    client = Client([{"clues": []}, {"criteria": []}, {"criteria": []}])
    with pytest.raises(LlmInvalidResponseError):
        CriteriaDiscoveryPipeline(repo, PromptRenderer(), StructuredCallExecutor(client, sleep=lambda _: None)).run("j", lambda: None)
    assert repo.proposal is None
