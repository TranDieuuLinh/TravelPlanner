from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExplorerIntake(Base):
    __tablename__ = "explorer_intakes"
    __table_args__ = (
        Index(
            "ix_explorer_intakes_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class YouTubeTranscriptCacheEntry(Base):
    __tablename__ = "youtube_transcript_cache"
    __table_args__ = (
        Index(
            "ix_youtube_transcript_cache_video_fetched",
            "video_id",
            "fetched_at",
        ),
    )

    video_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    language: Mapped[str] = mapped_column(String(32), primary_key=True)
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    is_generated: Mapped[bool | None] = mapped_column(nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserMustPlace(Base):
    __tablename__ = "user_must_place"
    __table_args__ = (
        UniqueConstraint(
            "intake_id",
            "candidate_key",
            name="uq_user_must_place_intake_candidate",
        ),
        Index(
            "ix_user_must_place_intake_user",
            "intake_id",
            "user_id",
        ),
        UniqueConstraint(
            "source_url",
            "candidate_key",
            name="uq_user_must_place_source_candidate",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Legacy ownership columns are retained during the compatibility window.
    # New reads use UserMustPlaceUser so one shared extraction can belong to
    # many users/intakes without being deleted with the first intake.
    intake_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    address_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    primary_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sources_json: Mapped[list[dict]] = mapped_column(
        "sources",
        JSON,
        nullable=False,
        default=list,
    )
    attributes_json: Mapped[list[str]] = mapped_column(
        "attributes",
        JSON,
        nullable=False,
        default=list,
    )
    source_evidence_json: Mapped[dict[str, str]] = mapped_column(
        "source_evidence",
        JSON,
        nullable=False,
        default=dict,
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        server_default="0",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_confidence: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="low",
    )
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="unresolved",
    )
    resolution_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    # Place-shaped shared snapshot. Nullable fields are expected when neither
    # the catalog nor the external resolver supplies the value.
    place_id: Mapped[str | None] = mapped_column(
        ForeignKey("places.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    place_type: Mapped[str | None] = mapped_column(String(96), nullable=True)
    region_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opening_hours: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=list
    )
    typical_duration_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    source_platform: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    source_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    plus_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revision: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1"
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    preference_level: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="preferred",
    )
    source_order: Mapped[int | None] = mapped_column(nullable=True)
    source_day: Mapped[int | None] = mapped_column(nullable=True)
    source_time_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_duration_minutes: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserMustPlaceUser(Base):
    """Many-to-many link between a shared URL/place extraction and users."""

    __tablename__ = "user_must_place_users"
    __table_args__ = (
        UniqueConstraint(
            "intake_id",
            "user_must_place_id",
            name="uq_user_must_place_users_intake_place",
        ),
        Index("ix_user_must_place_users_user", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_must_place_id: Mapped[str] = mapped_column(
        ForeignKey("user_must_place.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    intake_id: Mapped[str] = mapped_column(
        ForeignKey("explorer_intakes.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UrlExtractionCacheEntry(Base):
    """Provider-neutral normalized URL extraction shared by all users."""

    __tablename__ = "url_extraction_cache"

    source_url: Mapped[str] = mapped_column(Text, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_context_json: Mapped[dict] = mapped_column(
        "extracted_context", JSON, nullable=False, default=dict
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now()
    )
