from app.modules.plans.domain.entities import CheckReport, CheckIssue, Plan
from app.modules.plans.domain.validators import find_empty_days


class BackupValidator:
    def validate(self, main_plan: Plan, backup_plan: Plan) -> CheckReport:
        issues: list[CheckIssue] = find_empty_days(backup_plan)
        issues.extend(
            CheckIssue(
                code="unscheduled_backup_place",
                severity="warning",
                message=(
                    f"{place.name} could not be scheduled in the backup plan: "
                    f"{place.reason}"
                ),
                evidence=[place.reason_code],
                canAutoFix=False,
            )
            for place in backup_plan.unscheduled_places
        )
        issues.extend(
            CheckIssue(
                code="backup_planning_warning",
                severity="warning",
                message=warning,
                canAutoFix=False,
            )
            for warning in dict.fromkeys(backup_plan.warnings)
        )
        if backup_plan.id == main_plan.id:
            issues.append(CheckIssue(code="mutates_main", severity="error", message="Backup plan must be separate from main plan."))
        if backup_plan.parent_plan_id != main_plan.id:
            issues.append(CheckIssue(code="missing_parent", severity="error", message="Backup plan must reference the main plan."))
        status = (
            "invalid"
            if any(issue.severity == "error" for issue in issues)
            else "needs_revision"
            if issues
            else "valid"
        )
        return CheckReport(status=status, issues=issues, summary="Validated backup plan as a separate plan.")
