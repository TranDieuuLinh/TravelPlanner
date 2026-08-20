from app.modules.explorer.public import (
    ExplorerOutput,
    ExplorerReview,
    TripContextPatch,
    apply_trip_context_patch,
    build_explorer_review,
)
from app.modules.supervisor.public import infer_source_action
from app.orchestration.explorer_handoff import explorer_output_to_intent
from app.orchestration.memory_projection import (
    memory_field,
    supervisor_conversation_context,
)
from app.orchestration.root_state import RootState
from app.shared.entity_linking import link_verified_entities


class ExplorerReviewNodes:
    """Supervisor/Explorer coordination kept separate from downstream agents."""

    async def run_supervisor(self, state: RootState) -> dict:
        pending_review = state.get("pending_explorer_review")
        if pending_review is not None:
            pending_review = ExplorerReview.model_validate(pending_review)
            decision = self.supervisor_service.decide_explorer_review_reply(
                message=state["message"],
                review=pending_review,
                tag_definitions=self.explorer_tag_catalog.definitions(),
            )
            update = {
                **self._new_turn_update(),
                "decision": decision,
                "warnings": decision.warnings,
                "suggestions": [],
                "clarification_question": decision.clarification_question,
            }
            if decision.response is not None:
                update["response"] = decision.response
            return update

        source_action = infer_source_action(
            state.get("message") or "",
            attached=bool(state.get("urls") or state.get("images")),
        )
        conversation_context = supervisor_conversation_context(
            state.get("recent_messages"),
            state.get("response"),
        )
        memory = state.get("conversation_memory")
        supervisor_payload = {
            "message": state["message"],
            "conversation_context": conversation_context,
            "has_source_input": bool(state.get("urls") or state.get("images")),
            "has_itinerary": state.get("existing_itinerary") is not None,
            "has_edit_operation": state.get("edit_operation") is not None,
            "destination": memory_field(memory, "destination"),
            "duration_days": memory_field(memory, "duration_days"),
            "mentioned_places": memory_field(memory, "mentioned_places", []) or [],
            "selected_places": memory_field(memory, "selected_places", []) or [],
            "clarification_required": (
                memory_field(memory, "pending_goal") == "clarify_reference"
            ),
            "conversation_summary": memory_field(memory, "summary"),
        }
        if source_action == "summarize_source":
            decision = self.supervisor_service.decide_source_action(source_action)
        else:
            result = await self.supervisor.ainvoke(supervisor_payload)
            decision = result["decision"]
            if decision.route != "explorer":
                source_action = None
        update = {
            **self._new_turn_update(),
            "decision": decision,
            "conversation_context": conversation_context,
            "warnings": decision.warnings,
            "suggestions": list(decision.suggestions),
            "clarification_question": None,
            "source_action": source_action,
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
                }
            })
            output = result["output"]

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
