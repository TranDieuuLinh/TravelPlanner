from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.modules.places.model import Place
from app.modules.places.repository import SqlAlchemyPlaceRepository


@dataclass(frozen=True)
class PlaceCreate:
    id: str
    name: str
    place_type: str
    region_key: str
    address: str | None = None
    city: str | None = None
    country: str | None = None
    country_code: str | None = None
    primary_area: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    status: str = "unverified"
    opening_hours: list[dict[str, Any]] = field(default_factory=list)
    typical_duration_minutes: int | None = None
    data_confidence: str = "low"
    source_fetched_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PlaceCatalogService:
    MUTABLE_FIELDS = {
        "name",
        "place_type",
        "region_key",
        "address",
        "city",
        "country",
        "country_code",
        "primary_area",
        "latitude",
        "longitude",
        "status",
        "opening_hours",
        "typical_duration_minutes",
        "data_confidence",
        "source_fetched_at",
        "metadata",
        "deleted_at",
    }

    def __init__(self, repository: SqlAlchemyPlaceRepository) -> None:
        self.repository = repository

    def create_place(self, payload: PlaceCreate) -> Place:
        if self.repository.get(payload.id) is not None:
            raise ValueError(f"Place already exists: {payload.id}")
        place = Place(
            id=payload.id,
            name=payload.name,
            place_type=payload.place_type,
            region_key=payload.region_key,
            address=payload.address,
            city=payload.city,
            country=payload.country,
            country_code=payload.country_code,
            primary_area=payload.primary_area,
            latitude=payload.latitude,
            longitude=payload.longitude,
            status=payload.status,
            opening_hours=payload.opening_hours,
            typical_duration_minutes=payload.typical_duration_minutes,
            data_confidence=payload.data_confidence,
            source_fetched_at=payload.source_fetched_at,
            metadata_json=payload.metadata,
        )
        self.repository.add(place)
        self.repository.commit()
        self.repository.refresh(place)
        return place

    def update_place(self, place_id: str, changes: dict[str, Any]) -> Place:
        unknown_fields = set(changes).difference(self.MUTABLE_FIELDS)
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unsupported Place fields: {names}")
        place = self.repository.get(place_id)
        if place is None:
            raise LookupError(f"Place not found: {place_id}")

        for field_name, value in changes.items():
            model_field = "metadata_json" if field_name == "metadata" else field_name
            setattr(place, model_field, value)
        place.revision += 1
        self.repository.commit()
        self.repository.refresh(place)
        return place
