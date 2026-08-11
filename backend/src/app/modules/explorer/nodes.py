from app.modules.explorer.service import ExplorerService
from app.modules.explorer.state import ExplorerState
from app.shared.contracts.agent import AgentError


class ExplorerNodes:
    def __init__(self, service: ExplorerService) -> None:
        self.service = service

    def prepare_intake(self, state: ExplorerState) -> dict:
        return self.service.prepare(state["payload"])

    async def extract_prompt_structured_draft(self, state: ExplorerState) -> dict:
        try:
            return {"draft": await self.service.prompt_draft(state["payload"].raw_prompt or "")}
        except Exception as exc:
            return {"failure": self.service.error_from_exception(
                exc, "DRAFT_GENERATION_FAILED"
            )}

    async def extract_sources(self, state: ExplorerState) -> dict:
        return {"source_results": await self.service.extract_sources(state["payload"])}

    def evaluate_batch_coverage(self, state: ExplorerState) -> dict:
        coverage, failure = self.service.evaluate_coverage(state["source_results"])
        update = {"coverage": coverage}
        if failure is not None:
            update["failure"] = failure
        return update

    async def synthesize_explorer_draft(self, state: ExplorerState) -> dict:
        try:
            draft = await self.service.source_draft(state["payload"], state["source_results"])
            return {"draft": draft}
        except Exception as exc:
            return {"failure": self.service.error_from_exception(
                exc, "DRAFT_GENERATION_FAILED"
            )}

    def normalize_and_validate(self, state: ExplorerState) -> dict:
        return {"normalized_draft": self.service.normalize(
            state["draft"], state["payload"].raw_prompt
        )}

    def reconcile_input_adm(self, state: ExplorerState) -> dict:
        adm, conflict = self.service.reconcile_adm(state["normalized_draft"])
        return {"input_adm": adm, "adm_conflict": conflict}

    def apply_defaults_and_precedence(self, state: ExplorerState) -> dict:
        return {"output": self.service.finalize(
            intake_id=state["intake_id"], draft=state["normalized_draft"],
            input_adm=state.get("input_adm"), adm_conflict=state.get("adm_conflict", False),
            prompt_days=state.get("prompt_days"), coverage=state.get("coverage"),
            source_results=state.get("source_results"),
        )}

    def mark_failure(self, state: ExplorerState) -> dict:
        error = state.get("failure") or AgentError(
            code="EXPLORER_FAILED", message="Explorer không thể xử lý đầu vào."
        )
        return {"output": self.service.failure(state["intake_id"], error)}

    async def persist_ready_snapshot(self, state: ExplorerState) -> dict:
        return await self._persist(state, "ready")

    async def persist_clarification_snapshot(self, state: ExplorerState) -> dict:
        return await self._persist(state, "clarification")

    async def persist_failure_snapshot(self, state: ExplorerState) -> dict:
        return await self._persist(state, "failure")

    async def _persist(self, state: ExplorerState, kind: str) -> dict:
        failure_output = await self.service.persist_or_failure(state["output"], kind)
        return {"output": failure_output} if failure_output is not None else {}
