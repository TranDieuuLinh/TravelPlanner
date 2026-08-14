from app.modules.place_checker.enums import VerificationStatus
from app.modules.place_checker.output_contract import (
    PlaceCheckerResult,
    PlannerOutputAccommodation,
    PlannerPrice,
)
from app.modules.place_checker.price_policy import typical_cost

PERCENTILE_BY_BUDGET_LEVEL = {"low": 0.25, "medium": 0.50, "high": 0.80}
ACCOMMODATION_CANDIDATE_LIMIT = 3


def select_accommodations(
    result: PlaceCheckerResult,
) -> list[PlannerOutputAccommodation]:
    """Return a small priced pool around the requested budget percentile."""
    priced = []
    budget_currency = result.trip_context.budget.currency or "VND"
    for checked in result.checked_places:
        if (
            checked.category != "accommodation"
            or not checked.place_id
            or not checked.canonical_name
            or checked.coordinates is None
            or checked.evaluation.avoid_conflicts
            or (
                checked.cost.currency is not None
                and checked.cost.currency != budget_currency
            )
            or checked.verification.status
            not in {
                VerificationStatus.verified_kg,
                VerificationStatus.verified_external,
            }
        ):
            continue
        cost = typical_cost(
            minimum=checked.cost.minimum,
            typical=checked.cost.typical,
            maximum=checked.cost.maximum,
            tier=checked.cost.tier,
        )
        if cost is not None and cost > 0:
            priced.append((cost, checked))
    if not priced:
        return []

    priced.sort(key=lambda item: (item[0], item[1].canonical_name or ""))
    percentile = PERCENTILE_BY_BUDGET_LEVEL[result.trip_context.budget.level]
    target_index = round((len(priced) - 1) * percentile)
    ranked = sorted(
        enumerate(priced),
        key=lambda item: (
            abs(item[0] - target_index),
            -(item[1][1].rating or 0),
            -(item[1][1].review_count or 0),
            item[1][0],
        ),
    )[:ACCOMMODATION_CANDIDATE_LIMIT]
    return [
        PlannerOutputAccommodation(
            place_id=checked.place_id or "",
            name=checked.canonical_name or "",
            coordinates=checked.coordinates,
            address=checked.address,
            rating=checked.rating,
            review_count=checked.review_count,
            price_per_night=PlannerPrice(
                cost=cost,
                currency=checked.cost.currency or budget_currency,
            ),
        )
        for _, (cost, checked) in ranked
    ]
