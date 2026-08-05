from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.modules.preferences.model import (
    TravelerPreferenceSignal,
    TravelerPreferenceSignalSource,
    TravelerProfile,
)
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
    PreferenceAggregate,
)


class TravelerProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_record(self, user_id: int) -> TravelerProfile | None:
        return self.db.scalar(
            select(TravelerProfile)
            .options(
                selectinload(TravelerProfile.signals).selectinload(
                    TravelerPreferenceSignal.sources
                )
            )
            .where(TravelerProfile.user_id == user_id)
        )

    def get(self, user_id: int) -> LongTermPreferenceProfile:
        record = self.get_record(user_id)
        if record is None:
            return LongTermPreferenceProfile()
        explicit = [
            signal.label
            for signal in record.signals
            if signal.dimension == "explicit" and signal.status == "active"
        ]
        scores = {
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
        }
        return LongTermPreferenceProfile(
            version=record.version,
            explicit=explicit,
            scores=scores,
            observationCount=record.observation_count,
            updatedAt=record.updated_at,
        )

    def save(
        self,
        user_id: int,
        profile: LongTermPreferenceProfile,
        *,
        evidence_intake_id: str | None = None,
    ) -> LongTermPreferenceProfile:
        record = self.get_record(user_id)
        if record is None:
            record = TravelerProfile(user_id=user_id)
            self.db.add(record)
            self.db.flush()

        record.version = profile.version
        record.observation_count = profile.observation_count
        now = datetime.now(timezone.utc)
        existing = {
            (signal.dimension, signal.value, signal.scope, signal.destination): signal
            for signal in record.signals
        }
        retained: set[tuple[str, str, str, str]] = set()

        for position, label in enumerate(profile.explicit):
            value = _normalize(label)
            if not value:
                continue
            signal = existing.get(("explicit", value, "global", ""))
            if signal is None:
                signal = TravelerPreferenceSignal(
                    user_id=user_id,
                    dimension="explicit",
                    value=value,
                    label=label.strip(),
                    score=1.0,
                    confidence=1.0,
                    observations=1,
                    position=position,
                    scope="global",
                    destination="",
                    origin="explicit",
                    status="active",
                    first_observed_at=now,
                    last_observed_at=now,
                )
                record.signals.append(signal)
            else:
                signal.label = label.strip()
                signal.position = position
                signal.status = "active"
            retained.add(("explicit", value, "global", ""))

        for key, aggregate in profile.scores.items():
            dimension, separator, value = key.partition(":")
            if not separator or not value:
                continue
            identity = (dimension, value, "global", "")
            signal = existing.get(identity)
            if signal is None:
                signal = TravelerPreferenceSignal(
                    user_id=user_id,
                    dimension=dimension,
                    value=value,
                    label=value.replace("_", " "),
                    score=aggregate.score,
                    confidence=aggregate.confidence,
                    observations=aggregate.observations,
                    position=0,
                    scope="global",
                    destination="",
                    origin=aggregate.origin,
                    status="active",
                    first_observed_at=aggregate.last_observed_at or now,
                    last_observed_at=aggregate.last_observed_at or now,
                )
                record.signals.append(signal)
            else:
                signal.score = aggregate.score
                signal.confidence = aggregate.confidence
                signal.observations = aggregate.observations
                signal.origin = aggregate.origin
                signal.status = "active"
                signal.last_observed_at = aggregate.last_observed_at or now
            if evidence_intake_id is not None:
                signal.last_evidence_intake_id = evidence_intake_id
            signal.sources = [
                TravelerPreferenceSignalSource(source_type=source)
                for source in dict.fromkeys(aggregate.source_types)
            ]
            retained.add(identity)

        for signal in list(record.signals):
            identity = (
                signal.dimension,
                signal.value,
                signal.scope,
                signal.destination,
            )
            if identity not in retained:
                self.db.delete(signal)
        record.updated_at = profile.updated_at or now
        self.db.flush()
        self.db.expire(record, ["signals"])
        return self.get(user_id)

    def replace_explicit(self, user_id: int, values: list[str]) -> LongTermPreferenceProfile:
        profile = self.get(user_id).model_copy(update={"explicit": values})
        return self.save(user_id, profile)

    def delete(self, user_id: int) -> None:
        self.db.execute(
            delete(TravelerProfile).where(TravelerProfile.user_id == user_id)
        )
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()


def _normalize(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")
