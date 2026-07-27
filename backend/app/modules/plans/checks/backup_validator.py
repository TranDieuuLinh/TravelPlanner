from app.modules.plans.domain.entities import CheckReport, CheckIssue, Plan
from app.modules.plans.domain.validators import find_empty_days


class BackupValidator:
    def validate(self, main_plan: Plan, backup_plan: Plan) -> CheckReport:
        issues: list[CheckIssue] = find_empty_days(backup_plan)
        if backup_plan.id == main_plan.id:
            issues.append(CheckIssue(code="mutates_main", severity="error", message="Backup plan must be separate from main plan."))
        if backup_plan.parent_plan_id != main_plan.id:
            issues.append(CheckIssue(code="missing_parent", severity="error", message="Backup plan must reference the main plan."))
        status = "valid" if not any(issue.severity == "error" for issue in issues) else "invalid"
        return CheckReport(status=status, issues=issues, summary="Validated backup plan as a separate plan.")
