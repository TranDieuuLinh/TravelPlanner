from __future__ import annotations

import json
from pathlib import Path


_DATASET_DIR = Path(__file__).resolve().parents[4] / "database" / "golden_dataset"
_MODULE_FILES = {
    "extractor": "extractor_cases.json",
    "explorer": "explorer_cases.json",
    "planner": "planner_cases.json",
    "finder": "finder_cases.json",
    "checker_backup": "checker_backup_cases.json",
    "full_pipeline": "full_pipeline_cases.json",
}


def load_golden_cases(
    *,
    module: str | None = None,
    query: str | None = None,
) -> list[dict]:
    selected = (
        {module: _MODULE_FILES[module]}
        if module in _MODULE_FILES
        else _MODULE_FILES
    )
    normalized_query = (query or "").strip().casefold()
    items: list[dict] = []
    for module_name, filename in selected.items():
        payload = json.loads(
            (_DATASET_DIR / filename).read_text(encoding="utf-8")
        )
        for case in payload.get("cases", []):
            item = {
                "module": module_name,
                "datasetVersion": payload.get("version"),
                **case,
            }
            item["validation"] = _validate_case(module_name, case)
            if normalized_query and normalized_query not in " ".join(
                str(item.get(key, "")).casefold()
                for key in ("id", "scenarioName", "scenarioPurpose", "category")
            ):
                continue
            items.append(item)
    return items


def golden_modules() -> list[str]:
    return list(_MODULE_FILES)


def get_golden_case(case_id: str) -> dict | None:
    normalized_id = case_id.strip().casefold()
    for item in load_golden_cases():
        if str(item.get("id", "")).casefold() == normalized_id:
            return item
    return None


def update_golden_case_input(case_id: str, new_input: dict) -> dict | None:
    normalized_id = case_id.strip().casefold()
    for module_name, filename in _MODULE_FILES.items():
        filepath = _DATASET_DIR / filename
        if not filepath.exists():
            continue
        payload = json.loads(filepath.read_text(encoding="utf-8"))
        for case in payload.get("cases", []):
            if str(case.get("id", "")).casefold() == normalized_id:
                case["input"] = new_input
                filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                
                item = {
                    "module": module_name,
                    "datasetVersion": payload.get("version"),
                    **case,
                }
                item["validation"] = _validate_case(module_name, case)
                return item
    return None


def _validate_case(module: str, case: dict) -> dict:
    issues: list[dict[str, str]] = []

    def issue(path: str, message: str, severity: str = "error") -> None:
        issues.append({"path": path, "message": message, "severity": severity})

    for key in (
        "id",
        "scenarioName",
        "scenarioPurpose",
        "category",
        "input",
        "goldenOutput",
        "assertions",
    ):
        if key not in case:
            issue(key, "Missing required golden-case field.")
    input_data = case.get("input", {})
    output = case.get("goldenOutput", {})
    if not isinstance(input_data, dict):
        issue("input", "Input must be a JSON object.")
        return _validation_result(issues)
    if not isinstance(output, dict):
        issue("goldenOutput", "Golden output must be a JSON object.")
        return _validation_result(issues)

    if module == "explorer":
        days = input_data.get("tripSpec", {}).get("days")
        if days is None:
            issue(
                "input.tripSpec.days",
                "Current TripPlanningSpec requires days >= 1; null is invalid.",
            )
        if "trace" not in output:
            issue(
                "goldenOutput.trace",
                "Current ExplorerAgentOutput requires AgentTrace.",
            )
    elif module == "extractor":
        if not {
            "url",
            "platform",
            "metadata",
            "artifacts",
            "speechToText",
            "extractedContext",
            "timings",
        }.issubset(output):
            issue(
                "goldenOutput",
                "Output is an evaluation projection, not the current "
                "UrlReelExtractionResult contract.",
            )
        for index, observation in enumerate(
            output.get("structuredSttObservations", [])
        ):
            if "addressHint" in observation:
                issue(
                    f"goldenOutput.structuredSttObservations[{index}].addressHint",
                    "SpeechToTextObservation forbids addressHint; address belongs "
                    "to ExtractedPlace after evidence merging.",
                )
    elif module == "planner":
        for key in ("intent", "tripSpec", "regionContext"):
            if key not in input_data:
                issue(
                    f"input.{key}",
                    "Current PlannerAgentInput requires this field.",
                )
        for key in ("mode", "macroPlan", "tripSpec", "trace"):
            if key not in output:
                issue(
                    f"goldenOutput.{key}",
                    "Current PlannerAgentOutput requires this field.",
                )
        if output.get("macroPlan", object()) is None:
            issue(
                "goldenOutput.macroPlan",
                "PlannerAgentOutput does not allow null macroPlan, including "
                "the blocked response.",
            )
        for item in output.get("unallocatedSelectedPlaces", []):
            if item.get("reasonCode") == "CONSTRAINT_EXCLUDED":
                issue(
                    "goldenOutput.unallocatedSelectedPlaces.reasonCode",
                    "Current reason codes are lower snake_case, normally "
                    "excluded_place_type or avoided_by_user.",
                )
    elif module == "finder":
        for key in ("intent", "tripSpec", "macroPlan"):
            if key not in input_data:
                issue(
                    f"input.{key}",
                    "Current FinderAgentInput requires this field.",
                )
        for key in ("mode", "finalDays", "trace"):
            if key not in output:
                issue(
                    f"goldenOutput.{key}",
                    "Current FinderAgentOutput requires this field.",
                )
        for day_index, day in enumerate(output.get("finalDays", [])):
            for item_index, item in enumerate(day.get("items", [])):
                if item.get("placeType") == "transport":
                    issue(
                        (
                            f"goldenOutput.finalDays[{day_index}].items"
                            f"[{item_index}]"
                        ),
                        "Current Finder stores travel in transportLegs, not as "
                        "a transport PlanItem.",
                    )
    elif module == "checker_backup":
        check_report = output.get("checkReport")
        if isinstance(check_report, dict):
            if "summary" not in check_report:
                issue(
                    "goldenOutput.checkReport.summary",
                    "Current CheckReport requires summary.",
                )
            for index, check_issue in enumerate(check_report.get("issues", [])):
                if "violationCode" in check_issue:
                    issue(
                        f"goldenOutput.checkReport.issues[{index}].violationCode",
                        "Current CheckIssue field is code, not violationCode.",
                    )
        backup_plan = output.get("backupPlan")
        if isinstance(backup_plan, dict):
            if "mainPlanId" in backup_plan:
                issue(
                    "goldenOutput.backupPlan.mainPlanId",
                    "Current Plan link field is parentPlanId.",
                )
            if any(
                "isLocked" in item
                for day in backup_plan.get("days", [])
                for item in day.get("items", [])
            ):
                issue(
                    "goldenOutput.backupPlan.days.items.isLocked",
                    "PlanItem has no isLocked field; locked IDs live in "
                    "FinderPlanStatus.lockedItemIds.",
                )
            required_plan_fields = {
                "id",
                "title",
                "destination",
                "intent",
                "macroPlan",
                "days",
            }
            if not required_plan_fields.issubset(backup_plan):
                issue(
                    "goldenOutput.backupPlan",
                    "Backup output is a partial projection, not a valid Plan.",
                )
    elif module == "full_pipeline":
        issue(
            "goldenOutput",
            "E2E golden output is a compact assertion projection, not the "
            "current ExploreIntakeResponse or Plan API shape.",
            "warning",
        )

    return _validation_result(issues)


def _validation_result(issues: list[dict[str, str]]) -> dict:
    error_count = sum(issue["severity"] == "error" for issue in issues)
    return {
        "status": "invalid" if error_count else "warning" if issues else "valid",
        "errorCount": error_count,
        "warningCount": len(issues) - error_count,
        "issues": issues,
    }
