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
        previous_context = state.get("conversation_context", [])
        context_items = [*previous_context]
        if previous_response and previous_response not in context_items:
            context_items.append(f"[Trợ lý] {previous_response}")
        conversation_context = [
            *context_items,
            *([state["message"]] if state.get("message") else []),
        ][-6:]
        result = await self.supervisor.ainvoke(
            {
                "message": state["message"],
                "conversation_context": conversation_context,
                "has_source_input": bool(state.get("urls") or state.get("images")),
                "has_itinerary": state.get("existing_itinerary") is not None,
                "has_edit_operation": state.get("edit_operation") is not None,
            }
        )
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
        return {
            "warnings": list(
                dict.fromkeys([*state.get("warnings", []), *result.get("warnings", [])])
            ),
            "planner_output": ItineraryPlannerOutput.model_validate(result["output"]),
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
