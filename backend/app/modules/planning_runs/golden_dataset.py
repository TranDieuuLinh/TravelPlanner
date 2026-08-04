from __future__ import annotations

import json
from pathlib import Path


_DATASET_DIR = Path(__file__).resolve().parents[4] / "database" / "golden_dataset"
_MODULE_FILES = {
    "extractor": "extractor_cases.json",
    "explorer": "explorer_cases.json",
    # These two files retain their historical filenames so existing local
    # datasets keep working. Cases are exposed under the current module names.
    "trip_theme_planner": "planner_cases.json",
    "place_selector": "finder_cases.json",
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
            case = _adapt_legacy_planning_case(module_name, case)
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
                
                adapted_case = _adapt_legacy_planning_case(
                    module_name, case
                )
                item = {
                    "module": module_name,
                    "datasetVersion": payload.get("version"),
                    **adapted_case,
                }
                item["validation"] = _validate_case(
                    module_name, adapted_case
                )
                return item
    return None


def _adapt_legacy_planning_case(module: str, case: dict) -> dict:
    """Project stored pre-migration fixtures onto the current contracts.

    The JSON files are retained as migration fixtures; evaluation and the API
    expose only TripThemePlanner and PlaceSelector shapes.
    """

    adapted = json.loads(json.dumps(case))
    input_data = adapted.get("input", {})
    output = adapted.get("goldenOutput", {})
    if module == "trip_theme_planner":
        legacy_macro = output.pop("macroPlan", None) or {}
        themes = legacy_macro.get("tripThemes") or _themes_from_legacy_days(
            legacy_macro.get("dayBriefs", [])
        )
        output.pop("unallocatedSelectedPlaces", None)
        output["tripThemesReady"] = bool(themes)
        output["tripThemes"] = themes
        output.setdefault("tripSpec", input_data.get("tripSpec", {"days": 1}))
    elif module == "place_selector":
        legacy_macro = input_data.pop("macroPlan", None) or {}
        input_data["regionKey"] = legacy_macro.get(
            "regionKey", "vn,ha-noi"
        )
        input_data["tripThemes"] = legacy_macro.get(
            "tripThemes"
        ) or _themes_from_legacy_days(legacy_macro.get("dayBriefs", []))
        if "allowFinderSuggestions" in input_data:
            input_data["allowPlaceSuggestions"] = input_data.pop(
                "allowFinderSuggestions"
            )
    return adapted


def _themes_from_legacy_days(days: list[dict]) -> list[dict]:
    themes: list[dict] = []
    for day in days:
        theme = str(day.get("theme") or "Khám phá địa phương")
        if any(item["theme"] == theme for item in themes):
            continue
        themes.append(
            {
                "theme": theme,
                "focusTags": day.get("focusTags", []),
                "minimumActivities": 1,
            }
        )
    return themes or [
        {
            "theme": "Khám phá địa phương",
            "focusTags": ["local"],
            "minimumActivities": 1,
        }
    ]


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
    elif module == "trip_theme_planner":
        for key in ("intent", "tripSpec", "regionContext"):
            if key not in input_data:
                issue(
                    f"input.{key}",
                    "Current TripThemePlanningInput requires this field.",
                )
        for key in (
            "mode",
            "tripThemesReady",
            "tripThemes",
            "tripSpec",
            "trace",
        ):
            if key not in output:
                issue(
                    f"goldenOutput.{key}",
                    "Current TripThemePlanningOutput requires this field.",
                )
        if "macroPlan" in output or "dayBriefs" in output:
            issue(
                "goldenOutput",
                "TripThemePlanner must not return calendar allocation.",
            )
    elif module == "place_selector":
        for key in ("intent", "tripSpec", "regionKey", "tripThemes"):
            if key not in input_data:
                issue(
                    f"input.{key}",
                    "Current PlaceSelectionInput requires this field.",
                )
        for key in ("mode", "finalDays", "trace"):
            if key not in output:
                issue(
                    f"goldenOutput.{key}",
                    "Current PlaceSelectionOutput requires this field.",
                )
        for day_index, day in enumerate(output.get("finalDays", [])):
            for item_index, item in enumerate(day.get("items", [])):
                if item.get("placeType") == "transport":
                    issue(
                        (
                            f"goldenOutput.finalDays[{day_index}].items"
                            f"[{item_index}]"
                        ),
                        "Current PlaceSelector stores travel in transportLegs, not as "
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
                    "PlaceSelectionStatus.lockedItemIds.",
                )
            required_plan_fields = {
                "id",
                "title",
                "destination",
                "intent",
                "tripThemes",
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
