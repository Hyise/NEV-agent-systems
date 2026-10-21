"""Closed-schema, one-request-per-review annotation pipeline."""

from .config import LlmConfigurationError
from .deepseek import LlmInvalidResponseError, LlmTransientError
from .domain import CriterionSnapshot, ControlAction, parse_review_annotation


def _retain_verbatim_evidence(payload, review_text: str):
    if not isinstance(payload, dict):
        return payload
    annotations = payload.get("annotations")
    unmatched = payload.get("unmatched_evidence")
    if not isinstance(annotations, list) or not isinstance(unmatched, list):
        return payload

    cleaned_annotations = []
    for item in annotations:
        if not isinstance(item, dict) or not isinstance(item.get("evidence"), list):
            cleaned_annotations.append(item)
            continue
        evidence = list(
            dict.fromkeys(
                value
                for value in item["evidence"]
                if isinstance(value, str) and value in review_text
            )
        )
        if evidence:
            cleaned_annotations.append({**item, "evidence": evidence})

    cleaned_unmatched = list(
        dict.fromkeys(
            value
            for value in unmatched
            if isinstance(value, str) and value in review_text
        )
    )
    return {
        **payload,
        "annotations": cleaned_annotations,
        "unmatched_evidence": cleaned_unmatched,
    }


class ReviewAnnotationPipeline:
    def __init__(self, repository, renderer, executor):
        self.repository = repository
        self.renderer = renderer
        self.executor = executor

    def run(self, job_id: str, control) -> None:
        job = self.repository.get_job(job_id)
        if self.executor.model is not None and self.executor.model != job["model"]:
            raise LlmConfigurationError("任务模型配置已变化，请新建任务")
        criteria = [CriterionSnapshot.model_validate(item) for item in job["criteria"]]
        current = self.renderer.review_annotation(criteria, "占位").manifest
        expected = job["prompt_manifests"][0]
        if expected["version"] != current.version or expected["sha256"] != current.sha256:
            raise LlmConfigurationError("任务 Prompt 版本已变化，请新建任务")
        for row in self.repository.pending_review_snapshots(job_id):
            action = control()
            if action in {ControlAction.PAUSE, ControlAction.CANCEL}:
                return
            prompt = self.renderer.review_annotation(criteria, row["analysis_text"])
            cached = self.repository.find_cached_result(
                row["content_hash"], job["schema_fingerprint"], job["model"], prompt.manifest.sha256,
            )
            if cached is not None:
                self.repository.mark_review_succeeded(job_id, row["snapshot_id"], cached["id"], cached=True)
                continue
            try:
                result, completion = self.executor.call(
                    prompt,
                    lambda payload: parse_review_annotation(
                        _retain_verbatim_evidence(payload, row["analysis_text"]),
                        criteria=criteria,
                        review_text=row["analysis_text"],
                    ),
                    max_tokens=3_000,
                    attempts=2,
                )
            except (LlmInvalidResponseError, LlmTransientError) as exc:
                code = "invalid_response" if isinstance(exc, LlmInvalidResponseError) else "transient_exhausted"
                self.repository.mark_review_failed(job_id, row["snapshot_id"], code, str(exc))
                continue
            saved = self.repository.save_result(
                content_hash=row["content_hash"], schema_fingerprint=job["schema_fingerprint"],
                model=job["model"], prompt_version=prompt.manifest.version,
                prompt_sha256=prompt.manifest.sha256, result=result.model_dump(),
                input_tokens=completion.input_tokens, output_tokens=completion.output_tokens,
                cached_tokens=completion.cached_tokens,
            )
            self.repository.mark_review_succeeded(
                job_id, row["snapshot_id"], saved["id"], cached=False,
                input_tokens=completion.input_tokens, output_tokens=completion.output_tokens,
                cached_tokens=completion.cached_tokens,
            )
        final = self.repository.get_job(job_id)
        self.repository.finish_job(
            job_id,
            "partial_failed" if final["failed_count"] else "completed",
        )
