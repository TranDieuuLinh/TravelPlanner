from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.plans.plan_editor.contract import PlanEditorOperation
from app.modules.plans.explorer.model import SourceDocument
from app.shared.errors import AppError


@dataclass(frozen=True)
class HydratedCandidate:
    operation: PlanEditorOperation
    warnings: list[str] = field(default_factory=list)


class CandidateHydrationError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(422, code, message)


class PlanEditorAgent:
    """Hydrate user-selected candidates before handing them to mutation tools."""

    def __init__(self, chat_repository: Any, explorer_repository: Any) -> None:
        self.chat_repository = chat_repository
        self.explorer_repository = explorer_repository

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


def _node_confidence(status: str | None) -> str:
    return {"resolved": "high", "branch_ambiguous": "low"}.get(status, "medium")


def _review_confidence(status: str) -> str:
    return "high" if status == "resolved" else "low" if status == "needs_review" else "medium"
