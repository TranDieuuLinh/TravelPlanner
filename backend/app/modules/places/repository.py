from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator, Protocol
from uuid import uuid4

from sqlalchemy import Select, Text, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modules.places.auto_statistics.domain import PlaceStatisticsRecord
from app.modules.places.model import (
    Place,
    PlaceRegionCatalogState,
    PlaceRegionSnapshot,
)


class PlaceStatisticsRepository(Protocol):
    def source_signature(self, region_key: str | None = None) -> dict[str, str | int]: ...

    def iter_statistics_records(
        self,
        region_key: str | None = None,
    ) -> Iterator[PlaceStatisticsRecord]: ...

    def get_current_snapshot(
        self,
        region_key: str,
    ) -> PlaceRegionSnapshot | None: ...

    def save_region_snapshot(
        self,
        *,
        region_key: str,
        algorithm_version: str,
        source_signature: dict[str, str | int],
        regions: list[dict],
        generated_at: datetime,
        expires_at: datetime,
    ) -> PlaceRegionSnapshot: ...


class SqlAlchemyPlaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def source_signature(self, region_key: str | None = None) -> dict[str, str | int]:
        query = select(
            func.count(Place.id),
            func.max(Place.updated_at),
            func.coalesce(func.sum(Place.revision), 0),
        ).where(Place.deleted_at.is_(None))
        query = self._scope_query(query, region_key)
        row_count, max_updated_at, revision_sum = self.session.execute(
            query
        ).one()
        updated_at_text = (
            _as_utc_iso(max_updated_at) if isinstance(max_updated_at, datetime) else ""
        )
        catalog_version = f"{row_count}:{revision_sum}:{updated_at_text}"
        fingerprint = hashlib.sha256(catalog_version.encode("utf-8")).hexdigest()
        dialect = self.session.get_bind().dialect.name
        return {
            "storage": dialect,
            "regionKey": region_key or "*",
            "fingerprint": fingerprint,
            "rowCount": int(row_count),
            "revisionSum": int(revision_sum),
            "maxUpdatedAt": updated_at_text,
        }

    def iter_statistics_records(
        self,
        region_key: str | None = None,
    ) -> Iterator[PlaceStatisticsRecord]:
        query = select(Place).where(Place.deleted_at.is_(None))
        query = self._scope_query(query, region_key)
        places = self.session.scalars(
            query.order_by(Place.id).execution_options(yield_per=1000)
        )
        for place in places:
            yield PlaceStatisticsRecord(
                id=place.id,
                region_key=place.region_key,
                place_type=place.place_type,
                status=place.status,
                latitude=float(place.latitude) if place.latitude is not None else None,
                longitude=float(place.longitude) if place.longitude is not None else None,
                opening_hours=place.opening_hours or [],
                typical_duration_minutes=place.typical_duration_minutes,
                data_confidence=place.data_confidence,
                source_fetched_at=place.source_fetched_at,
                metadata=place.metadata_json or {},
            )

    def get(self, place_id: str) -> Place | None:
        return self.session.scalar(
            select(Place)
            .options(selectinload(Place.images))
            .where(Place.id == place_id)
        )

    def list_for_finder(
        self,
        region_key: str,
        *,
        limit: int = 10000,
    ) -> list[Place]:
        _validate_region_key(region_key)
        query = (
            select(Place)
            .options(selectinload(Place.images))
            .where(
                Place.deleted_at.is_(None),
                Place.status == "active",
                or_(
                    Place.region_key == region_key,
                    Place.region_key.like(f"{region_key},%"),
                ),
            )
            .order_by(Place.id)
            .limit(limit)
        )
        return list(self.session.scalars(query))

    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[Place]:
        query = select(Place).where(
            Place.deleted_at.is_(None),
            Place.status == "active",
        )
        query = self._scope_query(query, region_key)
        return list(
            self.session.scalars(
                query.order_by(Place.region_key, Place.id).limit(limit)
            )
        )

    def search_active_by_names(
        self,
        names: list[str],
        *,
        limit: int = 100,
    ) -> list[Place]:
        """Find global name/branch matches for candidate aliases.

        This is the second pass for place resolution when a region-scoped
        lookup misses. Keeping the comparison in SQL avoids loading the whole
        place catalog into Python.
        """
        lookup_names = {
            " ".join(name.split()).lower()
            for name in names
            if name and " ".join(name.split())
        }
        if not lookup_names:
            return []
        query = (
            select(Place)
            .where(
                Place.deleted_at.is_(None),
                Place.status == "active",
                Place.latitude.is_not(None),
                Place.longitude.is_not(None),
                or_(
                    *(
                        or_(
                            Place.name.ilike(
                                f"%{_escape_like(name)}%",
                                escape="\\",
                            ),
                            cast(Place.metadata_json, Text).ilike(
                                f"%{_escape_like(name)}%",
                                escape="\\",
                            ),
                        )
                        for name in lookup_names
                    )
                ),
            )
            .order_by(Place.region_key, Place.id)
            .limit(limit)
        )
        return list(self.session.scalars(query))

    def upsert_verified_google_aliases(
        self,
        *,
        external_id: str,
        canonical_name: str,
        aliases: list[str],
        place_type: str,
        address: str | None,
        city: str | None,
        country: str | None,
        country_code: str | None,
        primary_area: str | None,
        latitude: Decimal,
        longitude: Decimal,
        region_key: str,
        source_link: str | None,
        fetched_at: datetime,
        attribution: str | None,
    ) -> bool:
        """Persist source spellings verified against a stable Google identity."""
        external_id = external_id.strip()
        canonical_name = " ".join(canonical_name.split())
        if (
            not external_id
            or len(external_id) > 96
            or not canonical_name
            or len(canonical_name) > 255
        ):
            return False
        _validate_region_key(region_key)

        learned_aliases: list[str] = []
        seen = {_alias_key(canonical_name)}
        for value in aliases:
            alias = " ".join(value.split())
            key = _alias_key(alias)
            if (
                not alias
                or len(alias) > 255
                or not key
                or key in seen
            ):
                continue
            seen.add(key)
            learned_aliases.append(alias)
            if len(learned_aliases) == 64:
                break
        try:
            place = self.session.scalar(
                select(Place)
                .where(Place.id == external_id)
                .with_for_update()
            )
            created = place is None
            if not created and not learned_aliases:
                return False
            if place is None:
                place = Place(
                    id=external_id,
                    name=canonical_name,
                    place_type=(place_type or "other")[:96],
                    address=address,
                    city=city,
                    country=country,
                    country_code=country_code,
                    region_key=region_key,
                    primary_area=primary_area,
                    latitude=latitude,
                    longitude=longitude,
                    status="active",
                    opening_hours=[],
                    data_confidence="medium",
                    source_platform="google_maps_scraper",
                    source_link=source_link,
                    source_fetched_at=fetched_at,
                    revision=1,
                    metadata_json={},
                )
                self.session.add(place)

            metadata = dict(place.metadata_json or {})
            existing_aliases = [
                str(value)
                for value in metadata.get("aliases", [])
                if isinstance(value, str) and _alias_key(value)
            ]
            existing_keys = {
                _alias_key(place.name),
                *(_alias_key(value) for value in existing_aliases),
            }
            aliases_to_add = [
                alias
                for alias in learned_aliases
                if _alias_key(alias) not in existing_keys
            ]

            verified = [
                value
                for value in metadata.get("verifiedAliases", [])
                if isinstance(value, dict) and value.get("name")
            ]
            verified_keys = {
                _alias_key(str(value["name"])) for value in verified
            }
            verified_to_add = [
                alias
                for alias in learned_aliases
                if _alias_key(alias) not in verified_keys
            ]
            if not created and not aliases_to_add and not verified_to_add:
                return False

            verified_at = fetched_at.astimezone(timezone.utc).isoformat()
            metadata["aliases"] = [*existing_aliases, *aliases_to_add]
            metadata["verifiedAliases"] = [
                *verified,
                *(
                    {
                        "name": alias,
                        "provider": "google_maps_scraper",
                        "externalId": external_id,
                        "verifiedAt": verified_at,
                    }
                    for alias in verified_to_add
                ),
            ][-64:]
            metadata["aliasLearningVersion"] = 1
            if attribution:
                metadata.setdefault("attribution", attribution)
            place.metadata_json = metadata
            if not created:
                place.revision = int(place.revision or 1) + 1
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            raise

    def add(self, place: Place) -> Place:
        self.session.add(place)
        return place

    def commit(self) -> None:
        self.session.commit()

    def refresh(self, place: Place) -> None:
        self.session.refresh(place)

    def get_current_snapshot(
        self,
        region_key: str,
    ) -> PlaceRegionSnapshot | None:
        state = self.session.get(PlaceRegionCatalogState, region_key)
        if state is None or state.current_snapshot_id is None:
            return None
        return self.session.get(PlaceRegionSnapshot, state.current_snapshot_id)

    def save_region_snapshot(
        self,
        *,
        region_key: str,
        algorithm_version: str,
        source_signature: dict[str, str | int],
        regions: list[dict],
        generated_at: datetime,
        expires_at: datetime,
    ) -> PlaceRegionSnapshot:
        state = self.session.scalar(
            select(PlaceRegionCatalogState)
            .where(PlaceRegionCatalogState.region_key == region_key)
            .with_for_update()
        )
        if state is None:
            state = PlaceRegionCatalogState(
                region_key=region_key,
                catalog_version=0,
                refresh_status="pending",
                refresh_attempts=0,
            )
            self.session.add(state)
            self.session.flush()

        root_metrics = next(
            (region for region in regions if region["regionKey"] == region_key),
            None,
        )
        next_version = state.catalog_version + 1
        snapshot = PlaceRegionSnapshot(
            id=str(uuid4()),
            region_key=region_key,
            catalog_version=next_version,
            algorithm_version=algorithm_version,
            source_fingerprint=str(source_signature["fingerprint"]),
            place_count=int(root_metrics["placeCount"]) if root_metrics else 0,
            active_place_count=(
                int(root_metrics["activePlaceCount"]) if root_metrics else 0
            ),
            source_max_updated_at=_parse_optional_datetime(
                str(source_signature.get("maxUpdatedAt", ""))
            ),
            metrics_json={
                "requestedRegionKey": region_key,
                "rollupPolicy": "Requested region and its descendant region_key values.",
                "regions": regions,
            },
            generated_at=generated_at,
            expires_at=expires_at,
        )
        self.session.add(snapshot)
        self.session.flush()

        state.catalog_version = next_version
        state.current_snapshot_id = snapshot.id
        state.dirty_since = None
        state.refresh_status = "clean"
        state.refresh_attempts = 0
        state.next_retry_at = None
        state.last_error_code = None
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def _scope_query(self, query: Select, region_key: str | None) -> Select:
        if region_key is None:
            return query
        _validate_region_key(region_key)
        return query.where(
            or_(
                Place.region_key == region_key,
                Place.region_key.like(f"{region_key},%"),
            )
        )


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _validate_region_key(region_key: str) -> None:
    parts = region_key.split(",")
    if len(parts) < 2 or parts[0] != "vn" or any(not part for part in parts):
        raise ValueError(f"Invalid region_key: {region_key}")
    if any("%" in part or "_" in part for part in parts):
        raise ValueError(f"Invalid region_key wildcard: {region_key}")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _alias_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", without_marks)


def _parse_optional_datetime(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
