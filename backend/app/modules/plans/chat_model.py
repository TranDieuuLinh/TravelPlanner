from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


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
    current_intake_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    plan_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    explorer_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chat: Mapped[TripChat] = relationship(back_populates="plan_revisions")
