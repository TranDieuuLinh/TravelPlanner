from app.modules.place_checker.contract import InputItem, TripEvaluationContext
from app.modules.place_checker.enums import CostTier
from app.modules.place_checker.item_contract import ItemPlaceOption
from app.modules.place_checker.resolution_contract import EnrichedIdentityPlace
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km, text_similarity

FOOD_TYPES = {"food", "meal", "drink", "coffee"}
FOOD_CATEGORIES = {
    "food",
    "food venue",
    "restaurant",
    "cafe",
    "coffee shop",
    "bakery",
    "drink dessert",
}
ACTIVITY_TYPES = {"activity", "experience", "attraction"}


class ItemProximityPolicy:
    @staticmethod
    def related_place(
        item: InputItem,
        places: list[EnrichedIdentityPlace],
    ) -> EnrichedIdentityPlace | None:
        if not item.related_place_name:
            return None
        target = item.related_place_name
        scored = [
            (
                max(
                    text_similarity(target, name)
                    for name in [
                        place.canonical_name or "",
                        *place.original_names,
                        *place.aliases,
                    ]
                ),
                place,
            )
            for place in places
        ]
        scored.sort(key=lambda value: value[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] >= 0.90 else None

    @staticmethod
    def anchor(
        related: EnrichedIdentityPlace | None,
        places: list[EnrichedIdentityPlace],
    ) -> Coordinates | None:
        if related and related.metadata and related.metadata.coordinates:
            return related.metadata.coordinates
        attraction_coordinates = [
            place.metadata.coordinates
            for place in places
            if place.metadata
            and place.metadata.coordinates
            and normalize_text(place.metadata.category) not in FOOD_CATEGORIES
        ]
        coordinates = attraction_coordinates or [
            place.metadata.coordinates
            for place in places
            if place.metadata and place.metadata.coordinates
        ]
        if not coordinates:
            return None
        return Coordinates(
            latitude=sum(point.latitude for point in coordinates) / len(coordinates),
            longitude=sum(point.longitude for point in coordinates) / len(coordinates),
        )

    @staticmethod
    def direct_option(
        item: InputItem,
        related: EnrichedIdentityPlace | None,
    ) -> ItemPlaceOption | None:
        if related is None or related.place_id is None or related.metadata is None:
            return None
        item_type = normalize_text(item.item_type)
        category = normalize_text(related.metadata.category)
        compatible = (
            item_type in FOOD_TYPES and category in FOOD_CATEGORIES
        ) or (
            item_type in ACTIVITY_TYPES and category not in FOOD_CATEGORIES
        )
        if not compatible or related.metadata.coordinates is None:
            return None
        metadata = related.metadata
        return ItemPlaceOption(
            place_id=related.place_id,
            name=related.canonical_name or related.original_names[0],
            provider="resolved_place",
            category=metadata.category,
            address=metadata.address,
            coordinates=metadata.coordinates,
            tags=metadata.tags,
            cost_tier=metadata.cost_tier,
            cost_currency=metadata.cost_currency,
            minimum_cost=metadata.minimum_cost,
            typical_cost=metadata.typical_cost,
            maximum_cost=metadata.maximum_cost,
            children_suitable=metadata.children_suitable,
            infants_suitable=metadata.infants_suitable,
            minimum_duration_minutes=metadata.minimum_duration_minutes,
            typical_duration_minutes=metadata.typical_duration_minutes,
            maximum_duration_minutes=metadata.maximum_duration_minutes,
            anchor_distance_km=0,
            proximity_status="nearby",
            score=related.identity_confidence or 0.9,
        )

    @staticmethod
    def with_distance(
        option: ItemPlaceOption,
        anchor: Coordinates | None,
    ) -> ItemPlaceOption:
        if anchor is None or option.coordinates is None:
            return option.model_copy(update={"proximity_status": "unknown"})
        distance = distance_km(anchor, option.coordinates)
        status = "nearby" if distance <= 2 else "acceptable" if distance <= 5 else "far"
        return option.model_copy(
            update={
                "anchor_distance_km": round(distance, 3),
                "proximity_status": status,
            }
        )

    @staticmethod
    def too_far(option: ItemPlaceOption, *, strict: bool) -> bool:
        if option.anchor_distance_km is None:
            return False
        return option.anchor_distance_km > (5 if strict else 15)

    @staticmethod
    def rank(
        option: ItemPlaceOption,
        context: TripEvaluationContext,
    ) -> tuple[int, float, int, float, float, float]:
        budget_penalty = int(
            context.budget.level == "low"
            and option.cost_tier in {CostTier.high, CostTier.premium}
        )
        distance = option.anchor_distance_km
        distance_rank = distance if distance is not None else 999.0
        labels = {
            normalize_text(value)
            for value in [option.name, option.category or "", *option.tags]
            if value
        }
        preference_matches = sum(
            normalize_text(preference) in labels
            for preference in context.preferences
        )
        rating_rank = -(option.rating or 0.0)
        review_rank = -(option.review_count or 0)
        return (
            budget_penalty,
            distance_rank,
            -preference_matches,
            rating_rank,
            review_rank,
            -option.score,
        )
