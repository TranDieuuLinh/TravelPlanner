from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.model import (
    ExplorerIntake,
    UrlExtractionCacheEntry,
    UserMustPlace,
    UserMustPlaceUser,
)
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    ExtractedPlace,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
)
from app.modules.plans.explorer.tools.url_reels.utils import (
    canonicalize_url,
    detect_platform,
)
from app.modules.plans.explorer.place_policy import (
    concise_source_activity,
    is_schedulable_place,
)
from app.modules.plans.planner.region_context import normalize_region_key
from app.modules.plans.schema import SelectedPlaceCreate


URL_EXTRACTION_CACHE_VERSION = 2


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
        url_results: list[UrlReelExtractionResult] | None = None,
    ) -> None:
        self.session.add(
            ExplorerIntake(
                id=intake_id,
                user_id=user_id,
                destination=destination,
            )
        )
        self._save_url_cache(url_results or [])
        for resolution in resolutions:
            if not _is_persistable_resolution(
                resolution,
                destination=destination,
            ):
                continue
            candidate = resolution.candidate
            source_url = _candidate_source_url(candidate)
            candidate_key = _shared_candidate_key(candidate, destination)
            must_place = self._find_shared_place(
                source_url=source_url,
                candidate_key=candidate_key,
                candidate_name=candidate.name,
            )
            if must_place is None:
                must_place = UserMustPlace(
                    id=str(uuid4()),
                    intake_id=intake_id,
                    user_id=user_id,
                    destination=destination,
                    candidate_key=candidate_key,
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
                    notes=_place_notes(candidate),
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
                    place_id=resolution.place_id,
                    name=resolution.name,
                    place_type=(
                        resolution.place_type or candidate.category.value
                    ),
                    region_key=(
                        resolution.region_key
                        or normalize_region_key(resolution.city or destination)
                    ),
                    status=resolution.place_status or "active",
                    opening_hours=list(resolution.opening_hours),
                    typical_duration_minutes=(
                        resolution.typical_duration_minutes
                        or candidate.source_duration_minutes
                    ),
                    source_platform=(
                        resolution.source_platform or resolution.provider
                    ),
                    source_link=resolution.source_link or source_url,
                    source_url=source_url,
                    plus_code=resolution.plus_code,
                    rating=resolution.rating,
                    review_count=resolution.review_count,
                    source_fetched_at=(
                        resolution.fetched_at
                    ),
                    revision=resolution.place_revision,
                    metadata_json={
                        **resolution.place_metadata,
                        "candidateName": candidate.name,
                        "sourceEvidence": dict(candidate.source_evidence),
                    },
                )
                self.session.add(must_place)
                self.session.flush()
            self._link_user(
                must_place=must_place,
                intake_id=intake_id,
                user_id=user_id,
            )
        self.session.commit()

    def load_must_places(
        self,
        intake_id: str,
        user_id: str | None,
    ) -> list[SelectedPlaceCreate]:
        rows = list(self.session.scalars(
            select(UserMustPlace)
            .join(
                UserMustPlaceUser,
                UserMustPlaceUser.user_must_place_id == UserMustPlace.id,
            )
            .where(
                UserMustPlaceUser.intake_id == intake_id,
                (
                    UserMustPlaceUser.user_id == _numeric_user_id(user_id)
                    if user_id is not None
                    else UserMustPlaceUser.user_id.is_(None)
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
                # Display the verified provider label in plans. The original
                # caption/OCR spelling remains in candidate_name and evidence
                # on UserMustPlace for provenance and debugging.
                name=must_place.resolved_name,
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
                sourceProvider=must_place.provider,
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

    def load_cached_url_result(
        self,
        url: str,
    ) -> UrlReelExtractionResult | None:
        source_url = canonicalize_url(url)
        cached = self.session.get(UrlExtractionCacheEntry, source_url)
        if cached is None:
            rows = self._rows_for_source_url(source_url)
            if not rows:
                return None
            context = _context_from_shared_places(rows)
            platform = detect_platform(source_url)
        else:
            if (
                cached.extracted_context_json.get("_cacheVersion")
                != URL_EXTRACTION_CACHE_VERSION
            ):
                return None
            context = ExtractedContext.model_validate(
                cached.extracted_context_json
            )
            platform = cached.platform
        return UrlReelExtractionResult(
            url=source_url,
            platform=platform,
            metadata=UrlMetadata(
                originalUrl=url,
                canonicalUrl=source_url,
                platform=platform,
            ),
            artifacts=MediaArtifacts(),
            speechToText=SpeechToTextResult(
                text="",
                status="cached",
                source="shared_url_cache",
                durationSeconds=0,
            ),
            extractedContext=context,
            timings={"sharedUrlCache": 0.0},
        )

    def _rows_for_source_url(self, source_url: str) -> list[UserMustPlace]:
        exact = list(self.session.scalars(
            select(UserMustPlace).where(UserMustPlace.source_url == source_url)
        ))
        if exact:
            return exact
        return [
            row
            for row in self.session.scalars(
                select(UserMustPlace).where(UserMustPlace.source_url.is_not(None))
            )
            if row.source_url and canonicalize_url(row.source_url) == source_url
        ]

    def find_cached_resolution(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution | None:
        source_url = _candidate_source_url(candidate)
        if source_url is None:
            return None
        row = self._find_shared_place(
            source_url=source_url,
            candidate_key=_shared_candidate_key(candidate, destination),
            candidate_name=candidate.name,
        )
        if row is None or row.deleted_at is not None:
            return None
        return PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider=row.provider or row.source_platform or "shared_url_cache",
            externalId=row.external_id,
            placeId=row.place_id,
            name=row.name or row.resolved_name,
            placeType=row.place_type or row.category,
            address=row.address,
            city=row.city,
            country=row.country,
            countryCode=row.country_code,
            regionKey=row.region_key,
            primaryArea=row.primary_area,
            latitude=row.latitude,
            longitude=row.longitude,
            description=row.description,
            placeStatus=row.status,
            openingHours=list(row.opening_hours or []),
            typicalDurationMinutes=row.typical_duration_minutes,
            sourcePlatform=row.source_platform,
            sourceLink=row.source_link,
            plusCode=row.plus_code,
            rating=row.rating,
            reviewCount=row.review_count,
            dataConfidence=row.data_confidence,
            fetchedAt=row.source_fetched_at or row.fetched_at,
            placeRevision=row.revision,
            placeMetadata=dict(row.metadata_json or {}),
            attribution=row.attribution,
        )

    def _save_url_cache(self, results: list[UrlReelExtractionResult]) -> None:
        for result in results:
            source_url = canonicalize_url(result.metadata.canonical_url or result.url)
            row = self.session.get(UrlExtractionCacheEntry, source_url)
            payload = result.extracted_context.model_dump(
                mode="json", by_alias=True
            )
            payload["_cacheVersion"] = URL_EXTRACTION_CACHE_VERSION
            if row is None:
                self.session.add(
                    UrlExtractionCacheEntry(
                        source_url=source_url,
                        platform=result.platform,
                        extracted_context_json=payload,
                    )
                )
            else:
                row.platform = result.platform
                row.extracted_context_json = payload

    def _find_shared_place(
        self,
        *,
        source_url: str | None,
        candidate_key: str,
        candidate_name: str,
    ) -> UserMustPlace | None:
        if source_url is None:
            return None
        rows = list(self.session.scalars(
            select(UserMustPlace).where(UserMustPlace.source_url == source_url)
        ))
        normalized_name = _slug(candidate_name)
        return next(
            (
                row for row in rows
                if row.candidate_key == candidate_key
                or _slug(row.candidate_name) == normalized_name
            ),
            None,
        )

    def _link_user(
        self,
        *,
        must_place: UserMustPlace,
        intake_id: str,
        user_id: str | None,
    ) -> None:
        existing = self.session.scalar(
            select(UserMustPlaceUser).where(
                UserMustPlaceUser.intake_id == intake_id,
                UserMustPlaceUser.user_must_place_id == must_place.id,
            )
        )
        if existing is not None:
            return
        numeric_user_id = (
            int(user_id) if user_id is not None and user_id.isdigit() else None
        )
        self.session.add(
            UserMustPlaceUser(
                id=str(uuid4()),
                user_must_place_id=must_place.id,
                user_id=numeric_user_id,
                intake_id=intake_id,
            )
        )


def _candidate_key(name: str, destination: str) -> str:
    return f"{_slug(destination)}:{_slug(name)}"


def _candidate_source_url(candidate: UnifiedPlaceCandidate) -> str | None:
    source_url = next(
        (source.url for source in candidate.sources if source.url),
        None,
    )
    return canonicalize_url(source_url) if source_url else None


def _shared_candidate_key(
    candidate: UnifiedPlaceCandidate,
    destination: str,
) -> str:
    return (
        _slug(candidate.name)
        if _candidate_source_url(candidate)
        else _candidate_key(candidate.name, destination)
    )


def _place_notes(candidate: UnifiedPlaceCandidate) -> str | None:
    parts = [
        value.strip()
        for value in [candidate.notes, *candidate.source_evidence.values()]
        if value and value.strip()
    ]
    unique = list(dict.fromkeys(parts))
    return "\n".join(unique) or None


def _context_from_shared_places(
    rows: list[UserMustPlace],
) -> ExtractedContext:
    details = [
        ExtractedPlace(
            name=row.candidate_name,
            category=row.category,
            address=row.address_hint or row.address,
            searchRegion=row.search_region or row.city,
            evidence=row.notes,
            sourceEvidence=dict(row.source_evidence_json or {}),
            attributes=list(row.attributes_json or []),
            sourceOrder=row.source_order,
            sourceDay=row.source_day,
            sourceTimeHint=row.source_time_hint,
            sourceActivity=row.source_activity,
            sourceDurationMinutes=row.source_duration_minutes,
        )
        for row in sorted(
            rows,
            key=lambda item: (
                item.source_order is None,
                item.source_order or 10_000,
                item.created_at,
                item.id,
            ),
        )
    ]
    return ExtractedContext(
        extractedPlaces=[place.name for place in details],
        extractedPlaceDetails=details,
        confidence=max((float(row.confidence) for row in rows), default=0.0),
    )


def _numeric_user_id(user_id: str | None) -> int | None:
    if user_id is None:
        return None
    return int(user_id) if user_id.isdigit() else -1


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
        candidate_name=must_place.candidate_name,
        resolved_name=must_place.resolved_name,
        city=must_place.city,
        destination=must_place.destination,
        country=must_place.country,
    )


def _is_persistable_resolution(
    resolution: PlaceResolution,
    *,
    destination: str,
) -> bool:
    if resolution.status != "resolved":
        return False
    return is_schedulable_place(
        is_url_source=any(
            source.type.value == "url" and source.url
            for source in resolution.candidate.sources
        ),
        resolution_status=resolution.status,
        latitude=resolution.latitude,
        longitude=resolution.longitude,
        candidate_name=resolution.candidate.name,
        resolved_name=resolution.name,
        city=resolution.city,
        destination=destination,
        country=resolution.country,
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
