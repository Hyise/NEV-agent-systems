from collections import deque

from backend.review_analysis.annotation import ReviewAnnotationPipeline
from backend.review_analysis.deepseek import JsonCompletion
from backend.review_analysis.domain import ControlAction, CriterionSnapshot
from backend.review_analysis.prompting import PromptRenderer
from backend.review_analysis.structured_calls import StructuredCallExecutor


class Client:
    def __init__(self, payloads): self.payloads = deque(payloads); self.calls = 0
    def complete_json(self, prompt, *, max_tokens):
        self.calls += 1
        return JsonCompletion(self.payloads.popleft(), 5, 2, 7, 0, "stop")


class Repo:
    def __init__(self, rows):
        self.rows = rows; self.results = {}; self.links = {}; self.failures = {}; self.states = []
        criteria = [{"name": "空间", "labels": ["宽敞", "局促"]}, {"name": "续航", "labels": ["充足", "不足"]}]
        manifest = PromptRenderer().review_annotation(
            [CriterionSnapshot.model_validate(item) for item in criteria], "占位"
        ).manifest.model_dump()
        self.job = {"model": "deepseek-flash", "schema_fingerprint": "b" * 64,
                    "criteria": criteria, "prompt_manifests": [manifest],
                    "failed_count": 0}
    def get_job(self, job_id): return self.job
    def pending_review_snapshots(self, job_id): return [r for r in self.rows if r["review_id"] not in self.links and r["review_id"] not in self.failures]
    def find_cached_result(self, content_hash, schema, model, prompt_hash): return self.results.get((content_hash, schema, model, prompt_hash))
    def save_result(self, **values):
        item = {"id": f"a{len(self.results)+1}", "result": values["result"]}
        self.results[(values["content_hash"], values["schema_fingerprint"], values["model"], values["prompt_sha256"])] = item
        return item
    def mark_review_succeeded(self, job_id, review_id, annotation_id, **values): self.links[review_id] = (annotation_id, values["cached"])
    def mark_review_failed(self, job_id, review_id, code, message): self.failures[review_id] = code; self.job["failed_count"] += 1
    def set_job_state(self, job_id, status, **kwargs): self.states.append(status)


def row(review_id, content_hash="1" * 64, text="后排很宽敞，冬季续航不足"):
    return {"review_id": review_id, "content_hash": content_hash, "analysis_text": text}


def test_annotation_allows_multiple_criteria_and_explicit_empty_success():
    payloads = [
        {"annotations": [
            {"criterion": "空间", "label": "宽敞", "evidence": ["后排很宽敞"], "basis": "空间评价"},
            {"criterion": "续航", "label": "不足", "evidence": ["冬季续航不足"], "basis": "续航评价"},
        ], "unmatched_evidence": []},
        {"annotations": [], "unmatched_evidence": []},
    ]
    repo = Repo([row("r1"), row("r2", "2" * 64, "只是提车记录")])
    client = Client(payloads)
    ReviewAnnotationPipeline(repo, PromptRenderer(), StructuredCallExecutor(client)).run("j", lambda: None)
    assert len(repo.results) == 2 and len(repo.links) == 2
    assert repo.states[-1] == "completed"


def test_duplicate_content_reuses_result_but_preserves_both_review_links():
    repo = Repo([row("r1"), row("r2")])
    client = Client([{"annotations": [], "unmatched_evidence": []}])
    ReviewAnnotationPipeline(repo, PromptRenderer(), StructuredCallExecutor(client)).run("j", lambda: None)
    assert client.calls == 1
    assert repo.links["r1"][0] == repo.links["r2"][0]
    assert repo.links["r2"][1] is True


def test_invalid_annotation_isolated_and_following_review_continues():
    bad = {"annotations": [{"criterion": "体系外", "label": "好", "evidence": ["后排很宽敞"], "basis": "错误"}], "unmatched_evidence": []}
    good = {"annotations": [], "unmatched_evidence": []}
    repo = Repo([row("r1"), row("r2", "2" * 64)])
    client = Client([bad, bad, good])
    ReviewAnnotationPipeline(repo, PromptRenderer(), StructuredCallExecutor(client, sleep=lambda _: None)).run("j", lambda: None)
    assert repo.failures == {"r1": "invalid_response"}
    assert "r2" in repo.links
    assert repo.states[-1] == "partial_failed"


def test_pause_before_call_does_not_process_item():
    repo = Repo([row("r1")]); client = Client([])
    ReviewAnnotationPipeline(repo, PromptRenderer(), StructuredCallExecutor(client)).run("j", lambda: ControlAction.PAUSE)
    assert client.calls == 0 and repo.states[-1] == "paused"
