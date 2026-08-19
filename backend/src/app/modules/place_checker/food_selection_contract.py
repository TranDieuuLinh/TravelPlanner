from typing import Literal

from pydantic import Field, model_validator

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
    offered_food_item_id: str = Field(min_length=1, max_length=200)
    offered_food_item_name: str = Field(min_length=1, max_length=200)
    style_id: str | None = Field(default=None, max_length=200)
    style_name: str | None = Field(default=None, max_length=200)
    food_match_type: Literal[
        "direct_id",
        "offer_item_fallback",
    ]
    food_match_confidence: float = Field(ge=0, le=1)
    restaurant_id: str = Field(min_length=1, max_length=200)
    restaurant_name: str = Field(min_length=1, max_length=200)
    offer_confidence: float = Field(default=0.7, ge=0, le=1)
    distance_km: float | None = Field(default=None, ge=0)
    threshold_km: float | None = Field(default=None, gt=0)
    proximity_source: Literal[
        "kg_special_near",
        "computed_distance",
        "both",
        "general_adm",
    ] = "computed_distance"
    metadata: PlaceMetadata


class SelectedFoodRestaurant(ContractModel):
    anchor_place_id: str = Field(min_length=1, max_length=200)
    anchor_name: str = Field(min_length=1, max_length=200)
    related_anchor_place_ids: list[str] = Field(default_factory=list)
    food_item_id: str = Field(min_length=1, max_length=200)
    food_item_name: str = Field(min_length=1, max_length=200)
    offered_food_item_id: str = Field(min_length=1, max_length=200)
    offered_food_item_name: str = Field(min_length=1, max_length=200)
    style_id: str | None = Field(default=None, max_length=200)
    style_name: str | None = Field(default=None, max_length=200)
    food_match_type: Literal[
        "direct_id",
        "offer_item_fallback",
    ]
    food_match_confidence: float = Field(ge=0, le=1)
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
        "style_item_diversity",
    ]
    proximity_source: Literal[
        "kg_special_near",
        "computed_distance",
        "both",
        "general_adm",
    ] = "computed_distance"
    evidence_types: list[str] = Field(default_factory=list)
    metadata: PlaceMetadata

    @model_validator(mode="after")
    def keep_primary_anchor_relationship(self) -> "SelectedFoodRestaurant":
        if not self.related_anchor_place_ids and self.proximity_source != "general_adm":
            self.related_anchor_place_ids = [self.anchor_place_id]
        else:
            self.related_anchor_place_ids = list(
                dict.fromkeys(self.related_anchor_place_ids)
            )
        return self


MealName = Literal["breakfast", "lunch", "dinner"]


class FoodMealSlot(ContractModel):
    day: int = Field(ge=1, le=30)
    meal: MealName


class FoodMealSlotAssignment(FoodMealSlot):
    restaurant_id: str = Field(min_length=1, max_length=200)


class FoodMealCoverage(ContractModel):
    days: int = Field(default=0, ge=0, le=30)
    hard_complete: bool = False
    reserve_complete: bool = False
    hard_assignments: list[FoodMealSlotAssignment] = Field(default_factory=list)
    hard_missing_slots: list[FoodMealSlot] = Field(default_factory=list)
    reserve_assignments: list[FoodMealSlotAssignment] = Field(default_factory=list)
    reserve_missing_slots: list[FoodMealSlot] = Field(default_factory=list)


class FoodStyleCoverage(ContractModel):
    style_id: str = Field(min_length=1, max_length=200)
    style_name: str = Field(min_length=1, max_length=200)
    target_items: int = Field(ge=0)
    selected_restaurants: int = Field(ge=0)
    distinct_items: int = Field(ge=0)
    complete: bool = False


class FoodSelectionBatch(ContractModel):
    selections: list[SelectedFoodRestaurant] = Field(default_factory=list)
    unmatched_anchor_place_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meal_coverage: FoodMealCoverage = Field(default_factory=FoodMealCoverage)
    style_coverage: list[FoodStyleCoverage] = Field(default_factory=list)
