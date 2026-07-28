from app.modules.plans.domain.entities import CheckReport, CheckIssue, Plan
from app.modules.plans.domain.validators import find_empty_days


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
                    "Increase the trip duration, relax the pace constraint, "
                    "or remove the Place from the confirmed list."
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
                        if item.item_id
                        and item.place_id in duplicate_place_ids
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
        issues.extend(
            [
                CheckIssue(
                    code="route_check_unavailable",
                    severity="info",
                    message=(
                        "Route duration and transport feasibility were not checked "
                        "because no route provider is configured."
                    ),
                    canAutoFix=False,
                ),
                CheckIssue(
                    code="operational_data_check_unavailable",
                    severity="info",
                    message=(
                        "Opening hours and live availability were not checked "
                        "against an external provider."
                    ),
                    canAutoFix=False,
                ),
            ]
        )
        status = (
            "failed"
            if any(issue.severity == "error" for issue in issues)
            else "needs_backup"
            if any(issue.severity == "warning" for issue in issues)
            else "passed"
        )
        summary = (
            "Deterministic schema and allocation checks completed. "
            "External route, opening-hours, availability, and live weather "
            "verification remain unavailable."
        )
        return CheckReport(status=status, issues=issues, summary=summary)

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
