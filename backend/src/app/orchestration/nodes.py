import logging

from pydantic import ValidationError

from app.modules.explorer.public import YamlTagCatalog, build_explorer_graph
from app.modules.information_finder.entity_linking import link_verified_entities
from app.modules.information_finder.public import (
    InformationFinderService,
    build_information_finder_graph,
)
from app.modules.itinerary_planner.public import (
    ItineraryPlannerInput,
    ItineraryPlannerOutput,
    build_itinerary_planner_graph,
)
from app.modules.place_checker.errors import (
    CandidateSourceTimeout,
    PlaceCatalogUnavailableError,
)
from app.modules.place_checker.public import (
    PlaceCheckerFailure,
    PlaceCheckerPipeline,
    PlaceCheckerPlannerOutputBuilder,
    PlaceCheckerPlanningProjector,
    build_place_checker_graph,
    build_place_checker_pipeline_graph,
)
from app.modules.plan_editor.public import PlanEditorInput, build_plan_editor_graph
from app.modules.supervisor.public import (
    SupervisorService,
    build_supervisor_graph,
)
from app.orchestration.explorer_handoff import (
    ExplorerHandoffError,
    ExplorerHandoffProjector,
    explorer_output_to_intent,
)
from app.orchestration.memory_projection import (
    build_blocked_clarification,
    information_query,
    memory_field,
    supervisor_conversation_context,
)
from app.orchestration.root_state import RootState
from app.shared.contracts.agent import AgentError

logger = logging.getLogger(__name__)


class RootNodes:
    def __init__(
        self,
        information_finder_service: InformationFinderService | None = None,
        supervisor_service: SupervisorService | None = None,
        explorer_service=None,
        place_checker_pipeline: PlaceCheckerPipeline | None = None,
        itinerary_planner_graph=None,
        handoff_projector: ExplorerHandoffProjector | None = None,
    ) -> None:
        self.information_finder_service = information_finder_service
        self.supervisor_service = supervisor_service or SupervisorService()
        self.supervisor = build_supervisor_graph(self.supervisor_service)
        self.explorer = build_explorer_graph(explorer_service)
        tag_catalog = getattr(explorer_service, "tag_catalog", None)
        self.explorer_handoff = handoff_projector or ExplorerHandoffProjector(
            tag_catalog or YamlTagCatalog()
        )
        self.information_finder = build_information_finder_graph(
            information_finder_service
        )
        self.rich_place_checker = place_checker_pipeline is not None
        self.place_checker = (
            build_place_checker_pipeline_graph(place_checker_pipeline)
            if place_checker_pipeline is not None
            else build_place_checker_graph()
        )
        self.itinerary_planner = (
            itinerary_planner_graph or build_itinerary_planner_graph()
        )
        self.plan_editor = build_plan_editor_graph()

    async def run_supervisor(self, state: RootState) -> dict:
        conversation_context = supervisor_conversation_context(
            state.get("recent_messages"),
            state.get("response"),
        )

        memory = state.get("conversation_memory")
        dest = memory_field(memory, "destination")
        dur = memory_field(memory, "duration_days")
        places = memory_field(memory, "mentioned_places", []) or []
        sel_places = memory_field(memory, "selected_places", []) or []
        summary = memory_field(memory, "summary")
        pending_goal = memory_field(memory, "pending_goal")
        clarification = pending_goal == "clarify_reference"

        supervisor_payload = {
            "message": state["message"],
            "conversation_context": conversation_context,
            "has_source_input": bool(state.get("urls") or state.get("images")),
            "has_itinerary": state.get("existing_itinerary") is not None,
            "has_edit_operation": state.get("edit_operation") is not None,
            "destination": dest,
            "duration_days": dur,
            "mentioned_places": places,
            "selected_places": sel_places,
            "clarification_required": clarification,
            "conversation_summary": summary,
        }

        result = await self.supervisor.ainvoke(supervisor_payload)
        decision = result["decision"]
        update = {
            "decision": decision,
            "conversation_context": conversation_context,
            "warnings": decision.warnings,
            "suggestions": [],
        }
        if decision.response is not None:
            response = decision.response
            resolver = getattr(self.information_finder_service, "entity_resolver", None)
            if resolver is not None and decision.entity_names:
                response = await link_verified_entities(
                    response,
                    decision.entity_names,
                    resolver,
                )
            update["response"] = response
        if decision.clarification_question is not None:
            update["clarification_question"] = decision.clarification_question
        return update

    async def run_explorer(self, state: RootState) -> dict:
        result = await self.explorer.ainvoke(
            {
                "payload": {
                    "rawPrompt": state.get("message") or None,
                    "urls": state.get("urls", []),
                    "images": state.get("images", []),
                    "forceRefresh": state.get("force_refresh", False),
                }
            }
        )
        output = result["output"]
        update = {
            "explorer_output": output,
            "warnings": [*state.get("warnings", []), *output.warnings],
        }
        if output.input_adm:
            update["intent"] = explorer_output_to_intent(output)
        return update

    async def run_information_finder(self, state: RootState) -> dict:
        result = await self.information_finder.ainvoke(
            {"query": information_query(state)}
        )
        output = result["output"]
        response = await self.supervisor_service.compose_information_response(
            message=state.get("message", ""),
            conversation_summary=state.get("conversation_summary"),
            output=output,
        )
        if output.suggestions:
            response = "Để tiếp tục, Penguin cần thêm ngân sách. Bạn có thể chọn một gợi ý bên dưới hoặc nhập mức khác."
        return {
            "information_output": output,
            "response": response,
            "warnings": [*state.get("warnings", []), *output.warnings],
        }

    async def run_place_checker(self, state: RootState) -> dict:
        try:
            return await self._run_place_checker(state)
        except ExplorerHandoffError as exc:
            return self._place_checker_failure(
                state,
                code=exc.code,
                message=str(exc),
                status=exc.status,
                retryable=exc.retryable,
            )
        except ValidationError:
            logger.warning("PlaceChecker handoff validation failed", exc_info=True)
            return self._place_checker_failure(
                state,
                code="PLACE_CHECKER_INPUT_INVALID",
                message="Dữ liệu Explorer chưa hợp lệ để kiểm tra địa điểm.",
                status="blocked",
            )
        except (PlaceCatalogUnavailableError, CandidateSourceTimeout):
            logger.warning("PlaceChecker provider unavailable", exc_info=True)
            return self._place_checker_failure(
                state,
                code="PLACE_CHECKER_PROVIDER_UNAVAILABLE",
                message="Nguồn dữ liệu địa điểm tạm thời không khả dụng.",
                status="error",
                retryable=True,
            )
        except Exception:
            logger.exception("PlaceChecker pipeline failed")
            return self._place_checker_failure(
                state,
                code="PLACE_CHECKER_FAILED",
                message="Không thể kiểm tra địa điểm cho chuyến đi.",
                status="error",
            )

    async def _run_place_checker(self, state: RootState) -> dict:
        handoff = self.explorer_handoff.project(
            state["explorer_output"],
            raw_prompt=state.get("message") or "",
            memory=state.get("conversation_memory"),
            resolved_references=state.get("resolved_references"),
            has_source_input=bool(state.get("urls") or state.get("images")),
        )
        explorer = handoff.explorer_output
        payload = handoff.place_checker_input
        if self.rich_place_checker:
            graph_result = await self.place_checker.ainvoke(
                {
                    "request_id": state["request_id"],
                    "correlation_id": state.get("request_id"),
                    "payload": payload,
                }
            )
            output = graph_result["result"]
            projection = PlaceCheckerPlanningProjector().project(output)
            update = {
                "explorer_output": explorer,
                "place_output": output,
                "warnings": list(
                    dict.fromkeys(
                        [
                            *state.get("warnings", []),
                            *projection.warnings,
                            *output.warnings,
                        ]
                    )
                ),
            }
            if output.status.value == "blocked":
                clarification_q, response_msg = build_blocked_clarification(output)
                update.update(
                    {
                        "clarification_question": clarification_q,
                        "response": response_msg,
                    }
                )
            else:
                compact = PlaceCheckerPlannerOutputBuilder().build(
                    output,
                    start_date=explorer.start_date.isoformat(),
                    timezone=explorer.timezone,
                )
                update["planner_input"] = ItineraryPlannerInput.model_validate(
                    compact.model_dump(mode="json", by_alias=True)
                )
            return update

        result = await self.place_checker.ainvoke(
            {
                "input_adm": payload.input_adm,
                "places": payload.places,
                "input_items": payload.input_items,
                "url_notes": payload.url_notes,
                "days": payload.days,
                "budget": payload.budget,
                "people": payload.people,
                "short_preferences": payload.short_preferences,
                "short_avoids": payload.short_avoids,
                "special_notes": payload.special_notes,
            }
        )
        output = result["output"]
        warning = (
            "FinalItineraryPlanner requires the new trip/places/food input "
            "contract; no itinerary was generated."
        )
        return {
            "explorer_output": explorer,
            "place_output": output,
            "warnings": [*state.get("warnings", []), *output.warnings, warning],
            "response": warning,
        }

    @staticmethod
    def _place_checker_failure(
        state: RootState,
        *,
        code: str,
        message: str,
        status: str,
        retryable: bool = False,
    ) -> dict:
        failure = PlaceCheckerFailure(
            status=status,
            error=AgentError(code=code, message=message, retryable=retryable),
            warnings=[message],
        )
        update = {
            "place_output": failure,
            "warnings": list(dict.fromkeys([*state.get("warnings", []), message])),
            "response": message,
        }
        if status == "blocked":
            update["clarification_question"] = message
        return update

    async def run_itinerary_planner(self, state: RootState) -> dict:
        planner_input = state.get("planner_input")
        if planner_input is None:
            warning = (
                "FinalItineraryPlanner requires the new trip/places/food input "
                "contract; no itinerary was generated."
            )
            return {
                "warnings": [*state.get("warnings", []), warning],
                "response": warning,
            }

        result = await self.itinerary_planner.ainvoke({"input": planner_input})
        if error := result.get("error"):
            update = {
                "warnings": [*state.get("warnings", []), error],
                "response": f"Itinerary planning stopped: {error}",
                "planner_error_code": result.get(
                    "error_code", "itinerary_planning_failed"
                ),
            }
            if failure := result.get("preflight_failure"):
                update["planner_preflight_failure"] = failure
            return update
        output = ItineraryPlannerOutput.model_validate(result["output"])
        expected_days = set(range(1, planner_input.trip.days + 1))
        scheduled_days = {day.day for day in output.days if day.stops}
        if (
            len(output.days) != planner_input.trip.days
            or scheduled_days != expected_days
        ):
            warning = (
                "FinalItineraryPlanner returned an incomplete schedule; "
                "every requested day must contain at least one stop."
            )
            return {
                "warnings": list(
                    dict.fromkeys(
                        [
                            *state.get("warnings", []),
                            *result.get("warnings", []),
                            *output.warnings,
                            warning,
                        ]
                    )
                ),
                "response": f"Itinerary planning stopped: {warning}",
            }
        return {
            "warnings": list(
                dict.fromkeys([*state.get("warnings", []), *result.get("warnings", [])])
            ),
            "planner_output": output,
            "response": "Itinerary was optimized successfully.",
        }

    async def run_plan_editor(self, state: RootState) -> dict:
        itinerary = state.get("existing_itinerary")
        operation = state.get("edit_operation")
        if itinerary is None or operation is None:
            return {
                "response": "A structured edit operation and itinerary are required.",
                "warnings": ["Plan edit was not executed."],
            }
        payload = PlanEditorInput(itinerary=itinerary, operation=operation)
        result = await self.plan_editor.ainvoke(payload.model_dump())
        output = result["output"]
        return {
            "itinerary": output.itinerary,
            "warnings": [*state.get("warnings", []), *output.warnings],
            "response": (
                "The itinerary was updated."
                if output.changed
                else "The itinerary was not changed."
            ),
        }

    @staticmethod
    def finish(state: RootState) -> dict:
        return {
            "response": state.get(
                "response",
                "I can help with travel planning and destination information.",
            )
        }
