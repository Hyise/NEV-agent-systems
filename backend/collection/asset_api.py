"""HTTP boundary for review asset querying and management metadata."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from .asset_domain import (
    AssetConflict,
    AssetGone,
    AssetNotFound,
    BatchMetadataPatchBody,
    DeleteAssetBody,
    ImportBatchBody,
    ImportConfirmBody,
    ImportValidationError,
    MetadataPatchBody,
)
from .asset_repository import ReviewAssetRepository
from .asset_service import ReviewAssetService

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def _run(action):
    try:
        return action()
    except AssetNotFound as error:
        raise HTTPException(status_code=404, detail="评论资产不存在") from error
    except AssetGone as error:
        raise HTTPException(
            status_code=410,
            detail={"message": str(error), "deletion": error.audit},
        ) from error
    except AssetConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ImportValidationError as error:
        raise HTTPException(status_code=422, detail=error.result) from error


def create_review_asset_router(
    repository: ReviewAssetRepository, service: ReviewAssetService
) -> APIRouter:
    router = APIRouter(prefix="/api/collection", tags=["review-assets"])

    @router.get("/review-assets")
    def list_assets(
        keyword: str = "",
        series_id: str | None = None,
        source_kind: str | None = None,
        tag: str | None = None,
        analysis_enabled: bool | None = None,
        page: Page = 1,
        page_size: PageSize = 20,
    ) -> dict[str, Any]:
        return repository.list_assets(
            keyword=keyword,
            series_id=series_id,
            source_kind=source_kind,
            tag=tag,
            analysis_enabled=analysis_enabled,
            page=page,
            page_size=page_size,
        )

    @router.get("/review-assets/summary")
    def asset_summary() -> dict[str, Any]:
        return repository.summary()

    @router.patch("/review-assets/metadata")
    def batch_update_metadata(body: BatchMetadataPatchBody) -> dict[str, int]:
        return _run(lambda: repository.batch_update_metadata(body))

    @router.post("/review-assets/import/validate")
    def validate_import(body: ImportBatchBody) -> dict[str, Any]:
        return service.validate_import(body.items, body.payload_bytes)

    @router.post("/review-assets/import", status_code=201)
    def import_reviews(body: ImportConfirmBody) -> dict[str, Any]:
        return _run(
            lambda: service.import_validated(
                body.items, body.payload_bytes, body.validation_fingerprint
            )
        )

    @router.get("/deletions")
    def list_deletions(
        page: Page = 1, page_size: PageSize = 20
    ) -> dict[str, Any]:
        return repository.list_deletions(page=page, page_size=page_size)

    @router.post("/deletions/{asset_id}/allow-recollection")
    def allow_recollection(asset_id: str) -> dict[str, Any]:
        return _run(lambda: service.allow_recollection(asset_id))

    @router.get("/review-assets/{asset_id}")
    def asset_detail(asset_id: str) -> dict[str, Any]:
        return _run(lambda: repository.get_asset(asset_id))

    @router.patch("/review-assets/{asset_id}/metadata")
    def update_metadata(asset_id: str, body: MetadataPatchBody) -> dict[str, Any]:
        return _run(lambda: repository.update_metadata(asset_id, body))

    @router.delete("/review-assets/{asset_id}")
    def delete_asset(asset_id: str, body: DeleteAssetBody) -> dict[str, Any]:
        return _run(lambda: service.delete_asset(asset_id, body))

    return router
