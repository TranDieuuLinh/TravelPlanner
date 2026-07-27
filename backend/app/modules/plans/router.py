from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.modules.plans.dependencies import get_plan_service
from app.modules.plans.schema import (
    BackupPlanCreate,
    ExplorerRequest,
    FeatureMapItem,
    MainPlanCreate,
    PlanBundleRead,
    PlanRead,
    TravelIntentRead,
)
from app.modules.plans.service import PlanService

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/feature-map", response_model=list[FeatureMapItem])
def feature_map(service: Annotated[PlanService, Depends(get_plan_service)]) -> list[FeatureMapItem]:
    return service.feature_map()


@router.post("/explore", response_model=TravelIntentRead)
def explore(payload: ExplorerRequest, service: Annotated[PlanService, Depends(get_plan_service)]) -> TravelIntentRead:
    return service.explore(payload)


@router.post("/main", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
async def create_main_plan(
    payload: MainPlanCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanRead:
    return await service.create_main_plan(payload)


@router.post("/{plan_id}/backup", response_model=PlanBundleRead, status_code=status.HTTP_201_CREATED)
async def create_backup_plan(
    plan_id: str,
    payload: BackupPlanCreate,
    service: Annotated[PlanService, Depends(get_plan_service)],
) -> PlanBundleRead:
    return await service.create_backup_plan(plan_id, payload)
