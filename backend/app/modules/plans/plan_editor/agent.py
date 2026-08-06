from __future__ import annotations

from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any

from app.modules.plans.plan_editor.contract import PlanEditorOperation
from app.modules.plans.explorer.model import SourceDocument
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    MutationResponse,
    UpdateItemRequest,
)
from app.shared.errors import AppError


@dataclass(frozen=True)
class HydratedCandidate:
    operation: PlanEditorOperation
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanEditorExecution:
    result: MutationResponse
    summary: str
    warnings: list[str] = field(default_factory=list)


class CandidateHydrationError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(422, code, message)


class PlanEditorAgent:
    """Hydrate user-selected candidates before handing them to mutation tools."""

    def __init__(
        self,
        chat_repository: Any,
        explorer_repository: Any,
        mutation_service: Any | None = None,
    ) -> None:
        self.chat_repository = chat_repository
        self.explorer_repository = explorer_repository
        self.mutation_service = mutation_service

    async def execute(
        self,
        *,
        plan: Any,
        chat: Any,
        turn: Any,
        intent: str,
        operation: PlanEditorOperation | dict[str, Any],
        allow_locked_change: bool = False,
    ) -> PlanEditorExecution:
        """Validate and execute exactly one deterministic editor operation."""
        if self.mutation_service is None:
            raise RuntimeError("PlanEditorAgent requires a PlanMutationService")

        from app.modules.plans.plan_editor.contract import validate_operation_for_intent

        supported_intents = {
            "add_place", "update_place", "remove_place", "move_place",
            "lock_item", "unlock_item",
        }
        if intent not in supported_intents:
            raise AppError(422, "UNSUPPORTED_OPERATION", "Operation is not supported by PlanEditor.")
        operation_model = PlanEditorOperation.model_validate(operation)
        try:
            validate_operation_for_intent(intent, operation_model)
        except ValueError as exc:
            raise AppError(422, "VALIDATION_ERROR", str(exc)) from exc

        warnings: list[str] = []
        if intent in {"add_place", "update_place"}:
            hydrated = self.hydrate_candidate(chat, turn, operation_model)
            operation_model = hydrated.operation
            warnings = hydrated.warnings

        if intent == "update_place" and operation_model.item_id:
            existing = _find_item(plan, operation_model.item_id)
            if existing is not None:
                operation_model = operation_model.model_copy(update={
                    "source_refs": _merge(operation_model.source_refs, existing.source_refs),
                    "candidate_entity_ids": _merge(
                        operation_model.candidate_entity_ids, existing.candidate_entity_ids
                    ),
                    "source_provider": operation_model.source_provider or existing.source_provider,
                    "identity_confidence": (
                        operation_model.identity_confidence or existing.identity_confidence
                    ),
                    "source_import_node_id": (
                        operation_model.source_import_node_id or existing.source_import_node_id
                    ),
                })

        item = _find_item(plan, operation_model.item_id or "")
        if item is not None and item.locked and intent not in {"lock_item", "unlock_item"} and not allow_locked_change:
            raise AppError(409, "LOCKED_ITEM", "Locked items require confirmation before they can be changed.")

        if intent == "add_place":
            return await self.handle_add(plan, operation_model, warnings)
        if intent == "update_place":
            return await self.handle_update(plan, operation_model, warnings)
        if intent == "remove_place":
            return await self.handle_remove(plan, operation_model)
        if intent == "move_place":
            return await self.handle_move(plan, operation_model)
        if intent == "lock_item":
            return await self.handle_lock(plan, operation_model)
        return await self.handle_unlock(plan, operation_model)

    async def handle_add(
        self, plan: Any, operation: PlanEditorOperation, warnings: list[str] | None = None
    ) -> PlanEditorExecution:
        self._require_service()
        display_name = operation.name or operation.candidate_id or operation.place_id
        result = await self._call(
            self.mutation_service.add_item,
            plan,
            AddItemRequest(
                day=operation.day,
                name=str(display_name),
                candidateId=operation.candidate_id,
                placeId=operation.place_id,
                sourceRefs=operation.source_refs,
                sourceImportNodeId=operation.source_import_node_id,
                candidateEntityIds=operation.candidate_entity_ids,
                sourceProvider=operation.source_provider,
                identityConfidence=operation.identity_confidence,
            ),
        )
        self._reject_new_errors(plan, result)
        return PlanEditorExecution(result, f"Added {display_name} to Day {operation.day}.", warnings or [])

    async def handle_update(
        self, plan: Any, operation: PlanEditorOperation, warnings: list[str] | None = None
    ) -> PlanEditorExecution:
        self._require_service()
        result = await self._call(
            self.mutation_service.update_item,
            plan,
            operation.day,
            operation.item_id,
            UpdateItemRequest(
                name=operation.name,
                placeId=operation.place_id,
                sourceRefs=operation.source_refs,
                sourceImportNodeId=operation.source_import_node_id,
                candidateEntityIds=operation.candidate_entity_ids,
                sourceProvider=operation.source_provider,
                identityConfidence=operation.identity_confidence,
            ),
        )
        self._reject_new_errors(plan, result)
        return PlanEditorExecution(result, "Updated the place.", warnings or [])

    async def handle_remove(self, plan: Any, operation: PlanEditorOperation) -> PlanEditorExecution:
        self._require_service()
        result = await self._call(self.mutation_service.remove_item, plan, operation.day, operation.item_id)
        self._reject_new_errors(plan, result)
        return PlanEditorExecution(result, "Removed the place.")

    async def handle_move(self, plan: Any, operation: PlanEditorOperation) -> PlanEditorExecution:
        self._require_service()
        result = await self._call(
            self.mutation_service.move_item,
            plan,
            operation.day,
            operation.item_id,
            MoveItemRequest(toDay=operation.to_day),
        )
        self._reject_new_errors(plan, result)
        return PlanEditorExecution(result, f"Moved the place to Day {operation.to_day}.")

    async def handle_lock(self, plan: Any, operation: PlanEditorOperation) -> PlanEditorExecution:
        return await self._handle_lock_change(plan, operation, True)

    async def handle_unlock(self, plan: Any, operation: PlanEditorOperation) -> PlanEditorExecution:
        return await self._handle_lock_change(plan, operation, False)

    async def _handle_lock_change(self, plan: Any, operation: PlanEditorOperation, locked: bool) -> PlanEditorExecution:
        self._require_service()
        result = await self._call(
            self.mutation_service.update_item,
            plan,
            operation.day,
            operation.item_id,
            UpdateItemRequest(locked=locked),
        )
        self._reject_new_errors(plan, result)
        return PlanEditorExecution(result, "Locked the place." if locked else "Unlocked the place.")

    def _require_service(self) -> None:
        if self.mutation_service is None:
            raise RuntimeError("PlanEditorAgent requires a PlanMutationService")

    @staticmethod
    async def _call(method: Any, *args: Any) -> Any:
        result = method(*args)
        return await result if isawaitable(result) else result

    def _reject_new_errors(self, plan: Any, result: MutationResponse) -> None:
        before = _error_codes(self.mutation_service.checker.check(plan))
        after = _error_codes(result.check_report)
        new_errors = sorted(after - before)
        if new_errors:
            raise AppError(
                422,
                "MUTATION_VALIDATION_FAILED",
                "Mutation introduced new checker errors and was rejected.",
                {"newErrors": new_errors},
            )

    def hydrate_candidate(
        self,
        chat: Any,
        turn: Any,
        operation: PlanEditorOperation,
    ) -> HydratedCandidate:
        candidate_id = operation.candidate_id
        node_id = operation.source_import_node_id
        if not candidate_id and node_id is None:
            return HydratedCandidate(operation)

        snapshots = self.chat_repository.load_candidate_snapshots(chat, turn)
        snapshot = next(
            (
                item for item in snapshots
                if candidate_id
                and str(item.get("candidateId") or item.get("candidate_id") or item.get("id"))
                == candidate_id
            ),
            None,
        )
        if node_id is not None:
            node = self.explorer_repository.load_candidate_node(
                chat.current_intake_id,
                node_id,
                user_id=str(chat.user_id),
                chat_id=chat.id,
            )
            if node is None:
                raise CandidateHydrationError(
                    "FOREIGN_IMPORT_NODE",
                    "Candidate import node does not belong to this chat.",
                )
            if candidate_id and candidate_id not in {
                str(node.id), str(node.candidate_key or ""), str(node.entity_id)
            } and (snapshot is None or snapshot.get("sourceImportNodeId") != node_id):
                raise CandidateHydrationError(
                    "CANDIDATE_NOT_FOUND",
                    "The selected candidate is not in this chat.",
                )
            snapshot = self._snapshot_from_node(node, snapshot)

        if snapshot is None:
            raise CandidateHydrationError(
                "CANDIDATE_NOT_FOUND",
                "The selected candidate is no longer available in this chat.",
            )

        reviews = self.chat_repository.load_candidate_reviews(chat)
        review = next(
            (item for item in reviews if item.candidate_id == candidate_id), None
        )
        if review is not None and review.status == "ignored":
            raise CandidateHydrationError("CANDIDATE_NOT_FOUND", "The selected candidate is unavailable.")

        values = dict(snapshot)
        if review is not None:
            values.setdefault("name", review.resolved_name or review.name)
            values.setdefault("sourceRefs", list(review.source_urls))
            values.setdefault("sourceProvider", review.provider)
            if not values.get("placeId"):
                selected = [match for match in review.top_matches if match.selected]
                if len(selected) == 1:
                    values["placeId"] = selected[0].place_id or selected[0].external_id
            values.setdefault("identityConfidence", _review_confidence(review.status))

        place_id = operation.place_id or values.get("placeId")
        source_refs = _merge(operation.source_refs, values.get("sourceRefs"))
        entity_ids = _merge(operation.candidate_entity_ids, values.get("candidateEntityIds"))
        if node_id is not None:
            node = self.explorer_repository.load_candidate_node(
                chat.current_intake_id, node_id, user_id=str(chat.user_id), chat_id=chat.id
            )
            assert node is not None
            source_refs = _merge(source_refs, self._source_refs(node))
            entity_ids = _merge(entity_ids, [
                str(match["entityId"])
                for match in (node.match_candidates or [])
                if match.get("entityId")
            ])
            place_id = operation.place_id or node.selected_entity_id or place_id
            values.setdefault("sourceProvider", node.provider)
            values.setdefault("identityConfidence", _node_confidence(node.identity_status))

        if not place_id and (review is None or review.status != "resolved"):
            raise CandidateHydrationError(
                "CANDIDATE_IDENTITY_REQUIRED",
                "The selected candidate needs confirmation before it can be added.",
            )
        if not place_id and review is not None and review.status == "resolved":
            raise CandidateHydrationError(
                "CANDIDATE_IDENTITY_REQUIRED",
                "The verified candidate has no stable place identity.",
            )

        update = {
            "name": operation.name or values.get("resolvedName") or values.get("name"),
            "place_id": place_id,
            "source_refs": source_refs,
            "source_provider": operation.model_dump().get("source_provider") or values.get("sourceProvider"),
            "source_import_node_id": node_id,
            "candidate_entity_ids": entity_ids,
            "identity_confidence": operation.model_dump().get("identity_confidence") or values.get("identityConfidence"),
        }
        if not update["name"]:
            raise CandidateHydrationError("CANDIDATE_NOT_FOUND", "The selected candidate has no display name.")
        warnings = []
        if update["identity_confidence"] not in {"high", "verified"}:
            warnings.append("candidate_identity_provisional")
        return HydratedCandidate(operation.model_copy(update=update), warnings)

    @staticmethod
    def _snapshot_from_node(node: Any, snapshot: dict | None) -> dict:
        result = dict(snapshot or {})
        result.setdefault("candidateId", node.candidate_key or str(node.id))
        result.setdefault("name", node.candidate_name or node.canonical_name)
        result.setdefault("placeId", node.selected_entity_id)
        result.setdefault("sourceImportNodeId", node.id)
        result.setdefault("sourceProvider", node.provider)
        result.setdefault("candidateEntityIds", [
            str(item["entityId"])
            for item in (node.match_candidates or [])
            if item.get("entityId")
        ])
        result.setdefault("identityConfidence", _node_confidence(node.identity_status))
        return result

    def _source_refs(self, node: Any) -> list[str]:
        document_id = getattr(node, "source_document_id", None)
        if not document_id:
            return []
        document = self.explorer_repository.session.get(
            SourceDocument, document_id
        )
        return [document.canonical_url] if document is not None else []


def _merge(left: list[str] | None, right: object) -> list[str]:
    values = list(left or [])
    if isinstance(right, list):
        values.extend(str(item) for item in right if item)
    return list(dict.fromkeys(values))


def _find_item(plan: Any, item_id: str) -> Any | None:
    for day in plan.days:
        for item in day.items:
            if item.item_id == item_id:
                return item
    return None


def _error_codes(report: Any) -> set[str]:
    return {issue.code for issue in report.issues if issue.severity == "error"}


def _node_confidence(status: str | None) -> str:
    return {"resolved": "high", "branch_ambiguous": "low"}.get(status, "medium")


def _review_confidence(status: str) -> str:
    return "high" if status == "resolved" else "low" if status == "needs_review" else "medium"
