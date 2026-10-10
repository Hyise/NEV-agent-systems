"""Two-stage criterion discovery over immutable review snapshots."""

from pydantic import BaseModel, ConfigDict, Field

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
        if action is ControlAction.PAUSE:
            self.repository.set_job_state(job_id, "paused")
            return True
        if action is ControlAction.CANCEL:
            self.repository.set_job_state(job_id, "cancelled")
            return True
        return False

    def run(self, job_id: str, control) -> None:
        rows = self.repository.pending_review_snapshots(job_id)
        self.repository.set_job_state(job_id, "running", phase="extracting")
        all_clues: list[dict] = []
        for texts in _batches(rows, self.character_budget, self.max_reviews_per_batch):
            if self._control(job_id, control): return
            parsed, completion = self.executor.call(
                self.renderer.discovery_batch(texts),
                lambda payload: _Clues.model_validate(payload),
                max_tokens=2_500,
                attempts=3,
            )
            self.repository.add_usage(job_id, completion)
            all_clues.extend(item.model_dump() for item in parsed.clues)
        if self._control(job_id, control): return
        self.repository.set_job_state(job_id, "running", phase="merging")
        proposal, completion = self.executor.call(
            self.renderer.criteria_merge(all_clues),
            parse_criteria_proposal,
            max_tokens=4_000,
            attempts=2,
        )
        self.repository.add_usage(job_id, completion)
        self.repository.save_proposal(
            job_id, proposal.model_dump(),
            source_review_count=len(rows), sample_review_count=len(rows),
        )
        self.repository.set_job_state(job_id, "completed")

