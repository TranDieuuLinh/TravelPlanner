from app.modules.place_checker.resolution.item_contract import ItemPlaceOption
from app.modules.place_checker.resolution.contract import PlaceMetadata


def apply_metadata(
    option: ItemPlaceOption,
    metadata: PlaceMetadata | None,
) -> ItemPlaceOption:
    if metadata is None:
        return option
    rejection_reasons = list(option.rejection_reasons)
    if metadata.coordinates is not None:
        rejection_reasons = [
            reason for reason in rejection_reasons if reason != "coordinates_missing"
        ]
    return option.model_copy(
        update={
            "cost_tier": metadata.cost_tier,
            "cost_currency": metadata.cost_currency,
            "minimum_cost": metadata.minimum_cost,
            "typical_cost": metadata.typical_cost,
            "maximum_cost": metadata.maximum_cost,
            "opening_hours": metadata.opening_hours,
            "relationships": metadata.relationships,
            "address": metadata.address or option.address,
            "coordinates": metadata.coordinates or option.coordinates,
            "category": metadata.category or option.category,
            "tags": list(dict.fromkeys([*option.tags, *metadata.tags])),
            "image_urls": list(
                dict.fromkeys([*option.image_urls, *metadata.image_urls])
            ),
            "rating": metadata.rating if metadata.rating is not None else option.rating,
            "review_count": (
                metadata.review_count
                if metadata.review_count is not None
                else option.review_count
            ),
            "children_suitable": metadata.children_suitable,
            "infants_suitable": metadata.infants_suitable,
            "minimum_duration_minutes": metadata.minimum_duration_minutes,
            "typical_duration_minutes": metadata.typical_duration_minutes,
            "maximum_duration_minutes": metadata.maximum_duration_minutes,
            "rejection_reasons": rejection_reasons,
        }
    )
