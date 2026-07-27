from app.modules.plans.domain.entities import CheckIssue, Plan


def find_empty_days(plan: Plan) -> list[CheckIssue]:
    return [
        CheckIssue(code="empty_day", severity="warning", message=f"Day {day.day} has no committed places.")
        for day in plan.days
        if not day.items
    ]
