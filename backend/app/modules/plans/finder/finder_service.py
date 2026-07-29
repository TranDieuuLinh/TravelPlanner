from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from app.modules.plans.domain.entities import (
    FinderPlanStatus,
    FinderResult,
    FinderUsage,
    MacroPlan,
    PlanDay,
    PlanItem,
    TravelIntent,
    UnscheduledPlace,
    UserStatus,
    UserStatusLocation,
)
from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    FinderAgentInput,
    FinderAgentOutput,
    PlanningAgentName,
    PlanningAgentStatus,
    SelectedPlaceContext,
)
from app.modules.plans.finder.place_tool import (
    EmptyFinderPlaceTool,
    FinderPlace,
    FinderPlaceTool,
)
from app.modules.plans.finder.skeleton_builder import (
    DayBlock,
    DaySkeletonBuilder,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer


INTENSITY_EFFECTS: dict[str, dict[str, int]] = {
    "light": {"physical": -5, "energy": -5},
    "moderate": {"physical": -10, "energy": -10},
    "high": {"physical": -20, "energy": -20, "mental": -5},
}

BREAK_EFFECTS = {"energy": 5, "mental": 3}


@dataclass(frozen=True)
class CandidateRejection:
    reason_code: str
    reason: str


class FinderService:
    def __init__(
        self,
        place_tool: FinderPlaceTool | None = None,
        *,
        max_candidates_per_block: int = 5,
        skeleton_builder: DaySkeletonBuilder | None = None,
        route_optimizer: GeographicRouteOptimizer | None = None,
    ) -> None:
        if max_candidates_per_block < 1:
            raise ValueError("max_candidates_per_block must be at least 1")
        self.place_tool = place_tool or EmptyFinderPlaceTool()
        self.max_candidates_per_block = max_candidates_per_block
        self.skeleton_builder = skeleton_builder or DaySkeletonBuilder()
        self.route_optimizer = route_optimizer or GeographicRouteOptimizer()

    def fill_main_plan(
        self,
        macro_plan: MacroPlan,
        intent: TravelIntent,
        selected_places: list[SelectedPlaceContext] | list[str],
        *,
        user_status: UserStatus | None = None,
        plan_status: FinderPlanStatus | None = None,
    ) -> FinderResult:
        return self._fill_days(
            macro_plan,
            self._normalize_selected_places(selected_places),
            mode="main",
            user_status=user_status or UserStatus(),
            plan_status=plan_status or FinderPlanStatus(),
            avoided_place_names={
                name.casefold() for name in intent.avoid_places
            },
            intent_constraints=intent.constraints,
            budget_level=intent.budget.value,
        )

    def fill_backup_plan(
        self,
        macro_plan: MacroPlan,
        intent: TravelIntent,
        selected_places: list[SelectedPlaceContext] | list[str],
        *,
        user_status: UserStatus | None = None,
        plan_status: FinderPlanStatus | None = None,
    ) -> FinderResult:
        return self._fill_days(
            macro_plan,
            self._normalize_selected_places(selected_places),
            mode="backup",
            user_status=user_status or UserStatus(),
            plan_status=plan_status or FinderPlanStatus(),
            avoided_place_names={
                name.casefold() for name in intent.avoid_places
            },
            intent_constraints=intent.constraints,
            budget_level=intent.budget.value,
        )

    def fill_agent_plan(
        self,
        finder_input: FinderAgentInput,
    ) -> FinderAgentOutput:
        result = self._fill_days(
            finder_input.macro_plan,
            finder_input.selected_places,
            mode=finder_input.mode.value,
            user_status=finder_input.user_status,
            plan_status=finder_input.finder_plan_status,
            avoided_place_names={
                name.casefold()
                for name in finder_input.intent.avoid_places
            },
            intent_constraints=finder_input.intent.constraints,
            budget_level=finder_input.intent.budget_level.value,
        )
        committed_place_count = sum(
            item.place_id is not None or item.source == "selected_place"
            for day in result.days
            for item in day.items
        )
        return FinderAgentOutput(
            mode=finder_input.mode,
            finalDays=result.days,
            tripCostEstimate=None,
            unscheduledPlaces=result.unscheduled_places,
            finalUserStatus=result.final_user_status,
            finalPlanStatus=result.final_plan_status,
            warnings=result.warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.finder,
                status=(
                    PlanningAgentStatus.completed
                    if committed_place_count
                    else PlanningAgentStatus.blocked
                ),
                summary=(
                    "Filled dynamic day skeletons from MacroPlan."
                    if committed_place_count
                    else "No Place could be committed to the day skeletons."
                ),
                notes=[
                    f"committedPlaceCount={committed_place_count}",
                    f"unscheduledPlaceCount={len(result.unscheduled_places)}",
                ],
            ),
        )

    def _fill_days(
        self,
        macro_plan: MacroPlan,
        selected_places: list[SelectedPlaceContext],
        *,
        mode: str,
        user_status: UserStatus,
        plan_status: FinderPlanStatus,
        avoided_place_names: set[str],
        intent_constraints: list[str],
        budget_level: str,
    ) -> FinderResult:
        committed_user_status = user_status.model_copy(deep=True)
        committed_plan_status = plan_status.model_copy(deep=True)
        if not committed_plan_status.remaining_selected_place_ids:
            committed_plan_status.remaining_selected_place_ids = [
                place.stable_ref for place in selected_places
            ]

        days: list[PlanDay] = []
        warnings: list[str] = []
        rejected_selected_places: dict[str, CandidateRejection] = {}
        selected_by_ref = {
            place.stable_ref: place for place in selected_places
        }

        for brief in macro_plan.day_briefs:
            day_start_location = committed_user_status.location
            tentative_user_status = committed_user_status.model_copy(deep=True)
            tentative_plan_status = committed_plan_status.model_copy(deep=True)
            skeleton = self.skeleton_builder.build(
                brief,
                tentative_user_status,
                intent_constraints=intent_constraints,
            )
            tentative_plan_status.current_day = brief.day
            tentative_plan_status.current_strategy = skeleton.strategy
            tentative_plan_status.day_usage = FinderUsage()
            day_items: list[PlanItem] = []

            for block in skeleton.blocks:
                tentative_plan_status.current_slot = block.role
                if not self._block_is_available(block, tentative_user_status):
                    if block.activity and not block.optional:
                        message = (
                            f"Day {brief.day} skipped {block.role} because "
                            f"the user is only available at "
                            f"{tentative_user_status.available_at}."
                        )
                        warnings.append(message)
                        tentative_plan_status.warnings.append(message)
                    continue
                if not block.activity:
                    day_items.append(self._build_non_activity_item(block))
                    self._apply_break(
                        tentative_user_status,
                        tentative_plan_status,
                        block,
                    )
                    continue

                candidate = self._choose_candidate(
                    brief=brief,
                    block=block,
                    selected_by_ref=selected_by_ref,
                    plan_status=tentative_plan_status,
                    user_status=tentative_user_status,
                    avoided_place_names=avoided_place_names,
                    intent_constraints=intent_constraints,
                    budget_level=budget_level,
                    rejected_selected_places=rejected_selected_places,
                )
                if candidate is None:
                    message = (
                        f"Day {brief.day} has no valid candidate for "
                        f"{block.role}."
                    )
                    if not block.optional:
                        warnings.append(message)
                        tentative_plan_status.warnings.append(message)
                    continue

                selected_source = candidate.stable_ref in selected_by_ref
                day_items.append(
                    self._build_activity_item(
                        candidate,
                        block,
                        mode=mode,
                        selected_source=selected_source,
                    )
                )
                self._apply_activity(
                    candidate,
                    block,
                    tentative_user_status,
                    tentative_plan_status,
                )

            self._finish_day_location(tentative_user_status)
            tentative_user_status.available_at = None
            tentative_user_status.after_committed_day = brief.day
            tentative_plan_status.current_slot = None
            committed_user_status = tentative_user_status
            committed_plan_status = tentative_plan_status
            start_coordinate = (
                (
                    day_start_location.latitude,
                    day_start_location.longitude,
                )
                if day_start_location is not None
                and day_start_location.latitude is not None
                and day_start_location.longitude is not None
                else None
            )
            optimized_items, transport_legs = self.route_optimizer.optimize(
                day_items,
                start=start_coordinate,
            )
            optimized_items = self._fit_timeline_after_routing(
                optimized_items,
                transport_legs,
                day=brief.day,
                warnings=warnings,
                plan_status=tentative_plan_status,
            )
            travel_minutes = sum(
                leg.estimated_duration_minutes for leg in transport_legs
            )
            walking_minutes = sum(
                leg.estimated_duration_minutes
                for leg in transport_legs
                if leg.mode == "walk"
            )
            self._increment_usage(
                tentative_plan_status.day_usage,
                travel_minutes=travel_minutes,
                walking_minutes=walking_minutes,
            )
            self._increment_usage(
                tentative_plan_status.trip_usage,
                travel_minutes=travel_minutes,
                walking_minutes=walking_minutes,
            )
            self._append_constraint_warnings(
                day=brief.day,
                user_status=tentative_user_status,
                plan_status=tentative_plan_status,
                warnings=warnings,
            )
            days.append(
                PlanDay(
                    day=brief.day,
                    theme=brief.theme,
                    strategy=skeleton.strategy,
                    items=optimized_items,
                    transportLegs=transport_legs,
                )
            )

        unscheduled = []
        for place in selected_places:
            if place.stable_ref not in committed_plan_status.remaining_selected_place_ids:
                continue
            rejection = rejected_selected_places.get(
                place.stable_ref,
                CandidateRejection(
                    "no_available_slot",
                    "Finder could not allocate this selected Place.",
                ),
            )
            unscheduled.append(
                UnscheduledPlace(
                    placeId=place.place_id,
                    name=place.name,
                    reasonCode=rejection.reason_code,
                    reason=rejection.reason,
                )
            )
        return FinderResult(
            days=days,
            finalUserStatus=committed_user_status,
            finalPlanStatus=committed_plan_status,
            unscheduledPlaces=unscheduled,
            warnings=warnings,
        )

    def _choose_candidate(
        self,
        *,
        brief,
        block: DayBlock,
        selected_by_ref: dict[str, SelectedPlaceContext],
        plan_status: FinderPlanStatus,
        user_status: UserStatus,
        avoided_place_names: set[str],
        intent_constraints: list[str],
        budget_level: str,
        rejected_selected_places: dict[str, CandidateRejection],
    ) -> FinderPlace | None:
        candidates: list[FinderPlace] = []
        preferred_refs = [
            ref
            for ref in brief.allocated_selected_place_refs
            if ref in plan_status.remaining_selected_place_ids
        ]
        for ref in preferred_refs:
            selected = selected_by_ref.get(ref)
            if selected is None:
                continue
            candidates.append(self._selected_to_candidate(selected, brief))

        region_key = (
            brief.target_region_key
            or brief.target_area
        )
        if region_key.startswith("vn,"):
            selected_place_ids = {
                place.place_id
                for place in selected_by_ref.values()
                if place.place_id is not None
            }
            candidates.extend(
                self.place_tool.search(
                    region_key=region_key,
                    target_tags=brief.focus_tags,
                    excluded_place_ids=(
                        set(plan_status.used_place_ids) | selected_place_ids
                    ),
                    limit=self.max_candidates_per_block,
                )
            )

        unique_candidates: list[FinderPlace] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.stable_ref in seen:
                continue
            seen.add(candidate.stable_ref)
            unique_candidates.append(candidate)

        attempts = 0
        for candidate in unique_candidates:
            if attempts >= self.max_candidates_per_block:
                break
            attempts += 1
            candidate_ref = candidate.stable_ref
            if candidate_ref in plan_status.used_place_ids:
                continue
            rejection = self._candidate_rejection(
                candidate,
                block,
                user_status,
                avoided_place_names=avoided_place_names,
                intent_constraints=intent_constraints,
                budget_level=budget_level,
            )
            if rejection is not None:
                if candidate_ref not in plan_status.rejected_candidate_ids:
                    plan_status.rejected_candidate_ids.append(
                        candidate_ref
                    )
                if candidate_ref in selected_by_ref:
                    rejected_selected_places[candidate_ref] = rejection
                continue
            return candidate
        return None

    def _selected_to_candidate(
        self,
        selected: SelectedPlaceContext,
        brief,
    ) -> FinderPlace:
        if selected.place_id:
            stored_place = self.place_tool.get(selected.place_id)
            if stored_place is not None:
                return stored_place.model_copy(
                    update={
                        "must_visit": selected.must_visit,
                        "source_refs": list(selected.source_refs),
                        "tags": list(
                            dict.fromkeys(
                                [*selected.tags, *stored_place.tags]
                            )
                        ),
                    }
                )
        return FinderPlace(
            placeId=selected.place_id,
            name=selected.name,
            placeType="selected_place",
            regionKey=(
                selected.region_key
                or brief.target_region_key
                or brief.target_area
            ),
            tags=selected.tags,
            latitude=selected.latitude,
            longitude=selected.longitude,
            mustVisit=selected.must_visit,
            sourceRefs=selected.source_refs,
            openingHours=[],
            dataConfidence="user_confirmed",
        )

    def _intensity_allowed(
        self,
        candidate: FinderPlace,
        user_status: UserStatus,
    ) -> bool:
        allowed = user_status.constraints.allowed_activity_intensities
        if not allowed or candidate.activity_intensity is None:
            return True
        return candidate.activity_intensity in allowed

    def _candidate_rejection(
        self,
        candidate: FinderPlace,
        block: DayBlock,
        user_status: UserStatus,
        *,
        avoided_place_names: set[str],
        intent_constraints: list[str],
        budget_level: str,
    ) -> CandidateRejection | None:
        if candidate.name.casefold() in avoided_place_names:
            return CandidateRejection(
                "avoided_by_user",
                "Place is explicitly avoided by the user.",
            )
        normalized_constraints = {
            constraint.strip().casefold().replace("-", "_").replace(" ", "_")
            for constraint in intent_constraints
        }
        if (
            normalized_constraints.intersection({"avoid_outdoor", "bad_weather", "rain", "indoor_only"})
            and self._is_outdoor(candidate)
        ):
            return CandidateRejection(
                "avoid_outdoor_constraint",
                "Place is outdoor but the plan requires avoiding outdoor activities.",
            )
        if (
            normalized_constraints.intersection({"bad_weather", "rain"})
            and candidate.weather_sensitivity
            and candidate.weather_sensitivity.casefold() in {"high", "outdoor"}
        ):
            return CandidateRejection(
                "weather_sensitivity",
                "Place is weather-sensitive and the plan has bad-weather constraints.",
            )
        if (
            budget_level == "budget"
            and candidate.price_level
            and candidate.price_level.casefold() in {"premium", "luxury", "high"}
        ):
            return CandidateRejection(
                "budget_mismatch",
                "Place price level is too high for the trip budget.",
            )
        duration = (
            candidate.typical_duration_minutes
            or block.duration_minutes
        )
        if not self._opening_hours_cover_block(candidate, block.time_window, duration):
            return CandidateRejection(
                "opening_hours_mismatch",
                "Place opening hours do not cover the planned time window.",
            )
        if duration > block.duration_minutes:
            return CandidateRejection(
                "duration_exceeds_slot",
                (
                    f"Typical duration {duration} minutes exceeds "
                    f"the {block.duration_minutes}-minute slot."
                ),
            )
        max_consecutive = (
            user_status.constraints.max_consecutive_active_minutes
        )
        if max_consecutive is not None and duration > max_consecutive:
            return CandidateRejection(
                "max_consecutive_active_minutes",
                (
                    f"Activity duration {duration} minutes exceeds the user's "
                    f"{max_consecutive}-minute consecutive activity limit."
                ),
            )
        accessibility_needs = {
            need.casefold()
            for need in user_status.constraints.accessibility_needs
        }
        accessibility_features = {
            feature.casefold()
            for feature in candidate.accessibility_features
        }
        if (
            accessibility_needs
            and not accessibility_needs.issubset(accessibility_features)
        ):
            return CandidateRejection(
                "accessibility_unmet",
                "Place does not satisfy the user's accessibility needs.",
            )
        if not self._intensity_allowed(candidate, user_status):
            return CandidateRejection(
                "activity_intensity_not_allowed",
                "Place intensity is outside the user's allowed activity intensities.",
            )
        return None

    def _is_outdoor(self, candidate: FinderPlace) -> bool:
        outdoor_markers = {
            "outdoor",
            "nature",
            "park",
            "beach",
            "hiking",
        }
        values = {
            candidate.place_type.casefold(),
            *(tag.casefold() for tag in candidate.tags),
        }
        return bool(values.intersection(outdoor_markers))

    def _block_is_available(
        self,
        block: DayBlock,
        user_status: UserStatus,
    ) -> bool:
        if not user_status.available_at:
            return True
        available_minutes = self._extract_clock_minutes(
            user_status.available_at
        )
        if available_minutes is None:
            return True
        block_start = self._extract_clock_minutes(block.time_window)
        return block_start is None or block_start >= available_minutes

    def _extract_clock_minutes(self, value: str) -> int | None:
        match = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)", value)
        if match is None:
            return None
        return int(match.group(1)) * 60 + int(match.group(2))

    def _append_constraint_warnings(
        self,
        *,
        day: int,
        user_status: UserStatus,
        plan_status: FinderPlanStatus,
        warnings: list[str],
    ) -> None:
        required_rest = user_status.constraints.required_rest_minutes
        if (
            required_rest is not None
            and plan_status.day_usage.rest_minutes < required_rest
        ):
            message = (
                f"Day {day} provides {plan_status.day_usage.rest_minutes} rest "
                f"minutes, below the required {required_rest}."
            )
            warnings.append(message)
            plan_status.warnings.append(message)
        max_walking = user_status.constraints.max_walking_minutes_per_day
        if max_walking is not None:
            if plan_status.day_usage.walking_minutes > max_walking:
                message = (
                    f"Day {day} estimated walking time "
                    f"{plan_status.day_usage.walking_minutes} minutes exceeds "
                    f"the {max_walking}-minute limit."
                )
            else:
                message = (
                    f"Day {day} estimated walking time is "
                    f"{plan_status.day_usage.walking_minutes} minutes; "
                    "route provider verification is still unavailable."
                )
            warnings.append(message)
            plan_status.warnings.append(message)

    def _build_activity_item(
        self,
        candidate: FinderPlace,
        block: DayBlock,
        *,
        mode: str,
        selected_source: bool,
    ) -> PlanItem:
        return PlanItem(
            itemId=str(uuid4()),
            placeId=candidate.place_id,
            name=candidate.name,
            timeWindow=block.time_window,
            placeType=(
                "must_visit"
                if selected_source
                and mode == "main"
                and candidate.must_visit
                else "selected_place"
                if selected_source and mode == "main"
                else "backup_option"
                if mode == "backup"
                else candidate.place_type
            ),
            role=block.role,
            source=(
                "selected_place"
                if selected_source
                else "finder_suggestion"
            ),
            durationMinutes=(
                candidate.typical_duration_minutes
                or block.duration_minutes
            ),
            activityIntensity=candidate.activity_intensity,
            sourceRefs=candidate.source_refs,
            tags=candidate.tags,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            notes="Selected by deterministic Finder candidate loop.",
        )

    def _build_non_activity_item(self, block: DayBlock) -> PlanItem:
        if block.kind == "meal":
            return PlanItem(
                itemId=str(uuid4()),
                name=(
                    "Lunch break"
                    if "lunch" in block.role
                    else "Meal break"
                ),
                timeWindow=block.time_window,
                placeType="meal",
                role=block.role,
                source="finder_rule",
                durationMinutes=block.duration_minutes,
                notes="Meal/rest block inserted by Finder day skeleton.",
            )
        return PlanItem(
            itemId=str(uuid4()),
            name=(
                "Break between main and support activities"
                if block.role == "break_main_support"
                else "Break between support and bonus activities"
                if block.role == "break_support_bonus"
                else "Flexible break"
            ),
            timeWindow=block.time_window,
            placeType="break",
            role=block.role,
            source="finder_rule",
            durationMinutes=block.duration_minutes,
            notes="No Place is required for this break block.",
        )

    def _fit_timeline_after_routing(
        self,
        items: list[PlanItem],
        transport_legs,
        *,
        day: int,
        warnings: list[str],
        plan_status: FinderPlanStatus,
    ) -> list[PlanItem]:
        if not items:
            return items
        leg_by_pair = {
            (leg.from_item_id, leg.to_item_id): leg
            for leg in transport_legs
        }
        fitted: list[PlanItem] = []
        previous: PlanItem | None = None
        previous_end: int | None = None
        shifted = False
        for item in items:
            start = self._extract_clock_minutes(item.time_window)
            duration = item.duration_minutes or self._window_duration_minutes(item.time_window)
            if start is None or duration is None:
                fitted.append(item)
                previous = item
                previous_end = None
                continue
            required_start = start
            if previous is not None and previous_end is not None:
                leg = leg_by_pair.get((previous.item_id, item.item_id))
                if leg is not None:
                    required_start = max(
                        required_start,
                        previous_end + leg.estimated_duration_minutes,
                    )
                else:
                    required_start = max(required_start, previous_end)
            if required_start > start:
                shifted = True
                item = item.model_copy(
                    update={
                        "time_window": self._format_clock_window(
                            required_start,
                            duration,
                        )
                    }
                )
            fitted.append(item)
            previous = item
            previous_end = required_start + duration
        if shifted:
            message = (
                f"Day {day} timeline was shifted to account for estimated "
                "travel time between scheduled places."
            )
            warnings.append(message)
            plan_status.warnings.append(message)
        last_end = previous_end
        if last_end is not None and last_end > 21 * 60:
            message = (
                f"Day {day} ends after 21:00 after route-aware timeline fitting."
            )
            warnings.append(message)
            plan_status.warnings.append(message)
        return fitted

    def _window_duration_minutes(self, value: str) -> int | None:
        parts = value.split("-", 1)
        if len(parts) != 2:
            return None
        start = self._extract_clock_minutes(parts[0])
        end = self._extract_clock_minutes(parts[1])
        if start is None or end is None:
            return None
        return max(0, end - start)

    def _format_clock_window(self, start: int, duration: int) -> str:
        return f"{self._format_clock(start)}-{self._format_clock(start + duration)}"

    def _format_clock(self, minutes: int) -> str:
        hour = minutes // 60
        minute = minutes % 60
        return f"{hour:02d}:{minute:02d}"

    def _opening_hours_cover_block(
        self,
        candidate: FinderPlace,
        time_window: str,
        duration_minutes: int,
    ) -> bool:
        if not candidate.opening_hours:
            return True
        start = self._extract_clock_minutes(time_window)
        if start is None:
            return True
        end = start + duration_minutes
        for hours in candidate.opening_hours:
            if hours.get("is24Hours"):
                return True
            open_minutes = self._parse_hour_value(hours.get("openTime"))
            close_minutes = self._parse_hour_value(hours.get("closeTime"))
            if open_minutes is None or close_minutes is None:
                continue
            if close_minutes <= open_minutes:
                close_minutes += 24 * 60
            adjusted_start = start
            adjusted_end = end
            if adjusted_start < open_minutes and adjusted_end <= close_minutes - 24 * 60:
                adjusted_start += 24 * 60
                adjusted_end += 24 * 60
            if open_minutes <= adjusted_start and adjusted_end <= close_minutes:
                return True
        return False

    def _parse_hour_value(self, value: object) -> int | None:
        if not isinstance(value, str):
            return None
        return self._extract_clock_minutes(value)

    def _apply_activity(
        self,
        candidate: FinderPlace,
        block: DayBlock,
        user_status: UserStatus,
        plan_status: FinderPlanStatus,
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
        duration = (
            candidate.typical_duration_minutes
            or block.duration_minutes
        )
        self._increment_usage(
            plan_status.day_usage,
            activity_minutes=duration,
            place_count=1,
        )
        self._increment_usage(
            plan_status.trip_usage,
            activity_minutes=duration,
            place_count=1,
        )
        if candidate.activity_intensity:
            self._apply_metric_delta(
                user_status,
                INTENSITY_EFFECTS.get(candidate.activity_intensity, {}),
            )
        user_status.location = UserStatusLocation(
            placeId=candidate.place_id,
            regionKey=candidate.region_key,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
        )

    def _apply_break(
        self,
        user_status: UserStatus,
        plan_status: FinderPlanStatus,
        block: DayBlock,
    ) -> None:
        self._increment_usage(
            plan_status.day_usage,
            rest_minutes=block.duration_minutes,
        )
        self._increment_usage(
            plan_status.trip_usage,
            rest_minutes=block.duration_minutes,
        )
        self._apply_metric_delta(user_status, BREAK_EFFECTS)

    def _apply_metric_delta(
        self,
        user_status: UserStatus,
        delta: dict[str, int],
    ) -> None:
        for metric, change in delta.items():
            current = getattr(user_status.metrics, metric)
            if current is None:
                continue
            setattr(
                user_status.metrics,
                metric,
                max(0, min(100, current + change)),
            )

    def _increment_usage(
        self,
        usage: FinderUsage,
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

    def _finish_day_location(self, user_status: UserStatus) -> None:
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

    def _normalize_selected_places(
        self,
        selected_places: list[SelectedPlaceContext] | list[str],
    ) -> list[SelectedPlaceContext]:
        return [
            (
                place
                if isinstance(place, SelectedPlaceContext)
                else SelectedPlaceContext(name=place, mustVisit=True)
            )
            for place in selected_places
        ]
