from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TravelGroup(Base):
    __tablename__ = "travel_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), unique=True, index=True, nullable=False)
    country_name: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    photo_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), default="public", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TravelGroupMembership(Base):
    __tablename__ = "travel_group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_travel_group_memberships_group_user"),
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("travel_groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TravelGroupPost(Base):
    __tablename__ = "travel_group_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("travel_groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
