from app.modules.place_checker.checked_output_contract import CheckedPlace
from app.modules.place_checker.enums import SourceTier, VerificationStatus
from app.modules.place_checker.output_contract import (
    PlaceCheckerPlannerOutput,
    PlaceCheckerResult,
    PlannerBudget,
    PlannerOutputFood,
    PlannerOutputPlace,
    PlannerOutputTrip,
    PlannerPrice,
    PlannerTimeWindow,
)
from app.modules.place_checker.planning_projection import PlaceCheckerPlanningProjector
from app.modules.place_checker.price_policy import has_usable_cost, typical_cost
from app.modules.place_checker.food_planning_output import SelectedFoodPlanningProjector

__all__ = ["PlaceCheckerPlannerOutputBuilder", "PlaceCheckerPlanningProjector"]


class PlaceCheckerPlannerOutputBuilder:
    """Build the compact camelCase JSON contract consumed by the planner."""

    def build(
        self,
        result: PlaceCheckerResult,
        *,
        start_date: str,
        timezone: str,
    ) -> PlaceCheckerPlannerOutput:
        places: list[PlannerOutputPlace] = []
        food: list[PlannerOutputFood] = []
        for checked in result.checked_places:
            if not self._eligible(checked):
                continue
            if checked.category in {"restaurant", "drink_dessert"}:
                meals = self._supported_meals(checked)
                if meals:
                    food.append(
                        self._food(checked, result.trip_context.days, meals)
                    )
            else:
                places.append(self._place(checked, result.trip_context.days))
        seen = {place.place_id for place in [*places, *food] if place.place_id}
        for item in result.resolved_items:
            if (
                item.selected is None
                or item.selected.place_id in seen
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
            if item.selected.category in {"restaurant", "drink_dessert"}:
                meals = self._meals_for_hours(item.selected.opening_hours)
                if not meals:
                    continue
                food.append(self._item_food(item, result.trip_context.days, meals))
            else:
                places.append(self._item_place(item, result.trip_context.days))
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
                                [*current.relationships, selection.anchor_place_id]
                            )
                        ),
                        "tags": list(
                            dict.fromkeys(
                                [
                                    *current.tags,
                                    f"food-item:{selection.food_item_id}",
                                    f"food:{selection.food_item_name}",
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
        budget = result.trip_context.budget
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
                budget=PlannerBudget(
                    amount=budget.target_amount,
                    currency=budget.currency or "VND",
                ),
                preferences=result.trip_context.preferences,
            ),
            places=places,
            food=food,
        )

    @staticmethod
    def _eligible(checked: CheckedPlace) -> bool:
        return bool(
            checked.place_id
            and checked.canonical_name
            and checked.coordinates
            and checked.duration.typical_minutes
            and has_usable_cost(
                minimum=checked.cost.minimum,
                typical=checked.cost.typical,
                maximum=checked.cost.maximum,
                tier=checked.cost.tier,
            )
            and checked.evaluation.planner_eligible
            and (checked.mandatory or not checked.evaluation.avoid_conflicts)
            and checked.verification.status
            in {VerificationStatus.verified_kg, VerificationStatus.verified_external}
        )

    @classmethod
    def _place(cls, checked: CheckedPlace, days: int) -> PlannerOutputPlace:
        return PlannerOutputPlace(
            place_id=checked.place_id,
            name=checked.canonical_name or "",
            coordinates=checked.coordinates,
            address=checked.address,
            priority=cls._priority(checked),
            notes=cls._notes(checked),
            tags=checked.tags,
            rating=checked.rating,
            review_count=checked.review_count,
            duration_minutes=checked.duration.typical_minutes,
            opening_hours=cls._opening_hours(checked.opening.hours, days),
            preferred_time_windows=cls._preferred_windows(checked),
            price=cls._price(checked),
            relationships=cls._related_place_ids(checked),
        )

    @classmethod
    def _food(
        cls, checked: CheckedPlace, days: int, supported_meals: list[str]
    ) -> PlannerOutputFood:
        values = cls._place(checked, days).model_dump()
        return PlannerOutputFood(
            **values,
            supported_meals=supported_meals,
        )

    @classmethod
    def _item_place(cls, item, days: int) -> PlannerOutputPlace:
        option = item.selected
        relations = option.relationships
        relation_types = {relation.relationship_type for relation in relations}
        if relation_types & {"Special_Near", "Near"}:
            priority = "special_near"
        elif "Special_Experience" in relation_types:
            priority = "special_experience"
        else:
            priority = "special_experience"
        return PlannerOutputPlace(
            place_id=option.place_id,
            name=option.name,
            coordinates=option.coordinates,
            address=option.address,
            priority=priority,
            notes=item.evidence,
            tags=option.tags,
            rating=option.rating,
            review_count=option.review_count,
            duration_minutes=option.typical_duration_minutes,
            opening_hours=cls._opening_hours(option.opening_hours, days),
            preferred_time_windows=[],
            price=PlannerPrice(
                cost=typical_cost(
                    minimum=option.minimum_cost,
                    typical=option.typical_cost,
                    maximum=option.maximum_cost,
                    tier=option.cost_tier,
                ),
                currency=option.cost_currency or "VND",
            ),
            relationships=list(
                dict.fromkeys(
                    relation.related_entity_id
                    for relation in relations
                    if relation.direction == "place_to_place"
                    and relation.related_entity_id
                )
            ),
        )

    @classmethod
    def _item_food(
        cls, item, days: int, supported_meals: list[str]
    ) -> PlannerOutputFood:
        values = cls._item_place(item, days).model_dump()
        return PlannerOutputFood(
            **values,
            supported_meals=supported_meals,
        )

    @staticmethod
    def _related_place_ids(checked: CheckedPlace) -> list[str]:
        return list(
            dict.fromkeys(
                relation.related_entity_id
                for relation in checked.relationship_evidence
                if relation.direction == "place_to_place" and relation.related_entity_id
            )
        )

    @staticmethod
    def _priority(checked: CheckedPlace) -> str:
        if checked.source_tier == SourceTier.direct_user or checked.mandatory:
            return "user_input"
        if checked.source_tier == SourceTier.url:
            return "url"
        types = {relation.relationship_type for relation in checked.relationship_evidence}
        if types & {"Special_Near", "Near"}:
            return "special_near"
        return "special_experience"

    @staticmethod
    def _notes(checked: CheckedPlace) -> str | None:
        prefix = (
            "Cần xác minh đúng địa điểm/chi nhánh trước khi chốt lịch."
            if checked.verification.status == VerificationStatus.provisional
            else None
        )
        direct = next(
            (
                source.evidence
                for source in checked.provenance.source_places
                if source.origin.value != "system" and source.evidence
            ),
            None,
        )
        if direct:
            return f"{prefix} {direct}" if prefix else direct
        nearest = min(
            (
                relation
                for relation in checked.relationship_evidence
                if relation.relationship_type in {"Special_Near", "Near"}
                and relation.distance_km is not None
            ),
            key=lambda relation: relation.distance_km,
            default=None,
        )
        if nearest is None:
            return prefix
        note = (
            f"Cách {nearest.related_name or 'địa điểm liên quan'} "
            f"khoảng {nearest.distance_km:.2f} km theo Knowledge Graph."
        )
        return f"{prefix} {note}" if prefix else note

    @classmethod
    def _preferred_windows(cls, checked: CheckedPlace) -> list[PlannerTimeWindow]:
        values = list(checked.time_preferences)
        for relation in checked.relationship_evidence:
            if relation.relationship_type != "Has_Style":
                continue
            for item in relation.properties.get("time_windows", []):
                if isinstance(item, dict) and item.get("start") and item.get("end"):
                    values.append(f"{item['start']}-{item['end']}")
        return cls._windows(values)

    @classmethod
    def _opening_hours(
        cls, values: list[str] | None, days: int
    ) -> dict[str, list[PlannerTimeWindow]] | None:
        windows = cls._windows(values or [])
        return {str(day): windows for day in range(1, days + 1)} if windows else None

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

    @classmethod
    def _supported_meals(cls, checked: CheckedPlace) -> list[str]:
        if checked.category not in {"restaurant", "drink_dessert"}:
            return []
        return cls._meals_for_hours(checked.opening.hours)

    @classmethod
    def _meals_for_hours(cls, opening_hours: list[str] | None) -> list[str]:
        spans = cls._windows(opening_hours or [])
        if not spans:
            return ["breakfast", "lunch", "dinner"]
        return [
            meal
            for meal, minute in (("breakfast", 480), ("lunch", 720), ("dinner", 1140))
            if any(window.start_minute <= minute <= window.end_minute for window in spans)
        ]

    @staticmethod
    def _price(checked: CheckedPlace) -> PlannerPrice:
        cost = typical_cost(
            minimum=checked.cost.minimum,
            typical=checked.cost.typical,
            maximum=checked.cost.maximum,
            tier=checked.cost.tier,
        )
        return PlannerPrice(
            cost=cost,
            currency=checked.cost.currency or "VND",
        )
