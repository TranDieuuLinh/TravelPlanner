import re

from app.modules.plans.domain.entities import CheckReport, CheckIssue, Plan
from app.modules.plans.domain.constraint_policy import constraint_policy_rejection
from app.modules.plans.domain.validators import find_empty_days
from app.modules.plans.place_selector.timeline_policy import MEAL_ANCHORS


class OverallChecker:
    def check(self, plan: Plan) -> CheckReport:
        issues: list[CheckIssue] = find_empty_days(plan)
        issues.extend(
            CheckIssue(
                code="unscheduled_selected_place",
                severity="warning",
                message=(
                    f"{place.name} was confirmed but could not be scheduled: "
                    f"{place.reason}"
                ),
                evidence=[place.reason_code],
                canAutoFix=False,
                suggestedAction=(
                    "Increase the trip duration, change a fixed time, or "
                    "remove the Place from the confirmed list."
                ),
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
