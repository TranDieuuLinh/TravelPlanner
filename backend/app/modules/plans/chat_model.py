from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


PROCESSING_TURN_STATUSES = frozenset({"classifying", "executing"})
ACTIVE_TURN_STATUSES = frozenset(
    {"queued", "classifying", "executing", "awaiting_confirmation"}
)


class TripChat(Base):
    __tablename__ = "trip_chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    current_explorer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latest_explorer_timing: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latest_planner_timing: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    current_intake_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversation_phase: Mapped[str] = mapped_column(String(32), default="discovery", nullable=False)
    conversation_context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active_pending_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
        index=True,
    )

    messages: Mapped[list["TripChatMessage"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="TripChatMessage.sequence",
    )
    plan_revisions: Mapped[list["TripChatPlanRevision"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="TripChatPlanRevision.revision",
    )
    turns: Mapped[list["TripChatTurn"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="TripChatTurn.created_at",
    )


class TripChatMessage(Base):
    __tablename__ = "trip_chat_messages"
    __table_args__ = (
        UniqueConstraint("chat_id", "sequence", name="uq_trip_chat_message_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_id: Mapped[str] = mapped_column(
        ForeignKey("trip_chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    attachment_names: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    plan_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    message_kind: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    content_blocks: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chat: Mapped[TripChat] = relationship(back_populates="messages")


class TripChatPlanRevision(Base):
    __tablename__ = "trip_chat_plan_revisions"
    __table_args__ = (
        UniqueConstraint("chat_id", "revision", name="uq_trip_chat_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_id: Mapped[str] = mapped_column(
        ForeignKey("trip_chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    intake_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    plan_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    explorer_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chat: Mapped[TripChat] = relationship(back_populates="plan_revisions")


class TripChatTurn(Base):
    __tablename__ = "trip_chat_turns"
    __table_args__ = (
        UniqueConstraint("chat_id", "client_turn_id", name="uq_trip_chat_turn_client_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_id: Mapped[str] = mapped_column(
        ForeignKey("trip_chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_turn_id: Mapped[str] = mapped_column(String(72), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_names: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    proposed_operations: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    assistant_blocks: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    chat: Mapped[TripChat] = relationship(back_populates="turns")

    @property
    def plan_revision(self) -> int | None:
        return self.result_summary.get("planRevision")
