from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.model import UserMustPlace
from app.modules.plans.explorer.place_policy import (
    concise_source_activity,
    is_schedulable_place,
)
from app.modules.plans.planner.region_context import normalize_region_key
from app.modules.plans.schema import SelectedPlaceCreate


class ExplorerPersistenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(
        self,
        *,
        intake_id: str,
        user_id: str | None,
        destination: str,
        resolutions: list[PlaceResolution],
    ) -> None:
        for resolution in resolutions:
            candidate = resolution.candidate
            self.session.add(
                UserMustPlace(
                    id=str(uuid4()),
                    intake_id=intake_id,
                    user_id=user_id,
                    destination=destination,
                    candidate_key=_candidate_key(
                        candidate.name,
                        destination,
                    ),
                    candidate_name=candidate.name,
                    category=candidate.category.value,
                    address_hint=candidate.address_hint,
                    search_region=candidate.search_region,
                    sources_json=[
                        source.model_dump(mode="json")
                        for source in candidate.sources
                    ],
                    attributes_json=list(candidate.attributes),
                    source_evidence_json=dict(candidate.source_evidence),
                    confidence=Decimal(str(candidate.confidence)),
                    notes=candidate.notes,
                    resolved_name=resolution.name,
                    address=resolution.address,
                    city=resolution.city,
                    country=resolution.country,
                    country_code=resolution.country_code,
                    primary_area=resolution.primary_area,
                    latitude=resolution.latitude,
                    longitude=resolution.longitude,
                    description=resolution.description,
                    provider=resolution.provider,
                    external_id=resolution.external_id,
                    data_confidence=resolution.data_confidence,
                    fetched_at=resolution.fetched_at,
                    attribution=resolution.attribution,
                    resolution_status=resolution.status,
                    resolution_reason=resolution.resolution_reason,
                    preference_level=candidate.preference_level.value,
                    source_order=candidate.source_order,
                    source_day=candidate.source_day,
                    source_time_hint=candidate.source_time_hint,
                    source_activity=candidate.source_activity,
                    source_duration_minutes=candidate.source_duration_minutes,
                )
            )
        self.session.commit()

    def load_must_places(
        self,
        intake_id: str,
        user_id: str | None,
    ) -> list[SelectedPlaceCreate]:
        rows = list(self.session.scalars(
            select(UserMustPlace)
            .where(
                UserMustPlace.intake_id == intake_id,
                (
                    UserMustPlace.user_id == user_id
                    if user_id is not None
                    else UserMustPlace.user_id.is_(None)
                ),
            )
            .order_by(UserMustPlace.created_at, UserMustPlace.id)
        ).all())
        rows.sort(
            key=lambda row: (
                row.source_order is None,
                row.source_order or 10_000,
                row.created_at,
                row.id,
            )
        )
        return [
            SelectedPlaceCreate(
                # Preserve the source label in URL itineraries. Provider
                # resolution contributes coordinates/address, but a broad
                # match such as "Hà Nội" must not replace "Văn Miếu" in the
                # plan or collapse two distinct source stops.
                name=(
                    must_place.candidate_name
                    if must_place.source_order is not None
                    else must_place.resolved_name
                ),
                address=must_place.address,
                priority=_priority_from_confidence(must_place.confidence),
                mustVisit=must_place.preference_level == "must_visit",
                preferenceLevel=must_place.preference_level,
                regionKey=normalize_region_key(
                    must_place.city or must_place.destination
                ),
                tags=list(
                    dict.fromkeys(
                        [must_place.category, *(must_place.attributes_json or [])]
                    )
                ),
                latitude=(
                    float(must_place.latitude)
                    if must_place.latitude is not None
                    else None
                ),
                longitude=(
                    float(must_place.longitude)
                    if must_place.longitude is not None
                    else None
                ),
                sourceRefs=[
                    source.get("url") or source.get("type", "unknown")
                    for source in (must_place.sources_json or [])
                ],
                # Extraction evidence is retained on UserMustPlace for
                # provenance, but raw captions are not user-facing plan notes.
                notes=must_place.description,
                sourceOrder=must_place.source_order,
                sourceDay=must_place.source_day,
                sourceTimeHint=must_place.source_time_hint,
                sourceActivity=concise_source_activity(
                    must_place.source_activity
                ),
                sourceDurationMinutes=must_place.source_duration_minutes,
            )
            for must_place in rows
            if _is_schedulable_must_place(must_place)
        ]


def _candidate_key(name: str, destination: str) -> str:
    return f"{_slug(destination)}:{_slug(name)}"


def _is_schedulable_must_place(must_place: UserMustPlace) -> bool:
    is_url_source = any(
        source.get("type") == "url" and source.get("url")
        for source in (must_place.sources_json or [])
    )
    return is_schedulable_place(
        is_url_source=is_url_source,
        resolution_status=must_place.resolution_status,
        latitude=must_place.latitude,
        longitude=must_place.longitude,
        resolved_name=must_place.resolved_name,
        city=must_place.city,
        destination=must_place.destination,
        country=must_place.country,
    )


def _priority_from_confidence(confidence: Decimal) -> int:
    value = float(confidence)
    if value >= 0.85:
        return 1
    if value >= 0.7:
        return 2
    if value >= 0.5:
        return 3
    return 4


def _slug(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "-", without_marks).strip("-") or "unknown"
