from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from app.modules.plans.domain.constraint_policy import (
    ConstraintPolicy,
    constraint_policy_rejection,
)
from app.modules.plans.domain.entities import (
    DayBrief,
    FinderPlanStatus,
    MacroPlan,
    UserStatus,
)
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.finder.place_tool import (
    FinderPlace,
    FinderPlaceTool,
    _normalize_text,
    place_category,
    place_matches_categories,
    semantic_categories,
)
from app.modules.plans.finder.skeleton_builder import DayBlock
from app.modules.plans.finder.time_windows import parse_clock_minutes
from app.modules.plans.planner.opening_hours_parser import (
    extract_time_intervals,
    is_24_hours,
)
from app.modules.plans.knowledge_graph import (
    TravelKnowledgeSearchTool,
    get_default_travel_knowledge_tool,
)


DEFAULT_MAX_CANDIDATES_PER_BLOCK = 25
FAMOUS_PLACE_MIN_RATING = 4.5
FAMOUS_PLACE_MIN_REVIEW_COUNT = 1_000
FAMOUS_PLACE_MAX_DISTANCE_METERS = 8_000

_QUICK_FOOD_PLACE_TYPES = {
    "bakery",
    "cafe",
    "coffee_shop",
    "ice_cream",
    "quan_cafe",
    "quan_coffee",
    "quan_tra",
    "tiem_banh",
    "che",
    "bingsu",
    "tra_sua",
}

_CATEGORY_DEFAULT_DURATION_MINUTES = {
    "attraction": 120,
    "entertainment": 90,
    "food_drink": 75,
    "nature": 120,
    "shopping": 60,
}

_CONCRETE_MAIN_TYPE_MARKERS = {
    "church",
    "cultural_center",
    "cultural_landmark",
    "historic_site",
    "historical_landmark",
    "historical_place",
    "memorial",
    "monument",
    "museum",
    "pagoda",
    "shrine",
    "temple",
}
_GENERIC_ATTRACTION_TYPES = {"attraction", "tourist_attraction"}
_BROAD_AREA_TYPES = {
    "administrative_area",
    "city",
    "district",
    "neighborhood",
    "region",
}
_BROAD_AREA_NAMES = {
    "hanoi",
    "hanoi old quarter",
    "ha noi",
    "old quarter",
    "pho co",
}

def place_experience_signature(
    candidate: FinderPlace,
    knowledge_tool: TravelKnowledgeSearchTool | None = None,
) -> str | None:
    """Return a coarse visitor-experience signature, not a venue category."""

    category = place_category(candidate)
    if category is None:
        return None
    tool = knowledge_tool or get_default_travel_knowledge_tool()
    normalized_type = _normalize_text(candidate.place_type).replace(" ", "_")
    if category == "attraction":
        if any(
            marker in normalized_type
            for marker in (
                "church",
                "mosque",
                "pagoda",
                "place_of_worship",
                "shrine",
                "temple",
            )
        ):
            return "religious_heritage"
        if "museum" in normalized_type:
            return "museum"
        if any(
            marker in normalized_type
            for marker in ("landmark", "memorial", "monument")
        ):
            return "monument"

    primary_signature = tool.classify_experience(
        [candidate.name, candidate.place_type or "", *candidate.tags],
        region_key=candidate.region_key,
        category=category,
    )
    if primary_signature is not None:
        return primary_signature
    return tool.classify_experience(
        [candidate.description or ""],
        region_key=candidate.region_key,
        category=category,
    )


def food_drink_experience_signature(
    candidate: FinderPlace,
    knowledge_tool: TravelKnowledgeSearchTool | None = None,
) -> str | None:
    """Return a food/drink signature while keeping the public helper stable.

    Specific experiences such as coffee, bun or pho get their graph signature.
    A generic restaurant receives a coarse fallback signature so it cannot also
    occupy several non-meal activity slots. Meal blocks explicitly bypass that
    diversity filter, therefore lunch and dinner may still both be restaurants.
    """

    if place_category(candidate) != "food_drink":
        return None
    signature = place_experience_signature(candidate, knowledge_tool)
    if signature is not None:
        return signature
    normalized_type = _normalize_text(candidate.place_type).replace(" ", "_")
    if "restaurant" in normalized_type or normalized_type in {
        "food",
        "food_court",
        "fast_food",
    }:
        return "generic_restaurant"
    return None


@dataclass(frozen=True)
class CandidateRejection:
    reason_code: str
    reason: str


@dataclass
class CandidateSelectionContext:
    macro_plan: MacroPlan
    brief: DayBrief
    block: DayBlock
    selected_by_ref: dict[str, SelectedPlaceContext]
    plan_status: FinderPlanStatus
    user_status: UserStatus
    avoided_place_names: set[str]
    intent_constraints: list[str]
    allow_finder_suggestions: bool
    constraint_policy: ConstraintPolicy
    budget_level: str
    rejected_selected_places: dict[str, CandidateRejection]
    intent_interests: list[str]
    travel_style: str
    bbox_filter: tuple[float, float, float, float] | None = None
    zone_center: tuple[float, float] | None = None
    zone_radius_meters: int | None = None


def candidate_duration(candidate: FinderPlace, block: DayBlock) -> int:
    typical = candidate.typical_duration_minutes
    if typical is None:
        category = place_category(candidate)
        place_type = (candidate.place_type or "").strip().casefold()
        inferred = (
            45
            if category == "food_drink" and place_type in _QUICK_FOOD_PLACE_TYPES
            else _CATEGORY_DEFAULT_DURATION_MINUTES.get(category or "")
        )
        return min(inferred or block.duration_minutes, block.duration_minutes)
    if typical <= block.duration_minutes:
        return typical
    minimum = candidate.minimum_duration_minutes
    if minimum is not None and minimum <= block.duration_minutes:
        return block.duration_minutes
    return typical


def candidate_feasible_start(
    candidate: FinderPlace,
    block: DayBlock,
    duration_minutes: int,
) -> int | None:
    preferred_start = parse_clock_minutes(block.time_window)
    window_start = (
        parse_clock_minutes(block.earliest_start)
        if block.earliest_start
        else preferred_start
    )
    window_end = (
        parse_clock_minutes(block.latest_end)
        if block.latest_end
        else None
    )
    if window_start is None:
        return preferred_start
    if not candidate.opening_hours or is_24_hours(candidate.opening_hours):
        return window_start if window_end is None or window_start + duration_minutes <= window_end else None
    for open_minutes, close_minutes in extract_time_intervals(candidate.opening_hours):
        start = max(window_start, open_minutes)
        end_limit = min(close_minutes, window_end) if window_end is not None else close_minutes
        if start + duration_minutes <= end_limit:
            return start
    return None


class CandidateSelector:
    def __init__(
        self,
        place_tool: FinderPlaceTool,
        *,
        max_candidates_per_block: int = DEFAULT_MAX_CANDIDATES_PER_BLOCK,
        knowledge_tool: TravelKnowledgeSearchTool | None = None,
    ) -> None:
        self.place_tool = place_tool
        self.max_candidates_per_block = max_candidates_per_block
        self.knowledge_tool = knowledge_tool or get_default_travel_knowledge_tool()

    def _filter_repeated_food_drink(
        self,
        candidates: list[FinderPlace],
        selected_by_ref: dict,
        plan_status: FinderPlanStatus,
        block: DayBlock,
    ) -> list[FinderPlace]:
        """Drop repeated food/drink experiences already used in this day.

        The status field keeps coarse experience signatures for compatibility
        with the existing contract. User-selected places remain untouched.
        """

        if block.kind == "meal":
            return candidates
        used_signatures = set(plan_status.used_food_drink_place_types or [])
        if not used_signatures:
            return candidates
        filtered: list[FinderPlace] = []
        for candidate in candidates:
            if candidate.stable_ref in selected_by_ref:
                filtered.append(candidate)
                continue
            if place_category(candidate) != "food_drink":
                filtered.append(candidate)
                continue
            signature = food_drink_experience_signature(
                candidate,
                self.knowledge_tool,
            )
            if signature is not None and signature in used_signatures:
                continue
            filtered.append(candidate)
        return filtered

    def _filter_repeated_experiences(
        self,
        candidates: list[FinderPlace],
        selected_by_ref: dict,
        plan_status: FinderPlanStatus,
    ) -> list[FinderPlace]:
        used_groups = set(plan_status.used_experience_groups)
        if not used_groups:
            return candidates
        return [
            candidate
            for candidate in candidates
            if candidate.stable_ref in selected_by_ref
            or (
                place_experience_signature(candidate, self.knowledge_tool)
                not in used_groups
            )
        ]

    def _is_food_drink_duplicate(
        self,
        candidate: FinderPlace,
        already_accepted: list[FinderPlace],
    ) -> bool:
        """Return True if ``candidate`` looks like a duplicate of any
        already-accepted place that shares the same ``place_type``.
        """

        candidate_tokens = self._description_tokens(candidate.description)
        if not candidate_tokens:
            return False
        candidate_type = (candidate.place_type or "").strip()
        for accepted in already_accepted:
            if (accepted.place_type or "").strip() != candidate_type:
                continue
            if place_category(accepted) != "food_drink":
                continue
            accepted_tokens = self._description_tokens(accepted.description)
            if not accepted_tokens:
                continue
            shared = len(candidate_tokens.intersection(accepted_tokens))
            if shared >= self._FOOD_DRINK_DUPLICATE_TOKEN_THRESHOLD:
                return True
        return False

    @staticmethod
    def _description_tokens(description: str | None) -> set[str]:
        if not description:
            return set()
        normalized = _normalize_text(description)
        if not normalized:
            return set()
        return {token for token in normalized.split() if len(token) > 2}

    _FOOD_DRINK_DUPLICATE_TOKEN_THRESHOLD = 3

    def select(self, context: CandidateSelectionContext) -> FinderPlace | None:
        candidates: list[FinderPlace] = []
        search_terms = self._search_terms(
            context.macro_plan,
            context.brief,
            context.block,
            intent_interests=context.intent_interests,
            travel_style=context.travel_style,
        )
        query_categories = self._query_categories(
            context.macro_plan,
            context.brief,
            context.block,
            fallback_terms=search_terms,
        )
        if context.block.preferred_ref is not None:
            selected = context.selected_by_ref.get(context.block.preferred_ref)
            if (
                selected is None
                or context.block.preferred_ref
                not in context.plan_status.remaining_selected_place_ids
            ):
                return None
            candidate = self._selected_to_candidate(selected, context.brief)
            rejection = self._candidate_rejection(
                candidate,
                context.block,
                context.user_status,
                is_selected=True,
                query_categories=query_categories,
                avoided_place_names=context.avoided_place_names,
                intent_constraints=context.intent_constraints,
                constraint_policy=context.constraint_policy,
                budget_level=context.budget_level,
            )
            if rejection is None:
                return candidate
            if candidate.stable_ref not in context.plan_status.rejected_candidate_ids:
                context.plan_status.rejected_candidate_ids.append(candidate.stable_ref)
            context.rejected_selected_places[candidate.stable_ref] = rejection
            return None

        preferred_refs = [
            ref
            for ref in context.brief.allocated_selected_place_refs
            if ref in context.plan_status.remaining_selected_place_ids
        ]
        for ref in preferred_refs:
            selected = context.selected_by_ref.get(ref)
            if selected is None:
                continue
            candidates.append(self._selected_to_candidate(selected, context.brief))

        region_key = context.brief.target_region_key or context.brief.target_area
        if context.allow_finder_suggestions and region_key.startswith("vn,"):
            selected_place_ids = {
                place.place_id
                for place in context.selected_by_ref.values()
                if place.place_id is not None
            }
            catalog_candidates = self.place_tool.search(
                region_key=region_key,
                target_tags=search_terms,
                target_categories=query_categories,
                excluded_place_ids=(
                    set(context.plan_status.used_place_ids) | selected_place_ids
                ),
                limit=self.max_candidates_per_block,
                bbox_filter=context.bbox_filter,
            )
            catalog_candidates = self._inside_local_boundary(
                catalog_candidates,
                context,
            )
            candidates.extend(
                self._rerank_for_proximity(
                    catalog_candidates,
                    context.user_status,
                )
            )

        unique_candidates: list[FinderPlace] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.stable_ref in seen:
                continue
            seen.add(candidate.stable_ref)
            unique_candidates.append(candidate)

        if self._is_main_block(context.block):
            selected_candidates = [
                candidate
                for candidate in unique_candidates
                if candidate.stable_ref in context.selected_by_ref
            ]
            catalog_candidates = [
                candidate
                for candidate in unique_candidates
                if candidate.stable_ref not in context.selected_by_ref
            ]
            unique_candidates = [
                *selected_candidates,
                *self._prioritize_concrete_main_places(catalog_candidates),
            ]

        unique_candidates = self._filter_repeated_food_drink(
            unique_candidates,
            context.selected_by_ref,
            context.plan_status,
            context.block,
        )
        unique_candidates = self._filter_repeated_experiences(
            unique_candidates,
            context.selected_by_ref,
            context.plan_status,
        )

        attempts = 0
        for candidate in unique_candidates:
            if attempts >= self.max_candidates_per_block:
                break
            attempts += 1
            candidate_ref = candidate.stable_ref
            if candidate_ref in context.plan_status.used_place_ids:
                continue
            rejection = self._candidate_rejection(
                candidate,
                context.block,
                context.user_status,
                is_selected=candidate_ref in context.selected_by_ref,
                query_categories=query_categories,
                avoided_place_names=context.avoided_place_names,
                intent_constraints=context.intent_constraints,
                constraint_policy=context.constraint_policy,
                budget_level=context.budget_level,
            )
            if rejection is not None:
                if rejection.reason_code == "slot_category_mismatch":
                    continue
                if candidate_ref not in context.plan_status.rejected_candidate_ids:
                    context.plan_status.rejected_candidate_ids.append(candidate_ref)
                if candidate_ref in context.selected_by_ref:
                    context.rejected_selected_places[candidate_ref] = rejection
                continue
            return candidate
        return None

    @staticmethod
    def _is_main_block(block: DayBlock) -> bool:
        return block.need_role == "main" or "main_activity" in block.role

    @staticmethod
    def _prioritize_concrete_main_places(
        candidates: list[FinderPlace],
    ) -> list[FinderPlace]:
        """Prefer a visitable venue/landmark while retaining quality order.

        Retrieval has already ranked relevance, popularity and reviews. This
        stable partition only prevents a broad area label such as an entire
        old quarter from becoming the primary stop when a museum, temple or
        landmark is available in the same shortlist.
        """

        def specificity(candidate: FinderPlace) -> int:
            place_type = _normalize_text(candidate.place_type).replace(" ", "_")
            if any(marker in place_type for marker in _CONCRETE_MAIN_TYPE_MARKERS):
                return 2
            if place_type in _GENERIC_ATTRACTION_TYPES:
                return 0
            return 1

        return sorted(
            candidates,
            key=lambda candidate: (
                -specificity(candidate),
                -candidate.review_count,
                -(candidate.rating or 0),
            ),
        )

    @staticmethod
    def _is_exact_main_place(candidate: FinderPlace) -> bool:
        place_type = _normalize_text(candidate.place_type).replace(" ", "_")
        name = _normalize_text(candidate.name)
        return place_type not in _BROAD_AREA_TYPES and name not in _BROAD_AREA_NAMES

    @staticmethod
    def _is_drink_or_snack_only(candidate: FinderPlace) -> bool:
        normalized_type = (
            candidate.place_type.strip().casefold().replace(" ", "_")
            if candidate.place_type
            else ""
        )
        return normalized_type in {
            "bar",
            "bakery",
            "cafe",
            "cafe;bakery",
            "coffee",
            "coffee_shop",
            "dessert_restaurant",
            "ice_cream",
            "night_club",
            "pub",
            "tea_house",
        }

    def block_is_available(self, block: DayBlock, user_status: UserStatus) -> bool:
        if not user_status.available_at:
            return True
        available_minutes = parse_clock_minutes(user_status.available_at)
        if available_minutes is None:
            return True
        block_start = parse_clock_minutes(block.time_window)
        return block_start is None or block_start >= available_minutes

    def _rerank_for_proximity(
        self,
        candidates: list[FinderPlace],
        user_status: UserStatus,
    ) -> list[FinderPlace]:
        location = user_status.location
        if (
            location is None
            or location.latitude is None
            or location.longitude is None
        ):
            return candidates
        origin = (location.latitude, location.longitude)
        ranked: list[tuple[float, float, FinderPlace]] = []
        for relevance_rank, candidate in enumerate(candidates):
            if candidate.latitude is None or candidate.longitude is None:
                distance = float("inf")
                combined_rank = relevance_rank + 4
            else:
                distance = self._haversine_meters(
                    origin,
                    (candidate.latitude, candidate.longitude),
                )
                combined_rank = relevance_rank + min(distance / 2_000, 3)
            ranked.append((combined_rank, distance, candidate))
        return [
            candidate
            for _, _, candidate in sorted(
                ranked,
                key=lambda entry: (
                    entry[0],
                    entry[1],
                    entry[2].name.casefold(),
                ),
            )
        ]

    def _inside_local_boundary(
        self,
        candidates: list[FinderPlace],
        context: CandidateSelectionContext,
    ) -> list[FinderPlace]:
        if context.zone_center is not None and context.zone_radius_meters is not None:
            filtered: list[FinderPlace] = []
            locked_main_region = (
                context.brief.target_region_key
                if self._is_main_block(context.block)
                and context.brief.main_region_locked
                else None
            )
            for candidate in candidates:
                if candidate.latitude is None or candidate.longitude is None:
                    continue
                if (
                    locked_main_region is not None
                    and candidate.region_key != locked_main_region
                    and not candidate.region_key.startswith(
                        f"{locked_main_region},"
                    )
                ):
                    continue
                distance = self._haversine_meters(
                    context.zone_center,
                    (candidate.latitude, candidate.longitude),
                )
                if distance <= context.zone_radius_meters:
                    filtered.append(candidate)
                    continue
                if (
                    self._is_main_block(context.block)
                    and context.brief.main_region_locked
                ):
                    # Fame may justify a longer detour for an optional/support
                    # stop, but never replace the day's primary experience
                    # outside the verified tourism zone selected by Planner.
                    continue
                if (
                    distance <= FAMOUS_PLACE_MAX_DISTANCE_METERS
                    and (candidate.rating or 0) >= FAMOUS_PLACE_MIN_RATING
                    and candidate.review_count >= FAMOUS_PLACE_MIN_REVIEW_COUNT
                    and candidate.data_confidence in {"high", "verified"}
                ):
                    filtered.append(candidate)
            return filtered
        if context.brief.allow_region_fallback:
            return candidates
        region_key = context.brief.target_region_key or context.brief.target_area
        return [
            candidate
            for candidate in candidates
            if candidate.region_key == region_key
            or candidate.region_key.startswith(f"{region_key},")
        ]

    def _haversine_meters(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> float:
        latitude_1, longitude_1 = map(radians, origin)
        latitude_2, longitude_2 = map(radians, destination)
        delta_latitude = latitude_2 - latitude_1
        delta_longitude = longitude_2 - longitude_1
        value = (
            sin(delta_latitude / 2) ** 2
            + cos(latitude_1)
            * cos(latitude_2)
            * sin(delta_longitude / 2) ** 2
        )
        return 6_371_000 * 2 * asin(sqrt(value))

    def _search_terms(
        self,
        macro_plan: MacroPlan,
        brief: DayBrief,
        block: DayBlock,
        *,
        intent_interests: list[str],
        travel_style: str,
    ) -> list[str]:
        if block.kind == "meal":
            meal_goal = (
                brief.day_part_goals.lunch
                if "lunch" in block.role
                else brief.day_part_goals.evening
            )
            return list(
                dict.fromkeys(
                    value
                    for value in (
                        "food",
                        "local food",
                        "local cuisine",
                        "món địa phương",
                        "ăn trưa" if "lunch" in block.role else "ăn tối",
                        meal_goal,
                    )
                    if value
                )
            )
        day_goal = (
            brief.day_part_goals.morning
            if self._is_main_block(block)
            else brief.day_part_goals.evening
            if block.need_role == "bonus" or block.role == "bonus_activity"
            else brief.day_part_goals.afternoon
        )
        phase = next(
            (
                candidate
                for candidate in macro_plan.journey_phases
                if candidate.start_day <= brief.day <= candidate.end_day
            ),
            None,
        )
        primary_values = [
            value
            for value in (
                brief.theme,
                day_goal,
                phase.theme if phase is not None else None,
                phase.movement_goal if phase is not None else None,
                block.goal,
                *block.preferred_experiences,
            )
            if value
        ]
        primary_categories = semantic_categories(set(primary_values))
        compatible_focus_tags = [
            tag
            for tag in brief.focus_tags
            if (
                not primary_categories
                or not semantic_categories({tag})
                or bool(semantic_categories({tag}).intersection(primary_categories))
            )
        ]
        base_terms = list(
            dict.fromkeys(
                value
                for value in (
                    *compatible_focus_tags,
                    *primary_values,
                    brief.target_area,
                )
                if value
            )
        )
        expansion = self.knowledge_tool.expand(
            base_terms,
            region_key=brief.target_region_key or macro_plan.region_key,
            category=(
                next(iter(self._block_semantic_categories(block)), None)
                or brief.primary_activity_category
            ),
        )
        return list(dict.fromkeys([*base_terms, *expansion.query_terms]))

    def _query_categories(
        self,
        macro_plan: MacroPlan,
        brief: DayBrief,
        block: DayBlock,
        *,
        fallback_terms: list[str],
    ) -> set[str]:
        if block.candidate_category is not None:
            return {block.candidate_category}
        block_categories = self._block_semantic_categories(block)
        if block_categories:
            return block_categories
        if brief.primary_activity_category is not None:
            return {brief.primary_activity_category}
        day_goal = (
            brief.day_part_goals.morning
            if self._is_main_block(block)
            else brief.day_part_goals.evening
            if block.need_role == "bonus" or block.role == "bonus_activity"
            else brief.day_part_goals.afternoon
        )
        phase = next(
            (
                candidate
                for candidate in macro_plan.journey_phases
                if candidate.start_day <= brief.day <= candidate.end_day
            ),
            None,
        )
        primary_categories = semantic_categories(
            {
                value
                for value in (
                    brief.theme,
                    day_goal,
                    phase.theme if phase is not None else None,
                    phase.movement_goal if phase is not None else None,
                )
                if value
            }
        )
        if (
            self._is_main_block(block)
            and "attraction" in primary_categories
            and "food_drink" in primary_categories
        ):
            # A mixed day theme such as "heritage and food" must not turn the
            # primary sightseeing slot into a cafe/restaurant. Meal blocks
            # handle food separately; an explicitly food-only day remains
            # eligible for a culinary main experience.
            primary_categories = {"attraction"}
        focus_categories = semantic_categories(set(brief.focus_tags))
        return (
            primary_categories
            or focus_categories
            or semantic_categories(set(fallback_terms))
        )

    @staticmethod
    def _block_semantic_categories(block: DayBlock) -> set[str]:
        return semantic_categories(
            {
                value
                for value in (block.goal, *block.preferred_experiences)
                if value
            }
        )

    def _selected_to_candidate(
        self,
        selected: SelectedPlaceContext,
        brief: DayBrief,
    ) -> FinderPlace:
        if selected.place_id:
            stored_place = self.place_tool.get(selected.place_id)
            if stored_place is not None:
                return stored_place.model_copy(
                    update={
                        "must_visit": selected.must_visit,
                        "source_refs": list(selected.source_refs),
                        "source_provider": selected.source_provider,
                        "tags": list(dict.fromkeys([*selected.tags, *stored_place.tags])),
                        "source_order": selected.source_order,
                        "source_day": selected.source_day,
                        "source_time_hint": selected.source_time_hint,
                        "source_activity": selected.source_activity,
                        "source_duration_minutes": selected.source_duration_minutes,
                    }
                )
        return FinderPlace(
            placeId=selected.place_id,
            name=selected.name,
            placeType="selected_place",
            regionKey=selected.region_key or brief.target_region_key or brief.target_area,
            tags=selected.tags,
            latitude=selected.latitude,
            longitude=selected.longitude,
            mustVisit=selected.must_visit,
            sourceRefs=selected.source_refs,
            sourceProvider=selected.source_provider,
            openingHours=[],
            dataConfidence="user_confirmed",
            sourceOrder=selected.source_order,
            sourceDay=selected.source_day,
            sourceTimeHint=selected.source_time_hint,
            sourceActivity=selected.source_activity,
            sourceDurationMinutes=selected.source_duration_minutes,
        )

    def _intensity_allowed(self, candidate: FinderPlace, user_status: UserStatus) -> bool:
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
        is_selected: bool,
        query_categories: set[str],
        avoided_place_names: set[str],
        intent_constraints: list[str],
        constraint_policy: ConstraintPolicy,
        budget_level: str,
    ) -> CandidateRejection | None:
        if candidate.name.casefold() in avoided_place_names:
            return CandidateRejection("avoided_by_user", "Place is explicitly avoided by the user.")
        if (
            block.must_be_exact_place
            and not is_selected
            and not self._is_exact_main_place(candidate)
        ):
            return CandidateRejection(
                "main_requires_exact_place",
                "The required main experience must resolve to one visitable Place, not a broad area.",
            )
        policy_rejection = constraint_policy_rejection(
            constraint_policy,
            name=candidate.name,
            place_type=candidate.place_type,
            tags=candidate.tags,
            region_key=candidate.region_key,
        )
        if policy_rejection is not None:
            return CandidateRejection(*policy_rejection)
        category = place_category(candidate)
        if (
            block.kind == "meal"
            and block.role in {"lunch_meal", "dinner_meal"}
            and self._is_drink_or_snack_only(candidate)
        ):
            return CandidateRejection(
                "meal_venue_mismatch",
                "A cafe or snack-only venue cannot fill a lunch or dinner slot.",
            )
        if (
            block.candidate_category is not None
            and not place_matches_categories(candidate, {block.candidate_category})
        ):
            return CandidateRejection(
                "slot_category_mismatch",
                (
                    f"Place category {category or 'unknown'} cannot fill "
                    f"the {block.candidate_category} slot."
                ),
            )
        if (
            not is_selected
            and category in {"accommodation", "transport"}
            and category not in query_categories
        ):
            return CandidateRejection(
                "activity_category_mismatch",
                f"Place category {category} cannot fill a regular activity block.",
            )
        semantic_rejection = self._semantic_category_rejection(
            candidate,
            is_selected=is_selected,
            query_categories=query_categories,
        )
        if semantic_rejection is not None:
            return semantic_rejection
        normalized_constraints = {
            constraint.strip().casefold().replace("-", "_").replace(" ", "_")
            for constraint in intent_constraints
        }
        if (
            normalized_constraints.intersection(
                {"avoid_outdoor", "bad_weather", "rain", "indoor_only"}
            )
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
            budget_level == "low"
            and candidate.price_level
            and candidate.price_level.casefold() in {"premium", "luxury", "high"}
        ):
            return CandidateRejection(
                "budget_mismatch",
                "Place price level is too high for the trip budget.",
            )
        duration = candidate_duration(candidate, block)
        if not self._opening_hours_cover_block(candidate, block, duration):
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
        max_consecutive = user_status.constraints.max_consecutive_active_minutes
        if max_consecutive is not None and duration > max_consecutive:
            return CandidateRejection(
                "max_consecutive_active_minutes",
                (
                    f"Activity duration {duration} minutes exceeds the user's "
                    f"{max_consecutive}-minute consecutive activity limit."
                ),
            )
        accessibility_needs = {
            need.casefold() for need in user_status.constraints.accessibility_needs
        }
        accessibility_features = {
            feature.casefold() for feature in candidate.accessibility_features
        }
        if accessibility_needs and not accessibility_needs.issubset(accessibility_features):
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

    def _semantic_category_rejection(
        self,
        candidate: FinderPlace,
        *,
        is_selected: bool,
        query_categories: set[str],
    ) -> CandidateRejection | None:
        if is_selected:
            return None
        category = place_category(candidate)
        if category == "accommodation" and "accommodation" not in query_categories:
            return CandidateRejection(
                "activity_category_mismatch",
                "Accommodation cannot fill a regular activity block.",
            )
        if not query_categories:
            return None
        if category is None:
            return CandidateRejection(
                "activity_category_mismatch",
                "Place has no category evidence matching the activity goal.",
            )
        if not place_matches_categories(candidate, query_categories):
            return CandidateRejection(
                "activity_category_mismatch",
                "Place category {category} does not match the day theme or activity goal.".format(
                    category=category
                ),
            )
        normalized_type = _normalize_text(candidate.place_type).replace(" ", "_")
        if (
            "attraction" in query_categories
            and category == "attraction"
            and normalized_type in _GENERIC_ATTRACTION_TYPES
        ):
            textual_categories = semantic_categories(
                {
                    candidate.name,
                    candidate.description or "",
                    *candidate.tags,
                }
            )
            if textual_categories and "attraction" not in textual_categories:
                return CandidateRejection(
                    "activity_category_mismatch",
                    "Generic attraction label has stronger evidence for another activity category.",
                )
        return None

    def _is_outdoor(self, candidate: FinderPlace) -> bool:
        outdoor_markers = {"outdoor", "nature", "park", "beach", "hiking"}
        values = {
            candidate.place_type.casefold(),
            *(tag.casefold() for tag in candidate.tags),
        }
        return bool(values.intersection(outdoor_markers))

    def _opening_hours_cover_block(
        self,
        candidate: FinderPlace,
        block: DayBlock,
        duration_minutes: int,
    ) -> bool:
        return candidate_feasible_start(candidate, block, duration_minutes) is not None
