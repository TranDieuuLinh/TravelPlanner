from decimal import ROUND_HALF_UP, Decimal

from app.modules.place_checker.output_contract import (
    PlaceCheckerResult,
    PlannerBudget,
    PlannerDailyBudgetEstimate,
)
from app.shared.tools.daily_budget import DestinationDailyBudgetEstimator


def build_planner_budget(
    result: PlaceCheckerResult,
    estimator: DestinationDailyBudgetEstimator,
) -> PlannerBudget:
    """Prefer an explicit per-person amount, otherwise estimate the trip tier."""
    context = result.trip_context
    budget = context.budget
    currency = budget.currency or "VND"
    if budget.target_amount is not None:
        amount = budget.target_amount
        if budget.basis == "group_total":
            amount = (
                amount / Decimal(context.people.total)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return PlannerBudget(
            amount=float(amount),
            currency=currency,
            source="explicit",
        )

    destination = (
        context.destination.canonical_name or context.destination.input_name
    )
    estimate = estimator.estimate(
        destination=destination,
        level=budget.level,
        people=context.people.total,
        days=context.days,
    )
    if estimate is None:
        return PlannerBudget(currency=currency, source="unspecified")
    daily = estimate.daily_cost
    return PlannerBudget(
        amount=estimate.total_per_person,
        currency=daily.currency,
        source="estimated_daily_cost",
        daily_estimate=PlannerDailyBudgetEstimate(
            accommodation=daily.accommodation,
            food=daily.food,
            local_transport=daily.local_transport,
            activities=daily.activities,
            total=daily.total,
        ),
        profile_version=estimate.profile_version,
    )
