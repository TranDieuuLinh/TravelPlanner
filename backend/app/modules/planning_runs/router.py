from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencies import require_role
from app.modules.planning_runs.dependencies import get_planning_run_repository
from app.modules.planning_runs.golden_dataset import (
    get_golden_case,
    golden_modules,
    load_golden_cases,
)
from app.modules.planning_runs.golden_runner import GoldenCaseRunner
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.dependencies import get_plan_service
from app.modules.plans.service import PlanService
from app.modules.planning_runs.schema import (
    PlanningRunDetailRead,
    PlanningRunListRead,
    PlanningRunStageRead,
    PlanningRunSummaryRead,
)
from app.modules.users.model import User
from app.shared.errors import AppError

router = APIRouter(prefix="/admin/planning-runs", tags=["admin-planning-runs"])


@router.get("", response_model=PlanningRunListRead)
def list_planning_runs(
    _: Annotated[User, Depends(require_role("admin"))],
    repository: Annotated[
        PlanningRunRepository,
        Depends(get_planning_run_repository),
    ],
    status: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlanningRunListRead:
    rows, total = repository.list(
        status=status,
        stage=stage,
        query=query,
        limit=limit,
        offset=offset,
    )
    return PlanningRunListRead(
        items=[PlanningRunSummaryRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=PlanningRunDetailRead)
def get_planning_run(
    run_id: str,
    _: Annotated[User, Depends(require_role("admin"))],
    repository: Annotated[
        PlanningRunRepository,
        Depends(get_planning_run_repository),
    ],
) -> PlanningRunDetailRead:
    run, stages = repository.get(run_id)
    if run is None:
        raise AppError(404, "PLANNING_RUN_NOT_FOUND", "Planning run not found.")
    return PlanningRunDetailRead(
        **PlanningRunSummaryRead.model_validate(run).model_dump(),
        errorMessage=run.error_message,
        stages=[
            PlanningRunStageRead.model_validate(stage)
            for stage in stages
        ],
    )


@router.get("/golden/cases")
def list_golden_cases(
    _: Annotated[User, Depends(require_role("admin"))],
    module: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=255),
) -> dict:
    if module is not None and module not in golden_modules():
        raise AppError(
            422,
            "INVALID_GOLDEN_MODULE",
            "Golden dataset module is not supported.",
        )
    items = load_golden_cases(module=module, query=query)
    return {
        "items": items,
        "total": len(items),
        "modules": golden_modules(),
    }


@router.post("/golden/cases/{case_id}/run")
async def run_golden_case(
    case_id: str,
    current_user: Annotated[User, Depends(require_role("admin"))],
    repository: Annotated[
        PlanningRunRepository,
        Depends(get_planning_run_repository),
    ],
    plan_service: Annotated[PlanService, Depends(get_plan_service)],
) -> dict:
    case = get_golden_case(case_id)
    if case is None:
        raise AppError(
            404,
            "GOLDEN_CASE_NOT_FOUND",
            "Golden dataset case was not found.",
        )
    return await GoldenCaseRunner(
        plan_service,
        repository,
    ).run(case, user_id=current_user.id)
