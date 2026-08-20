"""Build one bounded catalog query for a PlaceChecker gap or pool."""

from app.modules.place_checker.analysis.contract import AnalysisGap
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import GapType
from app.modules.place_checker.resolution.item_contract import ItemResolutionBatch
from app.modules.place_checker.selection.pool_policy import (
    activity_pool_target_for_days,
    drink_dessert_pool_target_for_days,
    entertainment_pool_target_for_days,
    food_pool_target_for_days,
    per_gap_pool_target,
    pool_query_limit_for_days,
)
from app.modules.place_checker.retrieval.contract import TargetedRetrievalQuery


def build_targeted_query(
    gap: AnalysisGap,
    context: TripEvaluationContext,
    items: ItemResolutionBatch | None,
    *,
    anchor_place_ids: list[str],
    limit: int | None,
    core_specs,
    pool_specs,
    category_by_gap,
    intent_by_gap,
    relation_terms,
) -> TargetedRetrievalQuery:
    destination = context.destination
    assert destination.adm_id is not None
    assert destination.canonical_name is not None
    assert destination.country_code is not None
    indexes = set(gap.related_item_indexes)
    item_names = [
        item.normalized_requirement
        for item in (items.items if items else [])
        if item.item_index in indexes
    ]
    category = category_by_gap.get(gap.gap_type)
    intent = (
        ", ".join(item_names)
        or intent_by_gap.get(gap.gap_type)
        or category
        or gap.gap_type.value
    )
    all_specs = {**core_specs, **pool_specs}
    pool_spec = all_specs.get(gap.gap_id)
    query_text = pool_spec[1] if pool_spec else intent
    if gap.gap_id == "pool:restaurant_candidates" and item_names:
        query_text = f"{', '.join(item_names)} restaurant"
    elif gap.gap_id == "pool:drink_dessert_candidates" and item_names:
        query_text = f"{', '.join(item_names)} cafe"

    query_limit = limit or per_gap_pool_target(context.days, 1)
    if gap.gap_id in core_specs:
        query_limit = pool_query_limit_for_days(context.days)
    elif gap.gap_id == "pool:restaurant_candidates":
        query_limit = max(query_limit, min(60, food_pool_target_for_days(context.days)))
    elif gap.gap_id == "pool:entertainment_candidates":
        query_limit = max(
            query_limit,
            min(60, entertainment_pool_target_for_days(context.days)),
        )
    elif gap.gap_id == "pool:drink_dessert_candidates":
        query_limit = max(
            query_limit,
            min(60, drink_dessert_pool_target_for_days(context.days)),
        )
    elif gap.gap_type == GapType.food_coverage:
        query_limit = max(query_limit, min(60, food_pool_target_for_days(context.days)))
    elif category == "travel_place" and query_text == "travel place":
        query_limit = max(
            query_limit,
            min(60, activity_pool_target_for_days(context.days)),
        )

    people_tags = [
        tag
        for present, tag in (
            (context.people.children, "children_suitable"),
            (context.people.infants, "infants_suitable"),
        )
        if present
    ]
    return TargetedRetrievalQuery(
        gap_id=gap.gap_id,
        gap_type=gap.gap_type,
        severity=gap.severity,
        query_text=query_text,
        adm_id=destination.adm_id,
        adm_name=destination.canonical_name,
        country_code=destination.country_code,
        category_hint=(pool_spec[2] if pool_spec else category),
        budget_level=context.budget.level,
        people_tags=people_tags,
        time_hints=[],
        anchor_place_ids=list(dict.fromkeys(anchor_place_ids))[:10],
        relation_terms=relation_terms.get(gap.gap_id, []),
        limit=query_limit,
    )
