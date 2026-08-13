from app.modules.place_checker.checked_output_contract import CheckedPlace
from app.modules.place_checker.enums import (
    PlaceLifecycleState,
    SourceTier,
    VerificationStatus,
)
from app.modules.place_checker.output_contract import (
    PlaceCheckerPlannerOutput,
    PlaceCheckerPlanningProjection,
    PlaceCheckerResult,
    PlannerBudget,
    PlannerOutputFood,
    PlannerOutputPlace,
    PlannerOutputTrip,
    PlannerPlaceContext,
    PlannerPrice,
    PlannerTimeWindow,
)


class PlaceCheckerPlanningProjector:
    def project(self, result: PlaceCheckerResult) -> PlaceCheckerPlanningProjection:
        places: list[PlannerPlaceContext] = []
        blocked: list[str] = []
        warnings = list(result.warnings)
        for checked in result.checked_places:
            evaluation = checked.internal_evaluation
            if evaluation is None:
                warnings.append(
                    f"Bỏ qua {checked.canonical_name or 'place'} do thiếu internal evaluation."
                )
                continue
            if checked.mandatory and evaluation.state == PlaceLifecycleState.blocked:
                if checked.place_id:
                    blocked.append(checked.place_id)
                continue
            if not evaluation.planner_eligible:
                continue
            if checked.verification.status not in {
                VerificationStatus.verified_kg,
                VerificationStatus.verified_external,
            }:
                continue
            metadata = evaluation.place.metadata
            if not checked.place_id or not checked.canonical_name or metadata is None:
                warnings.append("Bỏ qua place thiếu canonical identity hoặc metadata.")
                continue
            if metadata.coordinates is None or not evaluation.place.source_places:
                warnings.append(f"Bỏ qua {checked.canonical_name} do thiếu tọa độ/provenance.")
                continue
            places.append(self._place(checked, evaluation, metadata))
        destination_id = result.trip_context.destination.adm_id or "unresolved"
        return PlaceCheckerPlanningProjection(
            destination_adm_id=destination_id,
            places=places,
            resolved_items=result.resolved_items,
            special_experiences=result.special_experiences,
            blocked_mandatory_place_ids=blocked,
            warnings=list(dict.fromkeys(warnings)),
            metadata={
                "place_checker_request_id": result.metadata.request_id,
                "place_checker_schema_version": result.metadata.schema_version,
            },
        )

    @staticmethod
    def _place(checked, evaluation, metadata) -> PlannerPlaceContext:
        return PlannerPlaceContext(
            place_id=checked.place_id,
            canonical_name=checked.canonical_name,
            coordinates=metadata.coordinates,
            address=checked.address,
            state=evaluation.state,
            source_tier=checked.source_tier,
            mandatory=checked.mandatory,
            removable=checked.removable,
            category=metadata.category,
            pool_category=checked.pool_category,
            tags=metadata.tags,
            rating=checked.rating,
            review_count=checked.review_count,
            distance_from_anchor_km=checked.distance_from_anchor_km,
            relationship_score=checked.relationship_score,
            relationships=PlaceCheckerPlannerOutputBuilder._related_place_ids(checked),
            minimum_duration_minutes=metadata.minimum_duration_minutes,
            typical_duration_minutes=metadata.typical_duration_minutes,
            maximum_duration_minutes=metadata.maximum_duration_minutes,
            cost_tier=metadata.cost_tier,
            minimum_cost=metadata.minimum_cost,
            typical_cost=metadata.typical_cost,
            maximum_cost=metadata.maximum_cost,
            currency=metadata.cost_currency,
            opening_hours=metadata.opening_hours,
            operational_status=metadata.operational_status,
            reservation_required=metadata.reservation_required,
            time_preferences=checked.time_preferences,
            adults_suitable=checked.suitability.adults,
            children_suitable=checked.suitability.children,
            infants_suitable=checked.suitability.infants,
            accessibility=checked.suitability.accessibility,
            verification_status=checked.verification.status,
            identity_confidence=checked.verification.identity_confidence,
            score=checked.ranking.score,
            constraints=evaluation.planner_constraints,
            provenance=evaluation.place.source_places,
            warnings=checked.warnings,
        )


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
                cost=option.typical_cost,
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
        direct = next(
            (
                source.evidence
                for source in checked.provenance.source_places
                if source.origin.value != "system" and source.evidence
            ),
            None,
        )
        if direct:
            return direct
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
            return None
        return (
            f"Cách {nearest.related_name or 'địa điểm liên quan'} "
            f"khoảng {nearest.distance_km:.2f} km theo Knowledge Graph."
        )

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
        minimum = checked.cost.minimum
        maximum = checked.cost.maximum
        if minimum is not None and maximum is not None:
            cost = (minimum + maximum) / 2
        elif checked.cost.typical is not None:
            cost = checked.cost.typical
        elif checked.cost.tier.value == "free":
            cost = 0
            minimum = minimum if minimum is not None else 0
            maximum = maximum if maximum is not None else 0
        else:
            cost = None
        return PlannerPrice(
            cost=cost,
            currency=checked.cost.currency or "VND",
        )
