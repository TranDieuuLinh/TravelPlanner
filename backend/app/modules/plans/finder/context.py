from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import (
    FinderPlanStatus,
    MacroPlan,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext


class FinderContext(BaseModel):
    selected_places: list[SelectedPlaceContext] = Field(
        default_factory=list,
        alias="selectedPlaces",
    )
    macro_plan: MacroPlan = Field(alias="macroPlan")
    intent: TravelIntent
    user_status: UserStatus = Field(default_factory=UserStatus, alias="userStatus")
    plan_status: FinderPlanStatus = Field(
        default_factory=FinderPlanStatus,
        alias="planStatus",
    )

    model_config = {"populate_by_name": True}
