from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TravelerProfile(Base):
    __tablename__ = "traveler_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    observation_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    signals: Mapped[list["TravelerPreferenceSignal"]] = relationship(
        cascade="all, delete-orphan",
        order_by=(
            "TravelerPreferenceSignal.origin, TravelerPreferenceSignal.position, "
            "TravelerPreferenceSignal.dimension, TravelerPreferenceSignal.value"
        ),
    )


class TravelerPreferenceSignal(Base):
    __tablename__ = "traveler_preference_signals"
    __table_args__ = (
        CheckConstraint("score >= -1 AND score <= 1", name="ck_traveler_signal_score"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_traveler_signal_confidence",
        ),
        CheckConstraint(
            "scope IN ('global','destination')", name="ck_traveler_signal_scope"
        ),
        CheckConstraint(
            "origin IN ('explicit','inferred')", name="ck_traveler_signal_origin"
        ),
        CheckConstraint(
            "status IN ('active','rejected')", name="ck_traveler_signal_status"
        ),
        UniqueConstraint(
            "user_id",
            "dimension",
            "value",
            "scope",
            "destination",
            name="uq_traveler_signal_identity",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("traveler_profiles.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observations: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), default="global", nullable=False)
    destination: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_evidence_intake_id: Mapped[str | None] = mapped_column(
        ForeignKey("explorer_intakes.id", ondelete="SET NULL"), nullable=True
    )

    sources: Mapped[list["TravelerPreferenceSignalSource"]] = relationship(
        cascade="all, delete-orphan",
        order_by="TravelerPreferenceSignalSource.source_type",
    )


class TravelerPreferenceSignalSource(Base):
    __tablename__ = "traveler_preference_signal_sources"

    signal_id: Mapped[str] = mapped_column(
        ForeignKey("traveler_preference_signals.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_type: Mapped[str] = mapped_column(String(40), primary_key=True)
