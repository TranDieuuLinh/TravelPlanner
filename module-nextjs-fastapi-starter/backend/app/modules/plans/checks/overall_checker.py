from app.modules.plans.domain.entities import CheckReport, CheckIssue, Plan
from app.modules.plans.domain.validators import find_empty_days


class OverallChecker:
    def check(self, plan: Plan) -> CheckReport:
        issues: list[CheckIssue] = find_empty_days(plan)
        if any("outdoor" in item.place_type for day in plan.days for item in day.items):
            issues.append(CheckIssue(code="weather_dependency", severity="info", message="Some items may need weather checks."))
        status = "needs_backup" if any(issue.severity == "warning" for issue in issues) else "passed"
        return CheckReport(status=status, issues=issues, summary="Checked weather, transport, and availability placeholders.")
