from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.modules.places.model import Place


class FinderPlace(BaseModel):
    place_id: str | None = Field(default=None, alias="placeId")
    name: str
    place_type: str = Field(alias="placeType")
    region_key: str = Field(alias="regionKey")
    tags: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    typical_duration_minutes: int | None = Field(
        default=None,
        alias="typicalDurationMinutes",
    )
    activity_intensity: str | None = Field(
        default=None,
        alias="activityIntensity",
    )
    must_visit: bool = Field(default=False, alias="mustVisit")
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")
    accessibility_features: list[str] = Field(
        default_factory=list,
        alias="accessibilityFeatures",
    )
    opening_hours: list[dict] = Field(default_factory=list, alias="openingHours")
    weather_sensitivity: str | None = Field(default=None, alias="weatherSensitivity")
    price_level: str | None = Field(default=None, alias="priceLevel")
    data_confidence: str = Field(default="low", alias="dataConfidence")

    model_config = {"populate_by_name": True}

    @property
    def stable_ref(self) -> str:
        return self.place_id or self.name


class FinderPlaceTool(Protocol):
    def get(self, place_id: str) -> FinderPlace | None: ...

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]: ...


class FinderPlaceRepository(Protocol):
    def get(self, place_id: str) -> Place | None: ...

    def list_for_finder(
        self,
        region_key: str,
        *,
        limit: int = 200,
    ) -> list[Place]: ...


class EmptyFinderPlaceTool:
    def get(self, place_id: str) -> FinderPlace | None:
        return None

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]:
        return []


class RepositoryFinderPlaceTool:
    def __init__(self, repository: FinderPlaceRepository) -> None:
        self.repository = repository

    def get(self, place_id: str) -> FinderPlace | None:
        place = self.repository.get(place_id)
        if place is None or place.deleted_at is not None:
            return None
        return self._to_finder_place(place)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]:
        places = [
            self._to_finder_place(place)
            for place in self.repository.list_for_finder(region_key)
            if place.id not in excluded_place_ids
        ]
        target_tag_set = {tag.casefold() for tag in target_tags}
        places.sort(
            key=lambda place: (
                -len(target_tag_set.intersection(tag.casefold() for tag in place.tags)),
                place.region_key != region_key,
                place.data_confidence != "high",
                place.name.casefold(),
            )
        )
        return places[:limit]

    def _to_finder_place(self, place: Place) -> FinderPlace:
        metadata = place.metadata_json or {}
        tags = metadata.get("tags", [])
        return FinderPlace(
            placeId=place.id,
            name=place.name,
            placeType=place.place_type,
            regionKey=place.region_key,
            tags=[
                str(tag)
                for tag in tags
                if isinstance(tag, str)
            ],
            latitude=(
                float(place.latitude) if place.latitude is not None else None
            ),
            longitude=(
                float(place.longitude) if place.longitude is not None else None
            ),
            typicalDurationMinutes=place.typical_duration_minutes,
            activityIntensity=metadata.get("activityIntensity"),
            accessibilityFeatures=[
                str(feature)
                for feature in metadata.get("accessibilityFeatures", [])
                if isinstance(feature, str)
            ],
            openingHours=list(place.opening_hours or []),
            weatherSensitivity=(
                str(metadata.get("weatherSensitivity"))
                if metadata.get("weatherSensitivity") is not None
                else None
            ),
            priceLevel=(
                str(metadata.get("priceLevel"))
                if metadata.get("priceLevel") is not None
                else None
            ),
            dataConfidence=place.data_confidence,
        )
