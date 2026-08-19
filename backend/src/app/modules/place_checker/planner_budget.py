from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from app.modules.place_checker.output_contract import (
    PlaceCheckerResult,
    PlannerBudget,
    PlannerDailyBudgetEstimate,
    PlannerOutputFood,
    PlannerOutputPlace,
)
from app.modules.place_checker.enums import VerificationStatus
from app.modules.place_checker.price_policy import typical_cost
from app.shared.tools.transport_cost import (
    TransportCostEstimator,
    XanhSmTransportCostEstimator,
)

PERCENTILE_BY_LEVEL = {"low": 0.25, "medium": 0.50, "high": 0.80}
ACTIVITIES_PER_DAY = {"low": 2, "medium": 3, "high": 4}
TRANSPORT_LEGS_PER_DAY = {"low": 4, "medium": 5, "high": 6}
MEALS_PER_DAY = 3
TYPICAL_LEG_DISTANCE_METERS = 5_000
PEOPLE_PER_ROOM = 2
PROFILE_VERSION = "adm-candidate-price-percentiles-v1"


class AdmCandidateBudgetEstimator:
    """Estimate a per-person trip budget from the ADM-scoped planner pools."""

    def __init__(
        self,
        transport_cost: TransportCostEstimator | None = None,
    ) -> None:
        self.transport_cost = transport_cost or XanhSmTransportCostEstimator()

    def estimate(
        self,
        result: PlaceCheckerResult,
        *,
        places: list[PlannerOutputPlace],
        food: list[PlannerOutputFood],
    ) -> PlannerBudget | None:
        context = result.trip_context
        level = context.budget.level
        currency = context.budget.currency or "VND"
        activity_prices = self._prices(places, currency)
        food_prices = self._prices(food, currency)
        accommodation_prices = self._accommodation_prices(result, currency)
        nights = max(0, context.days - 1)
        if not activity_prices or not food_prices or (nights and not accommodation_prices):
            return None

        percentile = PERCENTILE_BY_LEVEL[level]
        room_price = self._percentile(accommodation_prices, percentile)
        rooms = ceil(context.people.total / PEOPLE_PER_ROOM)
        accommodation = (
            ceil(room_price * rooms / context.people.total) if nights else 0
        )
        meal_price = self._percentile(food_prices, percentile)
        food_per_day = ceil(meal_price * MEALS_PER_DAY)
        activity_price = self._percentile(activity_prices, percentile)
        activities_per_day = ceil(activity_price * ACTIVITIES_PER_DAY[level])
        transport_per_leg, _ = self.transport_cost.estimate(
            TYPICAL_LEG_DISTANCE_METERS,
            "auto",
            context.people.total,
        )
        transport_per_day = (
            transport_per_leg * TRANSPORT_LEGS_PER_DAY[level]
        )
        daily_total = (
            accommodation + food_per_day + activities_per_day + transport_per_day
        )
        total_per_person = (
            (food_per_day + activities_per_day + transport_per_day) * context.days
            + accommodation * nights
        )
        adm_id = context.destination.adm_id or "unresolved"
        version = (
            f"{PROFILE_VERSION}:{adm_id}:"
            f"a{len(activity_prices)}-f{len(food_prices)}-h{len(accommodation_prices)}"
        )
        return PlannerBudget(
            amount=total_per_person,
            currency=currency,
            source="estimated_daily_cost",
            daily_estimate=PlannerDailyBudgetEstimate(
                accommodation=accommodation,
                food=food_per_day,
                local_transport=transport_per_day,
                activities=activities_per_day,
                total=daily_total,
            ),
            profile_version=version,
        )

    @staticmethod
    def _prices(
        candidates: list[PlannerOutputPlace],
        currency: str,
    ) -> list[float]:
        return [
            candidate.price.cost
            for candidate in candidates
            if candidate.price.currency == currency and candidate.price.cost >= 0
        ]

    @staticmethod
    def _accommodation_prices(
        result: PlaceCheckerResult,
        currency: str,
    ) -> list[float]:
        prices: list[float] = []
        for candidate in result.checked_places:
            if (
                candidate.category != "accommodation"
                or candidate.cost.currency not in {None, currency}
                or candidate.verification.status
                not in {
                    VerificationStatus.verified_kg,
                    VerificationStatus.verified_external,
                }
            ):
                continue
            price = typical_cost(
                minimum=candidate.cost.minimum,
                typical=candidate.cost.typical,
                maximum=candidate.cost.maximum,
                tier=candidate.cost.tier,
            )
            if price is not None and price > 0:
                prices.append(price)
        return prices

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        ordered = sorted(values)
        return ordered[round((len(ordered) - 1) * percentile)] if ordered else 0


def build_planner_budget(
    result: PlaceCheckerResult,
    estimator: AdmCandidateBudgetEstimator,
    *,
    places: list[PlannerOutputPlace],
    food: list[PlannerOutputFood],
) -> PlannerBudget:
    """Prefer an explicit amount, otherwise estimate from ADM-scoped prices."""
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

    estimate = estimator.estimate(
        result,
        places=places,
        food=food,
    )
    return estimate or PlannerBudget(currency=currency, source="unspecified")
