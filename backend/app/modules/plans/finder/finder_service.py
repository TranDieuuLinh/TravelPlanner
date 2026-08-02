from __future__ import annotations

from uuid import uuid4
from math import cos, radians

from app.modules.plans.domain.constraint_policy import ConstraintPolicy
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
)
from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    FinderAgentInput,
    FinderAgentOutput,
    PlanningAgentName,
    PlanningAgentStatus,
    SelectedPlaceContext,
    TourismZoneEvidence,
)
from app.modules.plans.finder.area_survey import (
    AreaProfile,
    AreaProfileProvider,
    StatisticsAreaProfileProvider,
)
from app.modules.plans.finder.candidate_selector import (
    CandidateRejection,
    CandidateSelectionContext,
    CandidateSelector,
    DEFAULT_MAX_CANDIDATES_PER_BLOCK,
    FAMOUS_PLACE_MAX_DISTANCE_METERS,
    candidate_feasible_start,
    candidate_duration,
)
from app.modules.plans.finder.place_tool import (
    EmptyFinderPlaceTool,
    FinderPlace,
    FinderPlaceTool,
    place_category,
)
from app.modules.plans.finder.skeleton_builder import DayBlock, DaySkeletonBuilder
from app.modules.plans.finder.status_tracker import PlanningStateTracker
from app.modules.plans.finder.timeline_fitter import TimelineFitter
from app.modules.plans.finder.time_windows import (
    format_clock_window,
    parse_clock_minutes,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer


class FinderService:
    def __init__(
        self,
        place_tool: FinderPlaceTool | None = None,
        *,
        max_candidates_per_block: int = DEFAULT_MAX_CANDIDATES_PER_BLOCK,
        skeleton_builder: DaySkeletonBuilder | None = None,
        route_optimizer: GeographicRouteOptimizer | None = None,
        candidate_selector: CandidateSelector | None = None,
        timeline_fitter: TimelineFitter | None = None,
        state_tracker: PlanningStateTracker | None = None,
        area_profile_provider: AreaProfileProvider | None = None,
    ) -> None:
        if max_candidates_per_block < 1:
            raise ValueError("max_candidates_per_block must be at least 1")
        self.place_tool = place_tool or EmptyFinderPlaceTool()
        self.max_candidates_per_block = max_candidates_per_block
        self.skeleton_builder = skeleton_builder or DaySkeletonBuilder()
        self.route_optimizer = route_optimizer or GeographicRouteOptimizer()
        self.candidate_selector = candidate_selector or CandidateSelector(
            self.place_tool,
            max_candidates_per_block=max_candidates_per_block,
        )
        self.timeline_fitter = timeline_fitter or TimelineFitter()
        self.state_tracker = state_tracker or PlanningStateTracker(self.place_tool)
        self.area_profile_provider = area_profile_provider
        if (
            self.area_profile_provider is None
            and not isinstance(self.place_tool, EmptyFinderPlaceTool)
        ):
            self.area_profile_provider = StatisticsAreaProfileProvider(self.place_tool)
        self._area_survey_cache: dict[str, AreaProfile] = {}

    def _get_area_profile(self, region_key: str) -> AreaProfile | None:
        if region_key not in self._area_survey_cache:
            if self.area_profile_provider is None:
                return None
            self._area_survey_cache[region_key] = self.area_profile_provider.get(
                region_key
            )
        return self._area_survey_cache.get(region_key)

    def fill_main_plan(
        self,
        macro_plan: MacroPlan,
        intent: TravelIntent,
        selected_places: list[SelectedPlaceContext] | list[str],
        *,
        user_status: UserStatus | None = None,
        plan_status: FinderPlanStatus | None = None,
        allow_finder_suggestions: bool = True,
    ) -> FinderResult:
        return self._fill_days(
            macro_plan,
            self._normalize_selected_places(selected_places),
            mode="main",
            user_status=user_status or UserStatus(),
            plan_status=plan_status or FinderPlanStatus(),
            avoided_place_names={name.casefold() for name in intent.avoid_places},
            intent_constraints=intent.constraints,
            allow_finder_suggestions=allow_finder_suggestions,
            constraint_policy=intent.constraint_policy,
            budget_level=intent.budget.value,
            trip_start_date=None,
            preferred_modes=set(),
            avoid_modes=set(),
            intent_interests=intent.interests,
            travel_style=intent.travel_style,
        )

    def fill_backup_plan(
        self,
        macro_plan: MacroPlan,
        intent: TravelIntent,
        selected_places: list[SelectedPlaceContext] | list[str],
        *,
        user_status: UserStatus | None = None,
        plan_status: FinderPlanStatus | None = None,
        allow_finder_suggestions: bool = True,
    ) -> FinderResult:
        return self._fill_days(
            macro_plan,
            self._normalize_selected_places(selected_places),
            mode="backup",
            user_status=user_status or UserStatus(),
            plan_status=plan_status or FinderPlanStatus(),
            avoided_place_names={name.casefold() for name in intent.avoid_places},
            intent_constraints=intent.constraints,
            allow_finder_suggestions=allow_finder_suggestions,
            constraint_policy=intent.constraint_policy,
            budget_level=intent.budget.value,
            trip_start_date=None,
            preferred_modes=set(),
            avoid_modes=set(),
            intent_interests=intent.interests,
            travel_style=intent.travel_style,
        )

    def fill_agent_plan(self, finder_input: FinderAgentInput) -> FinderAgentOutput:
        result = self._fill_days(
            finder_input.macro_plan,
            finder_input.selected_places,
            mode=finder_input.mode.value,
            user_status=finder_input.user_status,
            plan_status=finder_input.finder_plan_status,
            avoided_place_names={
                name.casefold() for name in finder_input.intent.avoid_places
            },
            intent_constraints=finder_input.intent.constraints,
            allow_finder_suggestions=finder_input.allow_finder_suggestions,
            constraint_policy=finder_input.intent.constraint_policy,
            budget_level=finder_input.trip_spec.budget.level.value,
            trip_start_date=finder_input.trip_spec.start_date,
            preferred_modes={
                mode.value for mode in finder_input.trip_spec.transport.preferred_modes
            },
            avoid_modes={
                mode.value for mode in finder_input.trip_spec.transport.avoid_modes
            },
            intent_interests=finder_input.intent.interests,
            travel_style=finder_input.intent.travel_style,
            tourism_zones=finder_input.tourism_zones,
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
        allow_finder_suggestions: bool,
        constraint_policy: ConstraintPolicy,
        budget_level: str,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
        intent_interests: list[str],
        travel_style: str,
        tourism_zones: list[TourismZoneEvidence] | None = None,
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
        selected_by_ref = {place.stable_ref: place for place in selected_places}
        zone_by_id = {
            zone.zone_id: zone for zone in (tourism_zones or [])
        }
        has_reference_places = any(
            place.source_order is not None
            or any(
                ref == "ocr" or ref.startswith(("http://", "https://"))
                for ref in place.source_refs
            )
            for place in selected_places
        )

        for brief in macro_plan.day_briefs:
            tourism_zone = (
                zone_by_id.get(brief.tourism_zone_ref)
                if brief.tourism_zone_ref is not None
                else None
            )
            day_start_location = committed_user_status.location
            tentative_user_status = committed_user_status.model_copy(deep=True)
            tentative_plan_status = committed_plan_status.model_copy(deep=True)
            allocated_places = [
                selected_by_ref[ref]
                for ref in brief.allocated_selected_place_refs
                if ref in selected_by_ref
            ]
            allow_suggestions_for_day = allow_finder_suggestions and (
                not has_reference_places or not allocated_places
            )
            if not allow_finder_suggestions and not allocated_places:
                days.append(
                    PlanDay(
                        day=brief.day,
                        theme=brief.theme,
                        strategy="reference_only",
                        items=[],
                        transportLegs=[],
                    )
                )
                continue
            has_source_itinerary = any(
                place.source_order is not None for place in allocated_places
            )
            region_key = brief.target_region_key or brief.target_area
            area_profile = self._get_area_profile(region_key) if region_key else None
            if has_source_itinerary:
                skeleton = self.skeleton_builder.build_source_itinerary(
                    brief,
                    allocated_places,
                    supplement_sparse_day=True,
                )
            else:
                skeleton = self.skeleton_builder.build_two_activity_day(
                    brief,
                    tentative_user_status,
                    intent_constraints=intent_constraints,
                    area_profile=area_profile,
                )
            skeleton = self.skeleton_builder.apply_flexible_needs(
                skeleton,
                brief,
            )
            tentative_plan_status.current_day = brief.day
            tentative_plan_status.current_strategy = skeleton.strategy
            tentative_plan_status.day_usage = FinderUsage()
            tentative_plan_status.used_food_drink_place_types = []
            tentative_plan_status.used_experience_groups = []
            day_items: list[PlanItem] = []
            committed_activities: dict[str, tuple[FinderPlace, DayBlock]] = {}
            deferred_slot_warnings: list[str] = []
            main_anchor_block = next(
                (
                    block
                    for block in skeleton.blocks
                    if block.activity
                    and block.kind == "activity"
                    and (
                        block.need_role == "main"
                        or "main_activity" in block.role
                    )
                ),
                None,
            )
            main_anchor_selected = main_anchor_block is None
            day_anchor_center: tuple[float, float] | None = None

            def selection_context(
                target_block: DayBlock,
                *,
                selection_user_status: UserStatus,
                selection_plan_status: FinderPlanStatus,
                allow_suggestions: bool,
                anchor_center: tuple[float, float] | None,
                corridor_destination: FinderPlace | None = None,
                reserved_place_ids: frozenset[str] = frozenset(),
            ) -> CandidateSelectionContext:
                return CandidateSelectionContext(
                    macro_plan=macro_plan,
                    brief=brief,
                    block=target_block,
                    selected_by_ref=selected_by_ref,
                    plan_status=selection_plan_status,
                    user_status=selection_user_status,
                    avoided_place_names=avoided_place_names,
                    intent_constraints=intent_constraints,
                    allow_finder_suggestions=allow_suggestions,
                    constraint_policy=constraint_policy,
                    budget_level=budget_level,
                    rejected_selected_places=rejected_selected_places,
                    intent_interests=intent_interests,
                    travel_style=travel_style,
                    bbox_filter=(
                        self._tourism_zone_bbox(tourism_zone)
                        if tourism_zone is not None
                        else area_profile.bbox
                        if area_profile is not None
                        else None
                    ),
                    zone_center=(
                        anchor_center
                        if anchor_center is not None
                        else (
                            tourism_zone.center_latitude,
                            tourism_zone.center_longitude,
                        )
                        if tourism_zone is not None
                        else None
                    ),
                    zone_radius_meters=(
                        tourism_zone.radius_meters
                        if tourism_zone is not None
                        else None
                    ),
                    corridor_destination=corridor_destination,
                    reserved_place_ids=reserved_place_ids,
                )

            # Phase 1: choose and reserve every activity before resolving any
            # meal. A disposable state copy preserves duplicate/proximity
            # behavior without applying activity effects to the real timeline.
            activity_candidates: dict[int, FinderPlace] = {}
            activity_selection_user = tentative_user_status.model_copy(deep=True)
            activity_selection_plan = tentative_plan_status.model_copy(deep=True)
            activity_anchor_center: tuple[float, float] | None = None
            activity_main_available = main_anchor_block is None
            for block_index, activity_block in enumerate(skeleton.blocks):
                if not activity_block.activity:
                    continue
                is_activity_main = (
                    main_anchor_block is not None
                    and activity_block.role == main_anchor_block.role
                )
                if not activity_main_available and not is_activity_main:
                    continue
                if not self.candidate_selector.block_is_available(
                    activity_block,
                    activity_selection_user,
                ):
                    continue
                activity_allow_suggestions = allow_suggestions_for_day
                if (
                    activity_block.role.startswith("finder_support")
                    and allow_finder_suggestions
                ):
                    activity_allow_suggestions = True
                activity_candidate = self.candidate_selector.select(
                    selection_context(
                        activity_block,
                        selection_user_status=activity_selection_user,
                        selection_plan_status=activity_selection_plan,
                        allow_suggestions=activity_allow_suggestions,
                        anchor_center=activity_anchor_center,
                    )
                )
                if activity_candidate is None:
                    continue
                activity_candidates[block_index] = activity_candidate
                self.state_tracker.apply_activity(
                    activity_candidate,
                    activity_block,
                    activity_selection_user,
                    activity_selection_plan,
                )
                if is_activity_main:
                    activity_main_available = True
                    if (
                        activity_candidate.latitude is not None
                        and activity_candidate.longitude is not None
                    ):
                        activity_anchor_center = (
                            activity_candidate.latitude,
                            activity_candidate.longitude,
                        )
            tentative_plan_status.rejected_candidate_ids = list(
                activity_selection_plan.rejected_candidate_ids
            )
            main_anchor_selected = activity_main_available
            reserved_activity_refs = frozenset(
                candidate.stable_ref
                for candidate in activity_candidates.values()
            )

            # Phase 2: fill the timeline. Meals can now see the next selected
            # activity and are ranked along the corridor between both stops.
            for block_index, block in enumerate(skeleton.blocks):
                tentative_plan_status.current_slot = block.role
                is_main_anchor = (
                    main_anchor_block is not None
                    and block.role == main_anchor_block.role
                )
                if (
                    not main_anchor_selected
                    and not is_main_anchor
                    and (block.activity or block.kind == "meal")
                ):
                    # A generated day is built around one concrete primary
                    # destination. Do not create a meals-only/support-only day
                    # from catalog suggestions when retrieval failed to
                    # establish that anchor. Core meal placeholders remain in
                    # the timeline so lunch/dinner semantics are not lost.
                    if block.kind == "meal":
                        day_items.append(self._build_non_activity_item(block))
                        self.state_tracker.apply_break(
                            tentative_user_status,
                            tentative_plan_status,
                            block,
                        )
                    continue
                if not self.candidate_selector.block_is_available(
                    block, tentative_user_status
                ):
                    if block.activity and not block.optional:
                        message = (
                            f"Day {brief.day} skipped {block.role} because "
                            "the user is only available at "
                            f"{tentative_user_status.available_at}."
                        )
                        warnings.append(message)
                        tentative_plan_status.warnings.append(message)
                    continue
                if not block.activity and block.kind != "meal":
                    if (
                        block.kind == "break"
                        and not self._break_is_needed(
                            block,
                            tentative_user_status,
                            tentative_plan_status,
                        )
                    ):
                        continue
                    day_items.append(self._build_non_activity_item(block))
                    if block.kind != "social_activity":
                        self.state_tracker.apply_break(
                            tentative_user_status,
                            tentative_plan_status,
                            block,
                        )
                    continue

                allow_suggestions_for_block = allow_suggestions_for_day
                if block.kind == "meal":
                    # Meal blocks always draw from the finder catalog. The
                    # ``has_reference_places`` gate is about respecting the
                    # user's reference itinerary for activity slots; meals
                    # need evidence-backed places regardless of whether the
                    # user attached a URL.
                    allow_suggestions_for_block = True
                corridor_destination = (
                    next(
                        (
                            activity_candidates[next_index]
                            for next_index in range(
                                block_index + 1,
                                len(skeleton.blocks),
                            )
                            if next_index in activity_candidates
                        ),
                        None,
                    )
                    if block.kind == "meal"
                    else None
                )
                candidate = activity_candidates.get(block_index)
                if not block.activity:
                    candidate = self.candidate_selector.select(
                        selection_context(
                            block,
                            selection_user_status=tentative_user_status,
                            selection_plan_status=tentative_plan_status,
                            allow_suggestions=allow_suggestions_for_block,
                            anchor_center=day_anchor_center,
                            corridor_destination=corridor_destination,
                            reserved_place_ids=reserved_activity_refs,
                        )
                    )
                if candidate is None:
                    message = (
                        f"Day {brief.day} has no valid candidate for {block.role}."
                    )
                    if block.kind == "meal":
                        day_items.append(self._build_non_activity_item(block))
                        self.state_tracker.apply_break(
                            tentative_user_status,
                            tentative_plan_status,
                            block,
                        )
                        if allow_suggestions_for_block:
                            meal_message = (
                                f"Day {brief.day} uses an unresolved meal "
                                f"placeholder for {block.role}; no verified "
                                "food place matched the slot."
                            )
                            warnings.append(meal_message)
                            tentative_plan_status.warnings.append(meal_message)
                    elif not block.optional:
                        if block.role.startswith("support_activity"):
                            deferred_slot_warnings.append(message)
                        else:
                            warnings.append(message)
                            tentative_plan_status.warnings.append(message)
                    continue

                selected_source = candidate.stable_ref in selected_by_ref
                activity_item = self._build_activity_item(
                    candidate,
                    block,
                    mode=mode,
                    selected_source=selected_source,
                )
                day_items.append(activity_item)
                if activity_item.item_id is not None:
                    committed_activities[activity_item.item_id] = (candidate, block)
                self.state_tracker.apply_activity(
                    candidate,
                    block,
                    tentative_user_status,
                    tentative_plan_status,
                )
                if is_main_anchor:
                    main_anchor_selected = True
                    if (
                        candidate.latitude is not None
                        and candidate.longitude is not None
                    ):
                        day_anchor_center = (
                            candidate.latitude,
                            candidate.longitude,
                        )

            present_roles = {item.role for item in day_items if item.role}
            break_requirements = {
                "break_main_support": ("main_activity", "support_activity"),
                "break_support_bonus": ("support_activity", "bonus_activity"),
            }
            retained_items: list[PlanItem] = []
            blocks_by_role = {block.role: block for block in skeleton.blocks}
            for item in day_items:
                required_roles = break_requirements.get(item.role or "")
                if required_roles and not all(
                    role in present_roles for role in required_roles
                ):
                    block = blocks_by_role.get(item.role or "")
                    if block is not None:
                        self.state_tracker.rollback_break(
                            tentative_user_status,
                            tentative_plan_status,
                            block,
                        )
                    continue
                retained_items.append(item)
            day_items = retained_items

            minimum_place_count = (
                4
                if skeleton.strategy == "multi_stop"
                else 2
                if skeleton.strategy in {"relaxed", "recovery"}
                else 3
            )
            if (
                deferred_slot_warnings
                and tentative_plan_status.day_usage.place_count < minimum_place_count
            ):
                warnings.extend(deferred_slot_warnings)
                tentative_plan_status.warnings.extend(deferred_slot_warnings)
            self.state_tracker.finish_day_location(tentative_user_status)
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
                preserve_order=(
                    has_source_itinerary
                    or any(item.role and "meal" in item.role for item in day_items)
                ),
                day=brief.day,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
            )
            timeline_result = self.timeline_fitter.fit(
                optimized_items,
                transport_legs,
                day=brief.day,
                warnings=warnings,
                plan_status=tentative_plan_status,
            )
            optimized_items = timeline_result.items
            overflow_items = timeline_result.overflow_items
            if overflow_items:
                retained_item_ids = {
                    item.item_id
                    for item in optimized_items
                    if item.item_id is not None
                }
                transport_legs = [
                    leg
                    for leg in transport_legs
                    if leg.from_item_id in retained_item_ids
                    and leg.to_item_id in retained_item_ids
                ]
                for item in overflow_items:
                    committed = (
                        committed_activities.get(item.item_id)
                        if item.item_id is not None
                        else None
                    )
                    if committed is None:
                        continue
                    candidate, block = committed
                    self.state_tracker.rollback_activity(
                        candidate,
                        block,
                        tentative_user_status,
                        tentative_plan_status,
                        restore_selected=candidate.stable_ref in selected_by_ref,
                    )
                    rejected_selected_places[candidate.stable_ref] = CandidateRejection(
                        "timeline_overflow",
                        (
                            f"Day {brief.day} has no remaining time before "
                            "24:00 after travel time is included."
                        ),
                    )
            travel_minutes = sum(
                leg.estimated_duration_minutes for leg in transport_legs
            )
            walking_minutes = sum(
                leg.estimated_duration_minutes
                for leg in transport_legs
                if leg.mode == "walk"
            )
            self.state_tracker.increment_usage(
                tentative_plan_status.day_usage,
                travel_minutes=travel_minutes,
                walking_minutes=walking_minutes,
            )
            self.state_tracker.increment_usage(
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

    @staticmethod
    def _break_is_needed(
        block: DayBlock,
        user_status: UserStatus,
        plan_status: FinderPlanStatus,
    ) -> bool:
        if block.role == "recovery_break":
            return True
        required_rest = user_status.constraints.required_rest_minutes
        return (
            required_rest is not None
            and plan_status.day_usage.rest_minutes < required_rest
        )
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
        timeline_category = (
            "food"
            if block.kind == "meal" or place_category(candidate) == "food_drink"
            else "activity"
        )
        duration_minutes = candidate_duration(candidate, block)
        block_start = candidate_feasible_start(
            candidate,
            block,
            duration_minutes,
        )
        time_window = (
            format_clock_window(block_start, duration_minutes, bound_to_day=True)
            if block_start is not None
            else block.time_window
        )
        return PlanItem(
            itemId=str(uuid4()),
            placeId=candidate.place_id,
            name=candidate.name,
            timeWindow=time_window,
            placeType=(
                "must_visit"
                if selected_source and mode == "main" and candidate.must_visit
                else "selected_place"
                if selected_source and mode == "main"
                else "backup_option"
                if mode == "backup"
                else candidate.place_type
            ),
            timelineCategory=timeline_category,
            regionKey=candidate.region_key,
            role=block.role,
            source="selected_place" if selected_source else "finder_suggestion",
            durationMinutes=duration_minutes,
            activityIntensity=candidate.activity_intensity,
            sourceRefs=candidate.source_refs,
            sourceProvider=candidate.source_provider,
            tags=candidate.tags,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            notes=candidate.source_activity or None,
            sourceOrder=candidate.source_order,
            sourceDay=candidate.source_day,
            sourceTimeHint=candidate.source_time_hint,
            sourceActivity=candidate.source_activity,
        )

    def _build_non_activity_item(self, block: DayBlock) -> PlanItem:
        if block.kind == "meal":
            return PlanItem(
                itemId=str(uuid4()),
                name=(
                    "Breakfast break"
                    if "breakfast" in block.role
                    else "Lunch break"
                    if "lunch" in block.role
                    else "Dinner break"
                    if "dinner" in block.role
                    else "Meal break"
                ),
                timeWindow=block.time_window,
                placeType="meal",
                timelineCategory="food",
                role=block.role,
                source="finder_rule",
                durationMinutes=block.duration_minutes,
                notes=(
                    "Chưa tìm được địa điểm ăn uống phù hợp đã được xác minh "
                    "cho khung giờ này."
                ),
            )
        if block.kind == "social_activity" or block.role == "group_social_activity":
            return PlanItem(
                itemId=str(uuid4()),
                name="Group social activity",
                timeWindow=block.time_window,
                placeType="group_activity",
                timelineCategory="activity",
                role=block.role,
                source="finder_rule",
                durationMinutes=block.duration_minutes,
                notes="Tính năng gợi ý hoạt động nhóm sẽ sớm ra mắt.",
            )
        return PlanItem(
            itemId=str(uuid4()),
            name=(
                "Thá»i gian nghá»‰ vÃ  phá»¥c há»“i"
                if block.role == "recovery_break"
                else "Thá»i gian nghá»‰ vÃ  linh hoáº¡t"
            ),
            timeWindow=block.time_window,
            placeType="break",
            timelineCategory="break",
            role=block.role,
            source="finder_rule",
            durationMinutes=block.duration_minutes,
            notes="KhÃ´ng cáº§n chá»n Ä‘á»‹a Ä‘iá»ƒm cho khoáº£ng nghá»‰ nÃ y.",
        )

    @staticmethod
    def _tourism_zone_bbox(
        zone: TourismZoneEvidence,
    ) -> tuple[float, float, float, float]:
        retrieval_radius = max(
            zone.radius_meters,
            FAMOUS_PLACE_MAX_DISTANCE_METERS,
        )
        latitude_delta = retrieval_radius / 111_320
        longitude_scale = max(
            0.01,
            cos(radians(zone.center_latitude)),
        )
        longitude_delta = retrieval_radius / (111_320 * longitude_scale)
        return (
            zone.center_latitude - latitude_delta,
            zone.center_longitude - longitude_delta,
            zone.center_latitude + latitude_delta,
            zone.center_longitude + longitude_delta,
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
