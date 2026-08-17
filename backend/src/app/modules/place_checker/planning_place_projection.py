from __future__ import annotations

from app.modules.place_checker.checked_output_contract import CheckedPlace
from app.modules.place_checker.enums import SourceTier
from app.modules.place_checker.output_contract import (
    PlannerAudience,
    PlannerOutputFood,
    PlannerOutputPlace,
    PlannerPrice,
    PlannerTimeWindow,
)
from app.modules.place_checker.planner_candidate_metadata import (
    preferred_time_values,
    source_metadata,
    time_source,
)
from app.modules.place_checker.planner_notes import select_planner_source_note
from app.modules.place_checker.planner_semantics import (
    audience_values,
    candidate_semantics,
)
from app.modules.place_checker.planning_time_windows import parse_planner_windows
from app.modules.place_checker.price_policy import typical_cost
from app.shared.contracts.source_note import SourceNote


class PlannerPlaceProjector:
    @classmethod
    def place(cls, checked: CheckedPlace, days: int) -> PlannerOutputPlace:
        source_kind, offered_activity_ids = source_metadata(
            checked.relationship_evidence
        )
        tags, styles = candidate_semantics(checked.tags, checked.relationship_evidence)
        adult_only, kid_suitable = audience_values(
            adults=checked.suitability.adults,
            children=checked.suitability.children,
            infants=checked.suitability.infants,
        )
        return PlannerOutputPlace(
            place_id=checked.place_id,
            name=checked.canonical_name or "",
            coordinates=checked.coordinates,
            address=checked.address,
            priority=cls._priority(checked),
            notes=select_planner_source_note(checked),
            tags=tags,
            styles=styles,
            audience=PlannerAudience(
                adult_only=adult_only,
                kid_suitable=kid_suitable,
            ),
            image_urls=checked.image_urls,
            rating=checked.rating,
            review_count=checked.review_count,
            duration_minutes=checked.duration.typical_minutes,
            opening_hours=cls._opening_hours(checked.opening.hours, days),
            preferred_time_windows=cls._preferred_windows(checked),
            source_kind=source_kind,
            offered_activity_ids=offered_activity_ids,
            time_source=time_source(
                direct_values=checked.time_preferences,
                opening_hours=checked.opening.hours,
                relationships=checked.relationship_evidence,
            ),
            price=cls._price(checked),
            relationships=cls._related_place_ids(checked),
        )

    @classmethod
    def food(
        cls, checked: CheckedPlace, days: int, supported_meals: list[str]
    ) -> PlannerOutputFood:
        return PlannerOutputFood(
            **cls.place(checked, days).model_dump(),
            venue_type=checked.category,
            supported_meals=supported_meals,
        )

    @classmethod
    def item_place(cls, item, days: int) -> PlannerOutputPlace:
        option = item.selected
        relations = option.relationships
        source_kind, offered_activity_ids = source_metadata(relations)
        tags, styles = candidate_semantics(option.tags, relations)
        adult_only, kid_suitable = audience_values(
            adults=True,
            children=option.children_suitable,
            infants=option.infants_suitable,
        )
        preferred_values, _ = preferred_time_values(
            direct_values=[], relationships=relations
        )
        return PlannerOutputPlace(
            place_id=option.place_id,
            name=option.name,
            coordinates=option.coordinates,
            address=option.address,
            priority="user_input",
            notes=SourceNote(text=item.evidence, source_type="backend"),
            tags=tags,
            styles=styles,
            audience=PlannerAudience(
                adult_only=adult_only,
                kid_suitable=kid_suitable,
            ),
            image_urls=option.image_urls,
            rating=option.rating,
            review_count=option.review_count,
            duration_minutes=option.typical_duration_minutes,
            opening_hours=cls._opening_hours(option.opening_hours, days),
            preferred_time_windows=parse_planner_windows(preferred_values),
            source_kind=source_kind,
            offered_activity_ids=offered_activity_ids,
            time_source=time_source(
                direct_values=[],
                opening_hours=option.opening_hours,
                relationships=relations,
            ),
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
    def item_food(
        cls, item, days: int, supported_meals: list[str]
    ) -> PlannerOutputFood:
        return PlannerOutputFood(
            **cls.item_place(item, days).model_dump(),
            venue_type=item.selected.category,
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
        types = {
            relation.relationship_type for relation in checked.relationship_evidence
        }
        return "special_near" if "Special_Near" in types else "special_experience"

    @classmethod
    def _preferred_windows(cls, checked: CheckedPlace) -> list[PlannerTimeWindow]:
        values, _ = preferred_time_values(
            direct_values=checked.time_preferences,
            relationships=checked.relationship_evidence,
        )
        return parse_planner_windows(values)

    @staticmethod
    def _opening_hours(
        values: list[str] | None, days: int
    ) -> dict[str, list[PlannerTimeWindow]] | None:
        windows = parse_planner_windows(values or [])
        return {str(day): windows for day in range(1, days + 1)} if windows else None

    @staticmethod
    def _price(checked: CheckedPlace) -> PlannerPrice:
        return PlannerPrice(
            cost=typical_cost(
                minimum=checked.cost.minimum,
                typical=checked.cost.typical,
                maximum=checked.cost.maximum,
                tier=checked.cost.tier,
            ),
            currency=checked.cost.currency or "VND",
        )
