from app.modules.plans.domain.entities import CheckIssue, Plan


def find_empty_days(plan: Plan) -> list[CheckIssue]:
    return [
        CheckIssue(
            code="empty_day",
            severity="warning",
            message=f"Day {day.day} has no committed Places.",
            canAutoFix=True,
            suggestedAction="Refill the day from confirmed or catalog Places.",
        )
        for day in plan.days
        if not any(
            item.place_id or item.source == "selected_place"
            for item in day.items
        )
    ]
