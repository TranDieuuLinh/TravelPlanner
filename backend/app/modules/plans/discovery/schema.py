from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.modules.plans.domain.enums import TravelPace
from app.modules.plans.dto.agent_contracts import BudgetEnvelope


class DestinationDiscoveryRequest(BaseModel):
    """Inputs needed to recommend a destination before macro planning."""

    days: Annotated[int, Field(ge=1, le=30)]
    budget: BudgetEnvelope
    origin_region_key: Annotated[
        str | None,
        Field(default=None, alias="originRegionKey"),
    ]
    interests: list[str] = Field(default_factory=list, max_length=12)
    pace: TravelPace = TravelPace.balanced
    budget_includes_transport: Annotated[
        bool,
        Field(default=False, alias="budgetIncludesTransport"),
    ]
    budget_includes_accommodation: Annotated[
        bool,
        Field(default=False, alias="budgetIncludesAccommodation"),
    ]
    limit: Annotated[int, Field(ge=1, le=10)] = 5

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def require_numeric_budget(self) -> "DestinationDiscoveryRequest":
        if self.budget.target_amount is None or self.budget.target_amount <= 0:
            raise ValueError("budget.targetAmount must be greater than zero")
        return self


class DestinationProposal(BaseModel):
    region_key: Annotated[str, Field(alias="regionKey")]
    destination: str
    score: Annotated[float, Field(ge=0, le=1)]
    catalog_place_count: Annotated[int, Field(ge=0, alias="catalogPlaceCount")]
    matching_place_count: Annotated[int, Field(ge=0, alias="matchingPlaceCount")]
    matched_interests: Annotated[list[str], Field(alias="matchedInterests")]
    estimated_catalog_activity_cost: Annotated[
        int | None,
        Field(default=None, alias="estimatedCatalogActivityCost"),
    ]
    budget_fit: Annotated[
        Literal["fits", "uncertain", "exceeds"],
        Field(alias="budgetFit"),
    ]
    data_confidence: Annotated[
        Literal["low", "medium", "high"],
        Field(alias="dataConfidence"),
    ]
    knowledge_graph_available: Annotated[
        bool,
        Field(alias="knowledgeGraphAvailable"),
    ]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class DestinationDiscoveryResponse(BaseModel):
    proposals: list[DestinationProposal] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
