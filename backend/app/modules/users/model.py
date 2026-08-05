from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="traveler", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    traveler_profile_record: Mapped["TravelerProfile | None"] = relationship(
        "TravelerProfile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    creator_status: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    creator_portfolio_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def travel_preferences(self) -> dict:
        """Compatibility projection for API serialization, never JSON storage."""
        from app.modules.preferences.schema import (
            LongTermPreferenceProfile,
            PreferenceAggregate,
        )

        record = self.traveler_profile_record
        if record is None:
            return LongTermPreferenceProfile().model_dump(mode="json", by_alias=True)
        return LongTermPreferenceProfile(
            version=record.version,
            explicit=[
                signal.label
                for signal in record.signals
                if signal.dimension == "explicit" and signal.status == "active"
            ],
            scores={
                f"{signal.dimension}:{signal.value}": PreferenceAggregate(
                    score=signal.score,
                    confidence=signal.confidence,
                    observations=signal.observations,
                    origin=signal.origin,
                    sourceTypes=[source.source_type for source in signal.sources],
                    lastObservedAt=signal.last_observed_at,
                )
                for signal in record.signals
                if signal.dimension != "explicit" and signal.status == "active"
            },
            observationCount=record.observation_count,
            updatedAt=record.updated_at,
        ).model_dump(mode="json", by_alias=True)


from app.modules.preferences.model import TravelerProfile  # noqa: E402
