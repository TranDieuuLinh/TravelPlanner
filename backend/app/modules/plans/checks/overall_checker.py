import re
from typing import Any

from app.modules.plans.domain.entities import CheckReport, CheckIssue, Plan
from app.modules.plans.domain.constraint_policy import constraint_policy_rejection
from app.modules.plans.domain.validators import find_empty_days
from app.modules.plans.place_selector.timeline_policy import MEAL_ANCHORS


class OverallChecker:
    def check(self, plan: Plan) -> CheckReport:
        issues: list[CheckIssue] = find_empty_days(plan)
        issues.extend(
            CheckIssue(
                code="selected_place_unscheduled",
                severity="warning",
                message=(
                    f"{place.name} was confirmed but could not be scheduled: "
                    f"{place.reason}"
                ),
                affectedItemIds=[place.place_id] if place.place_id else [],
                evidence=[place.reason_code],
                canAutoFix=False,
                suggestedAction=(
                    "Increase the trip duration, change a fixed time, or "
                    "remove the Place from the confirmed list."
                ),
                owner="selector",
            )
            for place in plan.unscheduled_places
        )
        issues.extend(
            CheckIssue(
                code="planning_warning",
                severity="warning",
                message=warning,
                canAutoFix=False,
            )
            for warning in dict.fromkeys(plan.warnings)
        )
        issues.extend(self._constraint_policy_issues(plan))
        issues.extend(self._timeline_issues(plan))
        quality_issues = self._quality_issues(plan)
        issues.extend(quality_issues)
        duplicate_place_ids = self._duplicate_place_ids(plan)
        if duplicate_place_ids:
            issues.append(
                CheckIssue(
                    code="duplicate_place",
                    severity="error",
                    message="A Place is committed more than once in the plan.",
                    affectedItemIds=[
                        item.item_id
                        for day in plan.days
                        for item in day.items
                        if item.item_id and item.place_id in duplicate_place_ids
                    ],
                    evidence=sorted(duplicate_place_ids),
                    canAutoFix=True,
                    suggestedAction="Remove later duplicate items and refill their blocks.",
                )
            )
        if any("outdoor" in item.place_type for day in plan.days for item in day.items):
            issues.append(
                CheckIssue(
                    code="weather_dependency",
                    severity="info",
                    message="Outdoor items require a fresh weather check before travel.",
                    canAutoFix=False,
                )
            )
        route_legs = [leg for day in plan.days for leg in day.transport_legs]
        unverified_route_legs = [leg for leg in route_legs if not leg.verified]
        if unverified_route_legs:
            issues.append(
                CheckIssue(
                    code="route_check_unavailable",
                    severity="info",
                    message=(
                        f"{len(unverified_route_legs)} route leg(s) use a "
                        "geographic estimate because provider routing was "
                        "unavailable."
                    ),
                    canAutoFix=False,
                )
            )
        issues.append(
            CheckIssue(
                code="operational_data_check_unavailable",
                severity="info",
                message=(
                    "Opening hours and live availability were not checked "
                    "against an external provider."
                ),
                canAutoFix=False,
            )
        )
        status = (
            "failed"
            if any(issue.severity == "error" for issue in issues)
            else "warning"
            if any(issue.severity == "warning" and issue.code in {
                "insufficient_main_experience_diversity",
                "food_drink_dominates_main_activities",
                "required_experience_missing",
                "special_experience_not_preserved",
                "selected_place_unscheduled",
                "timing_recommendation_ignored",
                "nearby_fill_without_evidence",
            } for issue in issues)
            else "needs_backup"
            if any(issue.severity == "warning" for issue in issues)
            else "passed"
        )
        route_summary = (
            "All generated route legs were verified by the configured provider. "
            if route_legs and not unverified_route_legs
            else "Some route legs still require provider verification. "
            if unverified_route_legs
            else "No route legs required verification. "
        )
        summary = (
            "Deterministic schema and allocation checks completed. "
            f"{route_summary}"
            "Opening-hours, availability, and live weather verification "
            "remain unavailable."
        )
        return CheckReport(status=status, issues=issues, summary=summary)

    def _quality_issues(self, plan: Plan) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        main_items = [
            item for day in plan.days for item in day.items
            if self._is_main_activity(item)
        ]
        food_items = [item for item in main_items if self._is_food_drink(item)]
        non_food_items = [item for item in main_items if item not in food_items]
        if len(main_items) >= 3 and len(non_food_items) < 2:
            issues.append(self._issue(
                "insufficient_main_experience_diversity", "warning",
                "Main activities contain fewer than two non-food experiences.",
                [self._item_id(item) for item in main_items],
                [f"mainActivities={len(main_items)}", f"nonFoodActivities={len(non_food_items)}"],
                "Planner produced a narrow main-experience mix; add evidence-backed culture, nature, history, or active activities.",
                "planner",
            ))
        if len(main_items) >= 3 and len(food_items) / len(main_items) >= 0.75:
            issues.append(self._issue(
                "food_drink_dominates_main_activities", "warning",
                "Food and drink account for at least 75% of the main activities.",
                [self._item_id(item) for item in food_items],
                [f"foodDrinkActivities={len(food_items)}", f"mainActivities={len(main_items)}", "threshold=75%"],
                "Planner should reserve main-activity capacity for diverse non-food experiences; Selector should refill from graph-backed candidates.",
                "planner",
            ))
        issues.extend(self._required_experience_issues(plan))
        issues.extend(self._timing_issues(plan))
        issues.extend(self._opening_hours_issues(plan))
        issues.extend(self._nearby_evidence_issues(plan))
        return issues

    def _required_experience_issues(self, plan: Plan) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        scheduled = [item for day in plan.days for item in day.items]
        for requirement in plan.required_experiences:
            requirement_id = self._value(requirement, "requirement_id", "requirementId")
            activity_id = self._value(requirement, "activity_id", "activityId")
            anchor_ids = self._values(requirement, "anchor_place_ids", "anchorPlaceIds")
            candidate_ids = self._values(requirement, "candidate_place_ids", "candidatePlaceIds")
            matches = [item for item in scheduled if (
                (item.place_id and item.place_id in {*anchor_ids, *candidate_ids})
                or (activity_id and item.activity_id == activity_id)
            )]
            if not matches:
                issues.append(self._issue(
                    "required_experience_missing", "error",
                    f"Required experience {requirement_id or 'unknown'} is not scheduled.",
                    [requirement_id] if requirement_id else [],
                    [f"activityId={activity_id}" if activity_id else "activityId=unknown", *anchor_ids, *candidate_ids, "owner=selector"],
                    "Selector must schedule the required anchor/candidate or retain it in unscheduled places with a reason.",
                    "selector",
                ))
                if self._value(requirement, "category") in {"main_experience", "culture", "history", "nature", "active", "outdoor", "nightlife"}:
                    issues.append(self._issue(
                        "special_experience_not_preserved", "error",
                        f"Special experience {requirement_id or 'unknown'} was not preserved in the main plan.",
                        [requirement_id] if requirement_id else [],
                        [f"requirementId={requirement_id or 'unknown'}", "graphEvidence=required", "owner=selector"],
                        "Keep the graph-backed special experience as a main item; do not replace it with a nearby fill without an explicit user choice.",
                        "selector",
                    ))
            else:
                matched = matches[0]
                category = self._value(requirement, "category")
                if category not in {None, "meal", "food"} and self._is_food_drink(matched):
                    issues.append(self._issue(
                        "special_experience_not_preserved", "error",
                        f"Required special experience {requirement_id or 'unknown'} was replaced by a food/drink item.",
                        [self._item_id(matched)],
                        [f"requirementId={requirement_id or 'unknown'}", f"itemCategory={matched.timeline_category}", "owner=selector"],
                        "Restore the required graph-backed experience and keep food/drink as a separate meal anchor.",
                        "selector",
                    ))
        return issues

    def _timing_issues(self, plan: Plan) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        for day in plan.days:
            for item in day.items:
                if not item.preferred_time_windows or not self._is_valid_same_day_window(item.time_window):
                    continue
                start, end = self._window(item)
                if not any(self._window_values(window)[0] <= start and end <= self._window_values(window)[1] for window in item.preferred_time_windows):
                    issues.append(self._issue(
                        "timing_recommendation_ignored", "warning",
                        f"{item.name} is scheduled outside its recommended visit window.",
                        [self._item_id(item)],
                        [f"scheduled={item.time_window}", *[f"recommended={window.start}-{window.end}" for window in item.preferred_time_windows], "owner=selector"],
                        "Selector should move the item into a recommended window or record an explicit fallback warning.",
                        "selector",
                    ))
        return issues

    def _opening_hours_issues(self, plan: Plan) -> list[CheckIssue]:
        return [self._issue(
            "opening_hours_unknown", "info",
            f"Opening hours are unknown for {item.name}; route feasibility is not inferred from this missing data.",
            [self._item_id(item)], ["openingHours=missing", "owner=provider"],
            "Refresh provider opening-hours data before travel and ask the user to verify the venue if it is time-critical.",
            "provider",
        ) for day in plan.days for item in day.items
        if item.timeline_category != "break" and not item.opening_hours]

    def _nearby_evidence_issues(self, plan: Plan) -> list[CheckIssue]:
        return [self._issue(
            "nearby_fill_without_evidence", "warning",
            f"Nearby fill {item.name} has no graph, source, or provider evidence.",
            [self._item_id(item)], [f"selectionMethod={item.selection_method}", "sourceRefs=missing", "owner=graph_data"],
            "Selector must only use nearby fills with graph claim/source evidence, or leave the slot unfilled.",
            "graph_data",
        ) for day in plan.days for item in day.items
        if item.selection_method and "nearby" in item.selection_method.casefold()
        and not (item.source_refs or item.claim_ids or item.source_import_node_id)]

    @staticmethod
    def _issue(code: str, severity: str, message: str, item_ids: list[str], evidence: list[str], action: str, owner: str) -> CheckIssue:
        return CheckIssue(code=code, severity=severity, message=message, affectedItemIds=[item_id for item_id in item_ids if item_id], evidence=evidence, canAutoFix=False, suggestedAction=action, owner=owner)

    @staticmethod
    def _item_id(item) -> str:
        return item.item_id or item.place_id or item.name

    @staticmethod
    def _value(value: Any, *names: str) -> Any:
        for name in names:
            if isinstance(value, dict) and name in value:
                return value[name]
            if hasattr(value, name):
                return getattr(value, name)
        return None

    def _values(self, value: Any, *names: str) -> list[str]:
        result = self._value(value, *names) or []
        return [str(item) for item in result]

    @staticmethod
    def _is_food_drink(item) -> bool:
        markers = {"food", "food_drink", "restaurant", "cafe", "coffee", "bakery", "bar", "drink", "dessert", "meal"}
        return item.timeline_category == "food" or bool(markers.intersection({item.place_type.casefold(), *(tag.casefold() for tag in item.tags)}))

    @staticmethod
    def _is_main_activity(item) -> bool:
        if item.timeline_category == "activity":
            return True
        return item.timeline_category == "food" and (item.role or "").casefold() not in {
            "meal", "breakfast", "lunch", "dinner", "snack"
        }

    @staticmethod
    def _window_values(window) -> tuple[int, int]:
        start = getattr(window, "start", window[0] if isinstance(window, (tuple, list)) else "00:00")
        end = getattr(window, "end", window[1] if isinstance(window, (tuple, list)) else "00:00")
        return OverallChecker._clock(start), OverallChecker._clock(end)

    @staticmethod
    def _clock(value: str) -> int:
        hour, minute = (int(part) for part in value.split(":", maxsplit=1))
        return hour * 60 + minute

    def _timeline_issues(self, plan: Plan) -> list[CheckIssue]:
        invalid_items = [
            item
            for day in plan.days
            for item in day.items
            if not self._is_valid_same_day_window(item.time_window)
        ]
        issues: list[CheckIssue] = []
        if invalid_items:
            issues.append(
                CheckIssue(
                    code="invalid_time_window",
                    severity="error",
                    message=("Plan contains a time window outside the same local day."),
                    affectedItemIds=[
                        item.item_id
                        for item in invalid_items
                        if item.item_id is not None
                    ],
                    evidence=[item.time_window for item in invalid_items],
                    canAutoFix=True,
                    suggestedAction=(
                        "Move overflowing items to another day or leave them "
                        "unscheduled."
                    ),
                )
            )

        anchor_windows = {anchor.role: anchor.time_window for anchor in MEAL_ANCHORS}
        for day in plan.days:
            valid_items = [
                item
                for item in day.items
                if self._is_valid_same_day_window(item.time_window)
            ]
            ordered = sorted(valid_items, key=lambda item: self._window(item)[0])
            overlapping_ids: list[str] = []
            for previous, current in zip(ordered, ordered[1:]):
                if self._window(current)[0] < self._window(previous)[1]:
                    overlapping_ids.extend(
                        item.item_id
                        for item in (previous, current)
                        if item.item_id is not None
                    )
            if overlapping_ids:
                issues.append(
                    CheckIssue(
                        code="timeline_overlap",
                        severity="error",
                        message=f"Day {day.day} contains overlapping timeline items.",
                        affectedItemIds=list(dict.fromkeys(overlapping_ids)),
                        canAutoFix=True,
                        suggestedAction="Re-fit activities between the fixed meal anchors.",
                    )
                )
            for item in day.items:
                expected = anchor_windows.get(item.role or "")
                if expected is None or item.time_window == expected:
                    continue
                issues.append(
                    CheckIssue(
                        code="meal_anchor_moved",
                        severity="warning",
                        message=f"{item.role} on day {day.day} moved from {expected}.",
                        affectedItemIds=[item.item_id] if item.item_id else [],
                        evidence=[item.time_window, expected],
                        canAutoFix=True,
                        suggestedAction="Restore the fixed meal anchor and re-fit activities.",
                    )
                )
        return issues

    @staticmethod
    def _window(item) -> tuple[int, int]:
        start, end = item.time_window.split("-", maxsplit=1)
        start_hour, start_minute = (int(value) for value in start.split(":"))
        end_hour, end_minute = (int(value) for value in end.split(":"))
        return start_hour * 60 + start_minute, end_hour * 60 + end_minute

    def _is_valid_same_day_window(self, value: str) -> bool:
        match = re.fullmatch(
            r"([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)",
            value,
        )
        if match is None:
            return False
        start = int(match.group(1)) * 60 + int(match.group(2))
        end = int(match.group(3)) * 60 + int(match.group(4))
        return start < end

    def _constraint_policy_issues(self, plan: Plan) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        for day in plan.days:
            for item in day.items:
                if item.source not in {
                    "selected_place",
                    "finder_suggestion",
                }:
                    continue
                rejection = constraint_policy_rejection(
                    plan.intent.constraint_policy,
                    name=item.name,
                    place_type=item.place_type,
                    tags=item.tags,
                    region_key=item.region_key,
                )
                if rejection is None:
                    continue
                reason_code, reason = rejection
                issues.append(
                    CheckIssue(
                        code=reason_code,
                        severity="error",
                        message=f"{item.name} violates a hard trip constraint: {reason}",
                        affectedItemIds=(
                            [item.item_id] if item.item_id is not None else []
                        ),
                        evidence=[
                            item.place_type,
                            *item.tags,
                            *([item.region_key] if item.region_key is not None else []),
                        ],
                        canAutoFix=True,
                        suggestedAction=(
                            "Remove this item and refill the slot with a Place "
                            "that has structured evidence satisfying the policy."
                        ),
                    )
                )
        return issues

    def _duplicate_place_ids(self, plan: Plan) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for day in plan.days:
            for item in day.items:
                if not item.place_id:
                    continue
                if item.place_id in seen:
                    duplicates.add(item.place_id)
                seen.add(item.place_id)
        return duplicates
