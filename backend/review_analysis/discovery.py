"""Two-stage criterion discovery over immutable review snapshots."""

from pydantic import BaseModel, ConfigDict, Field

from .config import LlmConfigurationError
from .domain import ControlAction, parse_criteria_proposal


class _Clue(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=50)
    terms: list[str] = Field(default_factory=list, max_length=30)
    evidence: list[str] = Field(default_factory=list, max_length=20)


class _Clues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clues: list[_Clue] = Field(default_factory=list, max_length=100)


def _batches(rows, character_budget: int, max_reviews: int):
    batch, size = [], 0
    for row in rows:
        text = row["analysis_text"]
        if batch and (size + len(text) > character_budget or len(batch) >= max_reviews):
            yield batch
            batch, size = [], 0
        batch.append(text)
        size += len(text)
    if batch:
        yield batch


class CriteriaDiscoveryPipeline:
    def __init__(self, repository, renderer, executor, *, character_budget: int = 40_000, max_reviews_per_batch: int = 100):
        self.repository = repository
        self.renderer = renderer
        self.executor = executor
        self.character_budget = character_budget
        self.max_reviews_per_batch = max_reviews_per_batch

    def _control(self, job_id, control) -> bool:
        action = control()
        return action in {ControlAction.PAUSE, ControlAction.CANCEL}

    def run(self, job_id: str, control) -> None:
        job = self.repository.get_job(job_id)
        if self.executor.model is not None and self.executor.model != job["model"]:
            raise LlmConfigurationError("任务模型配置已变化，请新建任务")
        expected = {item["version"]: item["sha256"] for item in job["prompt_manifests"]}
        current = [self.renderer.discovery_batch([]).manifest, self.renderer.criteria_merge([]).manifest]
        if any(expected.get(item.version) != item.sha256 for item in current):
            raise LlmConfigurationError("任务 Prompt 版本已变化，请新建任务")
        rows = self.repository.pending_review_snapshots(job_id)
        all_clues: list[dict] = []
        grouped = list(_batches(rows, self.character_budget, self.max_reviews_per_batch))
        batch_rows, offset = [], 0
        for texts in grouped:
            batch_rows.append(rows[offset:offset + len(texts)])
            offset += len(texts)
        checkpoints = self.repository.ensure_discovery_batches(job_id, batch_rows)
        by_id = {row["review_id"]: row for row in rows}
        for checkpoint in checkpoints:
            texts = [by_id[review_id]["analysis_text"] for review_id in checkpoint["review_ids"]]
            if checkpoint["status"] == "succeeded":
                all_clues.extend(checkpoint["clues"] or [])
                continue
            if self._control(job_id, control): return
            parsed, completion = self.executor.call(
                self.renderer.discovery_batch(texts),
                lambda payload: _validate_clues(payload, texts),
                max_tokens=2_500,
                attempts=3,
            )
            clues = [item.model_dump() for item in parsed.clues]
            self.repository.save_discovery_batch(job_id, checkpoint["batch_index"], clues, completion)
            all_clues.extend(clues)
        if self._control(job_id, control): return
        if self.repository.get_proposal(job_id) is not None:
            self.repository.finish_job(job_id, "completed")
            return
        self.repository.set_job_state(job_id, "running", phase="merging")
        proposal, completion = self.executor.call(
            self.renderer.criteria_merge(all_clues),
            lambda payload: _validate_proposal(payload, [row["analysis_text"] for row in rows]),
            max_tokens=4_000,
            attempts=2,
        )
        self.repository.save_proposal(
            job_id, proposal.model_dump(),
            source_review_count=len(rows), sample_review_count=len(rows), completion=completion,
        )
        self.repository.finish_job(job_id, "completed")


def _validate_clues(payload, texts: list[str]):
    result = _Clues.model_validate(payload)
    if any(
        not evidence or not any(evidence in text for text in texts)
        for clue in result.clues
        for evidence in clue.evidence
    ):
        raise ValueError("准则线索证据必须来自评论原文")
    return result


def _validate_proposal(payload, texts: list[str]):
    result = parse_criteria_proposal(payload)
    if any(
        not evidence or not any(evidence in text for text in texts)
        for criterion in result.criteria
        for evidence in criterion.evidence
    ):
        raise ValueError("候选方案证据必须来自样本原文")
    return result
