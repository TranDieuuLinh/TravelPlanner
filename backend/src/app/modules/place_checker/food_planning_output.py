from app.modules.place_checker.food_selection_contract import SelectedFoodRestaurant
from app.modules.place_checker.output_contract import (
    PlannerOutputFood,
    PlannerPrice,
    PlannerTimeWindow,
)
from app.modules.place_checker.price_policy import has_usable_cost, typical_cost


class SelectedFoodPlanningProjector:
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
        bayesian_note = (
            f" Bayesian rating {selection.bayesian_rating:.2f}/5."
            if selection.bayesian_rating is not None
            else ""
        )
        return PlannerOutputFood(
            place_id=selection.restaurant_id,
            name=selection.restaurant_name,
            coordinates=metadata.coordinates,
            address=metadata.address,
            priority="special_near",
            notes=(
                f"Gần {selection.anchor_name}; phục vụ món đặc trưng "
                f"{selection.food_item_name}.{bayesian_note}"
            ),
            tags=list(
                dict.fromkeys(
                    [
                        *metadata.tags,
                        f"food-item:{selection.food_item_id}",
                        f"food:{selection.food_item_name}",
                    ]
                )
            ),
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
            relationships=[selection.anchor_place_id],
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
            if any(window.start_minute <= minute <= window.end_minute for window in windows)
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
