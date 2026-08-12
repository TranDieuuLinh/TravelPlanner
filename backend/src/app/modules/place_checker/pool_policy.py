from __future__ import annotations

import math


MIN_POOL_TARGET = 20
MAX_POOL_TARGET = 120
POOL_PLACES_PER_DAY = 15


def pool_target_for_days(days: int) -> int:
    """Return the reserve pool size passed to the downstream planner."""
    return min(MAX_POOL_TARGET, max(MIN_POOL_TARGET, days * POOL_PLACES_PER_DAY))


def per_gap_pool_target(days: int, discovery_gap_count: int) -> int:
    """Spread the global target across discovery gaps without under-fetching."""
    target = pool_target_for_days(days)
    return min(50, max(10, math.ceil(target / max(1, discovery_gap_count))))
