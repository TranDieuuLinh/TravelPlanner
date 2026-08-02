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
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer


class FinderService:
    def __init__(
        self,
        place_tool: FinderPlaceTool | None = None,
        *,
        max_candidates_per_block: int = 5,
        skeleton_builder: DaySkeletonBuilder | None = None,
        route_optimizer: GeographicRouteOptimizer | None = None,
        candidate_selector: CandidateSelector | None = None,
        timeline_fitter: TimelineFitter | None = None,
        status_tracker: FinderStatusTracker | None = None,
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
        self.status_tracker = status_tracker or FinderStatusTracker(self.place_tool)
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
                    brief, allocated_places
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
                    item.source == "finder_suggestion" for item in day_items
                )
                if (
                    allow_suggestions_for_block
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
                        day_items.append(self._build_non_activity_item(block))
                        self.status_tracker.apply_break(
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
                    self.status_tracker.rollback_activity(
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
            notes=candidate.source_activity or None,
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
        if block.kind == "meal":
            return PlanItem(
                itemId=str(uuid4()),
                name=(
                    "Lunch break"
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
                "Break between main and support activities"
                if block.role == "break_main_support"
                else "Break between support and bonus activities"
                if block.role == "break_support_bonus"
                else "Flexible break"
            ),
            timeWindow=block.time_window,
            placeType="break",
            timelineCategory="break",
            role=block.role,
            source="finder_rule",
            durationMinutes=block.duration_minutes,
            notes="No Place is required for this break block.",
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
