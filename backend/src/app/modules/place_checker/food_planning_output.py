from app.modules.place_checker.food_selection_contract import SelectedFoodRestaurant
from app.modules.place_checker.output_contract import (
    PlannerAudience,
    PlannerOutputEntertainment,
    PlannerOutputFood,
    PlannerPrice,
    PlannerTimeWindow,
)
from app.modules.place_checker.planner_semantics import (
    audience_values,
    candidate_semantics,
)
from app.modules.place_checker.planner_category import planner_category
from app.modules.place_checker.price_policy import has_usable_cost, typical_cost
from app.shared.contracts.source_note import SourceNote


def limit_food_pool(
    food: list[PlannerOutputFood],
    *,
    limit: int,
    required_ids: set[str],
    paired_ids: set[str],
) -> list[PlannerOutputFood]:
    if len(food) <= limit:
        return food
    required = [candidate for candidate in food if candidate.place_id in required_ids]
    paired = [
        candidate
        for candidate in food
        if candidate.place_id in paired_ids and candidate.place_id not in required_ids
    ]
    optional = [
        candidate
        for candidate in food
        if candidate.place_id not in required_ids
        and candidate.place_id not in paired_ids
    ]
    remaining = max(0, limit - len(required))
    return [*required, *paired[:remaining], *optional[: max(0, remaining - len(paired))]]


class SelectedFoodPlanningProjector:
    @classmethod
    def project_entertainment(
        cls,
        selection: SelectedFoodRestaurant,
        *,
        days: int,
    ) -> PlannerOutputEntertainment | None:
        """Project DrinkDessert selections into the optional entertainment pool."""
        projected = cls.project(selection, days=days)
        if projected is None:
            return None
        return PlannerOutputEntertainment.model_validate(
            {
                **projected.model_dump(exclude={"venue_type", "supported_meals"}),
                "entity_type": "drink_dessert",
            }
        )

    @classmethod
    def project(
        cls,
        selection: SelectedFoodRestaurant,
        *,
        days: int,
    ) -> PlannerOutputFood | None:
        metadata = selection.metadata
        if (
            metadata.coordinates is None
            or metadata.typical_duration_minutes is None
            or not has_usable_cost(
                minimum=metadata.minimum_cost,
                typical=metadata.typical_cost,
                maximum=metadata.maximum_cost,
                tier=metadata.cost_tier,
            )
        ):
            return None
        meals = cls._meals(metadata.opening_hours)
        if not meals:
            return None
        tags, styles = candidate_semantics(metadata.tags, metadata.relationships)
        if planner_category(metadata.category) == "drink_dessert" and "drink_dessert" not in tags:
            tags.append("drink_dessert")
        adult_only, kid_suitable = audience_values(
            adults=True,
            children=metadata.children_suitable,
            infants=metadata.infants_suitable,
        )
        return PlannerOutputFood(
            place_id=selection.restaurant_id,
            name=selection.restaurant_name,
            coordinates=metadata.coordinates,
            address=metadata.address,
            priority=(
                "special_near"
                if selection.proximity_source != "general_adm"
                else "special_experience"
            ),
            notes=SourceNote(
                text=(
                    f"Gần {selection.anchor_name}; phục vụ món đặc trưng "
                    f"{selection.food_item_name}."
                ),
                source_type="knowledge_graph",
            ),
            tags=tags,
            styles=styles,
            audience=PlannerAudience(
                adult_only=adult_only,
                kid_suitable=kid_suitable,
            ),
            image_urls=metadata.image_urls,
            rating=metadata.rating,
            review_count=metadata.review_count,
            duration_minutes=metadata.typical_duration_minutes,
            opening_hours=cls._opening_hours(metadata.opening_hours, days),
            preferred_time_windows=[],
            price=PlannerPrice(
                cost=typical_cost(
                    minimum=metadata.minimum_cost,
                    typical=metadata.typical_cost,
                    maximum=metadata.maximum_cost,
                    tier=metadata.cost_tier,
                ),
                currency=metadata.cost_currency or "VND",
            ),
            relationships=list(selection.related_anchor_place_ids),
            venue_type="restaurant",
            supported_meals=meals,
        )

    @classmethod
    def _opening_hours(
        cls,
        values: list[str] | None,
        days: int,
    ) -> dict[str, list[PlannerTimeWindow]] | None:
        windows = cls._windows(values or [])
        return {str(day): windows for day in range(1, days + 1)} if windows else None

    @classmethod
    def _meals(cls, values: list[str] | None) -> list[str]:
        windows = cls._windows(values or [])
        if not windows:
            return ["breakfast", "lunch", "dinner"]
        return [
            meal
            for meal, minute in (("breakfast", 480), ("lunch", 720), ("dinner", 1140))
            if any(
                window.start_minute <= minute <= window.end_minute for window in windows
            )
        ]

    @staticmethod
    def _windows(values: list[str]) -> list[PlannerTimeWindow]:
        result: list[PlannerTimeWindow] = []
        for value in values:
            if "-" not in value:
                continue
            start, end = value.split("-", 1)
            try:
                start_hour, start_minute = (int(part) for part in start.split(":"))
                end_hour, end_minute = (int(part) for part in end.split(":"))
            except (TypeError, ValueError):
                continue
            start_total = start_hour * 60 + start_minute
            end_total = end_hour * 60 + end_minute
            if start_total == end_total:
                end_total = 1440
            if not (0 <= start_total <= 1439 and 0 <= end_total <= 1440):
                continue
            window = PlannerTimeWindow(
                start_minute=start_total,
                end_minute=end_total,
            )
            if window not in result:
                result.append(window)
        return result
