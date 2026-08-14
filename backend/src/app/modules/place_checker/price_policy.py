from app.modules.place_checker.enums import CostTier


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
