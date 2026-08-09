"""Read-only place search boundary for the InformationFinder agent."""

from __future__ import annotations

import asyncio
import logging
import math
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Mapping, Protocol, Sequence

from app.modules.knowledge_graph.place_search import KnowledgeGraphPlaceMatch

if TYPE_CHECKING:
    from app.modules.places.resolver import GoogleMapsSearchClient

from .schema import InformationCandidate, InformationResult, InformationSource

logger = logging.getLogger(__name__)


class PlaceSearchReader(Protocol):
    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> InformationResult: ...

    async def find_meeting_point(
        self,
        origins: Sequence[str],
        venue_type: str,
        destination: str | None,
        top_k: int,
    ) -> InformationResult: ...


class PlaceSearchProvider(Protocol):
    provider_name: str

    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Mapping[str, Any]]: ...


class GoogleMapsPlaceSearchProvider:
    """Adapt the existing scraper client to the read provider contract."""

    provider_name = "google_maps_scraper"

    def __init__(self, client: GoogleMapsSearchClient) -> None:
        self.client = client

    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        center = (filters or {}).get("center")
        if (
            isinstance(center, (tuple, list))
            and len(center) == 2
            and all(isinstance(value, (int, float)) for value in center)
        ):
            query = f"{query} gần {float(center[0]):.6f},{float(center[1]):.6f}"
            destination = None
        return await self.client.search(query, region=destination or None, limit=top_k)


class InformationFinderReader:
    """Graph-first, read-only place search with an external fallback."""

    def __init__(
        self,
        graph_repository: Any | None = None,
        provider: PlaceSearchProvider | None = None,
        *,
        clock: Any = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.graph_repository = graph_repository
        self.provider = provider
        self._clock = clock

    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> InformationResult:
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        cleaned = query.strip()
        if not cleaned:
            return InformationResult(
                kind="empty",
                message="A place search query is required.",
            )

        warnings: list[str] = []
        graph_candidates = self._graph_candidates(cleaned, destination, top_k, filters)
        candidates = list(graph_candidates)
        if len(candidates) < top_k and self.provider is not None:
            try:
                provider_results = await self.provider.search(
                    cleaned, destination, top_k, filters
                )
                candidates = _merge_candidates(
                    candidates,
                    [self._provider_candidate(item) for item in provider_results],
                    limit=top_k,
                )
            except Exception:
                provider_name = getattr(self.provider, "provider_name", "place_provider")
                warnings.append(f"provider_search_failed:{provider_name}")
                logger.warning("InformationFinder place provider failed", exc_info=True)

        return InformationResult(
            kind="candidates" if candidates else "empty",
            message=("Choose a place candidate." if candidates else "No places found."),
            candidates=candidates,
            needs_user_choice=bool(candidates),
            warnings=warnings,
        )

    async def find_meeting_point(
        self,
        origins: Sequence[str],
        venue_type: str,
        destination: str | None,
        top_k: int,
    ) -> InformationResult:
        """Resolve origins, calculate their geographic center, then rank venues.

        The center is an explicitly approximate straight-line midpoint. Route-time
        fairness can be layered behind the same boundary when a matrix provider is
        available; unresolved origins fail closed instead of becoming random stops.
        """
        cleaned_origins = list(
            dict.fromkeys(origin.strip() for origin in origins if origin.strip())
        )
        if len(cleaned_origins) < 2:
            return InformationResult(
                kind="meeting_point_clarification",
                message="Bạn hãy cung cấp ít nhất hai điểm xuất phát cụ thể.",
                warnings=["meeting_point_requires_two_origins"],
            )

        resolved = await asyncio.gather(
            *(self._resolve_origin(origin, destination) for origin in cleaned_origins)
        )
        missing = [
            origin for origin, match in zip(cleaned_origins, resolved, strict=True)
            if match is None
        ]
        if missing:
            names = ", ".join(missing)
            return InformationResult(
                kind="meeting_point_clarification",
                message=(
                    f"Mình chưa xác định chắc chắn được: {names}. "
                    "Bạn hãy nhập địa chỉ đầy đủ hơn hoặc chọn điểm trên bản đồ."
                ),
                warnings=[f"unresolved_meeting_origin:{name}" for name in missing],
            )

        origin_records = [item for item in resolved if item is not None]
        center_lat = sum(item["latitude"] for item in origin_records) / len(origin_records)
        center_lng = sum(item["longitude"] for item in origin_records) / len(origin_records)
        candidates, warnings = await self._meeting_venue_candidates(
            venue_type.strip() or "cafe",
            destination,
            top_k,
            center=(center_lat, center_lng),
            origins=origin_records,
        )
        if not candidates:
            return InformationResult(
                kind="meeting_point_empty",
                message=(
                    "Đã tính được vùng ở giữa nhưng chưa tìm thấy địa điểm gặp phù hợp "
                    "trong dữ liệu hiện có."
                ),
                meetingPoint={"latitude": center_lat, "longitude": center_lng},
                resolvedOrigins=origin_records,
                warnings=warnings or ["meeting_point_venue_not_found"],
            )
        candidate_lines = [
            (
                f"{index}. {candidate.display_name or candidate.candidate_id}"
                f" — cách tâm khoảng {candidate.distance_to_center_km:.2f} km,"
                f" xa nhất từ một điểm xuất phát khoảng "
                f"{candidate.max_origin_distance_km:.2f} km"
            )
            for index, candidate in enumerate(candidates, start=1)
            if candidate.distance_to_center_km is not None
            and candidate.max_origin_distance_km is not None
        ]
        return InformationResult(
            kind="meeting_point_candidates",
            message=(
                "Mình đã tính tâm địa lý gần đúng từ các điểm xuất phát và xếp "
                f"{venue_type or 'cafe'} theo độ gần/cân bằng:\n"
                + "\n".join(candidate_lines)
                + "\nHãy chọn một điểm gặp."
            ),
            candidates=candidates,
            needsUserChoice=True,
            meetingPoint={"latitude": center_lat, "longitude": center_lng},
            resolvedOrigins=origin_records,
            warnings=["meeting_point_uses_straight_line_distance", *warnings],
        )

    async def _resolve_origin(
        self, origin: str, destination: str | None
    ) -> dict[str, object] | None:
        provider_matches: Sequence[Mapping[str, Any]] = ()
        if self.provider is not None:
            try:
                provider_matches = await self.provider.search(
                    origin, destination, 5, {"purpose": "geocode_origin"}
                )
            except Exception:
                logger.warning("Meeting-point origin provider failed", exc_info=True)
        best = _best_origin_match(origin, provider_matches)
        if best is not None:
            return best

        if self.graph_repository is None:
            return None
        records = self.graph_repository.search(origin, destination, limit=5)
        graph_matches = [
            {
                "name": record.name,
                "address": record.address,
                "latitude": record.latitude,
                "longitude": record.longitude,
                "place_id": str(record.entity_id),
                "provider": "knowledge_graph",
            }
            for record in records
        ]
        return _best_origin_match(origin, graph_matches)

    async def _meeting_venue_candidates(
        self,
        venue_type: str,
        destination: str | None,
        top_k: int,
        *,
        center: tuple[float, float],
        origins: Sequence[Mapping[str, object]],
    ) -> tuple[list[InformationCandidate], list[str]]:
        warnings: list[str] = []
        candidates: list[InformationCandidate] = []
        if self.provider is not None:
            try:
                records = await self.provider.search(
                    venue_type,
                    destination,
                    min(10, max(top_k * 2, top_k)),
                    {"center": center, "purpose": "meeting_venue"},
                )
                candidates.extend(self._provider_candidate(item) for item in records)
            except Exception:
                provider_name = getattr(self.provider, "provider_name", "place_provider")
                warnings.append(f"provider_search_failed:{provider_name}")
                logger.warning("Meeting-point venue provider failed", exc_info=True)

        if len(candidates) < top_k and self.graph_repository is not None:
            records = self.graph_repository.search(venue_type, destination, limit=10)
            candidates = _merge_candidates(
                candidates,
                [self._graph_candidate(record) for record in records],
                limit=10,
            )

        scored: list[InformationCandidate] = []
        for candidate in candidates:
            if candidate.latitude is None or candidate.longitude is None:
                continue
            center_distance = _haversine_km(
                center,
                (candidate.latitude, candidate.longitude),
            )
            max_origin_distance = max(
                _haversine_km(
                    (float(origin["latitude"]), float(origin["longitude"])),
                    (candidate.latitude, candidate.longitude),
                )
                for origin in origins
            )
            scored.append(
                candidate.model_copy(
                    update={
                        "distance_to_center_km": round(center_distance, 2),
                        "max_origin_distance_km": round(max_origin_distance, 2),
                    }
                )
            )
        scored.sort(
            key=lambda item: (
                item.max_origin_distance_km
                if item.max_origin_distance_km is not None
                else math.inf,
                item.distance_to_center_km
                if item.distance_to_center_km is not None
                else math.inf,
                -(item.confidence or 0),
            )
        )
        return scored[:top_k], warnings

    def _graph_candidates(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None,
    ) -> list[InformationCandidate]:
        del filters
        if self.graph_repository is None:
            return []
        records = self.graph_repository.search(query, destination, limit=top_k)
        return [self._graph_candidate(record) for record in records]

    def _graph_candidate(self, record: KnowledgeGraphPlaceMatch) -> InformationCandidate:
        identity = str(record.entity_id)
        fetched_at = _timestamp(getattr(record, "source_fetched_at", None), self._clock)
        return InformationCandidate(
            candidateId=f"knowledge_graph:{identity}",
            placeId=identity,
            source=InformationSource.knowledge_graph,
            sourceRefs=[f"knowledge_graph:{identity}"],
            candidateEntityIds=[identity],
            latitude=record.latitude,
            longitude=record.longitude,
            confidence=1.0 if record.status == "verified" else 0.75,
            isVerified=record.status == "verified",
            fetchedAt=fetched_at,
            displayName=record.name,
            address=record.address,
        )

    def _provider_candidate(self, result: Mapping[str, Any]) -> InformationCandidate:
        provider = getattr(self.provider, "provider_name", "external_provider")
        identity = _text(result.get("place_id") or result.get("data_id"))
        name = _text(result.get("title") or result.get("name")) or "unknown"
        stable_identity = identity or _identity_key(name, result)
        lat = _number(result.get("latitude") or result.get("y"))
        lng = _number(result.get("longitude") or result.get("x"))
        return InformationCandidate(
            candidateId=f"{provider}:{stable_identity}",
            placeId=identity,
            source=InformationSource.external_provider,
            sourceRefs=[f"{provider}:{stable_identity}"],
            latitude=lat,
            longitude=lng,
            confidence=0.5,
            isVerified=False,
            fetchedAt=_timestamp(result.get("fetched_at") or result.get("fetchedAt"), self._clock),
            displayName=name,
            address=_text(result.get("address") or result.get("complete_address")),
        )


def _best_origin_match(
    query: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, object] | None:
    ranked: list[tuple[float, int, Mapping[str, Any]]] = []
    query_key = _plain_text(query)
    for index, record in enumerate(records):
        lat = _number(record.get("latitude") or record.get("y"))
        lng = _number(record.get("longitude") or record.get("x"))
        name = _text(record.get("title") or record.get("name"))
        if lat is None or lng is None or name is None:
            continue
        name_key = _plain_text(name)
        score = SequenceMatcher(None, query_key, name_key).ratio()
        if query_key in name_key or name_key in query_key:
            score = max(score, 0.9)
        ranked.append((score, -index, record))
    if not ranked:
        return None
    score, _, record = max(ranked, key=lambda item: (item[0], item[1]))
    if score < 0.5:
        return None
    name = _text(record.get("title") or record.get("name")) or query
    return {
        "query": query,
        "name": name,
        "address": _text(record.get("address") or record.get("complete_address")),
        "latitude": float(_number(record.get("latitude") or record.get("y"))),
        "longitude": float(_number(record.get("longitude") or record.get("x"))),
        "placeId": _text(record.get("place_id") or record.get("data_id")),
        "provider": _text(record.get("provider")) or "external_provider",
    }


def _plain_text(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode()
        .casefold()
        .split()
    )


def _haversine_km(
    left: tuple[float, float], right: tuple[float, float]
) -> float:
    lat1, lng1 = map(math.radians, left)
    lat2, lng2 = map(math.radians, right)
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(value))


def _merge_candidates(
    primary: list[InformationCandidate],
    fallback: list[InformationCandidate],
    *,
    limit: int,
) -> list[InformationCandidate]:
    merged: list[InformationCandidate] = []
    seen: set[str] = set()
    for candidate in [*primary, *fallback]:
        keys = {key for key in (candidate.place_id, *candidate.source_refs) if key}
        if not keys:
            keys = {candidate.candidate_id}
        if seen.intersection(keys):
            continue
        merged.append(candidate)
        seen.update(keys)
        if len(merged) >= limit:
            break
    return merged


def _identity_key(name: str, result: Mapping[str, Any]) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    lat = _number(result.get("latitude") or result.get("y"))
    lng = _number(result.get("longitude") or result.get("x"))
    return f"{text}:{lat}:{lng}"


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any, clock: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return clock()
