"""SQLAlchemy models for Knowledge Graph persistence."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    pass


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class KnowledgeEntity(Base):
    """Canonical knowledge graph entities."""

    __tablename__ = "knowledge_entities"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    aliases: Mapped[list[KnowledgeAlias]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    properties: Mapped[list[KnowledgeProperty]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    outgoing_relationships: Mapped[list[KnowledgeRelationship]] = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.from_entity_id",
        back_populates="from_entity",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list[KnowledgeRelationship]] = relationship(
        "KnowledgeRelationship",
        foreign_keys="KnowledgeRelationship.to_entity_id",
        back_populates="to_entity",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_knowledge_entities_normalized_type", "normalized_name", "entity_type"),
    )


class KnowledgeAlias(Base):
    """Aliases for knowledge entities."""

    __tablename__ = "knowledge_aliases"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)

    entity: Mapped[KnowledgeEntity] = relationship("KnowledgeEntity", back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("entity_id", "alias", name="uq_knowledge_aliases_entity_alias"),
        Index("ix_knowledge_aliases_normalized", "normalized_alias"),
    )


class KnowledgeProperty(Base):
    """Properties associated with knowledge entities."""

    __tablename__ = "knowledge_properties"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    entity: Mapped[KnowledgeEntity] = relationship("KnowledgeEntity", back_populates="properties")

    __table_args__ = (
        UniqueConstraint("entity_id", "key", name="uq_knowledge_properties_entity_key"),
    )


class KnowledgeRelationship(Base):
    """Relationships between knowledge entities."""

    __tablename__ = "knowledge_relationships"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    from_entity_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    to_entity_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    from_entity: Mapped[KnowledgeEntity] = relationship(
        "KnowledgeEntity",
        back_populates="outgoing_relationships",
        foreign_keys=[from_entity_id],
    )
    to_entity: Mapped[KnowledgeEntity] = relationship(
        "KnowledgeEntity",
        back_populates="incoming_relationships",
        foreign_keys=[to_entity_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "from_entity_id", "relationship_type", "to_entity_id",
            name="uq_knowledge_relationships_edge"
        ),
        Index("ix_knowledge_relationships_from_to", "from_entity_id", "to_entity_id"),
    )


class KnowledgeGraphImport(Base):
    """AI import job metadata."""

    __tablename__ = "knowledge_graph_imports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="extracting", index=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    warnings: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    node_count: Mapped[int] = mapped_column(nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(nullable=False, default=0)
    issue_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(nullable=True)
    applied_dataset_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    nodes: Mapped[list[KnowledgeGraphImportNode]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan"
    )
    edges: Mapped[list[KnowledgeGraphImportEdge]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan"
    )


class KnowledgeGraphImportNode(Base):
    """Proposed node from an AI import."""

    __tablename__ = "knowledge_graph_import_nodes"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    import_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_graph_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    temp_id: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(96), nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.5)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    match_candidates: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    selected_entity_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    validation_issues: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    required_properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    optional_properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    import_job: Mapped[KnowledgeGraphImport] = relationship(
        "KnowledgeGraphImport", back_populates="nodes"
    )

    __table_args__ = (
        UniqueConstraint("import_id", "temp_id", name="uq_kg_import_nodes"),
        Index("ix_kg_import_nodes_import_temp", "import_id", "temp_id"),
    )


class KnowledgeGraphImportEdge(Base):
    """Proposed edge from an AI import."""

    __tablename__ = "knowledge_graph_import_edges"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    import_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_graph_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    temp_id: Mapped[str] = mapped_column(String(80), nullable=False)
    from_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False)
    to_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    recommendations: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.5)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    validation_issues: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    import_job: Mapped[KnowledgeGraphImport] = relationship(
        "KnowledgeGraphImport", back_populates="edges"
    )

    __table_args__ = (
        UniqueConstraint("import_id", "temp_id", name="uq_kg_import_edges"),
        Index("ix_kg_import_edges_import_temp", "import_id", "temp_id"),
    )
