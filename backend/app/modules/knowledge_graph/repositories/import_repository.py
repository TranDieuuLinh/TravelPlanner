"""PostgreSQL repository for AI Knowledge Graph imports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeGraphImport,
    KnowledgeGraphImportEdge,
    KnowledgeGraphImportNode,
)

if TYPE_CHECKING:
    pass


class GraphImportRepository:
    """Repository for AI Knowledge Graph import jobs (PostgreSQL)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        """List import jobs with pagination and filtering."""
        query = select(KnowledgeGraphImport)
        count_query = select(func.count(KnowledgeGraphImport.id))

        if status:
            query = query.where(KnowledgeGraphImport.status == status)
            count_query = count_query.where(KnowledgeGraphImport.status == status)

        if search:
            pattern = f"%{search}%"
            query = query.where(KnowledgeGraphImport.source_label.ilike(pattern))
            count_query = count_query.where(KnowledgeGraphImport.source_label.ilike(pattern))

        query = query.order_by(KnowledgeGraphImport.created_at.desc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)

        items = list(self.db.scalars(query))
        total = self.db.scalar(count_query) or 0
        return [self._summary_dict(item) for item in items], total

    def count(self) -> int:
        """Count total import jobs."""
        return self.db.scalar(select(func.count(KnowledgeGraphImport.id))) or 0

    def get(self, import_id: str) -> dict | None:
        """Get full import job with nodes and edges."""
        job = self.db.scalars(
            select(KnowledgeGraphImport).where(KnowledgeGraphImport.id == import_id)
        ).first()
        if job is None:
            return None
        return self._job_dict(job)

    def get_meta(self, import_id: str) -> dict | None:
        """Get import job metadata (no nodes/edges)."""
        job = self.db.get(KnowledgeGraphImport, import_id)
        if job is None:
            return None
        return self._meta_dict(job)

    def save(self, job: dict) -> dict:
        """Save or update an import job."""
        existing = self.db.get(KnowledgeGraphImport, job["id"])
        if existing:
            for key, value in job.items():
                if key == "nodes" or key == "edges":
                    continue
                if hasattr(existing, key):
                    if key in {"created_at", "applied_at"}:
                        value = self._as_datetime(value)
                    setattr(existing, key, value)
        else:
            db_job = KnowledgeGraphImport(
                id=job["id"],
                source_label=job["source_label"],
                source_url=job.get("source_url"),
                source_content=job.get("source_content", ""),
                status=job["status"],
                schema_version=job["schema_version"],
                ontology_version=job["ontology_version"],
                dataset_hash=job["dataset_hash"],
                warnings=job.get("warnings") or [],
                node_count=job.get("node_count", 0),
                edge_count=job.get("edge_count", 0),
                issue_count=job.get("issue_count", 0),
                created_by=job["created_by"],
                created_at=self._as_datetime(job.get("created_at"))
                or datetime.now(timezone.utc),
                applied_at=self._as_datetime(job.get("applied_at")),
                applied_dataset_hash=job.get("applied_dataset_hash"),
                error_message=job.get("error_message"),
            )
            self.db.add(db_job)
        self.db.flush()

        if "nodes" in job:
            incoming_node_ids = {node["temp_id"] for node in job["nodes"]}
            stored_nodes = self.db.scalars(
                select(KnowledgeGraphImportNode).where(
                    KnowledgeGraphImportNode.import_id == job["id"]
                )
            )
            for node in stored_nodes:
                if node.temp_id not in incoming_node_ids:
                    self.db.delete(node)
            self.save_nodes(job["id"], job["nodes"])

        if "edges" in job:
            incoming_edge_ids = {edge["temp_id"] for edge in job["edges"]}
            stored_edges = self.db.scalars(
                select(KnowledgeGraphImportEdge).where(
                    KnowledgeGraphImportEdge.import_id == job["id"]
                )
            )
            for edge in stored_edges:
                if edge.temp_id not in incoming_edge_ids:
                    self.db.delete(edge)
            self.save_edges(job["id"], job["edges"])

        return job

    @staticmethod
    def _as_datetime(value: object) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise TypeError(f"Unsupported datetime value: {type(value).__name__}")

    def delete(self, import_id: str) -> bool:
        """Delete an import job and its nodes/edges (cascade)."""
        job = self.db.get(KnowledgeGraphImport, import_id)
        if job is None:
            return False
        self.db.delete(job)
        self.db.flush()
        return True

    def list_nodes(
        self,
        import_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List nodes for an import with pagination."""
        count = self.db.scalar(
            select(func.count(KnowledgeGraphImportNode.id)).where(
                KnowledgeGraphImportNode.import_id == import_id
            )
        ) or 0

        nodes = list(
            self.db.scalars(
                select(KnowledgeGraphImportNode)
                .where(KnowledgeGraphImportNode.import_id == import_id)
                .order_by(KnowledgeGraphImportNode.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return [self._node_dict(node) for node in nodes], count

    def list_edges(
        self,
        import_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List edges for an import with pagination."""
        count = self.db.scalar(
            select(func.count(KnowledgeGraphImportEdge.id)).where(
                KnowledgeGraphImportEdge.import_id == import_id
            )
        ) or 0

        edges = list(
            self.db.scalars(
                select(KnowledgeGraphImportEdge)
                .where(KnowledgeGraphImportEdge.import_id == import_id)
                .order_by(KnowledgeGraphImportEdge.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return [self._edge_dict(edge) for edge in edges], count

    def update_node(
        self,
        import_id: str,
        temp_id: str,
        data: dict,
    ) -> dict | None:
        """Update a proposed node in an import job."""
        node = self.db.scalars(
            select(KnowledgeGraphImportNode).where(
                KnowledgeGraphImportNode.import_id == import_id,
                KnowledgeGraphImportNode.temp_id == temp_id,
            )
        ).first()
        if node is None:
            return None
        for key, value in data.items():
            if hasattr(node, key):
                setattr(node, key, value)
        self.db.flush()
        return self._node_dict(node)

    def update_edge(
        self,
        import_id: str,
        temp_id: str,
        data: dict,
    ) -> dict | None:
        """Update a proposed edge in an import job."""
        edge = self.db.scalars(
            select(KnowledgeGraphImportEdge).where(
                KnowledgeGraphImportEdge.import_id == import_id,
                KnowledgeGraphImportEdge.temp_id == temp_id,
            )
        ).first()
        if edge is None:
            return None
        for key, value in data.items():
            if hasattr(edge, key):
                setattr(edge, key, value)
        self.db.flush()
        return self._edge_dict(edge)

    def delete_node(self, import_id: str, temp_id: str) -> bool:
        """Delete a proposed node from an import job."""
        node = self.db.scalars(
            select(KnowledgeGraphImportNode).where(
                KnowledgeGraphImportNode.import_id == import_id,
                KnowledgeGraphImportNode.temp_id == temp_id,
            )
        ).first()
        if node is None:
            return False
        self.db.delete(node)
        self.db.flush()
        return True

    def delete_edge(self, import_id: str, temp_id: str) -> bool:
        """Delete a proposed edge from an import job."""
        edge = self.db.scalars(
            select(KnowledgeGraphImportEdge).where(
                KnowledgeGraphImportEdge.import_id == import_id,
                KnowledgeGraphImportEdge.temp_id == temp_id,
            )
        ).first()
        if edge is None:
            return False
        self.db.delete(edge)
        self.db.flush()
        return True

    def save_nodes(self, import_id: str, nodes: list[dict]) -> None:
        """Save proposed nodes for an import job."""
        for node_data in nodes:
            existing = self.db.scalars(
                select(KnowledgeGraphImportNode).where(
                    KnowledgeGraphImportNode.import_id == import_id,
                    KnowledgeGraphImportNode.temp_id == node_data["temp_id"],
                )
            ).first()
            if existing:
                for key, value in node_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                node = KnowledgeGraphImportNode(
                    import_id=import_id,
                    temp_id=node_data["temp_id"],
                    entity_id=node_data["entity_id"],
                    type=node_data["type"],
                    canonical_name=node_data["canonical_name"],
                    aliases=node_data.get("aliases", []),
                    properties=node_data.get("properties", {}),
                    evidence=node_data.get("evidence", []),
                    confidence=node_data.get("confidence", 0.5),
                    match_status=node_data.get("match_status", "new"),
                    match_candidates=node_data.get("match_candidates", []),
                    selected_entity_id=node_data.get("selected_entity_id"),
                    decision=node_data.get("decision", "pending"),
                    validation_issues=node_data.get("validation_issues", []),
                    required_properties=node_data.get("required_properties", []),
                    optional_properties=node_data.get("optional_properties", []),
                )
                self.db.add(node)
        self.db.flush()

    def save_edges(self, import_id: str, edges: list[dict]) -> None:
        """Save proposed edges for an import job."""
        for edge_data in edges:
            existing = self.db.scalars(
                select(KnowledgeGraphImportEdge).where(
                    KnowledgeGraphImportEdge.import_id == import_id,
                    KnowledgeGraphImportEdge.temp_id == edge_data["temp_id"],
                )
            ).first()
            if existing:
                for key, value in edge_data.items():
                    model_key = "relationship_type" if key == "relationship" else key
                    if hasattr(existing, model_key):
                        setattr(existing, model_key, value)
            else:
                edge = KnowledgeGraphImportEdge(
                    import_id=import_id,
                    temp_id=edge_data["temp_id"],
                    from_ref=edge_data["from_ref"],
                    relationship_type=edge_data["relationship"],
                    to_ref=edge_data["to_ref"],
                    recommendations=edge_data.get("recommendations", []),
                    source=edge_data.get("source", ""),
                    evidence=edge_data.get("evidence", []),
                    confidence=edge_data.get("confidence", 0.5),
                    match_status=edge_data.get("match_status", "new"),
                    decision=edge_data.get("decision", "pending"),
                    validation_issues=edge_data.get("validation_issues", []),
                )
                self.db.add(edge)
        self.db.flush()

    def _summary_dict(self, job: KnowledgeGraphImport) -> dict:
        """Convert to summary dict (no nodes/edges)."""
        return {
            "id": job.id,
            "source_label": job.source_label,
            "source_url": job.source_url,
            "status": job.status,
            "node_count": job.node_count,
            "edge_count": job.edge_count,
            "issue_count": job.issue_count,
            "created_at": job.created_at.isoformat() if job.created_at else "",
            "applied_at": job.applied_at.isoformat() if job.applied_at else None,
            "error_message": job.error_message,
        }

    def _meta_dict(self, job: KnowledgeGraphImport) -> dict:
        """Convert to meta dict (summary + provenance)."""
        return {
            **self._summary_dict(job),
            "source_content": job.source_content,
            "schema_version": job.schema_version,
            "ontology_version": job.ontology_version,
            "dataset_hash": job.dataset_hash,
            "warnings": job.warnings or [],
        }

    def _job_dict(self, job: KnowledgeGraphImport) -> dict:
        """Convert to full job dict with nodes and edges."""
        nodes = list(
            self.db.scalars(
                select(KnowledgeGraphImportNode).where(
                    KnowledgeGraphImportNode.import_id == job.id
                )
            )
        )
        edges = list(
            self.db.scalars(
                select(KnowledgeGraphImportEdge).where(
                    KnowledgeGraphImportEdge.import_id == job.id
                )
            )
        )
        return {
            **self._meta_dict(job),
            "nodes": [self._node_dict(n) for n in nodes],
            "edges": [self._edge_dict(e) for e in edges],
        }

    def _node_dict(self, node: KnowledgeGraphImportNode) -> dict:
        """Convert node to dict."""
        return {
            "temp_id": node.temp_id,
            "entity_id": node.entity_id,
            "type": node.type,
            "canonical_name": node.canonical_name,
            "aliases": node.aliases or [],
            "properties": node.properties or {},
            "evidence": node.evidence or [],
            "confidence": node.confidence,
            "match_status": node.match_status,
            "match_candidates": node.match_candidates or [],
            "selected_entity_id": node.selected_entity_id,
            "decision": node.decision,
            "validation_issues": node.validation_issues or [],
            "required_properties": node.required_properties or [],
            "optional_properties": node.optional_properties or [],
        }

    def _edge_dict(self, edge: KnowledgeGraphImportEdge) -> dict:
        """Convert edge to dict."""
        return {
            "temp_id": edge.temp_id,
            "from_ref": edge.from_ref,
            "relationship": edge.relationship_type,
            "to_ref": edge.to_ref,
            "recommendations": edge.recommendations or [],
            "source": edge.source,
            "evidence": edge.evidence or [],
            "confidence": edge.confidence,
            "match_status": edge.match_status,
            "decision": edge.decision,
            "validation_issues": edge.validation_issues or [],
        }
