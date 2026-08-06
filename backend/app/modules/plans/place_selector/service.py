from __future__ import annotations

from uuid import uuid4

from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.plans.domain.entities import (
    PlaceSelectionDay,
    PlaceSelectionStatus,
    PlaceSelectionResult,
    PlaceSelectionUsage,
    PlaceSelectionBlueprint,
    PlanDay,
    PlanItem,
    PlanTransportLeg,
    TravelIntent,
    ExperienceCategory,
    UnscheduledPlace,
    UserStatus,
    UserStatusLocation,
)
from app.modules.plans.domain.enums import TravelPace
from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    PlaceSelectionInput,
    PlaceSelectionOutput,
    PlanningAgentName,
    PlanningAgentStatus,
    SelectedPlaceContext,
)
from app.modules.plans.place_selector.area_survey import AreaProfile, AreaSurveyService
from app.modules.plans.place_selector.candidate_selector import (
    CandidateRejection,
    CandidateSelectionContext,
    CandidateSelector,
    candidate_duration,
)
from app.modules.plans.place_selector.day_style_selector import select_day_style
from app.modules.plans.place_selector.place_tool import (
    EmptyPlaceSelectionTool,
    SelectablePlace,
    PlaceSelectionTool,
    place_category,
)
from app.modules.plans.place_selector.skeleton_builder import (
    DayBlock,
    DaySkeletonBuilder,
)
from app.modules.plans.place_selector.status_tracker import PlaceSelectionStatusTracker
from app.modules.plans.place_selector.timeline_fitter import TimelineFitter
from app.modules.plans.place_selector.meal_selector import MealStopSelector
from app.modules.plans.itinerary_optimizer import ItineraryOptimizer
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.plans.place_selector.timeline_policy import (
    ACTIVITY_WINDOWS,
    DAILY_ACTIVITY_MINUTES,
    DEFAULT_TRANSITION_MINUTES,
    MEAL_ANCHORS,
    MINIMUM_FILLABLE_GAP_MINUTES,
    activity_allocation_cost,
    hint_matches_activity_window,
    selected_activity_duration,
)
from app.modules.plans.place_selector.time_windows import (
    format_clock_window,
    parse_clock_minutes,
    preferred_start_minutes,
    time_window_matches_preference,
)


class PlaceSelectorService:
    def __init__(
        self,
        place_tool: PlaceSelectionTool | None = None,
        *,
        max_candidates_per_block: int = 5,
        skeleton_builder: DaySkeletonBuilder | None = None,
        route_optimizer: ItineraryOptimizer | GeographicRouteOptimizer | None = None,
        candidate_selector: CandidateSelector | None = None,
        timeline_fitter: TimelineFitter | None = None,
        status_tracker: PlaceSelectionStatusTracker | None = None,
        meal_selector=None,
        graph_repository=None,
        nearby_radius_km: float = 5.0,
        nearby_route_cost_provider=None,
    ) -> None:
        if max_candidates_per_block < 1:
            raise ValueError("max_candidates_per_block must be at least 1")
        self.place_tool = place_tool or EmptyPlaceSelectionTool()
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
        self.status_tracker = status_tracker or PlaceSelectionStatusTracker(
            self.place_tool
        )
        self.meal_selector = meal_selector or MealStopSelector(self.place_tool)
        self._area_survey_cache: dict[str, AreaProfile] = {}
        self._area_survey_service: AreaSurveyService | None = None
        self.graph_repository = graph_repository
        self.nearby_radius_km = nearby_radius_km
        self.nearby_route_cost_provider = nearby_route_cost_provider

    @property
    def _survey_service(self) -> AreaSurveyService:
        if self._area_survey_service is None:
            self._area_survey_service = AreaSurveyService(
                self.place_tool,
                graph_repository=self.graph_repository,
                route_cost_provider=self.nearby_route_cost_provider,
            )
        return self._area_survey_service

    def _fill_nearby_graph_experiences(
        self,
        selected_places: list[SelectedPlaceContext],
        *,
        region_key: str | None,
        interests: list[str],
    ) -> list[SelectedPlaceContext]:
        """Add bounded graph experiences after selected anchors are known."""
        if self.graph_repository is None:
            return selected_places
        result = list(selected_places)
        existing = {place.stable_ref for place in result}
        existing_activities = {
            place.activity_id for place in result if place.activity_id is not None
        }
        nearby_category_counts: dict[str, int] = {}
        for anchor in list(selected_places):
            if not anchor.must_visit or not anchor.place_id:
                continue
            stored_anchor = self.place_tool.get(anchor.place_id)
            if stored_anchor is None:
                continue
            survey = self._survey_service.survey_near_anchor(
                stored_anchor,
                region_key=region_key or anchor.region_key,
                interests=interests,
                radius_km=self.nearby_radius_km,
            )
            context_names = tuple(
                (survey.context_by_place_id or {}).get(anchor.place_id, ())
            )
            if context_names:
                index = next(
                    (position for position, item in enumerate(result)
                     if item.stable_ref == anchor.stable_ref),
                    None,
                )
                if index is not None:
                    result[index] = result[index].model_copy(update={
                        "context_places": list(dict.fromkeys([
                            *result[index].context_places,
                            *context_names,
                        ])),
                    })
            ordered_candidates = sorted(
                survey.candidates,
                key=lambda item: (
                    0 if item.predicate == "SPECIAL_EXPERIENCE" else 1,
                    0 if any(
                        token.casefold() in item.activity_name.casefold()
                        for token in interests
                        if token.strip()
                    ) else 1,
                    item.route_cost_km,
                ),
            )
            for nearby in ordered_candidates:
                if nearby.activity_id in existing_activities:
                    continue
                candidate = nearby.place
                if candidate.stable_ref in existing:
                    continue
                # A graph-backed offer may be a meal/supporting stop. It is never
                # promoted to a main experience unless SPECIAL_EXPERIENCE exists.
                is_meal = place_category(candidate) == "food_drink"
                candidate_bucket = "meal" if is_meal else nearby.predicate
                if nearby_category_counts.get(candidate_bucket, 0) >= 2:
                    continue
                category = (
                    ExperienceCategory.meal
                    if is_meal
                    else ExperienceCategory.main_experience
                    if nearby.predicate == "SPECIAL_EXPERIENCE"
                    else ExperienceCategory.supporting_stop
                )
                result.append(
                    SelectedPlaceContext(
                        placeId=candidate.place_id,
                        name=candidate.name,
                        address=candidate.address,
                        regionKey=candidate.region_key,
                        latitude=candidate.latitude,
                        longitude=candidate.longitude,
                        tags=candidate.tags,
                        sourceRefs=list(nearby.source_refs),
                        claimIds=list(nearby.claim_ids),
                        activityId=nearby.activity_id,
                        experienceCategory=category,
                        sourceProvider=candidate.source_provider,
                        candidateEntityIds=[candidate.place_id] if candidate.place_id else [],
                        selectionMethod="nearby_graph_survey",
                        identityConfidence=candidate.data_confidence,
                        notes=(
                            f"Graph evidence: {nearby.activity_name}; "
                            f"route cost {nearby.route_cost_km:.1f} km from {anchor.name}."
                        ),
                        sourceActivity=nearby.activity_name,
                        preferredTimeWindows=list(nearby.preferred_time_windows),
                    )
                )
                existing.add(candidate.stable_ref)
                existing_activities.add(nearby.activity_id)
                nearby_category_counts[candidate_bucket] = (
                    nearby_category_counts.get(candidate_bucket, 0) + 1
                )
        return result

    def _get_area_profile(self, region_key: str) -> AreaProfile | None:
        if region_key not in self._area_survey_cache:
            if not isinstance(self.place_tool, EmptyPlaceSelectionTool):
                result = self._survey_service.survey(region_key)
                self._area_survey_cache[region_key] = result.profile
            else:
                return None
        return self._area_survey_cache.get(region_key)

    def fill_main_plan(
        self,
        selection_blueprint: PlaceSelectionBlueprint,
        intent: TravelIntent,
        selected_places: list[SelectedPlaceContext] | list[str],
        *,
        user_status: UserStatus | None = None,
        plan_status: PlaceSelectionStatus | None = None,
        allow_place_suggestions: bool = True,
    ) -> PlaceSelectionResult:
        normalized_selected = self._fill_nearby_graph_experiences(
            self._normalize_selected_places(selected_places),
            region_key=selection_blueprint.region_key or intent.destination,
            interests=intent.interests,
        )
        selected_refs = {
            ref
            for day in selection_blueprint.selection_days
            for ref in day.allocated_selected_place_refs
        }
        added = [
            place for place in normalized_selected
            if place.stable_ref not in selected_refs
        ]
        if added and selection_blueprint.selection_days:
            selection_blueprint = selection_blueprint.model_copy(deep=True)
            target_day = selection_blueprint.selection_days[0]
            target_day.allocated_selected_place_refs.extend(
                place.stable_ref for place in added
            )
        return self._fill_days(
            selection_blueprint,
            normalized_selected,
            mode="main",
            user_status=user_status or UserStatus(),
            plan_status=plan_status or PlaceSelectionStatus(),
            avoided_place_names={name.casefold() for name in intent.avoid_places},
            intent_constraints=intent.constraints,
            allow_place_suggestions=allow_place_suggestions,
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
        selection_blueprint: PlaceSelectionBlueprint,
        intent: TravelIntent,
        selected_places: list[SelectedPlaceContext] | list[str],
        *,
        user_status: UserStatus | None = None,
        plan_status: PlaceSelectionStatus | None = None,
        allow_place_suggestions: bool = True,
    ) -> PlaceSelectionResult:
        return self._fill_days(
            selection_blueprint,
            self._normalize_selected_places(selected_places),
            mode="backup",
            user_status=user_status or UserStatus(),
            plan_status=plan_status or PlaceSelectionStatus(),
            avoided_place_names={name.casefold() for name in intent.avoid_places},
            intent_constraints=intent.constraints,
            allow_place_suggestions=allow_place_suggestions,
            constraint_policy=intent.constraint_policy,
            budget_level=intent.budget.value,
            trip_start_date=None,
            preferred_modes=set(),
            avoid_modes=set(),
            intent_interests=intent.interests,
            travel_style=intent.travel_style,
        )

    def fill_agent_plan(
        self,
        selection_input: PlaceSelectionInput,
    ) -> PlaceSelectionOutput:
        # Day creation belongs to PlaceSelector. TripThemePlanner supplies only
        # trip-wide requirements and never returns calendar structure.
        required_places, unresolved_requirements = self._required_experience_places(
            selection_input
        )
        selected_places = list(selection_input.selected_places)
        known_refs = {place.stable_ref for place in selected_places}
        for place in required_places:
            if place.stable_ref not in known_refs:
                selected_places.append(place)
                known_refs.add(place.stable_ref)
        effective_input = selection_input.model_copy(
            update={"selected_places": selected_places}
        )
        selected_places = self._fill_nearby_graph_experiences(
            selected_places,
            region_key=selection_input.region_key,
            interests=selection_input.intent.interests,
        )
        effective_input = effective_input.model_copy(
            update={"selected_places": selected_places}
        )
        selection_blueprint = self._build_selection_blueprint(effective_input)
        result = self._fill_days(
            selection_blueprint,
            selected_places,
            mode=selection_input.mode.value,
            user_status=selection_input.user_status,
            plan_status=selection_input.place_selection_status,
            avoided_place_names={
                name.casefold() for name in selection_input.intent.avoid_places
            },
            intent_constraints=selection_input.intent.constraints,
            allow_place_suggestions=selection_input.allow_place_suggestions,
            constraint_policy=selection_input.intent.constraint_policy,
            budget_level=selection_input.trip_spec.budget.level.value,
            trip_start_date=selection_input.trip_spec.start_date,
            preferred_modes={
                mode.value
                for mode in selection_input.trip_spec.transport.preferred_modes
            },
            avoid_modes={
                mode.value for mode in selection_input.trip_spec.transport.avoid_modes
            },
            intent_interests=selection_input.intent.interests,
            travel_style=selection_input.intent.travel_style,
        )
        committed_place_count = sum(
            item.place_id is not None or item.source == "selected_place"
            for day in result.days
            for item in day.items
        )
        warnings = list(result.warnings)
        if unresolved_requirements:
            warnings.append(
                "Một số special experience bắt buộc chưa resolve được thành "
                "địa điểm cụ thể và được giữ ở danh sách chưa xếp."
            )
        return PlaceSelectionOutput(
            mode=selection_input.mode,
            finalDays=result.days,
            tripCostEstimate=None,
            unscheduledPlaces=[
                *result.unscheduled_places,
                *unresolved_requirements,
            ],
            finalUserStatus=result.final_user_status,
            finalPlanStatus=result.final_plan_status,
            warnings=warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.place_selector,
                status=(
                    PlanningAgentStatus.completed
                    if committed_place_count
                    else PlanningAgentStatus.blocked
                ),
                summary=(
                    "PlaceSelector created and filled route-first days."
                    if committed_place_count
                    else "No Place could be committed to the day skeletons."
                ),
                notes=[
                    f"committedPlaceCount={committed_place_count}",
                    "requiredExperienceCount="
                    f"{len(selection_input.required_experiences)}",
                    "unscheduledPlaceCount="
                    f"{len(result.unscheduled_places) + len(unresolved_requirements)}",
                ],
            ),
        )

    def _required_experience_places(
        self,
        selection_input: PlaceSelectionInput,
    ) -> tuple[list[SelectedPlaceContext], list[UnscheduledPlace]]:
        existing = {
            place.place_id: place
            for place in selection_input.selected_places
            if place.place_id is not None
        }
        resolved: list[SelectedPlaceContext] = []
        unresolved: list[UnscheduledPlace] = []
        for requirement in selection_input.required_experiences:
            policy = requirement.selection_policy.value
            if policy == "required_anchor":
                candidate_ids = requirement.anchor_place_ids
            else:
                candidate_ids = requirement.candidate_place_ids
            if policy == "open_candidate":
                candidate_ids = []
                searched = self.place_tool.search(
                    region_key=selection_input.region_key,
                    target_tags=[requirement.theme, requirement.activity_id or ""],
                    excluded_place_ids=set(existing),
                    limit=max(requirement.minimum_required, 5),
                )
                candidate_ids = [candidate.stable_ref for candidate in searched]
                for candidate in searched:
                    if candidate.stable_ref not in existing:
                        existing[candidate.stable_ref] = self._candidate_to_selected(
                            candidate,
                            requirement,
                        )
            matched = 0
            attempted_ids: list[str] = []
            for place_id in candidate_ids:
                if policy != "required_anchor" and matched >= requirement.minimum_required:
                    break
                attempted_ids.append(place_id)
                selected = existing.get(place_id)
                if selected is None:
                    candidate = self.place_tool.get(place_id)
                    if candidate is not None:
                        selected = self._candidate_to_selected(candidate, requirement)
                else:
                    selected_category = (
                        ExperienceCategory.meal
                        if place_category(
                            self.candidate_selector._selected_to_candidate(
                                selected, PlaceSelectionDay(
                                    day=1,
                                    theme=requirement.theme,
                                    targetArea=selection_input.region_key,
                                )
                            )
                        ) == "food_drink"
                        else selected.experience_category or requirement.category
                    )
                    selected = selected.model_copy(
                        update={
                            "must_visit": True,
                            "source_refs": list(
                                dict.fromkeys(
                                    [
                                        *selected.source_refs,
                                        *requirement.source_refs,
                                        "required_experience:"
                                        f"{requirement.requirement_id}",
                                    ]
                                )
                            ),
                            "claim_ids": list(
                                dict.fromkeys(
                                    [*selected.claim_ids, *requirement.claim_ids]
                                )
                            ),
                            "activity_id": selected.activity_id or requirement.activity_id,
                            "experience_category": selected_category,
                            "source_activity": (
                                selected.source_activity or requirement.theme
                            ),
                            "source_duration_minutes": (
                                selected.source_duration_minutes
                                or requirement.recommended_visit_minutes
                            ),
                            # A current-trip timing cue has higher priority than
                            # taxonomy-derived graph guidance.
                            "preferred_time_windows": (
                                []
                                if selected.source_time_hint
                                else requirement.preferred_time_windows
                            ),
                        }
                    )
                if selected is not None:
                    resolved.append(selected)
                    matched += 1
            required_count = (
                len(requirement.anchor_place_ids)
                if policy == "required_anchor"
                else requirement.minimum_required
            )
            if matched < required_count:
                unresolved.append(
                    UnscheduledPlace(
                        placeId=(attempted_ids[-1] if attempted_ids else None),
                        name=requirement.theme,
                        reasonCode="required_experience_unresolved",
                        reason=requirement.reason,
                        sourceRefs=requirement.source_refs,
                        sourceActivity=(requirement.activity_id or requirement.theme),
                    )
                )
        return resolved, unresolved

    @staticmethod
    def _candidate_to_selected(candidate: SelectablePlace, requirement) -> SelectedPlaceContext:
        """Project a catalog candidate into the planner's selected-place contract."""
        source_refs = list(
            dict.fromkeys(
                [
                    *candidate.source_refs,
                    *requirement.source_refs,
                    f"required_experience:{requirement.requirement_id}",
                ]
            )
        )
        claim_ids = list(dict.fromkeys([*candidate.claim_ids, *requirement.claim_ids]))
        category = (
            ExperienceCategory.meal
            if place_category(candidate) == "food_drink"
            else requirement.category
        )
        return SelectedPlaceContext(
            placeId=candidate.place_id,
            name=candidate.name,
            address=candidate.address,
            mustVisit=True,
            regionKey=candidate.region_key,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            tags=candidate.tags,
            sourceRefs=source_refs,
            claimIds=claim_ids,
            activityId=candidate.activity_id or requirement.activity_id,
            experienceCategory=category,
            sourceProvider=candidate.source_provider,
            sourceImportNodeId=candidate.source_import_node_id,
            candidateEntityIds=candidate.candidate_entity_ids,
            selectionMethod=candidate.selection_method,
            routeScore=candidate.route_score,
            identityConfidence=candidate.identity_confidence,
            notes=requirement.reason,
            imageUrls=candidate.image_urls,
            rating=candidate.rating,
            reviewCount=candidate.review_count,
            sourceActivity=requirement.theme,
            preferredTimeWindows=requirement.preferred_time_windows,
            sourceDurationMinutes=requirement.recommended_visit_minutes,
        )

    @staticmethod
    def _build_selection_blueprint(
        selection_input: PlaceSelectionInput,
    ) -> PlaceSelectionBlueprint:
        """Build private route slots from trip duration and source anchors.

        PlaceSelectionBlueprint remains only as an internal compatibility type while the
        selector algorithms are migrated; it is no longer an LLM, workflow,
        API, or persisted Plan contract.
        """

        day_count = selection_input.trip_spec.days
        allocated_by_day: dict[int, list[str]] = {
            day: [] for day in range(1, day_count + 1)
        }
        activity_minutes_by_day = {day: 0 for day in range(1, day_count + 1)}
        meal_count_by_day = {day: 0 for day in range(1, day_count + 1)}
        for place in sorted(
            selection_input.selected_places,
            key=lambda value: (
                value.source_day or 10_000,
                value.source_order or 10_000,
                value.name.casefold(),
            ),
        ):
            meal = is_meal_place(
                tags=place.tags,
                source_activity=place.source_activity,
            ) and "cafe" not in {tag.casefold() for tag in place.tags}
            cost = activity_allocation_cost(place.source_duration_minutes)
            eligible_days = [
                candidate_day
                for candidate_day in allocated_by_day
                if (
                    meal_count_by_day[candidate_day] < len(MEAL_ANCHORS)
                    if meal
                    else activity_minutes_by_day[candidate_day] + cost
                    <= DAILY_ACTIVITY_MINUTES
                )
            ]
            source_day_is_available = (
                place.source_day is not None
                and place.source_day in allocated_by_day
                and (
                    not meal
                    or meal_count_by_day[place.source_day] < len(MEAL_ANCHORS)
                )
            )
            if source_day_is_available:
                day = place.source_day
            else:
                day = (
                    min(
                        eligible_days,
                        key=lambda candidate_day: (
                            meal_count_by_day[candidate_day]
                            if meal
                            else activity_minutes_by_day[candidate_day],
                            candidate_day,
                        ),
                    )
                    if eligible_days
                    else day_count
                )
            allocated_by_day[day].append(place.stable_ref)
            if meal:
                meal_count_by_day[day] += 1
            else:
                activity_minutes_by_day[day] += cost

        stay_by_day = {
            day: stay
            for stay in selection_input.intent.destination_stays
            for day in range(stay.start_day, stay.end_day + 1)
        }
        all_tags = list(
            dict.fromkeys(
                tag
                for requirement in selection_input.trip_themes
                for tag in requirement.focus_tags
            )
        )
        return PlaceSelectionBlueprint(
            title=f"Kế hoạch cho {selection_input.intent.destination}",
            destination=selection_input.intent.destination,
            regionKey=selection_input.region_key,
            tripThemes=selection_input.trip_themes,
            selectionDays=[
                PlaceSelectionDay(
                    day=day,
                    theme="Tối ưu theo tuyến",
                    targetArea=(
                        stay_by_day[day].name
                        if day in stay_by_day
                        else selection_input.intent.destination
                    ),
                    targetRegionKey=selection_input.region_key,
                    focusTags=all_tags,
                    pace=selection_input.intent.pace,
                    allocatedSelectedPlaceRefs=allocated_by_day[day],
                )
                for day in range(1, day_count + 1)
            ],
        )

    def _fill_days(
        self,
        selection_blueprint: PlaceSelectionBlueprint,
        selected_places: list[SelectedPlaceContext],
        *,
        mode: str,
        user_status: UserStatus,
        plan_status: PlaceSelectionStatus,
        avoided_place_names: set[str],
        intent_constraints: list[str],
        allow_place_suggestions: bool,
        constraint_policy: ConstraintPolicy,
        budget_level: str,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
        intent_interests: list[str],
        travel_style: str,
    ) -> PlaceSelectionResult:
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
                selection_blueprint,
                selected_places,
                mode=mode,
                user_status=committed_user_status,
                plan_status=committed_plan_status,
                avoided_place_names=avoided_place_names,
                intent_constraints=intent_constraints,
                allow_place_suggestions=allow_place_suggestions,
                constraint_policy=constraint_policy,
                budget_level=budget_level,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
                intent_interests=intent_interests,
                travel_style=travel_style,
            )

        for brief in selection_blueprint.selection_days:
            day_start_location = committed_user_status.location
            tentative_user_status = committed_user_status.model_copy(deep=True)
            tentative_plan_status = committed_plan_status.model_copy(deep=True)
            allocated_places = [
                selected_by_ref[ref]
                for ref in brief.allocated_selected_place_refs
                if ref in selected_by_ref
            ]
            allow_suggestions_for_day = allow_place_suggestions and (
                route_first_mode or not has_reference_places or not allocated_places
            )
            if not allow_place_suggestions and not allocated_places:
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
                            self._resolve_place_for_style(
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
            tentative_plan_status.day_usage = PlaceSelectionUsage()
            tentative_plan_status.used_food_drink_place_types = []
            day_items: list[PlanItem] = []
            committed_activities: dict[str, tuple[SelectablePlace, DayBlock]] = {}
            deferred_slot_warnings: list[str] = []
            place_suggestion_limit = self.skeleton_builder.minimum_activity_count(
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
                place_suggestion_count = sum(
                    item.source == "finder_suggestion"
                    and item.timeline_category == "activity"
                    for item in day_items
                )
                if (
                    block.kind != "meal"
                    and allow_suggestions_for_block
                    and place_suggestion_count >= place_suggestion_limit
                ):
                    allow_suggestions_for_block = False
                candidate = self.candidate_selector.select(
                    CandidateSelectionContext(
                        selection_blueprint=selection_blueprint,
                        brief=brief,
                        block=block,
                        selected_by_ref=selected_by_ref,
                        plan_status=tentative_plan_status,
                        user_status=tentative_user_status,
                        avoided_place_names=avoided_place_names,
                        intent_constraints=intent_constraints,
                        allow_place_suggestions=allow_suggestions_for_block,
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
                            area_profile.bbox if area_profile is not None else None
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
                leg.estimated_duration_minutes for leg in all_legs if leg.mode == "walk"
            )
            all_items = [item for day in days for item in day.items]
            committed_plan_status.trip_usage = PlaceSelectionUsage(
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
                committed_plan_status.day_usage = PlaceSelectionUsage(
                    activityMinutes=sum(
                        item.duration_minutes or 0
                        for item in last_day_items
                        if item.timeline_category == "activity"
                    ),
                    travelMinutes=sum(
                        leg.estimated_duration_minutes for leg in last_day_legs
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
                        if item.latitude is not None and item.longitude is not None
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
                day_usage = PlaceSelectionUsage(
                    travelMinutes=sum(
                        leg.estimated_duration_minutes for leg in day.transport_legs
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
        allocated_refs = {
            ref
            for day in selection_blueprint.selection_days
            for ref in day.allocated_selected_place_refs
        }
        for place in self._source_ordered_places(selected_places):
            if (
                place.stable_ref
                not in committed_plan_status.remaining_selected_place_ids
            ):
                continue
            rejection = rejected_selected_places.get(
                place.stable_ref,
                CandidateRejection(
                    (
                        "no_available_slot"
                        if place.stable_ref in allocated_refs
                        else "no_day_capacity"
                    ),
                    (
                        "PlaceSelector could not find a compatible slot."
                        if place.stable_ref in allocated_refs
                        else "PlaceSelector could not allocate this Place because "
                        "all daily activity slots are full."
                    ),
                ),
            )
            unscheduled.append(
                UnscheduledPlace(
                    placeId=place.place_id,
                    name=place.name,
                    reasonCode=rejection.reason_code,
                    reason=rejection.reason,
                    address=place.address,
                    latitude=place.latitude,
                    longitude=place.longitude,
                    tags=place.tags,
                    sourceRefs=place.source_refs,
                    sourceProvider=place.source_provider,
                    sourceActivity=place.source_activity,
                )
            )
        self._append_preferred_timing_warnings(
            [item for day in days for item in day.items],
            warnings=warnings,
            plan_status=committed_plan_status,
        )
        return PlaceSelectionResult(
            days=days,
            finalUserStatus=committed_user_status,
            finalPlanStatus=committed_plan_status,
            unscheduledPlaces=unscheduled,
            warnings=warnings,
        )

    def _fill_route_first_days(
        self,
        selection_blueprint: PlaceSelectionBlueprint,
        selected_places: list[SelectedPlaceContext],
        *,
        mode: str,
        user_status: UserStatus,
        plan_status: PlaceSelectionStatus,
        avoided_place_names: set[str],
        intent_constraints: list[str],
        allow_place_suggestions: bool,
        constraint_policy: ConstraintPolicy,
        budget_level: str,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
        intent_interests: list[str],
        travel_style: str,
    ) -> PlaceSelectionResult:
        """Fill meal-anchored daily timelines without an activity-count quota."""

        selected_by_ref = {place.stable_ref: place for place in selected_places}
        rejected_selected_places: dict[str, CandidateRejection] = {}
        warnings: list[str] = []
        activity_days: list[PlanDay] = []
        selected_meals_by_day: dict[int, list[SelectedPlaceContext]] = {}
        trip_theme_slots = [
            requirement
            for requirement in selection_blueprint.trip_themes
            for _ in range(requirement.minimum_activities)
        ]
        activity_slot_index = 0

        for brief in selection_blueprint.selection_days:
            allocated_places = [
                selected_by_ref[ref]
                for ref in brief.allocated_selected_place_refs
                if ref in selected_by_ref
                and ref in plan_status.remaining_selected_place_ids
            ]
            if not allow_place_suggestions and not allocated_places:
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
                )
                == "food_drink"
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
            plan_status.current_day = brief.day
            plan_status.current_strategy = "meal_anchored_timeline"
            plan_status.day_usage = PlaceSelectionUsage()
            day_items: list[PlanItem] = []
            activity_number = 0
            for available_window_index, available_window in enumerate(ACTIVITY_WINDOWS):
                cursor = available_window.start_minutes
                while (
                    available_window.end_minutes - cursor
                    >= MINIMUM_FILLABLE_GAP_MINUTES
                ):
                    remaining_minutes = available_window.end_minutes - cursor
                    activity_number += 1
                    role = f"main_activity_{activity_number}"
                    block = DayBlock(
                        role=role,
                        time_window=format_clock_window(cursor, remaining_minutes),
                        duration_minutes=remaining_minutes,
                        activity=True,
                    )
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
                    occupied_items = [
                        *(
                            item
                            for completed_day in activity_days
                            for item in completed_day.items
                        ),
                        *day_items,
                    ]
                    candidate = None
                    candidate_start = cursor
                    remaining_refs = [
                        ref
                        for ref in activity_brief.allocated_selected_place_refs
                        if ref in plan_status.remaining_selected_place_ids
                    ]
                    for preferred_ref in remaining_refs:
                        selected = selected_by_ref.get(preferred_ref)
                        if selected is None or not hint_matches_activity_window(
                            selected.source_time_hint, available_window_index
                        ):
                            continue
                        duration = selected_activity_duration(
                            selected.source_duration_minutes
                        )
                        timing_start = cursor
                        if selected.preferred_time_windows:
                            matched_start = preferred_start_minutes(
                                selected.preferred_time_windows,
                                interval_start=cursor,
                                interval_end=available_window.end_minutes,
                                duration_minutes=duration,
                            )
                            if matched_start is not None:
                                timing_start = matched_start
                            else:
                                has_future_preferred_fit = any(
                                    preferred_start_minutes(
                                        selected.preferred_time_windows,
                                        interval_start=future_window.start_minutes,
                                        interval_end=future_window.end_minutes,
                                        duration_minutes=duration,
                                    )
                                    is not None
                                    for future_window in ACTIVITY_WINDOWS[
                                        available_window_index + 1 :
                                    ]
                                )
                                if has_future_preferred_fit:
                                    continue
                        available_minutes = (
                            available_window.end_minutes - timing_start
                        )
                        if duration > available_minutes:
                            continue
                        candidate = self.candidate_selector.select(
                            CandidateSelectionContext(
                                selection_blueprint=selection_blueprint,
                                brief=selection_brief,
                                block=DayBlock(
                                    role=role,
                                    time_window=format_clock_window(
                                        timing_start,
                                        available_minutes,
                                    ),
                                    duration_minutes=available_minutes,
                                    activity=True,
                                    preferred_ref=preferred_ref,
                                ),
                                selected_by_ref=selected_by_ref,
                                plan_status=plan_status,
                                user_status=user_status,
                                avoided_place_names=avoided_place_names,
                                intent_constraints=intent_constraints,
                                allow_place_suggestions=False,
                                constraint_policy=constraint_policy,
                                budget_level=budget_level,
                                rejected_selected_places=rejected_selected_places,
                                intent_interests=intent_interests,
                                travel_style=travel_style,
                                strict_day_theme=False,
                                enforce_opening_hours=True,
                                occupied_items=occupied_items,
                                bbox_filter=(
                                    area_profile.bbox
                                    if area_profile is not None
                                    else None
                                ),
                            )
                        )
                        if candidate is not None:
                            candidate_start = timing_start
                            break
                    if candidate is None and allow_place_suggestions:
                        candidate = self.candidate_selector.select(
                            CandidateSelectionContext(
                                selection_blueprint=selection_blueprint,
                                brief=selection_brief.model_copy(
                                    update={"allocated_selected_place_refs": []}
                                ),
                                block=block,
                                selected_by_ref=selected_by_ref,
                                plan_status=plan_status,
                                user_status=user_status,
                                avoided_place_names=avoided_place_names,
                                intent_constraints=intent_constraints,
                                allow_place_suggestions=True,
                                constraint_policy=constraint_policy,
                                budget_level=budget_level,
                                rejected_selected_places=rejected_selected_places,
                                intent_interests=intent_interests,
                                travel_style=travel_style,
                                strict_day_theme=False,
                                enforce_opening_hours=True,
                                occupied_items=occupied_items,
                                bbox_filter=(
                                    area_profile.bbox
                                    if area_profile is not None
                                    else None
                                ),
                            )
                        )
                    if candidate is None:
                        # Preserve the uncovered part of the window as free time.
                        free_block = DayBlock(
                            role="free_time",
                            time_window=format_clock_window(
                                cursor,
                                available_window.end_minutes - cursor,
                            ),
                            duration_minutes=available_window.end_minutes - cursor,
                            activity=False,
                            optional=True,
                            kind="break",
                        )
                        day_items.append(self._build_non_activity_item(free_block))
                        self.status_tracker.apply_break(
                            user_status,
                            plan_status,
                            free_block,
                        )
                        break
                    cursor = candidate_start
                    selected_source = candidate.stable_ref in selected_by_ref
                    duration = candidate_duration(candidate, block)
                    scheduled_block = DayBlock(
                        role=role,
                        time_window=format_clock_window(cursor, duration),
                        duration_minutes=remaining_minutes,
                        activity=True,
                    )
                    item = self._build_activity_item(
                        candidate,
                        scheduled_block,
                        mode=mode,
                        selected_source=selected_source,
                    )
                    day_items.append(item)
                    self.status_tracker.apply_activity(
                        candidate,
                        scheduled_block,
                        user_status,
                        plan_status,
                    )
                    cursor += duration + DEFAULT_TRANSITION_MINUTES
            plan_status.current_slot = None
            user_status.after_committed_day = brief.day
            self.status_tracker.finish_day_location(user_status)
            activity_days.append(
                PlanDay(
                    day=brief.day,
                    theme=brief.theme,
                    strategy="meal_anchored_timeline",
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
        overflow_for_retry: list[PlanItem] = []
        used_refs = set(plan_status.used_place_ids)
        briefs_by_day = {
            brief.day: brief for brief in selection_blueprint.selection_days
        }
        for day in activity_days:
            brief = briefs_by_day[day.day]
            activities = [
                item for item in day.items if item.timeline_category == "activity"
            ]
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
            meal_items: list[PlanItem] = []
            for anchor in MEAL_ANCHORS:
                role = anchor.role
                block = DayBlock(
                    role=role,
                    time_window=anchor.time_window,
                    duration_minutes=anchor.duration_minutes,
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
                            selection_blueprint=selection_blueprint,
                            brief=brief,
                            block=DayBlock(
                                role=role,
                                time_window=anchor.time_window,
                                duration_minutes=anchor.duration_minutes,
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
                            allow_place_suggestions=False,
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
                                *activities,
                                *meal_items,
                            ],
                            bbox_filter=(
                                area_profile.bbox if area_profile is not None else None
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
                meal_items.append(meal_item)
                used_refs.add(candidate.stable_ref)
                # Keep meal venues varied across days even when a provider
                # exposes a venue with no stable place id.
                used_refs.add(candidate.name)
                if candidate.place_id is not None:
                    used_refs.add(candidate.place_id.casefold())
                self.status_tracker.apply_activity(
                    candidate,
                    block,
                    user_status,
                    plan_status,
                )

            ordered_items = sorted(
                [*activities, *meal_items],
                key=lambda item: (
                    item.time_window.split("-", maxsplit=1)[0],
                    item.name.casefold(),
                ),
            )

            routed_items, transport_legs = self.route_optimizer.optimize(
                ordered_items,
                preserve_order=True,
                day=day.day,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
            )
            prefit_items = routed_items
            routed_items, overflow_items = self._apply_travel_aware_timeline(
                routed_items,
                transport_legs,
            )
            original_windows = {
                item.item_id: item.time_window
                for item in prefit_items
                if item.item_id is not None
            }
            for item in routed_items:
                original_window = original_windows.get(item.item_id)
                if (
                    item.role in {anchor.role for anchor in MEAL_ANCHORS}
                    and original_window is not None
                    and item.time_window != original_window
                ):
                    message = (
                        f"Day {day.day} moved {item.role} from {original_window} "
                        f"to {item.time_window} to preserve route feasibility."
                    )
                    warnings.append(message)
                    plan_status.warnings.append(message)
            if overflow_items:
                overflow_for_retry.extend(overflow_items)
                overflow_names = ", ".join(item.name for item in overflow_items)
                message = (
                    f"Day {day.day} could not initially fit {overflow_names} "
                    "between meal anchors; trying one alternate day."
                )
                warnings.append(message)
                plan_status.warnings.append(message)
                routed_items, transport_legs = self.route_optimizer.optimize(
                    routed_items,
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
                            selection_blueprint,
                            activities,
                        ),
                        "items": routed_items,
                        "transport_legs": transport_legs,
                    }
                )
            )

        completed_days, overflow_for_retry = self._retry_overflow_on_other_day(
            completed_days,
            overflow_for_retry,
            trip_start_date=trip_start_date,
            preferred_modes=preferred_modes,
            avoid_modes=avoid_modes,
        )
        if overflow_for_retry:
            message = (
                f"{len(overflow_for_retry)} activity item(s) remain unscheduled "
                "after one alternate-day retry."
            )
            warnings.append(message)
            plan_status.warnings.append(message)

        scheduled_selected_refs = {
            selected_ref
            for day in completed_days
            for item in day.items
            if (selected_ref := self._selected_ref_for_item(item, selected_places))
            is not None
        }
        plan_status.remaining_selected_place_ids = [
            place.stable_ref
            for place in selected_places
            if place.stable_ref not in scheduled_selected_refs
        ]
        all_items = [item for day in completed_days for item in day.items]
        all_legs = [leg for day in completed_days for leg in day.transport_legs]
        plan_status.trip_usage = PlaceSelectionUsage(
            activityMinutes=sum(
                item.duration_minutes or 0
                for item in all_items
                if item.timeline_category == "activity"
            ),
            travelMinutes=sum(leg.estimated_duration_minutes for leg in all_legs),
            walkingMinutes=sum(
                leg.estimated_duration_minutes for leg in all_legs if leg.mode == "walk"
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
            plan_status.day_usage = PlaceSelectionUsage(
                activityMinutes=sum(
                    item.duration_minutes or 0
                    for item in last_items
                    if item.timeline_category == "activity"
                ),
                travelMinutes=sum(leg.estimated_duration_minutes for leg in last_legs),
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
        for place in self._source_ordered_places(selected_places):
            if place.stable_ref not in plan_status.remaining_selected_place_ids:
                continue
            rejection = rejected_selected_places.get(
                place.stable_ref,
                CandidateRejection(
                    "insufficient_time",
                    (
                        "The visit duration and calculated transitions do not "
                        "fit between the fixed meal anchors."
                    ),
                ),
            )
            unscheduled.append(
                UnscheduledPlace(
                    placeId=place.place_id,
                    name=place.name,
                    reasonCode=rejection.reason_code,
                    reason=rejection.reason,
                    address=place.address,
                    latitude=place.latitude,
                    longitude=place.longitude,
                    tags=place.tags,
                    sourceRefs=place.source_refs,
                    sourceProvider=place.source_provider,
                    sourceActivity=place.source_activity,
                )
            )
        self._append_preferred_timing_warnings(
            all_items,
            warnings=warnings,
            plan_status=plan_status,
        )
        return PlaceSelectionResult(
            days=completed_days,
            finalUserStatus=user_status,
            finalPlanStatus=plan_status,
            unscheduledPlaces=unscheduled,
            warnings=warnings,
        )

    @staticmethod
    def _apply_travel_aware_timeline(
        items: list[PlanItem],
        transport_legs: list[PlanTransportLeg],
    ) -> tuple[list[PlanItem], list[PlanItem]]:
        """Fit activities between fixed meals using calculated leg durations.

        Missing provider legs use a small deterministic transition estimate. The
        estimate is intentionally transport-mode agnostic; route mode remains a
        presentation/enrichment concern outside timeline capacity.
        """

        status = PlaceSelectionStatus()
        warnings: list[str] = []
        result = TimelineFitter().fit(
            items,
            transport_legs,
            day=1,
            warnings=warnings,
            plan_status=status,
        )
        return result.items, result.overflow_items

    def _retry_overflow_on_other_day(
        self,
        days: list[PlanDay],
        overflow_items: list[PlanItem],
        *,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> tuple[list[PlanDay], list[PlanItem]]:
        """Try each overflow activity once in another feasible day.

        A source-day or locked item never moves. A candidate day is accepted only
        when every existing item and the new item fit after route enrichment, so
        retrying one overflow cannot silently evict an already scheduled stop.
        """

        remaining: list[PlanItem] = []
        working = [day.model_copy(deep=True) for day in days]
        for overflow in overflow_items:
            candidate_days = [
                day
                for day in working
                if day.day != self._item_day(overflow, working)
                and (overflow.source_day is None or overflow.source_day == day.day)
                and not overflow.locked
            ]
            candidate_days.sort(
                key=lambda day: (
                    sum(
                        item.duration_minutes or 0
                        for item in day.items
                        if item.timeline_category == "activity"
                    ),
                    day.day,
                )
            )
            placed = False
            for day in candidate_days:
                merged = sorted(
                    [*day.items, overflow],
                    key=lambda item: (
                        parse_clock_minutes(item.time_window) or 0,
                        item.role or "",
                    ),
                )
                routed, legs = self.route_optimizer.optimize(
                    merged,
                    preserve_order=True,
                    day=day.day,
                    trip_start_date=trip_start_date,
                    preferred_modes=preferred_modes,
                    avoid_modes=avoid_modes,
                )
                fitted, still_overflow = self._apply_travel_aware_timeline(
                    routed,
                    legs,
                )
                if still_overflow:
                    continue
                working = [
                    candidate.model_copy(
                        update={"items": fitted, "transport_legs": legs}
                    )
                    if candidate.day == day.day
                    else candidate
                    for candidate in working
                ]
                placed = True
                break
            if not placed:
                remaining.append(overflow)
        return working, remaining

    @staticmethod
    def _item_day(item: PlanItem, days: list[PlanDay]) -> int | None:
        for day in days:
            if any(existing.item_id == item.item_id for existing in day.items):
                return day.day
        return None

    @staticmethod
    def _source_ordered_places(
        places: list[SelectedPlaceContext],
    ) -> list[SelectedPlaceContext]:
        return sorted(
            places,
            key=lambda place: (
                place.source_day or 10_000,
                place.source_order or 10_000,
                place.priority if place.priority is not None else 10_000,
                place.name.casefold(),
            ),
        )

    @staticmethod
    def _selected_meal_role_refs(
        places: list[SelectedPlaceContext],
    ) -> dict[str, str]:
        """Put URL food stops into meal slots before PlaceSelector suggestions."""

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
                if any(value in hint for value in ("dinner", "evening", "night"))
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
        selection_blueprint: PlaceSelectionBlueprint,
        activities: list[PlanItem],
    ) -> str:
        activity_tags = {tag.casefold() for item in activities for tag in item.tags}
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
                for index, requirement in enumerate(selection_blueprint.trip_themes)
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

    @staticmethod
    def _append_preferred_timing_warnings(
        items: list[PlanItem],
        *,
        warnings: list[str],
        plan_status: PlaceSelectionStatus,
    ) -> None:
        for item in items:
            if not item.preferred_time_windows:
                continue
            duration = item.duration_minutes or selected_activity_duration(None)
            if time_window_matches_preference(
                item.time_window,
                duration,
                item.preferred_time_windows,
            ):
                continue
            message = (
                f"{item.name} was scheduled outside its graph-recommended "
                "visit windows because no preferred window remained feasible."
            )
            if message not in warnings:
                warnings.append(message)
            if message not in plan_status.warnings:
                plan_status.warnings.append(message)

    def _append_constraint_warnings(
        self,
        *,
        day: int,
        user_status: UserStatus,
        plan_status: PlaceSelectionStatus,
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
        candidate: SelectablePlace,
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
        role = self._explicit_role(candidate, block, selected_source=selected_source)
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
            role=role,
            source="selected_place" if selected_source else "finder_suggestion",
            durationMinutes=candidate_duration(candidate, block),
            activityIntensity=candidate.activity_intensity,
            sourceRefs=candidate.source_refs,
            sourceProvider=candidate.source_provider,
            sourceImportNodeId=candidate.source_import_node_id,
            candidateEntityIds=candidate.candidate_entity_ids,
            selectionMethod=candidate.selection_method,
            routeScore=candidate.route_score,
            identityConfidence=candidate.identity_confidence,
            tags=candidate.tags,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            notes=(
                candidate.notes
                or candidate.source_activity
                or candidate.description
                or None
            ),
            contextPlaces=candidate.context_places,
            personalNotes=candidate.personal_notes,
            imageUrls=candidate.image_urls,
            rating=candidate.rating,
            reviewCount=candidate.review_count,
            openingHours=candidate.opening_hours,
            sourceLink=candidate.source_link,
            sourceOrder=candidate.source_order,
            sourceDay=candidate.source_day,
            sourceTimeHint=candidate.source_time_hint,
            sourceActivity=candidate.source_activity,
            preferredTimeWindows=candidate.preferred_time_windows,
        )

    @staticmethod
    def _explicit_role(
        candidate: SelectablePlace,
        block: DayBlock,
        *,
        selected_source: bool,
    ) -> str:
        """Keep experience semantics separate from the timeline slot name."""
        if block.kind == "meal" or place_category(candidate) == "food_drink":
            return "meal"
        category = candidate.experience_category
        if category in {
            ExperienceCategory.main_experience,
            ExperienceCategory.culture,
            ExperienceCategory.history,
            ExperienceCategory.nature,
            ExperienceCategory.active,
            ExperienceCategory.outdoor,
        }:
            return "main_experience"
        if category is ExperienceCategory.supporting_stop:
            return "supporting_stop"
        if category is ExperienceCategory.optional or block.optional:
            return "optional"
        # Existing non-experience selection callers still use their stable slot roles.
        return block.role

    def _resolve_place_for_style(
        self,
        ref: str,
        selected_by_ref: dict[str, SelectedPlaceContext],
        fallback_region_key: str,
    ) -> SelectablePlace:
        """Best-effort conversion of a selected_place ref into a SelectablePlace.

        Used only for day-style classification; missing data must not break
        the rest of the place-selection pipeline, so we fall back to a stub with the
        place_type field set to ``"selected_place"`` (an unknown category).
        """
        selected = selected_by_ref.get(ref)
        if selected is None:
            return SelectablePlace(
                name=ref,
                placeType="selected_place",
                regionKey=fallback_region_key,
            )
        if selected.place_id:
            stored = self.place_tool.get(selected.place_id)
            if stored is not None:
                return stored
        return SelectablePlace(
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
