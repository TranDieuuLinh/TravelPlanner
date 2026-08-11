from app.modules.explorer.public import build_explorer_graph
from app.modules.information_finder.public import (
    InformationFinderService,
    build_information_finder_graph,
)
from app.modules.itinerary_planner.public import build_itinerary_planner_graph
from app.modules.plan_editor.public import PlanEditorInput, build_plan_editor_graph
from app.modules.place_checker.public import build_place_checker_graph
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
    ) -> None:
        self.supervisor = build_supervisor_graph(supervisor_service)
        self.explorer = build_explorer_graph()
        self.information_finder = build_information_finder_graph(
            information_finder_service
        )
        self.place_checker = build_place_checker_graph()
        self.itinerary_planner = build_itinerary_planner_graph()
        self.plan_editor = build_plan_editor_graph()

    async def run_supervisor(self, state: RootState) -> dict:
        result = await self.supervisor.ainvoke(
            {
                "message": state["message"],
                "has_itinerary": state.get("existing_itinerary") is not None,
                "has_edit_operation": state.get("edit_operation") is not None,
            }
        )
        decision = result["decision"]
        update = {
            "decision": decision,
            "warnings": decision.warnings,
        }
        if decision.response is not None:
            update["response"] = decision.response
        if decision.clarification_question is not None:
            update["clarification_question"] = decision.clarification_question
        return update

    async def run_explorer(self, state: RootState) -> dict:
        result = await self.explorer.ainvoke(
            {
                "message": state["message"],
                "supplied_candidates": state.get("supplied_candidates", []),
            }
        )
        output = result["output"]
        update = {"explorer_output": output}
        if output.intent is None:
            update.update(
                {
                    "clarification_question": output.clarification_question,
                    "response": output.clarification_question
                    or "More trip information is required.",
                }
            )
        else:
            update["intent"] = output.intent
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
        result = await self.place_checker.ainvoke(
            {
                "intent": state["intent"],
                "candidates": state["explorer_output"].candidates,
            }
        )
        output = result["output"]
        return {
            "place_output": output,
            "warnings": [*state.get("warnings", []), *output.warnings],
        }

    async def run_itinerary_planner(self, state: RootState) -> dict:
        result = await self.itinerary_planner.ainvoke(
            {
                "intent": state["intent"],
                "places": state["place_output"].places,
                "upstream_warnings": state.get("warnings", []),
            }
        )
        itinerary = result["output"].itinerary
        return {
            "itinerary": itinerary,
            "warnings": [*state.get("warnings", []), *itinerary.warnings],
            "response": (
                f"Created a {len(itinerary.days)}-day itinerary for "
                f"{itinerary.intent.destination}."
            ),
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
