from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
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


class Place(Base):
    __tablename__ = "places"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    place_type: Mapped[str] = mapped_column(String(64), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(160), nullable=True)
    country: Mapped[str | None] = mapped_column(String(160), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    region_key: Mapped[str] = mapped_column(String(160), nullable=False)
    primary_area: Mapped[str | None] = mapped_column(String(160), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="unverified",
    )
    opening_hours: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    typical_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_confidence: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="low",
    )
    source_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revision: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="1",
    )
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PlaceRegionSnapshot(Base):
    __tablename__ = "place_region_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "region_key",
            "catalog_version",
            "algorithm_version",
            name="uq_place_region_snapshot_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    region_key: Mapped[str] = mapped_column(String(160), nullable=False)
    catalog_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    place_count: Mapped[int] = mapped_column(Integer, nullable=False)
    active_place_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_max_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metrics_json: Mapped[dict] = mapped_column(
        "metrics",
        JSON,
        nullable=False,
        default=dict,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PlaceRegionCatalogState(Base):
    __tablename__ = "place_region_catalog_state"

    region_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    catalog_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    current_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("place_region_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    dirty_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refresh_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
    )
    refresh_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Festival(Base):
    __tablename__ = "festivals"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_festival_source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    venue: Mapped[str | None] = mapped_column(String(512), nullable=True)
    scale_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="dia-phuong",
    )
    timing: Mapped[str | None] = mapped_column(String(255), nullable=True)
    province: Mapped[str | None] = mapped_column(String(160), nullable=True)
    district: Mapped[str | None] = mapped_column(String(160), nullable=True)
    deity: Mapped[str | None] = mapped_column(Text, nullable=True)
    ceremony_part: Mapped[str | None] = mapped_column(Text, nullable=True)
    festival_part: Mapped[str | None] = mapped_column(Text, nullable=True)
    festival_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    documentation: Mapped[str | None] = mapped_column(Text, nullable=True)
    protection_measure: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_time: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recurrence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    listed_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
