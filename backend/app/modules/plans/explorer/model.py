from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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


class SourceDocument(Base):
    """Shared URL source, retained artifacts and versioned derived extraction."""

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "canonical_url", name="uq_source_documents_canonical_url"
        ),
        Index(
            "ix_source_documents_platform_fetched",
            "platform",
            "fetched_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    artifacts_json: Mapped[dict] = mapped_column(
        "artifacts", JSON, nullable=False, default=dict
    )
    extracted_context_json: Mapped[dict] = mapped_column(
        "extracted_context", JSON, nullable=False, default=dict
    )
    artifact_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extractor_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DestinationRegionStory(Base):
    """Curated destination guidance projected into immutable plan snapshots."""

    __tablename__ = "destination_region_stories"
    __table_args__ = (
        CheckConstraint(
            "story_type LIKE 'destination_%'",
            name="ck_destination_region_stories_type",
        ),
        UniqueConstraint(
            "region_key",
            "story_type",
            "source_url",
            name="uq_destination_region_stories_source",
        ),
        Index(
            "ix_destination_region_stories_region_active_order",
            "region_key",
            "is_active",
            "sort_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    region_key: Mapped[str] = mapped_column(String(128), nullable=False)
    story_type: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_types_json: Mapped[list[str]] = mapped_column(
        "evidence_types", JSON, nullable=False, default=list
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
