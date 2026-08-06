from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.plans.domain.entities import PlaceSelectionStatus, PlanItem
from app.modules.plans.place_selector.time_windows import (
    format_clock_window,
    parse_unbounded_clock_minutes,
    window_duration,
)
from app.modules.plans.place_selector.timeline_policy import (
    DEFAULT_TRANSITION_MINUTES,
    MEAL_ANCHORS,
)


@dataclass(frozen=True)
class TimelineFitResult:
    items: list[PlanItem]
    overflow_items: list[PlanItem]


class TimelineFitter:
    def fit(
        self,
        items: list[PlanItem],
        transport_legs: list[Any],
        *,
        day: int,
        warnings: list[str],
        plan_status: PlaceSelectionStatus,
    ) -> TimelineFitResult:
        if not items:
            return TimelineFitResult(items=items, overflow_items=[])
        leg_by_pair = {
            (leg.from_item_id, leg.to_item_id): leg
            for leg in transport_legs
        }
        fitted: list[PlanItem] = []
        overflow: list[PlanItem] = []
        previous: PlanItem | None = None
        previous_end: int | None = None
        last_operational_end: int | None = None
        shifted = False
        ordered_items = sorted(
            items,
            key=lambda item: (
                parse_unbounded_clock_minutes(item.time_window) or 24 * 60,
                item.name.casefold(),
            ),
        )
        anchor_by_role = {anchor.role: anchor for anchor in MEAL_ANCHORS}
        for item in ordered_items:
            start = parse_unbounded_clock_minutes(item.time_window)
            duration = item.duration_minutes or window_duration(item.time_window)
            if start is None or duration is None:
                overflow.append(item)
                continue
            required_start = start
            if previous is not None and previous_end is not None:
                leg = leg_by_pair.get((previous.item_id, item.item_id))
                transition = (
                    leg.estimated_duration_minutes
                    if leg is not None
                    else DEFAULT_TRANSITION_MINUTES
                )
                required_start = max(required_start, previous_end + transition)
            anchor = anchor_by_role.get(item.role or "")
            if anchor is not None:
                # Meal windows are soft. Preserve the anchor target when possible,
                # but move it when the preceding route makes that impossible.
                required_start = max(required_start, anchor.earliest)
            if required_start + duration >= 24 * 60:
                overflow.append(item)
                continue
            current_window_duration = window_duration(item.time_window)
            if (
                required_start > start
                or current_window_duration != duration
            ):
                shifted = True
                if anchor is not None:
                    message = (
                        f"Day {day} moved {item.role} from {item.time_window} "
                        f"to {format_clock_window(required_start, duration)} "
                        "to preserve route feasibility."
                    )
                    warnings.append(message)
                    plan_status.warnings.append(message)
                item = item.model_copy(
                    update={
                        "time_window": format_clock_window(
                            required_start,
                            duration,
                        )
                    }
                )
            fitted.append(item)
            previous = item
            previous_end = required_start + duration
            if item.role != "group_social_activity":
                last_operational_end = previous_end
        if shifted:
            message = (
                f"Day {day} timeline was shifted to account for estimated "
                "travel time between scheduled places."
            )
            warnings.append(message)
            plan_status.warnings.append(message)
        if last_operational_end is not None and last_operational_end > 21 * 60:
            message = (
                f"Day {day} ends after 21:00 after route-aware timeline fitting."
            )
            warnings.append(message)
            plan_status.warnings.append(message)
        if overflow:
            message = (
                f"Day {day} left {len(overflow)} item(s) unscheduled because "
                "their route-aware time windows would reach or exceed 24:00."
            )
            warnings.append(message)
            plan_status.warnings.append(message)
        return TimelineFitResult(items=fitted, overflow_items=overflow)
