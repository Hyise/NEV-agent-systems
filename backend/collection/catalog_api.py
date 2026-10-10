"""HTTP boundary for vehicle-series catalog discovery and selection."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status

from .catalog_domain import CatalogRunConflict
from .catalog_repository import SeriesCatalogRepository
from .catalog_service import SeriesCatalogService
from .domain import TaskControlError

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
CatalogQuery = Annotated[str, Query(max_length=200)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="车系发现任务不存在")


def create_catalog_router(
    repository: SeriesCatalogRepository, service: SeriesCatalogService
) -> APIRouter:
    router = APIRouter(prefix="/api/collection/catalog", tags=["collection-catalog"])

    @router.get("")
    def list_catalog(
        query: CatalogQuery = "", page: Page = 1, page_size: PageSize = 20
    ):
        return repository.list_catalog(query=query, page=page, page_size=page_size)

    @router.get("/selection")
    def catalog_selection(query: CatalogQuery = ""):
        return repository.selection_result(query=query)

    @router.get("/status")
    def catalog_status():
        return repository.catalog_status()

    @router.post("/discover", status_code=status.HTTP_202_ACCEPTED)
    def start_discovery():
        run_id = str(uuid4())
        batch_id = str(uuid4())
        try:
            service.start(run_id, batch_id)
        except (CatalogRunConflict, TaskControlError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=503, detail="车系发现任务调度失败，请重试"
            ) from error
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=503, detail="车系发现任务未能创建")
        return run

    @router.get("/discover/{run_id}")
    def discovery_detail(run_id: str):
        run = repository.get_run(run_id)
        if run is None:
            raise _not_found()
        return run

    @router.post("/discover/{run_id}/cancel")
    def cancel_discovery(run_id: str):
        try:
            service.cancel(run_id)
        except KeyError as error:
            raise _not_found() from error
        except (CatalogRunConflict, TaskControlError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        run = repository.get_run(run_id)
        if run is None:
            raise _not_found()
        return run

    return router
