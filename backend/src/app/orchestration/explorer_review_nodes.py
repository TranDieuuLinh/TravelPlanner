from app.modules.explorer.public import (
    ExplorerOutput,
    ExplorerReview,
    TripContextPatch,
    apply_trip_context_patch,
    build_explorer_review,
)
from app.orchestration.explorer_handoff import explorer_output_to_intent
from app.orchestration.memory_projection import (
    supervisor_conversation_context,
)
from app.orchestration.root_state import RootState
from app.shared.entity_linking import link_verified_entities


def _dump_explorer_output(output):
    if output is None:
        return None
    if hasattr(output, "model_dump"):
        return output.model_dump(mode="json", by_alias=True)
    return output


def _explorer_context(output) -> dict:
    if output is None:
        return {"destination": None, "duration_days": None, "travelers": None,
                "mentioned_places": [], "selected_places": []}
    data = _dump_explorer_output(output)
    people = data.get("people") or {}
    places = data.get("places") or []
    names = [item.get("name") for item in places if item.get("name")]
    return {
        "destination": data.get("input_ADM") or data.get("inputADM"),
        "duration_days": data.get("days"),
        "travelers": sum(
            int(people.get(key) or 0) for key in ("adults", "children", "infants")
        ) or None,
        "mentioned_places": names,
        "selected_places": names,
    }


def _merge_previous_explorer_output(previous, current, message: str):
    if previous is None or current is None:
        return current
    previous = ExplorerOutput.model_validate(previous)
    updates = {}
    if not current.input_adm:
        updates["input_adm"] = previous.input_adm
    defaulted = set(current.defaulted_fields)
    if "days" in defaulted:
        updates["days"] = previous.days
    if "people" in defaulted:
        updates["people"] = previous.people
    previous_places = previous.places or []
    current_places = current.places or []
    known = {place.name.casefold() for place in current_places}
    updates["places"] = [
        *current_places,
        *[place for place in previous_places if place.name.casefold() not in known],
    ] or None
    updates["short_preferences"] = list(
        dict.fromkeys([*(previous.short_preferences or []), *(current.short_preferences or [])])
    )
    updates["short_avoids"] = list(
        dict.fromkeys([*(previous.short_avoids or []), *(current.short_avoids or [])])
    )
    if not current.input_items:
        updates["input_items"] = previous.input_items
    if current.budget.source == "default" and previous.budget.source != "default":
        updates["budget"] = previous.budget
    return current.model_copy(update=updates)


class ExplorerReviewNodes:
    """Supervisor/Explorer coordination kept separate from downstream agents."""

    async def run_supervisor(self, state: RootState) -> dict:
        explorer_context = _explorer_context(state.get("explorer_output"))
        pending_review = state.get("pending_explorer_review")
        if pending_review is not None:
            pending_review = ExplorerReview.model_validate(pending_review)
            result = await self.supervisor.ainvoke({
                "message": state["message"],
                "conversation_context": supervisor_conversation_context(
                    state.get("recent_messages"), state.get("response")
                ),
                "has_source_input": bool(state.get("urls") or state.get("images")),
                "has_itinerary": state.get("existing_itinerary") is not None,
                "has_edit_operation": state.get("edit_operation") is not None,
                **explorer_context,
                "clarification_required": False,
                "conversation_summary": state.get("conversation_summary"),
                "explorer_output": _dump_explorer_output(state.get("explorer_output")),
                "pending_review_kind": pending_review.kind,
                "pending_review_fields": list(pending_review.missing_fields or pending_review.defaulted_fields),
            })
            decision = result["decision"]
            update = {
                **self._new_turn_update(),
                "decision": decision,
                "warnings": decision.warnings,
                "suggestions": [],
                "clarification_question": decision.clarification_question,
                "source_action": decision.source_action,
            }
            if decision.response is not None:
                update["response"] = decision.response
            return update

        conversation_context = supervisor_conversation_context(
            state.get("recent_messages"),
            state.get("response"),
        )
        explorer_context = _explorer_context(state.get("explorer_output"))
        supervisor_payload = {
            "message": state["message"],
            "conversation_context": conversation_context,
            "has_source_input": bool(state.get("urls") or state.get("images")),
            "has_itinerary": state.get("existing_itinerary") is not None,
            "has_edit_operation": state.get("edit_operation") is not None,
            **explorer_context,
            "clarification_required": False,
            "conversation_summary": state.get("conversation_summary"),
            "explorer_output": _dump_explorer_output(state.get("explorer_output")),
        }
        result = await self.supervisor.ainvoke(supervisor_payload)
        decision = result["decision"]
        update = {
            **self._new_turn_update(),
            "decision": decision,
            "conversation_context": conversation_context,
            "warnings": decision.warnings,
            "suggestions": list(decision.suggestions),
            "clarification_question": None,
            "source_action": decision.source_action,
        }
        if decision.response is not None:
            response = decision.response
            if self.entity_resolver is not None and decision.entity_names:
                response = await link_verified_entities(
                    response,
                    decision.entity_names,
                    self.entity_resolver,
                )
            update["response"] = response
        if decision.clarification_question is not None:
            update["clarification_question"] = decision.clarification_question
        return update

    @staticmethod
    def _new_turn_update() -> dict:
        return {
            "response": "",
            "clarification_question": None,
            "information_output": None,
            "place_output": None,
            "planner_input": None,
            "planner_output": None,
            "planner_preflight_failure": None,
            "planner_error_code": "",
            "itinerary": None,
        }

    async def run_explorer(self, state: RootState) -> dict:
        pending_review = state.get("pending_explorer_review")
        pending_output = state.get("pending_explorer_output")
        if pending_review is not None:
            pending_review = ExplorerReview.model_validate(pending_review)
        if pending_output is not None:
            pending_output = ExplorerOutput.model_validate(pending_output)
        patch = getattr(state.get("decision"), "trip_context_patch", None)
        if pending_review is not None and pending_output is not None and patch is not None:
            output = apply_trip_context_patch(
                pending_output,
                TripContextPatch.model_validate(patch),
                raw_user_message=state.get("message") or "",
                tag_catalog=self.explorer_tag_catalog,
                insight_catalog=self.explorer_insight_catalog,
                budget_estimator=self.explorer_handoff.budget_estimator,
            )
        else:
            result = await self.explorer.ainvoke({
                "payload": {
                    "rawPrompt": state.get("message") or None,
                    "urls": state.get("urls", []),
                    "images": state.get("images", []),
                    "forceRefresh": state.get("force_refresh", False),
                    "conversationContext": state.get("conversation_context", []),
                    "conversationSummary": state.get("conversation_summary"),
                    "explorerOutput": _dump_explorer_output(state.get("explorer_output")),
                    "resolvedEntities": getattr(
                        state.get("decision"), "entity_names", []
                    ),
                }
            })
            output = result["output"]
            output = _merge_previous_explorer_output(
                state.get("explorer_output"), output, state.get("message") or ""
            )

            # A follow-up may only change duration/preferences. If the root
            # graph has no durable checkpoint, preserve the remembered
            # destination instead of sending the user through intake again.
            remembered_destination = _explorer_context(
                state.get("explorer_output")
            ).get("destination")
            if not output.input_adm and remembered_destination:
                output = output.model_copy(update={"input_adm": remembered_destination})


        review = build_explorer_review(output)
        if (
            pending_review is not None
            and pending_review.kind == "defaults_proposed"
            and review.kind == "defaults_proposed"
        ):
            review = review.model_copy(update={"kind": "ready_for_execution"})
        update = {
            "explorer_output": output,
            "explorer_review": review.model_dump(mode="json", by_alias=True),
            "warnings": [*state.get("warnings", []), *output.warnings],
            "clarification_question": None,
        }
        if review.kind == "ready_for_execution":
            update["pending_explorer_review"] = None
            update["pending_explorer_output"] = None
        if output.input_adm:
            update["intent"] = explorer_output_to_intent(output)
        return update
    async def run_supervisor_review(self, state: RootState) -> dict:
        review = ExplorerReview.model_validate(state["explorer_review"])
        response, clarification = self.supervisor_service.compose_explorer_review(review)
        pending = review.kind in {"missing_fields", "defaults_proposed"}
        return {
            "response": response,
            "clarification_question": clarification,
            "pending_explorer_review": (
                review.model_dump(mode="json", by_alias=True) if pending else None
            ),
            "pending_explorer_output": (
                ExplorerOutput.model_validate(state["explorer_output"]).model_dump(
                    mode="json", by_alias=True
                )
                if pending
                else None
            ),
        }

    async def run_supervisor_source_summary(self, state: RootState) -> dict:
        output = ExplorerOutput.model_validate(state["explorer_output"])
        return {
            "response": self.supervisor_service.compose_source_summary(output),
            "clarification_question": None,
            "pending_explorer_review": None,
            "pending_explorer_output": None,
        }
