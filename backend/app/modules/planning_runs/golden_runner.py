from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import ValidationError

from app.modules.planning_runs.redaction import safe_snapshot
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.domain.entities import (
    DayBrief,
    MacroPlan,
    Plan,
    PlanDay,
    PlanItem,
    TravelIntent,
)
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    FinderAgentInput,
    PlannerAgentInput,
)
from app.modules.plans.explorer.schema import FullExploreRequest
from app.modules.plans.explorer.tools.url_reels.schema import UrlReelInput
from app.modules.plans.schema import (
    BackupPlanCreate,
    MainPlanFromExplorerCreate,
)
from app.modules.plans.service import PlanService


class GoldenCaseExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GoldenCaseRunner:
    def __init__(
        self,
        plan_service: PlanService,
        planning_runs: PlanningRunRepository,
    ) -> None:
        self.plan_service = plan_service
        self.planning_runs = planning_runs

    async def run(self, case: dict, *, user_id: int) -> dict:
        module = str(case["module"])
        case_id = str(case["id"])
        source_input = case.get("input", {})
        destination = _destination(source_input)
        run_id = self.planning_runs.start(
            source="golden_dataset",
            destination=destination,
            mode=module,
            user_id=user_id,
            summary={"caseId": case_id, "module": module},
        )
        started = time.perf_counter()
        effective_input: object = source_input
        try:
            actual_output, effective_input, adaptations = await self._execute(
                module,
                case_id,
                source_input,
            )
            duration_ms = round((time.perf_counter() - started) * 1000)
            visible_output = safe_snapshot(actual_output)
            comparison = _compare_projection(
                case.get("goldenOutput"),
                visible_output,
            )
            self.planning_runs.add_stage(
                run_id,
                stage=module,
                status="completed",
                input_data=effective_input,
                output_data=visible_output,
                duration_ms=duration_ms,
                metadata={
                    "caseId": case_id,
                    "adaptations": adaptations,
                    "comparison": comparison,
                },
            )
            self.planning_runs.complete(
                run_id,
                status="completed",
                summary={
                    "caseId": case_id,
                    "module": module,
                    "mismatchCount": comparison["mismatchCount"],
                },
            )
            return {
                "runId": run_id,
                "caseId": case_id,
                "module": module,
                "status": "completed",
                "durationMs": duration_ms,
                "effectiveInput": safe_snapshot(effective_input),
                "actualOutput": visible_output,
                "adaptations": adaptations,
                "comparison": comparison,
                "error": None,
            }
        except ValidationError as exc:
            error = {
                "code": "GOLDEN_INPUT_INVALID",
                "message": "Golden case input does not match the current module contract.",
                "details": [
                    {
                        "path": ".".join(str(part) for part in item["loc"]),
                        "message": item["msg"],
                        "type": item["type"],
                    }
                    for item in exc.errors(include_url=False)
                ][:100],
            }
        except GoldenCaseExecutionError as exc:
            error = {"code": exc.code, "message": str(exc), "details": []}
        except Exception as exc:
            error = {
                "code": "GOLDEN_EXECUTION_FAILED",
                "message": str(exc)[:2_000],
                "details": [{"type": type(exc).__name__}],
            }

        duration_ms = round((time.perf_counter() - started) * 1000)
        self.planning_runs.add_stage(
            run_id,
            stage=module,
            status="failed",
            input_data=effective_input,
            duration_ms=duration_ms,
            error=error,
            metadata={"caseId": case_id},
        )
        self.planning_runs.complete(
            run_id,
            status="failed",
            summary={"caseId": case_id, "module": module},
            error_code=error["code"],
            error_message=error["message"],
        )
        return {
            "runId": run_id,
            "caseId": case_id,
            "module": module,
            "status": "failed",
            "durationMs": duration_ms,
            "effectiveInput": safe_snapshot(effective_input),
            "actualOutput": None,
            "adaptations": [],
            "comparison": None,
            "error": error,
        }

    async def _execute(
        self,
        module: str,
        case_id: str,
        source_input: dict,
    ) -> tuple[object, object, list[str]]:
        if module == "extractor":
            return await self._run_extractor(source_input)
        if module == "explorer":
            return await self._run_explorer(source_input)
        if module == "planner":
            planner_input = PlannerAgentInput.model_validate(source_input)
            output = await self.plan_service.main_workflow.planner.create_from_agent_input(
                planner_input
            )
            return output, planner_input, []
        if module == "finder":
            finder_input = FinderAgentInput.model_validate(source_input)
            output = self.plan_service.main_workflow.finder.fill_agent_plan(
                finder_input
            )
            return output, finder_input, []
        if module == "checker_backup":
            if case_id.startswith("CHK-"):
                plan = _checker_plan(source_input)
                report = self.plan_service.main_workflow.checker.check(plan)
                return {"checkReport": report}, plan, [
                    "Legacy checker input was expanded into the current Plan contract."
                ]
            main_plan_id = str(
                source_input.get("parentPlanId")
                or source_input.get("mainPlanId")
                or ""
            )
            if not main_plan_id:
                raise GoldenCaseExecutionError(
                    "GOLDEN_INPUT_INCOMPLETE",
                    "Backup case requires parentPlanId/mainPlanId.",
                )
            result = await self.plan_service.create_backup_plan(
                main_plan_id,
                BackupPlanCreate(
                    reason=str(
                        source_input.get("triggerReason")
                        or "golden_dataset_evaluation"
                    )
                ),
            )
            return result, source_input, []
        if module == "full_pipeline":
            return await self._run_full_pipeline(source_input)
        raise GoldenCaseExecutionError(
            "GOLDEN_MODULE_UNSUPPORTED",
            f"No execution adapter is registered for module {module}.",
        )

    async def _run_extractor(
        self,
        source_input: dict,
    ) -> tuple[object, object, list[str]]:
        url = source_input.get("url")
        if not url:
            raise GoldenCaseExecutionError(
                "GOLDEN_ASSET_MISSING",
                "This extractor case requires an attached image asset; imagePath alone is not executable.",
            )
        payload = UrlReelInput(
            url=str(url),
            destination=_destination(source_input),
            sttInitialPrompt=source_input.get("rawPrompt"),
        )
        output = await asyncio.to_thread(
            self.plan_service.url_reels.extract,
            payload,
        )
        return output, payload, []

    async def _run_explorer(
        self,
        source_input: dict,
    ) -> tuple[object, object, list[str]]:
        reel_signals = source_input.get("urlReelSignals") or []
        payload = FullExploreRequest(
            rawRequest=source_input.get("rawRequest") or "Golden evaluation",
            destination=source_input.get("destination") or "Hà Nội",
            urls=[
                signal["url"]
                for signal in reel_signals
                if isinstance(signal, dict) and signal.get("url")
            ],
            placeCandidates=source_input.get("placeCandidates") or [],
            userState={
                **(source_input.get("userState") or {}),
                "userId": None,
            },
            tripSpec=source_input.get("tripSpec") or {},
        )
        draft = await self.plan_service.explore_formatter.format(payload)
        return draft.explorer, payload, [
            "urlReelSignals were mapped to the current FullExploreRequest.urls contract.",
            "Fixture userId was cleared to keep evaluation runs isolated.",
        ]

    async def _run_full_pipeline(
        self,
        source_input: dict,
    ) -> tuple[object, object, list[str]]:
        raw_prompt = str(source_input.get("rawPrompt") or "")
        destination = _destination(source_input)
        user_state = {
            **(source_input.get("userState") or {}),
            "userId": None,
        }
        payload = FullExploreRequest(
            rawRequest=raw_prompt or "Golden full-pipeline evaluation",
            destination=destination,
            urls=[source_input["url"]] if source_input.get("url") else [],
            userState=user_state,
            tripSpec={"days": _days_from_text(raw_prompt)},
        )
        intake = await self.plan_service.explore_full(payload)
        plan = await self.plan_service.create_main_plan_from_explorer(
            MainPlanFromExplorerCreate(
                intent=intake.explorer.intent,
                tripSpec=intake.explorer.trip_spec,
                intakeId=intake.intake_id,
                userId=None,
                allowFinderSuggestions=intake.allow_finder_suggestions,
            )
        )
        return {
            "intakeId": intake.intake_id,
            "explorer": intake.explorer,
            "finalPlan": plan,
        }, payload, [
            "Destination and duration were derived from the fixture prompt.",
            "Fixture userId was cleared to keep evaluation runs isolated.",
        ]


def _checker_plan(source_input: dict) -> Plan:
    raw_days = source_input.get("days") or []
    day_count = max(len(raw_days), 1)
    destination = _destination(source_input)
    days: list[PlanDay] = []
    day_briefs: list[DayBrief] = []
    for day_index, raw_day in enumerate(raw_days or [{"day": 1, "items": []}], 1):
        day_number = int(raw_day.get("day") or day_index)
        items: list[PlanItem] = []
        for item_index, raw_item in enumerate(raw_day.get("items") or []):
            start_hour = min(8 + item_index * 2, 22)
            end_hour = min(start_hour + 1, 23)
            items.append(
                PlanItem(
                    itemId=raw_item.get("itemId") or f"golden-{day_number}-{item_index + 1}",
                    placeId=raw_item.get("placeId"),
                    name=raw_item.get("name") or "Unnamed golden place",
                    timeWindow=raw_item.get("timeWindow")
                    or f"{start_hour:02d}:00-{end_hour:02d}:00",
                    placeType=raw_item.get("placeType") or "attraction",
                    source=raw_item.get("source") or "selected_place",
                    latitude=raw_item.get("latitude"),
                    longitude=raw_item.get("longitude"),
                    tags=raw_item.get("tags") or [],
                )
            )
        days.append(
            PlanDay(
                day=day_number,
                theme=raw_day.get("theme") or f"Golden day {day_number}",
                items=items,
            )
        )
        day_briefs.append(
            DayBrief(
                day=day_number,
                theme=raw_day.get("theme") or f"Golden day {day_number}",
                targetArea=destination,
            )
        )
    intent = TravelIntent(
        destination=destination,
        days=day_count,
        budget="medium",
        travelStyle="local",
        pace="balanced",
    )
    return Plan(
        id=str(source_input.get("planId") or "golden-checker-plan"),
        kind=PlanKind.main,
        status=PlanStatus.checking,
        title=f"Golden checker plan for {destination}",
        destination=destination,
        intent=intent,
        macroPlan=MacroPlan(
            title=f"Golden checker plan for {destination}",
            destination=destination,
            dayBriefs=day_briefs,
        ),
        days=days,
    )


def _destination(source_input: dict) -> str:
    direct = source_input.get("destination")
    if direct:
        return str(direct)
    intent = source_input.get("intent")
    if isinstance(intent, dict) and intent.get("destination"):
        return str(intent["destination"])
    text = str(
        source_input.get("rawPrompt")
        or source_input.get("rawRequest")
        or ""
    ).casefold()
    return "Hà Nội" if "hà nội" in text or "ha noi" in text else "unspecified"


def _days_from_text(value: str) -> int:
    for days in range(1, 31):
        if f"{days} ngày" in value.casefold():
            return days
    return 3


def _compare_projection(expected: object, actual: object) -> dict:
    mismatches: list[dict[str, object]] = []
    matched = 0

    def walk(expected_value: object, actual_value: object, path: str) -> None:
        nonlocal matched
        if len(mismatches) >= 100:
            return
        if isinstance(expected_value, dict):
            if not isinstance(actual_value, dict):
                mismatches.append(
                    {"path": path or "$", "expected": expected_value, "actual": actual_value}
                )
                return
            for key, child in expected_value.items():
                child_path = f"{path}.{key}" if path else key
                if key not in actual_value:
                    mismatches.append(
                        {"path": child_path, "expected": child, "actual": "[missing]"}
                    )
                else:
                    walk(child, actual_value[key], child_path)
            return
        if isinstance(expected_value, list):
            if not isinstance(actual_value, list):
                mismatches.append(
                    {"path": path or "$", "expected": expected_value, "actual": actual_value}
                )
                return
            if len(expected_value) != len(actual_value):
                mismatches.append(
                    {
                        "path": f"{path}.length",
                        "expected": len(expected_value),
                        "actual": len(actual_value),
                    }
                )
            for index, child in enumerate(expected_value[: len(actual_value)]):
                walk(child, actual_value[index], f"{path}[{index}]")
            return
        if expected_value == actual_value:
            matched += 1
        else:
            mismatches.append(
                {"path": path or "$", "expected": expected_value, "actual": actual_value}
            )

    walk(expected, actual, "")
    return {
        "matchedFieldCount": matched,
        "mismatchCount": len(mismatches),
        "matchesGoldenProjection": not mismatches,
        "mismatches": mismatches,
    }
