from app.modules.place_checker.enums import CostTier

COST_REQUIRED_CATEGORIES = frozenset(
    {"restaurant", "drink_dessert", "entertainment", "accommodation"}
)


def place_defaults_to_free(category: str | None) -> bool:
    """Return whether a missing price should be projected as free for Planner."""
    normalized = (
        (category or "").strip().casefold().replace("-", "_").replace(" ", "_")
    )
    return normalized not in COST_REQUIRED_CATEGORIES


def typical_cost(
    *,
    minimum: float | None,
    typical: float | None,
    maximum: float | None,
    tier: CostTier,
) -> float | None:
    """Return the usable per-person cost passed to the itinerary planner."""
    if minimum is not None and maximum is not None:
        return (minimum + maximum) / 2
    if typical is not None:
        return typical
    if minimum is not None:
        return minimum
    if maximum is not None:
        return maximum
    if tier == CostTier.free:
        return 0
    return None


def has_usable_cost(
    *,
    minimum: float | None,
    typical: float | None,
    maximum: float | None,
    tier: CostTier,
) -> bool:
    return typical_cost(
        minimum=minimum,
        typical=typical,
        maximum=maximum,
        tier=tier,
    ) is not None


def planner_cost(
    *,
    category: str | None,
    minimum: float | None,
    typical: float | None,
    maximum: float | None,
    tier: CostTier,
) -> float | None:
    """Project unknown general-place prices as free without mutating KG data."""
    cost = typical_cost(
        minimum=minimum,
        typical=typical,
        maximum=maximum,
        tier=tier,
    )
    if cost is None and place_defaults_to_free(category):
        return 0
    return cost


def has_planner_cost(
    *,
    category: str | None,
    minimum: float | None,
    typical: float | None,
    maximum: float | None,
    tier: CostTier,
) -> bool:
    return planner_cost(
        category=category,
        minimum=minimum,
        typical=typical,
        maximum=maximum,
        tier=tier,
    ) is not None
