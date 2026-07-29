from __future__ import annotations

from datetime import datetime, timezone

from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
    PreferenceAggregate,
    PreferenceDimension,
    PreferenceSignal,
    PreferenceSnapshot,
)


class PreferenceLearningService:
    minimum_persist_confidence = 0.35

    def enrich_snapshot(
        self,
        snapshot: PreferenceSnapshot,
        *,
        destination: str,
        candidates: list,
        interests: list[str],
    ) -> PreferenceSnapshot:
        signals = list(snapshot.signals)
        for interest in interests:
            signals.append(
                PreferenceSignal(
                    dimension=PreferenceDimension.category,
                    value=interest,
                    score=0.65,
                    confidence=0.7,
                    scope="destination",
                    destination=destination,
                    sourceTypes=["explorer_intent"],
                )
            )
        for candidate in candidates:
            source_types = list(
                dict.fromkeys(source.type.value for source in candidate.sources)
            )
            confidence = max(0.2, min(float(candidate.confidence), 0.9))
            source_strength = (
                0.7
                if "user_prompt" in source_types
                else 0.45
                if "ocr" in source_types
                else 0.3
            )
            if candidate.category.value != "other":
                signals.append(
                    PreferenceSignal(
                        dimension=PreferenceDimension.category,
                        value=candidate.category.value,
                        score=source_strength,
                        confidence=confidence,
                        scope="destination",
                        destination=destination,
                        sourceTypes=source_types,
                    )
                )
            for attribute in candidate.attributes:
                signals.append(
                    PreferenceSignal(
                        dimension=PreferenceDimension.attribute,
                        value=attribute,
                        score=max(0.2, source_strength - 0.1),
                        confidence=confidence,
                        scope="destination",
                        destination=destination,
                        sourceTypes=source_types,
                    )
                )
        return snapshot.model_copy(
            update={"signals": self._deduplicate(signals)}
        )

    def merge(
        self,
        stored: object,
        snapshot: PreferenceSnapshot,
    ) -> LongTermPreferenceProfile:
        profile = LongTermPreferenceProfile.from_storage(stored).model_copy(
            deep=True
        )
        now = datetime.now(timezone.utc)
        persisted_count = 0
        for signal in snapshot.signals:
            if signal.confidence < self.minimum_persist_confidence:
                continue
            current = profile.scores.get(signal.key)
            source_types = list(
                dict.fromkeys(
                    [
                        *(current.source_types if current else []),
                        *signal.source_types,
                    ]
                )
            )
            signal_weight = max(0.05, abs(signal.score) * signal.confidence)
            if current is None:
                aggregate = PreferenceAggregate(
                    score=signal.score,
                    confidence=min(0.95, signal.confidence * 0.65),
                    observations=1,
                    sourceTypes=source_types,
                    lastObservedAt=now,
                )
            else:
                current_weight = max(
                    0.05,
                    current.confidence * min(current.observations, 8),
                )
                aggregate = PreferenceAggregate(
                    score=(
                        current.score * current_weight
                        + signal.score * signal_weight
                    )
                    / (current_weight + signal_weight),
                    confidence=min(
                        0.98,
                        1
                        - (1 - current.confidence)
                        * (1 - signal.confidence * 0.35),
                    ),
                    observations=current.observations + 1,
                    sourceTypes=source_types,
                    lastObservedAt=now,
                )
            profile.scores[signal.key] = aggregate
            persisted_count += 1
        profile.observation_count += persisted_count
        profile.updated_at = now
        return profile

    def effective_snapshot(
        self,
        snapshot: PreferenceSnapshot,
        stored: object,
    ) -> PreferenceSnapshot:
        profile = self.merge(stored, snapshot)
        return snapshot.model_copy(update={"effective_profile": profile})

    def _deduplicate(
        self,
        signals: list[PreferenceSignal],
    ) -> list[PreferenceSignal]:
        merged: dict[tuple[str, str, str, str | None], PreferenceSignal] = {}
        order: list[tuple[str, str, str, str | None]] = []
        for signal in signals:
            key = (
                signal.dimension.value,
                signal.value,
                signal.scope,
                signal.destination,
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = signal
                order.append(key)
                continue
            preferred = (
                signal
                if abs(signal.score) * signal.confidence
                > abs(existing.score) * existing.confidence
                else existing
            )
            merged[key] = preferred.model_copy(
                update={
                    "source_types": list(
                        dict.fromkeys(
                            [*existing.source_types, *signal.source_types]
                        )
                    )
                }
            )
        return [merged[key] for key in order]
