"""Project-scoped HTTP contracts for review analysis."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import CreateJobCommand, CriterionSnapshot, ProposalCriterion, ReviewSnapshot, schema_fingerprint, stable_stratified_sample
from .prompting import PromptRenderer
from .text import extract_analysis_text


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DiscoveryBody(_Strict):
    schema_id: str
    selected_series_ids: list[str] = Field(min_length=1, max_length=1000)
    sample_limit: int = Field(default=1500, ge=1, le=5000)

    @field_validator("selected_series_ids")
    @classmethod
    def unique(cls, values):
        if len(values) != len(set(values)): raise ValueError("车系不能重复")
        return values


class AnnotationBody(_Strict):
    schema_id: str
    selected_series_ids: list[str] = Field(min_length=1, max_length=1000)
    limit: int | None = Field(default=100, ge=1, le=5000)

    @field_validator("selected_series_ids")
    @classmethod
    def unique(cls, values):
        if len(values) != len(set(values)): raise ValueError("车系不能重复")
        return values


class ApplyBody(_Strict):
    revision: int = Field(ge=1)
    criteria: list[ProposalCriterion] | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_names(self):
        if self.criteria:
            names = [item.name for item in self.criteria]
            if len(names) != len(set(names)):
                raise ValueError("准则名称不能重复")
        return self


def _snapshots(assets, limit):
    selected = stable_stratified_sample(assets, limit or len(assets))
    return [ReviewSnapshot(source_asset_id=item.asset_id,
                           review_id=item.review_id, series_id=item.series_id,
                           series_name=item.series_name, content_hash=item.content_hash,
                           analysis_text=extract_analysis_text(item.original_review), ordinal=index)
            for index, item in enumerate(selected)]


def create_review_analysis_router(repository, service, settings) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/review-analysis", tags=["review-analysis"])
    renderer = PromptRenderer()

    def configured():
        if settings is None or service is None:
            raise HTTPException(503, "尚未配置 DEEPSEEK_API_KEY；其他本机功能仍可使用")

    def project_schema(project_id, schema_id):
        result = repository.get_project_schema(project_id, schema_id)
        if result is None: raise HTTPException(404, "项目或准则版本不存在")
        return result

    def project_job(project_id: str, job_id: str):
        value = repository.get_job(job_id)
        if value is None or value["project_id"] != project_id:
            raise HTTPException(404, "任务不存在")
        return value

    def create(command, limit):
        try:
            job = repository.create_job_with_snapshot(command, lambda assets: _snapshots(assets, limit))
            service.start(job["id"])
            return job
        except ValueError as exc:
            message = str(exc)
            status = 409 if "活动" in message else 422
            raise HTTPException(status, message) from exc

    @router.get("/sources")
    def sources(project_id: str, query: str = "", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        return repository.list_sources(query, page, page_size)

    @router.post("/discovery-jobs", status_code=201)
    def discovery_job(project_id: str, body: DiscoveryBody):
        configured(); project, schema = project_schema(project_id, body.schema_id)
        if project["mode"] != "custom" or schema["status"] != "draft":
            raise HTTPException(409, "准则发现只能应用到自定义项目草稿")
        prompts = [renderer.discovery_batch(["占位"]), renderer.criteria_merge([])]
        command = CreateJobCommand(project_id=project_id, schema_id=body.schema_id,
            job_type="criteria_discovery", selected_series_ids=body.selected_series_ids,
            schema_revision=schema["revision"],
            limit=body.sample_limit, model=settings.model,
            prompt_manifests=[item.manifest for item in prompts])
        return create(command, body.sample_limit)

    @router.post("/annotation-jobs", status_code=201)
    def annotation_job(project_id: str, body: AnnotationBody):
        configured(); project, schema = project_schema(project_id, body.schema_id)
        if project["mode"] != "custom" or schema["status"] != "frozen":
            raise HTTPException(409, "逐条评论标注只能使用自定义项目的冻结准则版本")
        criteria = [CriterionSnapshot.model_validate(item) for item in schema["criteria"]]
        prompt = renderer.review_annotation(criteria, "占位")
        command = CreateJobCommand(project_id=project_id, schema_id=body.schema_id,
            job_type="review_annotation", selected_series_ids=body.selected_series_ids,
            schema_revision=schema["revision"],
            limit=body.limit, model=settings.model, prompt_manifests=[prompt.manifest],
            schema_fingerprint=schema_fingerprint(criteria), criteria=criteria)
        return create(command, body.limit)

    @router.get("/jobs")
    def jobs(project_id: str, page: int = 1, page_size: int = 20): return repository.list_jobs(project_id, page, page_size)

    @router.get("/jobs/{job_id}")
    def job(project_id: str, job_id: str):
        return project_job(project_id, job_id)

    @router.post("/jobs/{job_id}/{action}")
    def control(project_id: str, job_id: str, action: Literal["pause", "resume", "cancel", "retry-failures"]):
        configured()
        project_job(project_id, job_id)
        try:
            if action == "pause": service.pause(job_id); return repository.get_job(job_id)
            if action == "resume": service.resume(job_id); return repository.get_job(job_id)
            if action == "cancel": service.cancel(job_id); return repository.get_job(job_id)
            return service.retry_failures(job_id)
        except (ValueError, KeyError) as exc: raise HTTPException(409, str(exc)) from exc

    @router.get("/jobs/{job_id}/proposal")
    def proposal(project_id: str, job_id: str):
        project_job(project_id, job_id)
        value = repository.get_proposal(job_id)
        if value is None: raise HTTPException(404, "候选方案不存在")
        return value

    @router.post("/jobs/{job_id}/proposal/apply")
    def apply_proposal(project_id: str, job_id: str, body: ApplyBody):
        project_job(project_id, job_id)
        try: return repository.apply_proposal(job_id, body.revision, body.criteria)
        except KeyError as exc: raise HTTPException(404, "候选方案不存在") from exc
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc

    @router.get("/annotations")
    def annotations(project_id: str, job_id: str | None = None, series_id: str | None = None,
                    criterion: str | None = None, label: str | None = None, status: str | None = None,
                    page: int = 1, page_size: int = 20):
        return repository.list_annotations(project_id, job_id=job_id, series_id=series_id,
            criterion=criterion, label=label, status=status, page=page, page_size=page_size)

    @router.get("/annotations/{annotation_id}")
    def annotation(project_id: str, annotation_id: str):
        value = repository.get_annotation(project_id, annotation_id)
        if value is None: raise HTTPException(404, "标注不存在")
        return value

    @router.get("/summary")
    def summary(project_id: str, job_id: str | None = None): return repository.annotation_summary(project_id, job_id)
    return router
