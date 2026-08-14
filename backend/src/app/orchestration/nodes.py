from app.modules.explorer.public import build_explorer_graph
from app.modules.information_finder.public import (
    InformationFinderService,
    build_information_finder_graph,
)
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
from app.orchestration.root_state import RootState


class RootNodes:
    def __init__(
        self,
        information_finder_service: InformationFinderService | None = None,
        supervisor_service: SupervisorService | None = None,
        explorer_service=None,
        place_checker_pipeline: PlaceCheckerPipeline | None = None,
        itinerary_planner_graph=None,
    ) -> None:
        self.supervisor = build_supervisor_graph(supervisor_service)
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
        previous_response = state.get("response")
        recent = state.get("recent_messages") or []
        context_items = list(recent)

        previous_response = state.get("response")
        if previous_response and previous_response not in context_items:
            context_items.append(previous_response)

        current_msg = state.get("message")
        if current_msg and current_msg not in context_items:
            context_items.append(current_msg)

        conversation_context = context_items[-10:]

        memory = state.get("conversation_memory")
        dest = (
            getattr(memory, "destination", None)
            if memory
            else None
        )
        if not dest and isinstance(memory, dict):
            dest = memory.get("destination")
        dur = (
            getattr(memory, "duration_days", None)
            if memory
            else None
        )
        if not dur and isinstance(memory, dict):
            dur = memory.get("duration_days") or memory.get("durationDays")
        places = (
            getattr(memory, "mentioned_places", [])
            if memory
            else []
        )
        if not places and isinstance(memory, dict):
            places = memory.get("mentioned_places") or memory.get("mentionedPlaces") or []
        sel_places = (
            getattr(memory, "selected_places", [])
            if memory
            else []
        )
        if not sel_places and isinstance(memory, dict):
            sel_places = memory.get("selected_places") or memory.get("selectedPlaces") or []
        summary = (
            getattr(memory, "summary", None)
            if memory
            else None
        )
        if not summary and isinstance(memory, dict):
            summary = memory.get("summary")
        pending_goal = (
            getattr(memory, "pending_goal", None)
            if memory
            else None
        )
        if not pending_goal and isinstance(memory, dict):
            pending_goal = memory.get("pending_goal") or memory.get("pendingGoal")
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
        }
        if decision.response is not None:
            update["response"] = decision.response
        if decision.clarification_question is not None:
            update["clarification_question"] = decision.clarification_question
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

        # Context enrichment from conversation memory if present
        memory = state.get("conversation_memory")
        if memory:
            dest = getattr(memory, "destination", None) or (memory.get("destination") if isinstance(memory, dict) else None)
            dur = getattr(memory, "duration_days", None) or (memory.get("duration_days") or memory.get("durationDays") if isinstance(memory, dict) else None)
            places = getattr(memory, "mentioned_places", None) or (memory.get("mentioned_places") or memory.get("mentionedPlaces") if isinstance(memory, dict) else None)

            if dest and not output.input_adm:
                output.input_adm = dest
            if dur and not output.days:
                output.days = dur
            if places and not output.places:
                from app.modules.explorer.contract import ExplorerPlace, PlaceSource
                output.places = [
                    ExplorerPlace(
                        name=p,
                        confidence=0.9,
                        source_places=[
                            PlaceSource(
                                origin="input",
                                evidence_type="raw_prompt",
                                evidence=f"Memory place: {p}",
                            )
                        ],
                    )
                    for p in places
                ]

            if output.status == "clarification" and output.input_adm:
                output.status = "ready"
                output.clarification_question = None

        update = {
            "explorer_output": output,
            "warnings": [*state.get("warnings", []), *output.warnings],
        }
        if output.status != "ready":
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
        result = await self.information_finder.ainvoke({"query": state["message"]})
        output = result["output"]
        return {
            "information_output": output,
            "response": output.answer,
            "warnings": [*state.get("warnings", []), *output.warnings],
        }

    async def run_place_checker(self, state: RootState) -> dict:
        if self.rich_place_checker:
            explorer = state["explorer_output"]
            payload = PlaceCheckerInput.model_validate(
                {
                    "inputADM": explorer.input_adm,
                    "places": self._place_checker_places(explorer.places or []),
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
            compact = PlaceCheckerPlannerOutputBuilder().build(
                output,
                start_date=explorer.start_date.isoformat(),
                timezone=explorer.timezone,
            )
            planner_input = ItineraryPlannerInput.model_validate(
                compact.model_dump(mode="json", by_alias=True)
            )
            update = {
                "place_output": output,
                "planner_input": planner_input,
                "warnings": [
                    *state.get("warnings", []),
                    *projection.warnings,
                ],
            }
            if output.status.value == "blocked":
                update.update(
                    {
                        "clarification_question": (
                            "Một địa điểm bắt buộc chưa được xác minh. "
                            "Bạn có thể bổ sung tên hoặc địa chỉ chính xác hơn không?"
                        ),
                        "response": "PlaceChecker cần làm rõ dữ liệu trước khi lập lịch.",
                    }
                )
            return update

        result = await self.place_checker.ainvoke(
            {
                "input_adm": state["explorer_output"].input_adm,
                "places": state["explorer_output"].places,
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
            return {
                "warnings": [*state.get("warnings", []), error],
                "response": f"Itinerary planning stopped: {error}",
            }
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
