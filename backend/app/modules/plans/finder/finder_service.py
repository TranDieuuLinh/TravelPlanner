from __future__ import annotations

from uuid import uuid4

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
    UserStatusLocation,
)
from app.modules.plans.domain.enums import TravelPace
from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    FinderAgentInput,
    FinderAgentOutput,
    PlanningAgentName,
    PlanningAgentStatus,
    SelectedPlaceContext,
)
from app.modules.plans.finder.area_survey import AreaProfile, AreaSurveyService
from app.modules.plans.finder.candidate_selector import (
    CandidateRejection,
    CandidateSelectionContext,
    CandidateSelector,
    candidate_duration,
)
from app.modules.plans.finder.day_style_selector import select_day_style
from app.modules.plans.finder.place_tool import (
    EmptyFinderPlaceTool,
    FinderPlace,
    FinderPlaceTool,
    place_category,
)
from app.modules.plans.finder.skeleton_builder import DayBlock, DaySkeletonBuilder
from app.modules.plans.finder.status_tracker import FinderStatusTracker
from app.modules.plans.finder.timeline_fitter import TimelineFitter
from app.modules.plans.itinerary_optimizer import ItineraryOptimizer
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer


class FinderService:
    def __init__(
        self,
        place_tool: FinderPlaceTool | None = None,
        *,
        max_candidates_per_block: int = 5,
        skeleton_builder: DaySkeletonBuilder | None = None,
        route_optimizer: ItineraryOptimizer | GeographicRouteOptimizer | None = None,
        candidate_selector: CandidateSelector | None = None,
        timeline_fitter: TimelineFitter | None = None,
        status_tracker: FinderStatusTracker | None = None,
        meal_selector=None,
    ) -> None:
        if max_candidates_per_block < 1:
            raise ValueError("max_candidates_per_block must be at least 1")
        self.place_tool = place_tool or EmptyFinderPlaceTool()
        self.skeleton_builder = skeleton_builder or DaySkeletonBuilder()
        self.route_optimizer = route_optimizer or GeographicRouteOptimizer()
        route_first_mode = bool(
            getattr(self.route_optimizer, "supports_fixed_anchors", False)
        )
        effective_candidate_limit = (
            max(250, max_candidates_per_block)
            if route_first_mode
            else max_candidates_per_block
        )
        self.max_candidates_per_block = effective_candidate_limit
        self.candidate_selector = candidate_selector or CandidateSelector(
            self.place_tool,
            max_candidates_per_block=effective_candidate_limit,
        )
        self.timeline_fitter = timeline_fitter or TimelineFitter()
        self.status_tracker = status_tracker or FinderStatusTracker(self.place_tool)
        self.meal_selector = meal_selector
        self._area_survey_cache: dict[str, AreaProfile] = {}
        self._area_survey_service: AreaSurveyService | None = None

    @property
    def _survey_service(self) -> AreaSurveyService:
        if self._area_survey_service is None:
            self._area_survey_service = AreaSurveyService(self.place_tool)
        return self._area_survey_service

    def _get_area_profile(self, region_key: str) -> AreaProfile | None:
        if region_key not in self._area_survey_cache:
            if not isinstance(self.place_tool, EmptyFinderPlaceTool):
                result = self._survey_service.survey(region_key)
                self._area_survey_cache[region_key] = result.profile
            else:
                return None
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
        has_reference_places = any(
            place.source_order is not None
            or any(
                ref == "ocr" or ref.startswith(("http://", "https://"))
                for ref in place.source_refs
            )
            for place in selected_places
        )
        route_first_mode = bool(
            getattr(self.route_optimizer, "supports_fixed_anchors", False)
        )
        if route_first_mode and self.meal_selector is not None:
            return self._fill_route_first_days(
                macro_plan,
                selected_places,
                mode=mode,
                user_status=committed_user_status,
                plan_status=committed_plan_status,
                avoided_place_names=avoided_place_names,
                intent_constraints=intent_constraints,
                allow_finder_suggestions=allow_finder_suggestions,
                constraint_policy=constraint_policy,
                budget_level=budget_level,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
                intent_interests=intent_interests,
                travel_style=travel_style,
            )

        for brief in macro_plan.day_briefs:
            day_start_location = committed_user_status.location
            tentative_user_status = committed_user_status.model_copy(deep=True)
            tentative_plan_status = committed_plan_status.model_copy(deep=True)
            allocated_places = [
                selected_by_ref[ref]
                for ref in brief.allocated_selected_place_refs
                if ref in selected_by_ref
            ]
            allow_suggestions_for_day = allow_finder_suggestions and (
                route_first_mode
                or not has_reference_places
                or not allocated_places
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
                    supplement_sparse_day=(
                        route_first_mode and allow_suggestions_for_day
                    ),
                )
            elif self.skeleton_builder._needs_recovery(tentative_user_status):
                skeleton = self.skeleton_builder.build(
                    brief,
                    tentative_user_status,
                    intent_constraints=intent_constraints,
                    area_profile=area_profile,
                )
            elif self.skeleton_builder._prefers_indoor(intent_constraints or []):
                skeleton = self.skeleton_builder.build(
                    brief,
                    tentative_user_status,
                    intent_constraints=intent_constraints,
                    area_profile=area_profile,
                )
            else:
                effective_pace = self.skeleton_builder._effective_pace(
                    brief.pace, tentative_user_status, area_profile
                )
                if effective_pace == TravelPace.packed:
                    skeleton = self.skeleton_builder.build(
                        brief,
                        tentative_user_status,
                        intent_constraints=intent_constraints,
                        area_profile=area_profile,
                    )
                elif effective_pace == TravelPace.relaxed:
                    skeleton = self.skeleton_builder.build(
                        brief,
                        tentative_user_status,
                        intent_constraints=intent_constraints,
                        area_profile=area_profile,
                    )
                else:
                    decision = select_day_style(
                        [
                            self._resolve_finder_place_for_style(
                                ref, selected_by_ref, region_key
                            )
                            for ref in brief.allocated_selected_place_refs
                        ],
                        area_profile_distribution=(
                            area_profile.distribution
                            if area_profile is not None
                            else None
                        ),
                    )
                    skeleton = self.skeleton_builder.build_by_style(
                        decision.style,
                        brief,
                        tentative_user_status,
                        intent_constraints=intent_constraints,
                        area_profile=area_profile,
                    )
            tentative_plan_status.current_day = brief.day
            tentative_plan_status.current_strategy = skeleton.strategy
            tentative_plan_status.day_usage = FinderUsage()
            tentative_plan_status.used_food_drink_place_types = []
            day_items: list[PlanItem] = []
            committed_activities: dict[str, tuple[FinderPlace, DayBlock]] = {}
            deferred_slot_warnings: list[str] = []
            finder_suggestion_limit = self.skeleton_builder.minimum_activity_count(
                brief.pace
            )

            for block in skeleton.blocks:
                tentative_plan_status.current_slot = block.role
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
                    if route_first_mode and block.kind == "social_activity":
                        # Do not pad a route-first plan with an unsupported
                        # feature placeholder. It adds no visitable Place and
                        # makes an otherwise sparse itinerary look complete.
                        continue
                    day_items.append(self._build_non_activity_item(block))
                    if block.kind != "social_activity":
                        self.status_tracker.apply_break(
                            tentative_user_status,
                            tentative_plan_status,
                            block,
                        )
                    continue

                allow_suggestions_for_block = allow_suggestions_for_day
                finder_suggestion_count = sum(
                    item.source == "finder_suggestion"
                    and item.timeline_category == "activity"
                    for item in day_items
                )
                if (
                    block.kind != "meal"
                    and allow_suggestions_for_block
                    and finder_suggestion_count >= finder_suggestion_limit
                ):
                    allow_suggestions_for_block = False
                candidate = self.candidate_selector.select(
                    CandidateSelectionContext(
                        macro_plan=macro_plan,
                        brief=brief,
                        block=block,
                        selected_by_ref=selected_by_ref,
                        plan_status=tentative_plan_status,
                        user_status=tentative_user_status,
                        avoided_place_names=avoided_place_names,
                        intent_constraints=intent_constraints,
                        allow_finder_suggestions=allow_suggestions_for_block,
                        constraint_policy=constraint_policy,
                        budget_level=budget_level,
                        rejected_selected_places=rejected_selected_places,
                        intent_interests=intent_interests,
                        travel_style=travel_style,
                        strict_day_theme=not bool(
                            getattr(
                                self.route_optimizer,
                                "supports_fixed_anchors",
                                False,
                            )
                        ),
                        occupied_items=[
                            *(
                                item
                                for completed_day in days
                                for item in completed_day.items
                            ),
                            *day_items,
                        ],
                        bbox_filter=(
                            area_profile.bbox
                            if area_profile is not None
                            else None
                        ),
                    )
                )
                if candidate is None:
                    message = (
                        f"Day {brief.day} has no valid candidate for {block.role}."
                    )
                    if block.kind == "meal":
                        self.status_tracker.apply_break(
                            tentative_user_status,
                            tentative_plan_status,
                            block,
                        )
                        if allow_suggestions_for_block:
                            meal_message = (
                                f"Day {brief.day} omits unresolved meal slot "
                                f"{block.role}; no verified food place matched it."
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
                self.status_tracker.apply_activity(
                    candidate,
                    block,
                    tentative_user_status,
                    tentative_plan_status,
                )

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
            self.status_tracker.finish_day_location(tentative_user_status)
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
            optimizer_handles_fixed_anchors = route_first_mode
            if optimizer_handles_fixed_anchors:
                # Route-first mode defers matrix ordering and all detailed
                # walk/car/transit leg calls until every day has candidates.
                optimized_items = list(day_items)
                transport_legs = []
            else:
                optimized_items, transport_legs = self.route_optimizer.optimize(
                    day_items,
                    start=start_coordinate,
                    preserve_order=(
                        has_source_itinerary
                        or any(
                            item.role and "meal" in item.role
                            for item in day_items
                        )
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
                        self.status_tracker.rollback_activity(
                            candidate,
                            block,
                            tentative_user_status,
                            tentative_plan_status,
                            restore_selected=candidate.stable_ref in selected_by_ref,
                        )
                        rejected_selected_places[candidate.stable_ref] = (
                            CandidateRejection(
                                "timeline_overflow",
                                (
                                    f"Day {brief.day} has no remaining time before "
                                    "24:00 after travel time is included."
                                ),
                            )
                        )
                travel_minutes = sum(
                    leg.estimated_duration_minutes for leg in transport_legs
                )
                walking_minutes = sum(
                    leg.estimated_duration_minutes
                    for leg in transport_legs
                    if leg.mode == "walk"
                )
                self.status_tracker.increment_usage(
                    tentative_plan_status.day_usage,
                    travel_minutes=travel_minutes,
                    walking_minutes=walking_minutes,
                )
                self.status_tracker.increment_usage(
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

        optimize_trip = getattr(self.route_optimizer, "optimize_trip", None)
        if callable(optimize_trip):
            days = optimize_trip(
                days,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
            )
            fitted_days: list[PlanDay] = []
            for day in days:
                timeline_result = self.timeline_fitter.fit(
                    day.items,
                    day.transport_legs,
                    day=day.day,
                    warnings=warnings,
                    plan_status=committed_plan_status,
                )
                retained_item_ids = {
                    item.item_id
                    for item in timeline_result.items
                    if item.item_id is not None
                }
                retained_legs = [
                    leg
                    for leg in day.transport_legs
                    if leg.from_item_id in retained_item_ids
                    and leg.to_item_id in retained_item_ids
                ]
                for item in timeline_result.overflow_items:
                    selected_ref = self._selected_ref_for_item(
                        item,
                        selected_places,
                    )
                    if selected_ref is not None:
                        rejected_selected_places[selected_ref] = CandidateRejection(
                            "timeline_overflow",
                            (
                                f"Day {day.day} has no remaining time before "
                                "24:00 after final route time is included."
                            ),
                        )
                fitted_days.append(
                    day.model_copy(
                        update={
                            "items": timeline_result.items,
                            "transport_legs": retained_legs,
                        }
                    )
                )
            days = fitted_days

            scheduled_selected_refs = {
                selected_ref
                for day in days
                for item in day.items
                if (
                    selected_ref := self._selected_ref_for_item(
                        item,
                        selected_places,
                    )
                )
                is not None
            }
            committed_plan_status.remaining_selected_place_ids = [
                place.stable_ref
                for place in selected_places
                if place.stable_ref not in scheduled_selected_refs
            ]
            all_legs = [leg for day in days for leg in day.transport_legs]
            trip_travel_minutes = sum(
                leg.estimated_duration_minutes for leg in all_legs
            )
            trip_walking_minutes = sum(
                leg.estimated_duration_minutes
                for leg in all_legs
                if leg.mode == "walk"
            )
            all_items = [item for day in days for item in day.items]
            committed_plan_status.trip_usage = FinderUsage(
                activityMinutes=sum(
                    item.duration_minutes or 0
                    for item in all_items
                    if item.timeline_category == "activity"
                ),
                travelMinutes=trip_travel_minutes,
                walkingMinutes=trip_walking_minutes,
                restMinutes=sum(
                    item.duration_minutes or 0
                    for item in all_items
                    if item.timeline_category == "break"
                ),
                placeCount=sum(item.place_id is not None for item in all_items),
            )
            if days:
                last_day_legs = days[-1].transport_legs
                last_day_items = days[-1].items
                committed_plan_status.day_usage = FinderUsage(
                    activityMinutes=sum(
                        item.duration_minutes or 0
                        for item in last_day_items
                        if item.timeline_category == "activity"
                    ),
                    travelMinutes=sum(
                        leg.estimated_duration_minutes
                        for leg in last_day_legs
                    ),
                    walkingMinutes=sum(
                        leg.estimated_duration_minutes
                        for leg in last_day_legs
                        if leg.mode == "walk"
                    ),
                    restMinutes=sum(
                        item.duration_minutes or 0
                        for item in last_day_items
                        if item.timeline_category == "break"
                    ),
                    placeCount=sum(
                        item.place_id is not None for item in last_day_items
                    ),
                )
                last_located = next(
                    (
                        item
                        for item in reversed(days[-1].items)
                        if item.latitude is not None
                        and item.longitude is not None
                    ),
                    None,
                )
                if last_located is not None:
                    committed_user_status.location = UserStatusLocation(
                        placeId=last_located.place_id,
                        regionKey=last_located.region_key,
                        latitude=last_located.latitude,
                        longitude=last_located.longitude,
                    )
            for day in days:
                day_usage = FinderUsage(
                    travelMinutes=sum(
                        leg.estimated_duration_minutes
                        for leg in day.transport_legs
                    ),
                    walkingMinutes=sum(
                        leg.estimated_duration_minutes
                        for leg in day.transport_legs
                        if leg.mode == "walk"
                    ),
                    restMinutes=sum(
                        item.duration_minutes or 0
                        for item in day.items
                        if item.timeline_category == "break"
                    ),
                )
                constraint_status = committed_plan_status.model_copy(
                    update={"day_usage": day_usage}
                )
                self._append_constraint_warnings(
                    day=day.day,
                    user_status=committed_user_status,
                    plan_status=constraint_status,
                    warnings=warnings,
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

    def _fill_route_first_days(
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
    ) -> FinderResult:
        """Select two activities, optimize them, then add three route meals."""

        selected_by_ref = {place.stable_ref: place for place in selected_places}
        rejected_selected_places: dict[str, CandidateRejection] = {}
        warnings: list[str] = []
        activity_days: list[PlanDay] = []
        selected_meals_by_day: dict[int, list[SelectedPlaceContext]] = {}
        trip_theme_slots = [
            requirement
            for requirement in macro_plan.trip_themes
            for _ in range(requirement.minimum_activities)
        ]
        activity_slot_index = 0

        for brief in macro_plan.day_briefs:
            allocated_places = [
                selected_by_ref[ref]
                for ref in brief.allocated_selected_place_refs
                if ref in selected_by_ref
                and ref in plan_status.remaining_selected_place_ids
            ]
            if not allow_finder_suggestions and not allocated_places:
                activity_days.append(
                    PlanDay(
                        day=brief.day,
                        theme=brief.theme,
                        strategy="reference_only",
                        items=[],
                        transportLegs=[],
                    )
                )
                continue

            region_key = brief.target_region_key or brief.target_area
            area_profile = self._get_area_profile(region_key) if region_key else None
            selected_meals = [
                place
                for place in allocated_places
                if place_category(
                    self.candidate_selector._selected_to_candidate(place, brief)
                ) == "food_drink"
            ]
            selected_meals_by_day[brief.day] = selected_meals
            selected_activities = [
                place for place in allocated_places if place not in selected_meals
            ]
            activity_brief = brief.model_copy(
                update={
                    "allocated_selected_place_refs": [
                        place.stable_ref for place in selected_activities
                    ]
                }
            )
            skeleton = self.skeleton_builder.build_route_first_activities(
                activity_brief,
                selected_activities,
            )
            plan_status.current_day = brief.day
            plan_status.current_strategy = skeleton.strategy
            plan_status.day_usage = FinderUsage()
            day_items: list[PlanItem] = []
            for block in skeleton.blocks:
                plan_status.current_slot = block.role
                requirement = (
                    trip_theme_slots[activity_slot_index]
                    if activity_slot_index < len(trip_theme_slots)
                    else None
                )
                activity_slot_index += 1
                selection_brief = (
                    activity_brief.model_copy(
                        update={
                            "theme": requirement.theme,
                            "focus_tags": requirement.focus_tags,
                        }
                    )
                    if requirement is not None
                    else activity_brief
                )
                candidate = self.candidate_selector.select(
                    CandidateSelectionContext(
                        macro_plan=macro_plan,
                        brief=selection_brief,
                        block=block,
                        selected_by_ref=selected_by_ref,
                        plan_status=plan_status,
                        user_status=user_status,
                        avoided_place_names=avoided_place_names,
                        intent_constraints=intent_constraints,
                        allow_finder_suggestions=allow_finder_suggestions,
                        constraint_policy=constraint_policy,
                        budget_level=budget_level,
                        rejected_selected_places=rejected_selected_places,
                        intent_interests=intent_interests,
                        travel_style=travel_style,
                        strict_day_theme=False,
                        enforce_opening_hours=False,
                        occupied_items=[
                            *(
                                item
                                for completed_day in activity_days
                                for item in completed_day.items
                            ),
                            *day_items,
                        ],
                        bbox_filter=(
                            area_profile.bbox
                            if area_profile is not None
                            else None
                        ),
                    )
                )
                if candidate is None:
                    message = (
                        f"Day {brief.day} has no valid candidate for {block.role}."
                    )
                    warnings.append(message)
                    plan_status.warnings.append(message)
                    continue
                selected_source = candidate.stable_ref in selected_by_ref
                item = self._build_activity_item(
                    candidate,
                    block,
                    mode=mode,
                    selected_source=selected_source,
                )
                day_items.append(item)
                self.status_tracker.apply_activity(
                    candidate,
                    block,
                    user_status,
                    plan_status,
                )
            plan_status.current_slot = None
            user_status.after_committed_day = brief.day
            self.status_tracker.finish_day_location(user_status)
            activity_days.append(
                PlanDay(
                    day=brief.day,
                    theme=brief.theme,
                    strategy=skeleton.strategy,
                    items=day_items,
                    transportLegs=[],
                )
            )

        optimize_trip = getattr(self.route_optimizer, "optimize_trip", None)
        if callable(optimize_trip):
            activity_days = optimize_trip(
                activity_days,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
                enrich_routes=False,
            )

        completed_days: list[PlanDay] = []
        used_refs = set(plan_status.used_place_ids)
        briefs_by_day = {brief.day: brief for brief in macro_plan.day_briefs}
        for day in activity_days:
            brief = briefs_by_day[day.day]
            activities = [
                item for item in day.items if item.timeline_category == "activity"
            ][:2]
            selected_meal_refs = self._selected_meal_role_refs(
                selected_meals_by_day.get(day.day, [])
            )
            region_key = brief.target_region_key or brief.target_area
            area_profile = self._get_area_profile(region_key) if region_key else None
            meal_candidates = self.meal_selector.select_for_day(
                region_key=region_key,
                activities=activities,
                excluded_place_ids={
                    *used_refs,
                    *(
                        place.stable_ref
                        for place in selected_meals_by_day.get(day.day, [])
                    ),
                    *(
                        place.place_id
                        for place in selected_meals_by_day.get(day.day, [])
                        if place.place_id is not None
                    ),
                },
                bbox_filter=(area_profile.bbox if area_profile is not None else None),
            )
            ordered_items: list[PlanItem] = []
            activity_index = 0
            sequence = (
                ("breakfast_meal", "00:00-00:01", "meal"),
                ("main_activity_1", "00:01-00:02", "activity"),
                ("lunch_meal", "00:02-00:03", "meal"),
                ("main_activity_2", "00:03-00:04", "activity"),
                ("dinner_meal", "00:04-00:05", "meal"),
            )
            for role, marker, kind in sequence:
                if kind == "activity":
                    if activity_index < len(activities):
                        ordered_items.append(
                            activities[activity_index].model_copy(
                                update={"role": role, "time_window": marker}
                            )
                        )
                    activity_index += 1
                    continue
                block = DayBlock(
                    role=role,
                    time_window=marker,
                    duration_minutes=60,
                    activity=False,
                    kind="meal",
                    candidate_category="food_drink",
                )
                selected_meal_ref = selected_meal_refs.get(role)
                candidate = None
                selected_source = False
                if selected_meal_ref is not None:
                    candidate = self.candidate_selector.select(
                        CandidateSelectionContext(
                            macro_plan=macro_plan,
                            brief=brief,
                            block=DayBlock(
                                role=role,
                                time_window=marker,
                                duration_minutes=60,
                                activity=False,
                                preferred_ref=selected_meal_ref,
                                kind="meal",
                                candidate_category="food_drink",
                            ),
                            selected_by_ref=selected_by_ref,
                            plan_status=plan_status,
                            user_status=user_status,
                            avoided_place_names=avoided_place_names,
                            intent_constraints=intent_constraints,
                            allow_finder_suggestions=False,
                            constraint_policy=constraint_policy,
                            budget_level=budget_level,
                            rejected_selected_places=rejected_selected_places,
                            intent_interests=intent_interests,
                            travel_style=travel_style,
                            strict_day_theme=False,
                            enforce_opening_hours=False,
                            occupied_items=[
                                *(
                                    item
                                    for completed_day in completed_days
                                    for item in completed_day.items
                                ),
                                *ordered_items,
                            ],
                            bbox_filter=(
                                area_profile.bbox
                                if area_profile is not None
                                else None
                            ),
                        )
                    )
                    selected_source = candidate is not None
                if candidate is None:
                    candidate = meal_candidates.get(role)
                if candidate is None:
                    message = (
                        f"Day {day.day} omits unresolved meal slot {role} "
                        "after route-based fallback search."
                    )
                    warnings.append(message)
                    plan_status.warnings.append(message)
                    continue
                meal_item = self._build_activity_item(
                    candidate,
                    block,
                    mode=mode,
                    selected_source=selected_source,
                )
                ordered_items.append(meal_item)
                used_refs.add(candidate.stable_ref)
                self.status_tracker.apply_activity(
                    candidate,
                    block,
                    user_status,
                    plan_status,
                )

            routed_items, transport_legs = self.route_optimizer.optimize(
                ordered_items,
                preserve_order=True,
                day=day.day,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
            )
            completed_days.append(
                day.model_copy(
                    update={
                        "theme": self._route_cluster_theme(
                            macro_plan,
                            activities,
                        ),
                        "items": routed_items,
                        "transport_legs": transport_legs,
                    }
                )
            )

        scheduled_selected_refs = {
            selected_ref
            for day in completed_days
            for item in day.items
            if (
                selected_ref := self._selected_ref_for_item(item, selected_places)
            )
            is not None
        }
        plan_status.remaining_selected_place_ids = [
            place.stable_ref
            for place in selected_places
            if place.stable_ref not in scheduled_selected_refs
        ]
        all_items = [item for day in completed_days for item in day.items]
        all_legs = [leg for day in completed_days for leg in day.transport_legs]
        plan_status.trip_usage = FinderUsage(
            activityMinutes=sum(
                item.duration_minutes or 0
                for item in all_items
                if item.timeline_category == "activity"
            ),
            travelMinutes=sum(
                leg.estimated_duration_minutes for leg in all_legs
            ),
            walkingMinutes=sum(
                leg.estimated_duration_minutes
                for leg in all_legs
                if leg.mode == "walk"
            ),
            restMinutes=sum(
                item.duration_minutes or 0
                for item in all_items
                if item.timeline_category == "food"
            ),
            placeCount=sum(item.place_id is not None for item in all_items),
        )
        if completed_days:
            last_items = completed_days[-1].items
            last_legs = completed_days[-1].transport_legs
            plan_status.day_usage = FinderUsage(
                activityMinutes=sum(
                    item.duration_minutes or 0
                    for item in last_items
                    if item.timeline_category == "activity"
                ),
                travelMinutes=sum(
                    leg.estimated_duration_minutes for leg in last_legs
                ),
                walkingMinutes=sum(
                    leg.estimated_duration_minutes
                    for leg in last_legs
                    if leg.mode == "walk"
                ),
                restMinutes=sum(
                    item.duration_minutes or 0
                    for item in last_items
                    if item.timeline_category == "food"
                ),
                placeCount=sum(item.place_id is not None for item in last_items),
            )
            last_located = next(
                (
                    item
                    for item in reversed(last_items)
                    if item.latitude is not None and item.longitude is not None
                ),
                None,
            )
            if last_located is not None:
                user_status.location = UserStatusLocation(
                    placeId=last_located.place_id,
                    regionKey=last_located.region_key,
                    latitude=last_located.latitude,
                    longitude=last_located.longitude,
                )

        unscheduled = []
        for place in selected_places:
            if place.stable_ref not in plan_status.remaining_selected_place_ids:
                continue
            rejection = rejected_selected_places.get(
                place.stable_ref,
                CandidateRejection(
                    "no_day_capacity",
                    "The fixed two-activity daily capacity is full.",
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
            days=completed_days,
            finalUserStatus=user_status,
            finalPlanStatus=plan_status,
            unscheduledPlaces=unscheduled,
            warnings=warnings,
        )

    @staticmethod
    def _selected_meal_role_refs(
        places: list[SelectedPlaceContext],
    ) -> dict[str, str]:
        """Put URL food stops into meal slots before Finder suggestions."""

        remaining_roles = ["breakfast_meal", "lunch_meal", "dinner_meal"]
        assignments: dict[str, str] = {}
        deferred: list[SelectedPlaceContext] = []
        ordered = sorted(
            places,
            key=lambda place: (
                place.source_order is None,
                place.source_order or 10_000,
                place.name.casefold(),
            ),
        )
        for place in ordered:
            hint = (place.source_time_hint or "").strip().casefold()
            role = (
                "breakfast_meal"
                if any(value in hint for value in ("breakfast", "morning"))
                else "lunch_meal"
                if any(value in hint for value in ("lunch", "noon"))
                else "dinner_meal"
                if any(
                    value in hint
                    for value in ("dinner", "evening", "night")
                )
                else None
            )
            if role is None or role not in remaining_roles:
                deferred.append(place)
                continue
            assignments[role] = place.stable_ref
            remaining_roles.remove(role)
        for role, place in zip(remaining_roles, deferred):
            assignments[role] = place.stable_ref
        return assignments

    @staticmethod
    def _route_cluster_theme(
        macro_plan: MacroPlan,
        activities: list[PlanItem],
    ) -> str:
        activity_tags = {
            tag.casefold()
            for item in activities
            for tag in item.tags
        }
        ranked = sorted(
            (
                (
                    len(
                        activity_tags.intersection(
                            tag.casefold() for tag in requirement.focus_tags
                        )
                    ),
                    index,
                    requirement.theme,
                )
                for index, requirement in enumerate(macro_plan.trip_themes)
            ),
            key=lambda entry: (-entry[0], entry[1]),
        )
        matched = [theme for score, _, theme in ranked if score > 0][:2]
        if matched:
            return " · ".join(matched)
        activity_names = [item.name for item in activities[:2]]
        if activity_names:
            return " · ".join(activity_names)
        return "Cụm tham quan gần nhau"

    @staticmethod
    def _selected_ref_for_item(
        item: PlanItem,
        selected_places: list[SelectedPlaceContext],
    ) -> str | None:
        for place in selected_places:
            if (
                place.place_id is not None
                and item.place_id is not None
                and place.place_id == item.place_id
            ) or place.name.casefold() == item.name.casefold():
                return place.stable_ref
        return None

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
        timeline_category = (
            "food"
            if block.kind == "meal" or place_category(candidate) == "food_drink"
            else "activity"
        )
        return PlanItem(
            itemId=str(uuid4()),
            placeId=candidate.place_id,
            name=candidate.name,
            address=candidate.address,
            timeWindow=block.time_window,
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
            durationMinutes=candidate_duration(candidate, block),
            activityIntensity=candidate.activity_intensity,
            sourceRefs=candidate.source_refs,
            sourceProvider=candidate.source_provider,
            tags=candidate.tags,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            notes=(
                candidate.notes
                or candidate.source_activity
                or candidate.description
                or None
            ),
            personalNotes=candidate.personal_notes,
            imageUrls=candidate.image_urls,
            rating=candidate.rating,
            reviewCount=candidate.review_count,
            sourceOrder=candidate.source_order,
            sourceDay=candidate.source_day,
            sourceTimeHint=candidate.source_time_hint,
            sourceActivity=candidate.source_activity,
        )

    def _resolve_finder_place_for_style(
        self,
        ref: str,
        selected_by_ref: dict[str, SelectedPlaceContext],
        fallback_region_key: str,
    ) -> FinderPlace:
        """Best-effort conversion of a selected_place ref into a FinderPlace.

        Used only for day-style classification; missing data must not break
        the rest of the finder pipeline, so we fall back to a stub with the
        place_type field set to ``"selected_place"`` (an unknown category).
        """
        selected = selected_by_ref.get(ref)
        if selected is None:
            return FinderPlace(
                name=ref,
                placeType="selected_place",
                regionKey=fallback_region_key,
            )
        if selected.place_id:
            stored = self.place_tool.get(selected.place_id)
            if stored is not None:
                return stored
        return FinderPlace(
            placeId=selected.place_id,
            name=selected.name,
            placeType=selected.tags[0] if selected.tags else "selected_place",
            regionKey=selected.region_key or fallback_region_key,
            tags=list(selected.tags),
        )

    def _build_non_activity_item(self, block: DayBlock) -> PlanItem:
        if block.kind == "social_activity" or block.role == "group_social_activity":
            return PlanItem(
                itemId=str(uuid4()),
                name="Hoạt động nhóm",
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
                "Nghỉ giữa hoạt động chính và hoạt động bổ trợ"
                if block.role == "break_main_support"
                else "Nghỉ giữa hoạt động bổ trợ và hoạt động thêm"
                if block.role == "break_support_bonus"
                else "Thời gian nghỉ linh hoạt"
            ),
            timeWindow=block.time_window,
            placeType="break",
            timelineCategory="break",
            role=block.role,
            source="finder_rule",
            durationMinutes=block.duration_minutes,
            notes="Khoảng nghỉ này không cần địa điểm cụ thể.",
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
