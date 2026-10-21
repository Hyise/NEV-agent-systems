from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateExperimentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_id: str
    model_keys: list[str] = Field(
        default_factory=lambda: ["ridge", "random_forest", "beast_mcdm"],
        min_length=1,
        max_length=5,
    )
    validation_months: int = Field(default=2, ge=1, le=12)
    test_months: int = Field(default=2, ge=1, le=12)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    simulations: int = Field(default=128, ge=16, le=2000)

    @field_validator("model_keys")
    @classmethod
    def unique_models(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("模型不能重复")
        return value


def create_model_experiment_router(repository, service, engine, snapshot_factory):
    router = APIRouter(
        prefix="/api/projects/{project_id}/model-experiments",
        tags=["model-experiments"],
    )

    def scoped(project_id, run_id):
        run = repository.get(run_id)
        if run is None or run["project_id"] != project_id:
            raise HTTPException(404, "模型实验不存在")
        return run

    @router.get("/capabilities")
    def capabilities(project_id: str):
        snapshot_factory(project_id, None, validate_only=True)
        return engine.capabilities()

    @router.get("")
    def runs(
        project_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ):
        snapshot_factory(project_id, None, validate_only=True)
        return repository.list(project_id, page, page_size)

    @router.post("", status_code=201)
    def create(project_id: str, body: CreateExperimentBody):
        known = {item["key"]: item for item in engine.capabilities()}
        unknown = [key for key in body.model_keys if key not in known]
        if unknown:
            raise HTTPException(422, f"未知模型：{', '.join(unknown)}")
        unavailable = [
            known[key]["label"]
            for key in body.model_keys
            if not known[key]["available"]
        ]
        if unavailable:
            raise HTTPException(422, f"模型依赖尚未安装：{', '.join(unavailable)}")
        snapshot = snapshot_factory(project_id, body.schema_id)
        config = body.model_dump(exclude={"schema_id"})
        try:
            run = repository.create(project_id, body.schema_id, snapshot, config)
            service.start(run["id"])
            return run
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/{run_id}")
    def detail(project_id: str, run_id: str):
        return scoped(project_id, run_id)

    @router.post("/{run_id}/cancel")
    def cancel(project_id: str, run_id: str):
        scoped(project_id, run_id)
        try:
            return service.cancel(run_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
