from pydantic import BaseModel, Field

from app.modules.plans.domain.entities import MacroPlan, TravelIntent


class FinderContext(BaseModel):
    selected_places: list[str] = Field(default_factory=list, alias="selectedPlaces")
    macro_plan: MacroPlan = Field(alias="macroPlan")
    intent: TravelIntent

    model_config = {"populate_by_name": True}
