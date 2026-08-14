from __future__ import annotations

import math


MIN_POOL_TARGET = 12
MAX_POOL_TARGET = 60
POOL_CANDIDATES_PER_TYPE_PER_DAY = 12
POOL_ENTITY_TYPE_COUNT = 2
ACCOMMODATION_POOL_TARGET = 1


def pool_target_for_days(days: int) -> int:
    """Return the target for one pool type: TravelPlace or Restaurant."""
    return min(
        MAX_POOL_TARGET,
        max(MIN_POOL_TARGET, days * POOL_CANDIDATES_PER_TYPE_PER_DAY),
    )


def combined_pool_target_for_days(days: int) -> int:
    """Return both stop pools plus one priced accommodation candidate."""
    return (
        pool_target_for_days(days) * POOL_ENTITY_TYPE_COUNT
        + ACCOMMODATION_POOL_TARGET
    )


def pool_query_limit_for_days(days: int) -> int:
    """Over-fetch one type so metadata filtering can still fill its quota."""
    target = pool_target_for_days(days)
    return min(MAX_POOL_TARGET, target * 2)


def per_gap_pool_target(days: int, discovery_gap_count: int) -> int:
    """Spread the global target across discovery gaps without under-fetching."""
    target = pool_target_for_days(days)
    return min(12, max(3, math.ceil(target / max(1, discovery_gap_count))))
