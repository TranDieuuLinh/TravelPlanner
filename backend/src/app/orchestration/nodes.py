import re

from app.modules.explorer.public import build_explorer_graph
from app.modules.information_finder.public import (
    InformationFinderService,
    build_information_finder_graph,
)
from app.modules.information_finder.entity_linking import link_verified_entities
from app.modules.itinerary_planner.public import (
    ItineraryPlannerInput,
    ItineraryPlannerOutput,
    build_itinerary_planner_graph,
)
from app.modules.plan_editor.public import PlanEditorInput, build_plan_editor_graph
from app.modules.place_checker.public import (
    PlaceCheckerInput,
    PlaceCheckerPipeline,
    PlaceCheckerPlannerOutputBuilder,
    PlaceCheckerPlanningProjector,
    build_place_checker_graph,
    build_place_checker_pipeline_graph,
)
from app.modules.supervisor.public import (
    SupervisorService,
    build_supervisor_graph,
)
from app.modules.supervisor.service import SupervisorService as SupervisorFormatter
from app.orchestration.root_state import RootState
from app.orchestration.routes import explorer_can_plan
from app.orchestration.memory_projection import (
    build_blocked_clarification,
    information_query,
    memory_field,
    merge_memory_places,
    supervisor_conversation_context,
)


class RootNodes:
    def __init__(
        self,
        information_finder_service: InformationFinderService | None = None,
        supervisor_service: SupervisorService | None = None,
        explorer_service=None,
        place_checker_pipeline: PlaceCheckerPipeline | None = None,
        itinerary_planner_graph=None,
    ) -> None:
        self.information_finder_service = information_finder_service
        self.supervisor_service = supervisor_service or SupervisorService()
        self.supervisor = build_supervisor_graph(self.supervisor_service)
        self.explorer = build_explorer_graph(explorer_service)
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
            if self.information_finder is not None and pending_context:
                fields = []
                for request in pending_context:
                    field = request.get("field") if isinstance(request, dict) else request.field
                    if field and field not in fields:
                        fields.append(field)
                destination = dest or "điểm đến của chuyến đi"
                query = (
                    f"Gợi ý lựa chọn {', '.join(fields)} cho chuyến đi tại {destination}; "
                    "ưu tiên địa điểm và hoạt động thực tế, có nguồn xác minh"
                )
                suggestion_result = await self.information_finder.ainvoke({"query": query})
                suggestion_output = suggestion_result["output"]
                update["suggestions"] = list(suggestion_output.suggestions)
                update["information_output"] = suggestion_output.model_copy(
                    update={"content_blocks": []}
                )
        return update

    async def run_explorer(self, state: RootState) -> dict:
        result = await self.explorer.ainvoke(
            {"payload": {
                "rawPrompt": state.get("message") or None,
                "urls": state.get("urls", []),
                "images": state.get("images", []),
                "forceRefresh": state.get("force_refresh", False),
            }}
        )
        output = result["output"]
        pending = state.get("pending_user_context", [])
        if self.information_finder_service and pending and any(
            (item.get("field") if isinstance(item, dict) else item.field) == "budget"
            for item in pending
        ):
            destination = getattr(state.get("explorer_output"), "input_adm", None)
            budget = await self.information_finder_service.suggest_budget_range(
                destination or "", category="daily_trip"
            )
            if budget and budget.sample_count:
                output = output.model_copy(update={"suggestions": [
                    {"field": "budget", "label": "Tiết kiệm", "value": budget.q1, "currency": budget.currency},
                    {"field": "budget", "label": "Tiêu chuẩn", "value": budget.median, "currency": budget.currency},
                    {"field": "budget", "label": "Thoải mái", "value": budget.q3, "currency": budget.currency},
                ]})

        # Context enrichment from conversation memory if present
        memory = state.get("conversation_memory")
        if memory:
            dest = getattr(memory, "destination", None) or (memory.get("destination") if isinstance(memory, dict) else None)
            dur = getattr(memory, "duration_days", None) or (memory.get("duration_days") or memory.get("durationDays") if isinstance(memory, dict) else None)
            if dest:
                output.input_adm = dest
            raw_prompt = state.get("message") or ""
            explicit_days = re.search(
                r"\b\d{1,2}\s*(?:ngày|days?)\b", raw_prompt, re.IGNORECASE
            )
            has_new_input = bool(
                state.get("urls")
                or state.get("images")
                or output.places
                or output.input_items
            )
            # A new source/place intake starts from Explorer's default unless
            # this turn explicitly states a duration. Pure follow-ups such as
            # "lên plan các điểm bên trên" still inherit the remembered trip
            # duration.
            if dur and not explicit_days and not has_new_input:
                output.days = dur
            if memory:
                output.places = merge_memory_places(
                    output.places or [],
                    memory,
                    resolved_references=state.get("resolved_references"),
                )
            travelers = memory_field(memory, "travelers")
            if travelers:
                output.people = output.people.model_copy(
                    update={"adults": travelers, "children": 0, "infants": 0}
                )
            preferences = memory_field(memory, "preferences", []) or []
            avoids = memory_field(memory, "avoids", []) or []
            if preferences:
                output.short_preferences = list(
                    dict.fromkeys([*output.short_preferences, *preferences])
                )
            if avoids:
                output.short_avoids = list(dict.fromkeys([*output.short_avoids, *avoids]))
            budget = memory_field(memory, "budget")
            if isinstance(budget, str) and budget in {"low", "medium", "high"}:
                output.budget = output.budget.model_copy(update={"level": budget})

            if output.status == "clarification" and output.input_adm:
                output.status = "ready"
                output.clarification_question = None

        update = {
            "explorer_output": output,
            "warnings": [*state.get("warnings", []), *output.warnings],
        }
        if not explorer_can_plan(output):
            update.update(
                {
                    "clarification_question": output.clarification_question,
                    "response": output.clarification_question
                    or (output.error.message if output.error else "Explorer failed."),
                }
            )
        else:
            update["intent"] = output_to_intent(output)
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
        if self.rich_place_checker:
            explorer = state["explorer_output"]
            payload = PlaceCheckerInput.model_validate(
                {
                    "inputADM": explorer.input_adm,
                    "places": self._place_checker_places(
                        merge_memory_places(
                            explorer.places or [],
                            state.get("conversation_memory"),
                            resolved_references=state.get("resolved_references"),
                        )
                    ),
                    "inputItems": explorer.input_items,
                    "urlNotes": explorer.url_notes,
                    "days": explorer.days,
                    "budget": explorer.budget,
                    "people": explorer.people,
                    "shortPreferences": explorer.short_preferences,
                    "shortAvoids": explorer.short_avoids,
                }
            )
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
                "place_output": output,
                "warnings": list(dict.fromkeys([
                    *state.get("warnings", []),
                    *projection.warnings,
                    *output.warnings,
                ])),
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
                "input_adm": state["explorer_output"].input_adm,
                "places": merge_memory_places(
                    state["explorer_output"].places or [],
                    state.get("conversation_memory"),
                    resolved_references=state.get("resolved_references"),
                ),
                "input_items": state["explorer_output"].input_items,
                "url_notes": state["explorer_output"].url_notes,
                "days": state["explorer_output"].days,
                "budget": state["explorer_output"].budget,
                "people": state["explorer_output"].people,
                "short_preferences": state["explorer_output"].short_preferences,
                "short_avoids": state["explorer_output"].short_avoids,
            }
        )
        output = result["output"]
        return {
            "place_output": output,
            "warnings": [*state.get("warnings", []), *output.warnings],
        }

    @staticmethod
    def _place_checker_places(places) -> list[dict]:
        """Map only the public evidence fields supported by PlaceChecker."""
        result = []
        for place in places:
            result.append(
                {
                    "name": place.name,
                    "addressHint": place.address_hint,
                    "confidence": place.confidence,
                    "sourcePlaces": [
                        source.model_dump(
                            mode="json",
                            by_alias=True,
                            include={
                                "origin",
                                "evidence_type",
                                "source_url",
                                "evidence",
                                "source_time_hint",
                                "address_hint",
                                "observed_at",
                            },
                        )
                        for source in place.source_places
                    ],
                }
            )
        return result

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


def output_to_intent(output):
    from app.shared.contracts.trip import TripIntent

    return TripIntent(
        destination=output.input_adm,
        days=output.days,
        budget=float(output.budget.target_amount) if output.budget.target_amount else None,
        people=output.people.total,
        preferences=output.short_preferences,
        avoids=output.short_avoids,
    )
