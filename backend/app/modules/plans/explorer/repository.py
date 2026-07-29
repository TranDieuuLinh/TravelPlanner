from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.model import UserMustPlace
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
                    sources_json=[
                        source.model_dump(mode="json")
                        for source in candidate.sources
                    ],
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
                )
            )
        self.session.commit()

    def load_must_places(
        self,
        intake_id: str,
        user_id: str | None,
    ) -> list[SelectedPlaceCreate]:
        rows = self.session.scalars(
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
        ).all()
        return [
            SelectedPlaceCreate(
                name=must_place.resolved_name,
                priority=1,
                mustVisit=True,
                regionKey=normalize_region_key(
                    must_place.city or must_place.destination
                ),
                tags=[must_place.category],
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
                notes=must_place.notes,
            )
            for must_place in rows
        ]


def _candidate_key(name: str, destination: str) -> str:
    return f"{_slug(destination)}:{_slug(name)}"


def _slug(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "-", without_marks).strip("-") or "unknown"
