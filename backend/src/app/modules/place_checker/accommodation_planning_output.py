from app.modules.place_checker.enums import VerificationStatus
from app.modules.place_checker.output_contract import (
    PlaceCheckerResult,
    PlannerOutputAccommodation,
    PlannerPrice,
)
from app.modules.place_checker.price_policy import typical_cost


PERCENTILE_BY_BUDGET_LEVEL = {"low": 0.25, "medium": 0.50, "high": 0.80}


def select_accommodation(
    result: PlaceCheckerResult,
) -> PlannerOutputAccommodation | None:
    """Select one verified, positive-priced stay for the requested budget tier."""
    priced = []
    budget_currency = result.trip_context.budget.currency or "VND"
    for checked in result.checked_places:
        if (
            checked.category != "accommodation"
            or not checked.place_id
            or not checked.canonical_name
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
        return None

    priced.sort(key=lambda item: (item[0], item[1].canonical_name or ""))
    percentile = PERCENTILE_BY_BUDGET_LEVEL[result.trip_context.budget.level]
    index = round((len(priced) - 1) * percentile)
    cost, checked = priced[index]
    return PlannerOutputAccommodation(
        place_id=checked.place_id or "",
        name=checked.canonical_name or "",
        address=checked.address,
        rating=checked.rating,
        review_count=checked.review_count,
        price_per_night=PlannerPrice(
            cost=cost,
            currency=checked.cost.currency or budget_currency,
        ),
    )
