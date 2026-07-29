from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    intake_id: Mapped[str] = mapped_column(String(36), nullable=False)
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
