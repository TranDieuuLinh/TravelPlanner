from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TripIntentVersion(Base):
    __tablename__ = "trip_intent_versions"
    __table_args__ = (
        UniqueConstraint(
            "chat_id", "revision", name="uq_trip_intent_chat_revision"
        ),
        Index("ix_trip_intent_chat_revision", "chat_id", "revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_id: Mapped[str] = mapped_column(
        ForeignKey("trip_chats.id", ondelete="CASCADE"), nullable=False
    )
    intake_id: Mapped[str | None] = mapped_column(
        ForeignKey("explorer_intakes.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    date_flexibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown"
    )

    party_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="solo"
    )
    adults: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    children: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    infants: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rooms: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    budget_amount: Mapped[int | None] = mapped_column(Numeric(16, 0), nullable=True)
    budget_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="VND"
    )
    budget_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium"
    )

    travel_style: Mapped[str] = mapped_column(
        String(64), nullable=False, default="local"
    )
    pace: Mapped[str] = mapped_column(
        String(16), nullable=False, default="balanced"
    )
    accommodation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    hotel_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    check_in_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    check_out_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    transport_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    include_between_places: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    include_arrival_departure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    geographic_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unrestricted"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    values: Mapped[list["TripIntentValue"]] = relationship(
        cascade="all, delete-orphan", order_by="TripIntentValue.position"
    )
    destination_stays: Mapped[list["TripIntentDestinationStay"]] = relationship(
        cascade="all, delete-orphan",
        order_by="TripIntentDestinationStay.position",
    )


class TripIntentValue(Base):
    __tablename__ = "trip_intent_values"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('note','interest','must_visit','avoid_place','constraint',"
            "'excluded_place_type','accommodation_preference','preferred_transport',"
            "'avoided_transport','clarifying_question')",
            name="ck_trip_intent_value_kind",
        ),
        UniqueConstraint(
            "trip_intent_id", "kind", "position", name="uq_trip_intent_value_position"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_intent_id: Mapped[str] = mapped_column(
        ForeignKey("trip_intent_versions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class TripIntentDestinationStay(Base):
    __tablename__ = "trip_intent_destination_stays"
    __table_args__ = (
        UniqueConstraint(
            "trip_intent_id",
            "position",
            name="uq_trip_intent_destination_stay_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trip_intent_id: Mapped[str] = mapped_column(
        ForeignKey("trip_intent_versions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    start_day: Mapped[int] = mapped_column(Integer, nullable=False)
    end_day: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
