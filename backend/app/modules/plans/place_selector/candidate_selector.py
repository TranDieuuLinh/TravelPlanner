from __future__ import annotations

from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt

from app.modules.plans.domain.constraint_policy import (
    ConstraintPolicy,
    constraint_policy_rejection,
)
from app.modules.plans.domain.entities import (
    PlaceSelectionDay,
    PlaceSelectionStatus,
    PlaceSelectionBlueprint,
    PlanItem,
    UserStatus,
)
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.place_selector.place_tool import (
    SelectablePlace,
    PlaceSelectionTool,
    _normalize_text,
    place_category,
    place_matches_categories,
    semantic_categories,
)
from app.modules.plans.place_selector.skeleton_builder import DayBlock
from app.modules.plans.place_selector.time_windows import parse_clock_minutes
from app.modules.plans.trip_theme_planner.opening_hours_parser import (
    extract_time_intervals,
    is_24_hours,
)


NON_TOURISM_PLACE_TYPES = {
    "courthouse",
    "embassy",
    "fire_station",
    "hospital",
    "local_government_office",
    "police",
    "post_office",
    "school",
    "university",
}


@dataclass(frozen=True)
class CandidateRejection:
    reason_code: str
    reason: str


@dataclass
class CandidateSelectionContext:
    selection_blueprint: PlaceSelectionBlueprint
    brief: PlaceSelectionDay
    block: DayBlock
    selected_by_ref: dict[str, SelectedPlaceContext]
    plan_status: PlaceSelectionStatus
    user_status: UserStatus
    avoided_place_names: set[str]
    intent_constraints: list[str]
    allow_place_suggestions: bool
    constraint_policy: ConstraintPolicy
    budget_level: str
    rejected_selected_places: dict[str, CandidateRejection]
    intent_interests: list[str]
    travel_style: str
    strict_day_theme: bool = True
    enforce_opening_hours: bool = True
    occupied_items: list[PlanItem] = field(default_factory=list)
    bbox_filter: tuple[float, float, float, float] | None = None


def candidate_duration(candidate: SelectablePlace, block: DayBlock) -> int:
    typical = candidate.typical_duration_minutes
    if typical is None:
        return block.duration_minutes
    if typical <= block.duration_minutes:
        return typical
    minimum = candidate.minimum_duration_minutes
    if minimum is not None and minimum <= block.duration_minutes:
        return block.duration_minutes
    return typical


class CandidateSelector:
    def __init__(
        self,
        place_tool: PlaceSelectionTool,
        *,
        max_candidates_per_block: int = 5,
    ) -> None:
        self.place_tool = place_tool
        self.max_candidates_per_block = max_candidates_per_block

    def _filter_repeated_food_drink(
        self,
        candidates: list[SelectablePlace],
        selected_by_ref: dict,
        plan_status: PlaceSelectionStatus,
    ) -> list[SelectablePlace]:
        """Drop PlaceSelector-suggested food_drink places that look like duplicates of
        an already-accepted place in the same day. Two places count as
        duplicates only when they share the same ``place_type`` AND their
        ``description`` overlap (by token count) meets the configured
        threshold. User-selected places are preserved because the user
        explicitly asked for them.
        """

        used_types = set(plan_status.used_food_drink_place_types or [])
        if not used_types:
            return candidates
        filtered: list[SelectablePlace] = []
        for candidate in candidates:
            if candidate.stable_ref in selected_by_ref:
                filtered.append(candidate)
                continue
            if place_category(candidate) != "food_drink":
                filtered.append(candidate)
                continue
            candidate_type = (
                candidate.place_type.strip() if candidate.place_type else ""
            )
            if not candidate_type or candidate_type not in used_types:
                filtered.append(candidate)
                continue
            duplicate = self._is_food_drink_duplicate(
                candidate,
                filtered,
            )
            if duplicate:
                continue
            filtered.append(candidate)
        return filtered

    def _is_food_drink_duplicate(
        self,
        candidate: SelectablePlace,
        already_accepted: list[SelectablePlace],
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

    def select(self, context: CandidateSelectionContext) -> SelectablePlace | None:
        candidates: list[SelectablePlace] = []
        search_terms = self._search_terms(
            context.selection_blueprint,
            context.brief,
            context.block,
            intent_interests=context.intent_interests,
            travel_style=context.travel_style,
            strict_day_theme=context.strict_day_theme,
        )
        query_categories = self._query_categories(
            context.selection_blueprint,
            context.brief,
            context.block,
            fallback_terms=search_terms,
            intent_interests=context.intent_interests,
            strict_day_theme=context.strict_day_theme,
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
                enforce_opening_hours=context.enforce_opening_hours,
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
        if context.allow_place_suggestions and region_key.startswith("vn,"):
            catalog_search_terms = search_terms
            if not context.strict_day_theme and context.block.kind != "meal":
                catalog_search_terms = list(
                    dict.fromkeys(
                        [
                            *sorted(query_categories),
                            *(
                                term
                                for term in search_terms
                                if (
                                    not semantic_categories({term})
                                    or semantic_categories({term}).issubset(
                                        query_categories
                                    )
                                )
                            ),
                        ]
                    )
                )
            selected_place_ids = {
                place.place_id
                for place in context.selected_by_ref.values()
                if place.place_id is not None
            }
            catalog_candidates = self.place_tool.search(
                region_key=region_key,
                target_tags=catalog_search_terms,
                excluded_place_ids=(
                    set(context.plan_status.used_place_ids) | selected_place_ids
                ),
                limit=self.max_candidates_per_block,
                bbox_filter=context.bbox_filter,
            )
            catalog_candidates = [
                candidate
                for candidate in catalog_candidates
                if not self._duplicates_existing_identity(
                    candidate,
                    selected_places=context.selected_by_ref.values(),
                    occupied_items=context.occupied_items,
                )
            ]
            candidates.extend(
                self._rerank_for_proximity(
                    catalog_candidates,
                    context.user_status,
                )
            )

        unique_candidates: list[SelectablePlace] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate.stable_ref in seen:
                continue
            seen.add(candidate.stable_ref)
            unique_candidates.append(candidate)

        unique_candidates = self._filter_repeated_food_drink(
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
                enforce_opening_hours=context.enforce_opening_hours,
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

    def _duplicates_existing_identity(
        self,
        candidate: SelectablePlace,
        *,
        selected_places,
        occupied_items: list[PlanItem],
    ) -> bool:
        return any(
            self._same_place_identity(candidate, existing)
            for existing in [*selected_places, *occupied_items]
        )

    def _same_place_identity(self, left, right) -> bool:
        left_id = getattr(left, "place_id", None)
        right_id = getattr(right, "place_id", None)
        if left_id and right_id and left_id == right_id:
            return True

        left_tokens = self._identity_tokens(getattr(left, "name", ""))
        right_tokens = self._identity_tokens(getattr(right, "name", ""))
        if not left_tokens or not right_tokens:
            return False
        if left_tokens == right_tokens:
            return True
        if (
            min(len(left_tokens), len(right_tokens)) < 2
            or not (
                left_tokens.issubset(right_tokens)
                or right_tokens.issubset(left_tokens)
            )
        ):
            return False

        coordinates = (
            getattr(left, "latitude", None),
            getattr(left, "longitude", None),
            getattr(right, "latitude", None),
            getattr(right, "longitude", None),
        )
        if any(value is None for value in coordinates):
            return True
        return self._haversine_meters(
            (coordinates[0], coordinates[1]),
            (coordinates[2], coordinates[3]),
        ) <= 750

    @staticmethod
    def _identity_tokens(value: str) -> set[str]:
        tokens = _normalize_text(value).split()
        normalized: list[str] = []
        index = 0
        while index < len(tokens):
            if tokens[index:index + 2] == ["ca", "phe"]:
                normalized.append("cafe")
                index += 2
                continue
            token = "cafe" if tokens[index] == "coffee" else tokens[index]
            if not token.isdigit():
                normalized.append(token)
            index += 1
        if len(normalized) >= 4 and normalized[-2:] == ["ha", "noi"]:
            normalized = normalized[:-2]
        return set(normalized)

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
        candidates: list[SelectablePlace],
        user_status: UserStatus,
    ) -> list[SelectablePlace]:
        location = user_status.location
        if (
            location is None
            or location.latitude is None
            or location.longitude is None
        ):
            return candidates
        origin = (location.latitude, location.longitude)
        ranked: list[tuple[float, float, SelectablePlace]] = []
        for relevance_rank, candidate in enumerate(candidates):
            if candidate.latitude is None or candidate.longitude is None:
                distance = float("inf")
                combined_rank = relevance_rank + 4
            else:
                distance = self._haversine_meters(
                    origin,
                    (candidate.latitude, candidate.longitude),
                )
                # Repository order already represents semantic/quality rank.
                # Compress that rank so a strong nearby candidate can beat a
                # marginally higher-ranked place on the other side of a city.
                combined_rank = relevance_rank * 0.02 + distance / 2_000
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
        selection_blueprint: PlaceSelectionBlueprint,
        brief: PlaceSelectionDay,
        block: DayBlock,
        *,
        intent_interests: list[str],
        travel_style: str,
        strict_day_theme: bool = True,
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
                        *intent_interests,
                        travel_style,
                        brief.theme,
                        *brief.focus_tags,
                        brief.target_area,
                    )
                    if value
                )
            )
        day_goal = (
            brief.day_part_goals.morning
            if block.role in {"main_activity", "late_main_activity"}
            else brief.day_part_goals.evening
            if block.role == "bonus_activity"
            else brief.day_part_goals.afternoon
        )
        primary_values = [
            value
            for value in (
                brief.theme,
                day_goal,
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
        if not strict_day_theme:
            compatible_focus_tags = list(brief.focus_tags)
            route_first_categories = semantic_categories(
                set([*compatible_focus_tags, *primary_values])
            )
            fallback_values = (
                []
                if route_first_categories
                else [*intent_interests, travel_style]
            )
        else:
            fallback_values = []
        return list(
            dict.fromkeys(
                value
                for value in (
                    *compatible_focus_tags,
                    *primary_values,
                    *fallback_values,
                    brief.target_area,
                )
                if value
            )
        )

    def _query_categories(
        self,
        selection_blueprint: PlaceSelectionBlueprint,
        brief: PlaceSelectionDay,
        block: DayBlock,
        *,
        fallback_terms: list[str],
        intent_interests: list[str] | None = None,
        strict_day_theme: bool = True,
    ) -> set[str]:
        if block.candidate_category is not None:
            return {block.candidate_category}

        def for_slot(categories: set[str]) -> set[str]:
            if block.kind != "meal" and "food_drink" in categories:
                non_food = categories - {"food_drink"}
                return non_food or {
                    "attraction",
                    "entertainment",
                    "nature",
                    "shopping",
                }
            return categories

        day_goal = (
            brief.day_part_goals.morning
            if block.role in {"main_activity", "late_main_activity"}
            else brief.day_part_goals.evening
            if block.role == "bonus_activity"
            else brief.day_part_goals.afternoon
        )
        primary_categories = semantic_categories(
            {
                value
                for value in (
                    brief.theme,
                    day_goal,
                )
                if value
            }
        )
        focus_categories = semantic_categories(set(brief.focus_tags))
        if not strict_day_theme:
            global_categories = semantic_categories(set(intent_interests or []))
            return for_slot(
                primary_categories
                or focus_categories
                or global_categories
                or semantic_categories(set(fallback_terms))
            )
        return for_slot(
            primary_categories
            or focus_categories
            or semantic_categories(set(fallback_terms))
        )

    def _selected_to_candidate(
        self,
        selected: SelectedPlaceContext,
        brief: PlaceSelectionDay,
    ) -> SelectablePlace:
        if selected.place_id:
            stored_place = self.place_tool.get(selected.place_id)
            if stored_place is not None:
                return stored_place.model_copy(
                    update={
                        "address": selected.address or stored_place.address,
                        "must_visit": selected.must_visit,
                        "source_refs": list(selected.source_refs),
                        "source_provider": selected.source_provider,
                        "tags": list(dict.fromkeys([*selected.tags, *stored_place.tags])),
                        "source_order": selected.source_order,
                        "source_day": selected.source_day,
                        "source_time_hint": selected.source_time_hint,
                        "source_activity": selected.source_activity,
                        "source_duration_minutes": selected.source_duration_minutes,
                        "notes": selected.notes,
                        "image_urls": (
                            list(selected.image_urls)
                            or stored_place.image_urls
                        ),
                        "rating": (
                            selected.rating
                            if selected.rating is not None
                            else stored_place.rating
                        ),
                        "review_count": (
                            selected.review_count
                            if selected.review_count is not None
                            else stored_place.review_count
                        ),
                    }
                )
        return SelectablePlace(
            placeId=selected.place_id,
            name=selected.name,
            address=selected.address,
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
            sourceLink=selected.source_refs[0] if selected.source_refs else None,
            sourceOrder=selected.source_order,
            sourceDay=selected.source_day,
            sourceTimeHint=selected.source_time_hint,
            sourceActivity=selected.source_activity,
            sourceDurationMinutes=selected.source_duration_minutes,
            notes=selected.notes,
            personalNotes=selected.personal_notes,
            imageUrls=selected.image_urls,
            rating=selected.rating,
            reviewCount=selected.review_count or 0,
        )

    def _intensity_allowed(self, candidate: SelectablePlace, user_status: UserStatus) -> bool:
        allowed = user_status.constraints.allowed_activity_intensities
        if not allowed or candidate.activity_intensity is None:
            return True
        return candidate.activity_intensity in allowed

    def _candidate_rejection(
        self,
        candidate: SelectablePlace,
        block: DayBlock,
        user_status: UserStatus,
        *,
        is_selected: bool,
        query_categories: set[str],
        avoided_place_names: set[str],
        intent_constraints: list[str],
        constraint_policy: ConstraintPolicy,
        budget_level: str,
        enforce_opening_hours: bool = True,
    ) -> CandidateRejection | None:
        if candidate.name.casefold() in avoided_place_names:
            return CandidateRejection("avoided_by_user", "Place is explicitly avoided by the user.")
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
        normalized_place_type = (
            candidate.place_type.strip().casefold().replace(" ", "_")
        )
        if (
            not is_selected
            and normalized_place_type in NON_TOURISM_PLACE_TYPES
        ):
            return CandidateRejection(
                "activity_category_mismatch",
                "The catalogue type is not a visitable tourism activity.",
            )
        if (
            not is_selected
            and block.role in {"main_activity_1", "main_activity_2"}
            and self._has_non_visit_name(candidate)
        ):
            return CandidateRejection(
                "activity_category_mismatch",
                "A service counter or ticket office is not a main activity.",
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
        if (
            not is_selected
            and block.kind != "meal"
            and (
                category == "food_drink"
                or (
                    block.role in {"main_activity_1", "main_activity_2"}
                    and self._has_strong_food_name(candidate)
                )
            )
        ):
            return CandidateRejection(
                "activity_category_mismatch",
                "A food venue cannot replace a regular sightseeing activity.",
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
        if (
            enforce_opening_hours
            and not self._opening_hours_cover_block(
                candidate,
                block.time_window,
                duration,
            )
        ):
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

    @staticmethod
    def _has_strong_food_name(candidate: SelectablePlace) -> bool:
        normalized = f" {_normalize_text(candidate.name)} "
        markers = (
            " restaurant ",
            " cafe ",
            " coffee ",
            " bakery ",
            " bistro ",
            " kitchen ",
            " cuisine ",
            " street food ",
            " vegan ",
            " bun ",
            " pho ",
            " com ",
            " banh ",
            " quan an ",
            " nha hang ",
            " bar dine ",
            " bar and dine ",
            " bar & dine ",
        )
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _has_non_visit_name(candidate: SelectablePlace) -> bool:
        normalized = f" {_normalize_text(candidate.name)} "
        return any(
            marker in normalized
            for marker in (
                " ticketing counter ",
                " ticket counter ",
                " ticket office ",
                " booking office ",
                " information counter ",
            )
        )

    def _semantic_category_rejection(
        self,
        candidate: SelectablePlace,
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
        return None

    def _is_outdoor(self, candidate: SelectablePlace) -> bool:
        outdoor_markers = {"outdoor", "nature", "park", "beach", "hiking"}
        values = {
            candidate.place_type.casefold(),
            *(tag.casefold() for tag in candidate.tags),
        }
        return bool(values.intersection(outdoor_markers))

    def _opening_hours_cover_block(
        self,
        candidate: SelectablePlace,
        time_window: str,
        duration_minutes: int,
    ) -> bool:
        if not candidate.opening_hours:
            return True
        if is_24_hours(candidate.opening_hours):
            return True
        start = parse_clock_minutes(time_window)
        if start is None:
            return True
        end = start + duration_minutes
        intervals = extract_time_intervals(candidate.opening_hours)
        for open_minutes, close_minutes in intervals:
            adjusted_start = start
            adjusted_end = end
            if adjusted_start < open_minutes and adjusted_end <= close_minutes - 24 * 60:
                adjusted_start += 24 * 60
                adjusted_end += 24 * 60
            if open_minutes <= adjusted_start and adjusted_end <= close_minutes:
                return True
        return False
