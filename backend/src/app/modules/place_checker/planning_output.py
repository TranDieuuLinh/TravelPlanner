from app.modules.place_checker.accommodation_planning_output import (
    select_accommodations,
)
from app.modules.place_checker.enums import SourceTier
from app.modules.place_checker.food_planning_output import (
    SelectedFoodPlanningProjector,
    limit_food_pool,
)
from app.modules.place_checker.output_contract import (
    PlaceCheckerPlannerOutput,
    PlannerExcludedCandidate,
    PlaceCheckerResult,
    PlannerOutputFood,
    PlannerOutputPlace,
    PlannerOutputTrip,
    PlannerParty,
    PlannerPreferences,
)
from app.modules.place_checker.planner_semantics import split_trip_preferences
from app.modules.place_checker.planner_budget import (
    AdmCandidateBudgetEstimator,
    build_planner_budget,
)
from app.modules.place_checker.planner_exclusions import build_excluded_candidate
from app.modules.place_checker.planner_eligibility import is_planner_eligible
from app.modules.place_checker.planning_place_projection import PlannerPlaceProjector
from app.modules.place_checker.planning_projection import PlaceCheckerPlanningProjector
from app.modules.place_checker.planning_time_windows import meals_for_hours
from app.modules.place_checker.pool_policy import (
    food_pool_target_for_days,
    planner_pool_shortfall,
)
from app.modules.place_checker.price_policy import has_usable_cost

__all__ = ["PlaceCheckerPlannerOutputBuilder", "PlaceCheckerPlanningProjector"]


class PlaceCheckerPlannerOutputBuilder:
    """Build the compact camelCase JSON contract consumed by the planner."""

    def __init__(
        self,
        budget_estimator: AdmCandidateBudgetEstimator | None = None,
    ) -> None:
        self.budget_estimator = budget_estimator or AdmCandidateBudgetEstimator()

    def build(
        self,
        result: PlaceCheckerResult,
        *,
        start_date: str,
        timezone: str,
    ) -> PlaceCheckerPlannerOutput:
        places, food, excluded_candidates = self._candidate_pools(result)
        accommodations = select_accommodations(result)
        preference_tags, avoid_tags, styles = split_trip_preferences(
            result.trip_context.preferences,
            result.trip_context.avoids,
        )
        return PlaceCheckerPlannerOutput(
            trip=PlannerOutputTrip(
                destination=(
                    result.trip_context.destination.canonical_name
                    or result.trip_context.destination.input_name
                ),
                days=result.trip_context.days,
                start_date=start_date,
                timezone=timezone,
                people=result.trip_context.people.total,
                party=PlannerParty(
                    adults=result.trip_context.people.adults,
                    kids=(
                        result.trip_context.people.children
                        + result.trip_context.people.infants
                    ),
                ),
                budget=build_planner_budget(
                    result,
                    self.budget_estimator,
                    places=places,
                    food=food,
                ),
                preferences=PlannerPreferences(
                    tags=preference_tags,
                    avoid_tags=avoid_tags,
                    styles=styles,
                ),
            ),
            places=places,
            food=food,
            food_coverage=result.food_meal_coverage,
            accommodations=accommodations,
            excluded_candidates=excluded_candidates,
        )

    def pool_shortfall(self, result: PlaceCheckerResult) -> tuple[int, int, int, int]:
        """Measure the exact eligible pools that would be sent to Planner."""
        places, food, _ = self._candidate_pools(result)
        shortfall = planner_pool_shortfall(
            days=result.trip_context.days,
            travel_place_count=len(places),
            food_count=len(food),
            food_meal_counts={
                meal: sum(meal in candidate.supported_meals for candidate in food)
                for meal in ("breakfast", "lunch", "dinner")
            },
        )
        return (
            shortfall[0],
            shortfall[1],
            shortfall[2],
            max(shortfall[3], len(result.food_meal_coverage.hard_missing_slots)),
        )

    def unpaired_travel_place_ids(self, result: PlaceCheckerResult) -> list[str]:
        """Return travel places without a linked special-near restaurant."""
        places, food, _ = self._candidate_pools(result)
        paired_place_ids = {
            related_place_id
            for restaurant in food
            for related_place_id in restaurant.relationships
        }
        return [
            place.place_id for place in places if place.place_id not in paired_place_ids
        ]

    def _candidate_pools(
        self, result: PlaceCheckerResult
    ) -> tuple[
        list[PlannerOutputPlace],
        list[PlannerOutputFood],
        list[PlannerExcludedCandidate],
    ]:
        places: list[PlannerOutputPlace] = []
        food: list[PlannerOutputFood] = []
        excluded_candidates: list[PlannerExcludedCandidate] = []
        for checked in result.checked_places:
            if checked.category == "accommodation":
                continue
            if not is_planner_eligible(checked):
                if checked.mandatory or checked.source_tier in {
                    SourceTier.direct_user,
                    SourceTier.url,
                }:
                    excluded_candidates.append(build_excluded_candidate(checked))
                continue
            if checked.category in {"restaurant", "drink_dessert"}:
                meals = meals_for_hours(checked.opening.hours)
                if meals:
                    food.append(
                        PlannerPlaceProjector.food(
                            checked, result.trip_context.days, meals
                        )
                    )
            else:
                places.append(
                    PlannerPlaceProjector.place(checked, result.trip_context.days)
                )
        seen = {place.place_id for place in [*places, *food] if place.place_id}
        for item in result.resolved_items:
            if (
                item.selected is None
                or item.selected.coordinates is None
                or item.selected.typical_duration_minutes is None
                or not has_usable_cost(
                    minimum=item.selected.minimum_cost,
                    typical=item.selected.typical_cost,
                    maximum=item.selected.maximum_cost,
                    tier=item.selected.cost_tier,
                )
            ):
                continue
            if item.selected.place_id in seen:
                places = self._promote_user_input(places, item.selected.place_id)
                food = self._promote_user_input(food, item.selected.place_id)
                continue
            if item.selected.category in {"restaurant", "drink_dessert"}:
                meals = meals_for_hours(item.selected.opening_hours)
                if not meals:
                    continue
                food.append(
                    PlannerPlaceProjector.item_food(
                        item, result.trip_context.days, meals
                    )
                )
            else:
                places.append(
                    PlannerPlaceProjector.item_place(item, result.trip_context.days)
                )
            seen.add(item.selected.place_id)
        for selection in result.food_restaurant_selections:
            existing_index = next(
                (
                    index
                    for index, candidate in enumerate(food)
                    if candidate.place_id == selection.restaurant_id
                ),
                None,
            )
            if existing_index is not None:
                current = food[existing_index]
                food[existing_index] = current.model_copy(
                    update={
                        "relationships": list(
                            dict.fromkeys(
                                [
                                    *current.relationships,
                                    *selection.related_anchor_place_ids,
                                ]
                            )
                        ),
                    }
                )
                continue
            pairing = SelectedFoodPlanningProjector.project(
                selection,
                days=result.trip_context.days,
            )
            if pairing is not None and pairing.place_id not in seen:
                food.append(pairing)
                seen.add(pairing.place_id)
        required_food_ids = {
            checked.place_id
            for checked in result.checked_places
            if checked.place_id
            and checked.category in {"restaurant", "drink_dessert"}
            and (
                checked.mandatory
                or checked.source_tier in {SourceTier.direct_user, SourceTier.url}
            )
        }
        required_food_ids.update(
            item.selected.place_id
            for item in result.resolved_items
            if item.selected is not None
        )
        paired_food_ids = {
            selection.restaurant_id for selection in result.food_restaurant_selections
        }
        food = limit_food_pool(
            food,
            limit=food_pool_target_for_days(result.trip_context.days),
            required_ids=required_food_ids,
            paired_ids=paired_food_ids,
        )
        return places, food, excluded_candidates

    _limit_food_pool = staticmethod(limit_food_pool)

    @staticmethod
    def _promote_user_input(candidates: list, place_id: str) -> list:
        return [
            candidate.model_copy(update={"priority": "user_input"})
            if candidate.place_id == place_id
            else candidate
            for candidate in candidates
        ]
