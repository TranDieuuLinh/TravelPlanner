from __future__ import annotations

from app.modules.plans.domain.entities import (
    PlaceSelectionStatus,
    PlaceSelectionUsage,
    UserStatus,
    UserStatusLocation,
)
from app.modules.plans.place_selector.candidate_selector import candidate_duration
from app.modules.plans.place_selector.place_tool import SelectablePlace, PlaceSelectionTool, place_category
from app.modules.plans.place_selector.skeleton_builder import DayBlock


INTENSITY_EFFECTS: dict[str, dict[str, int]] = {
    "light": {"physical": -5, "energy": -5},
    "moderate": {"physical": -10, "energy": -10},
    "high": {"physical": -20, "energy": -20, "mental": -5},
}

BREAK_EFFECTS = {"energy": 5, "mental": 3}
MEAL_EFFECTS = {"energy": 5, "mental": 2, "satiety": 20}


class PlaceSelectionStatusTracker:
    def __init__(self, place_tool: PlaceSelectionTool) -> None:
        self.place_tool = place_tool

    def apply_activity(
        self,
        candidate: SelectablePlace,
        block: DayBlock,
        user_status: UserStatus,
        plan_status: PlaceSelectionStatus,
    ) -> None:
        candidate_ref = candidate.stable_ref
        plan_status.used_place_ids.append(candidate_ref)
        if candidate_ref in plan_status.remaining_selected_place_ids:
            plan_status.remaining_selected_place_ids.remove(candidate_ref)
        for tag in candidate.tags:
            plan_status.visited_tag_counts[tag] = (
                plan_status.visited_tag_counts.get(tag, 0) + 1
            )
        plan_status.visited_region_counts[candidate.region_key] = (
            plan_status.visited_region_counts.get(candidate.region_key, 0) + 1
        )
        if place_category(candidate) == "food_drink" and candidate.place_type:
            place_type = candidate.place_type.strip()
            if place_type and place_type not in plan_status.used_food_drink_place_types:
                plan_status.used_food_drink_place_types.append(place_type)
        duration = candidate_duration(candidate, block)
        is_meal = block.kind == "meal"
        self.increment_usage(
            plan_status.day_usage,
            activity_minutes=0 if is_meal else duration,
            rest_minutes=duration if is_meal else 0,
            place_count=1,
        )
        self.increment_usage(
            plan_status.trip_usage,
            activity_minutes=0 if is_meal else duration,
            rest_minutes=duration if is_meal else 0,
            place_count=1,
        )
        if is_meal:
            self.apply_metric_delta(user_status, MEAL_EFFECTS)
        elif candidate.activity_intensity:
            self.apply_metric_delta(
                user_status,
                INTENSITY_EFFECTS.get(candidate.activity_intensity, {}),
            )
        user_status.location = UserStatusLocation(
            placeId=candidate.place_id,
            regionKey=candidate.region_key,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
        )

    def rollback_activity(
        self,
        candidate: SelectablePlace,
        block: DayBlock,
        user_status: UserStatus,
        plan_status: PlaceSelectionStatus,
        *,
        restore_selected: bool,
    ) -> None:
        candidate_ref = candidate.stable_ref
        if candidate_ref in plan_status.used_place_ids:
            plan_status.used_place_ids.remove(candidate_ref)
        if (
            restore_selected
            and candidate_ref not in plan_status.remaining_selected_place_ids
        ):
            plan_status.remaining_selected_place_ids.append(candidate_ref)
        for tag in candidate.tags:
            count = plan_status.visited_tag_counts.get(tag, 0)
            if count <= 1:
                plan_status.visited_tag_counts.pop(tag, None)
            else:
                plan_status.visited_tag_counts[tag] = count - 1
        region_count = plan_status.visited_region_counts.get(candidate.region_key, 0)
        if region_count <= 1:
            plan_status.visited_region_counts.pop(candidate.region_key, None)
        else:
            plan_status.visited_region_counts[candidate.region_key] = region_count - 1
        duration = candidate_duration(candidate, block)
        for usage in (plan_status.day_usage, plan_status.trip_usage):
            usage.activity_minutes = max(0, usage.activity_minutes - duration)
            usage.place_count = max(0, usage.place_count - 1)
        if candidate.activity_intensity:
            inverse_delta = {
                metric: -change
                for metric, change in INTENSITY_EFFECTS.get(
                    candidate.activity_intensity,
                    {},
                ).items()
            }
            self.apply_metric_delta(user_status, inverse_delta)

    def apply_break(
        self,
        user_status: UserStatus,
        plan_status: PlaceSelectionStatus,
        block: DayBlock,
    ) -> None:
        self.increment_usage(
            plan_status.day_usage,
            rest_minutes=block.duration_minutes,
        )
        self.increment_usage(
            plan_status.trip_usage,
            rest_minutes=block.duration_minutes,
        )
        self.apply_metric_delta(user_status, BREAK_EFFECTS)

    def apply_metric_delta(self, user_status: UserStatus, delta: dict[str, int]) -> None:
        for metric, change in delta.items():
            current = getattr(user_status.metrics, metric)
            if current is None:
                continue
            setattr(user_status.metrics, metric, max(0, min(100, current + change)))

    def increment_usage(
        self,
        usage: PlaceSelectionUsage,
        *,
        activity_minutes: int = 0,
        rest_minutes: int = 0,
        place_count: int = 0,
        travel_minutes: int = 0,
        walking_minutes: int = 0,
    ) -> None:
        usage.activity_minutes += activity_minutes
        usage.rest_minutes += rest_minutes
        usage.place_count += place_count
        usage.travel_minutes += travel_minutes
        usage.walking_minutes += walking_minutes

    def finish_day_location(self, user_status: UserStatus) -> None:
        accommodation_id = user_status.active_accommodation_place_id
        if not accommodation_id:
            return
        accommodation = self.place_tool.get(accommodation_id)
        if accommodation is None:
            user_status.location = UserStatusLocation(placeId=accommodation_id)
            return
        user_status.location = UserStatusLocation(
            placeId=accommodation.place_id,
            regionKey=accommodation.region_key,
            latitude=accommodation.latitude,
            longitude=accommodation.longitude,
        )
