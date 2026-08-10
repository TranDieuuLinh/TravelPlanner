"""Provenance-aware controlled tags for Knowledge Graph entities."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class KnowledgeTag(Base):
    __tablename__ = "knowledge_tags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tag_group: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name_vi: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    applicable_entity_types: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeTagRun(Base):
    __tablename__ = "knowledge_tag_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    processed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    tagged_count: Mapped[int] = mapped_column(nullable=False, default=0)
    no_evidence_count: Mapped[int] = mapped_column(nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class KnowledgeEntityTagAssertion(Base):
    __tablename__ = "knowledge_entity_tag_assertions"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(
        String(96),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("knowledge_tags.key", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    inference_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("knowledge_tag_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "entity_id", "tag_key", "source", name="uq_knowledge_entity_tag_assertion"
        ),
        Index(
            "ix_knowledge_entity_tag_effective",
            "entity_id",
            "status",
            "confidence",
        ),
    )


class KnowledgeTagScanResult(Base):
    __tablename__ = "knowledge_tag_scan_results"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("knowledge_tag_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(
        String(96),
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    assertion_count: Mapped[int] = mapped_column(nullable=False, default=0)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("run_id", "entity_id", name="uq_knowledge_tag_scan_run_entity"),
    )
