"""Batch service that scans every Place and persists controlled tag assertions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import KnowledgeEntity, KnowledgeProperty
from app.modules.knowledge_graph.research.schema import PLACE_TYPES
from app.modules.knowledge_graph.tag_model import (
    KnowledgeEntityTagAssertion,
    KnowledgeTagRun,
    KnowledgeTagScanResult,
)
from app.modules.knowledge_graph.tagging.classifier import classify_place


TAGGING_VERSION = "place-tags-v1"


class PlaceTaggingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, *, apply: bool, run_id: str | None = None) -> dict[str, object]:
        run_id = run_id or f"tagrun_{uuid4().hex}"
        entities = list(
            self.db.scalars(
                select(KnowledgeEntity)
                .where(KnowledgeEntity.entity_type.in_(PLACE_TYPES))
                .order_by(KnowledgeEntity.id)
            )
        )
        entity_ids = [entity.id for entity in entities]
        values: dict[str, dict[str, str]] = {entity_id: {} for entity_id in entity_ids}
        sources: dict[str, dict[str, str | None]] = {entity_id: {} for entity_id in entity_ids}
        for offset in range(0, len(entity_ids), 1000):
            batch = entity_ids[offset:offset + 1000]
            for prop in self.db.scalars(
                select(KnowledgeProperty).where(KnowledgeProperty.entity_id.in_(batch))
            ):
                values[prop.entity_id][prop.key] = prop.value
                sources[prop.entity_id][prop.key] = prop.source

        tagged_count = 0
        assertion_count = 0
        tag_counts: dict[str, int] = {}
        run = KnowledgeTagRun(
            id=run_id,
            version=TAGGING_VERSION,
            status="running",
            processed_count=0,
            tagged_count=0,
            no_evidence_count=0,
        )
        if apply:
            self.db.add(run)
            self.db.flush()

        for entity in entities:
            evidence = classify_place(
                name=entity.canonical_name,
                properties=values[entity.id],
                property_sources=sources[entity.id],
            )
            if evidence:
                tagged_count += 1
            assertion_count += len(evidence)
            for item in evidence:
                tag_counts[item.tag] = tag_counts.get(item.tag, 0) + 1
                if apply:
                    self._upsert_assertion(entity.id, item, run_id)
            if apply:
                self.db.add(
                    KnowledgeTagScanResult(
                        run_id=run_id,
                        entity_id=entity.id,
                        status="tagged" if evidence else "no_evidence",
                        assertion_count=len(evidence),
                    )
                )

        if apply:
            now = datetime.now(timezone.utc)
            run.status = "completed"
            run.processed_count = len(entities)
            run.tagged_count = tagged_count
            run.no_evidence_count = len(entities) - tagged_count
            run.completed_at = now
            self.db.flush()

        return {
            "runId": run_id,
            "version": TAGGING_VERSION,
            "mode": "apply" if apply else "dry-run",
            "processedCount": len(entities),
            "taggedPlaceCount": tagged_count,
            "noEvidenceCount": len(entities) - tagged_count,
            "assertionCount": assertion_count,
            "tagCounts": dict(sorted(tag_counts.items())),
        }

    def _upsert_assertion(self, entity_id, evidence, run_id: str) -> None:
        row = self.db.scalar(
            select(KnowledgeEntityTagAssertion).where(
                KnowledgeEntityTagAssertion.entity_id == entity_id,
                KnowledgeEntityTagAssertion.tag_key == evidence.tag,
                KnowledgeEntityTagAssertion.source == evidence.source,
            )
        )
        if row is None:
            self.db.add(
                KnowledgeEntityTagAssertion(
                    entity_id=entity_id,
                    tag_key=evidence.tag,
                    status=evidence.status,
                    confidence=evidence.confidence,
                    source=evidence.source,
                    evidence_summary=evidence.evidence_summary,
                    inference_run_id=run_id,
                )
            )
            return
        row.status = evidence.status
        row.confidence = evidence.confidence
        row.evidence_summary = evidence.evidence_summary
        row.inference_run_id = run_id
