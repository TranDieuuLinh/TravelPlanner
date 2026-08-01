from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterator, Protocol, Sequence
from uuid import uuid4

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

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
        return self.session.get(Place, place_id)

    def list_for_finder(
        self,
        region_key: str,
        *,
        limit: int = 10000,
    ) -> list[Place]:
        _validate_region_key(region_key)
        query = (
            select(Place)
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

    def rank_place_ids_by_embedding(
        self,
        place_ids: Sequence[str],
        query_embedding: list[float],
        *,
        embedding_model: str,
        limit: int,
    ) -> list[tuple[str, float]]:
        """Return cosine similarity after the caller has applied hard filters."""

        if not place_ids or limit < 1:
            return []
        cosine_distance = Place.embedding.cosine_distance(query_embedding)
        query = (
            select(Place.id, cosine_distance.label("distance"))
            .where(
                Place.id.in_(list(place_ids)),
                Place.embedding.is_not(None),
                Place.embedding_model == embedding_model,
            )
            .order_by(cosine_distance)
            .limit(limit)
        )
        return [
            (place_id, max(-1.0, min(1.0, 1.0 - float(distance))))
            for place_id, distance in self.session.execute(query)
        ]

    def has_place_embeddings(
        self,
        region_key: str,
        *,
        embedding_model: str,
    ) -> bool:
        _validate_region_key(region_key)
        query = select(Place.id).where(
            Place.deleted_at.is_(None),
            Place.status == "active",
            Place.embedding.is_not(None),
            Place.embedding_model == embedding_model,
            or_(
                Place.region_key == region_key,
                Place.region_key.like(f"{region_key},%"),
            ),
        ).limit(1)
        return self.session.scalar(query) is not None

    def list_places_needing_embeddings(
        self,
        region_key: str,
        *,
        embedding_model: str,
        limit: int,
    ) -> list[Place]:
        _validate_region_key(region_key)
        query = (
            select(Place)
            .where(
                Place.deleted_at.is_(None),
                Place.status == "active",
                or_(
                    Place.region_key == region_key,
                    Place.region_key.like(f"{region_key},%"),
                ),
                or_(
                    Place.embedding.is_(None),
                    Place.embedding_model != embedding_model,
                    Place.embedding_model.is_(None),
                    Place.embedded_at.is_(None),
                    Place.embedded_at < Place.updated_at,
                ),
            )
            .order_by(
                Place.review_count.desc().nullslast(),
                Place.rating.desc().nullslast(),
                Place.id,
            )
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


def _parse_optional_datetime(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
