from typing import Literal

from pydantic import Field

from app.modules.place_checker.contract import ContractModel
from app.modules.place_checker.resolution_contract import PlaceMetadata


class FoodSelectionAnchor(ContractModel):
    place_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)


class FoodRestaurantCandidate(ContractModel):
    anchor_place_id: str = Field(min_length=1, max_length=200)
    food_item_id: str = Field(min_length=1, max_length=200)
    food_item_name: str = Field(min_length=1, max_length=200)
    food_priority: float = Field(default=0.5, ge=0, le=1)
    food_confidence: float = Field(default=0.7, ge=0, le=1)
    restaurant_id: str = Field(min_length=1, max_length=200)
    restaurant_name: str = Field(min_length=1, max_length=200)
    offer_confidence: float = Field(default=0.7, ge=0, le=1)
    distance_km: float | None = Field(default=None, ge=0)
    threshold_km: float | None = Field(default=None, gt=0)
    metadata: PlaceMetadata


class SelectedFoodRestaurant(ContractModel):
    anchor_place_id: str = Field(min_length=1, max_length=200)
    anchor_name: str = Field(min_length=1, max_length=200)
    food_item_id: str = Field(min_length=1, max_length=200)
    food_item_name: str = Field(min_length=1, max_length=200)
    restaurant_id: str = Field(min_length=1, max_length=200)
    restaurant_name: str = Field(min_length=1, max_length=200)
    distance_km: float | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    bayesian_rating: float | None = Field(default=None, ge=0, le=5)
    pair_score: float = Field(ge=0, le=1)
    selection_reason: Literal[
        "sole_candidate_for_food",
        "bayesian_ranked",
        "quality_fallback",
    ]
    metadata: PlaceMetadata


class FoodSelectionBatch(ContractModel):
    selections: list[SelectedFoodRestaurant] = Field(default_factory=list)
    unmatched_anchor_place_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
