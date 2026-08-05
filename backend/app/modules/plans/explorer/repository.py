from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.places.model import Place
from app.modules.places.category import canonical_place_category
from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.model import (
    ExplorerIntake,
    UrlExtractionCacheEntry,
    UrlSourceArtifact,
    UserMustPlace,
    UserMustPlaceUser,
)
from app.modules.plans.explorer.schema import PlaceCandidateReview, UnifiedPlaceCandidate
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
    extract_youtube_video_id,
)
from app.modules.plans.explorer.place_policy import (
    concise_source_activity,
    is_schedulable_place,
)
from app.modules.plans.trip_theme_planner.region_context import normalize_region_key
from app.modules.plans.schema import SelectedPlaceCreate


URL_EXTRACTION_CACHE_VERSION = 5


def _artifact_source_url(url: str, platform: str | None = None) -> str:
    detected_platform = platform or detect_platform(url)
    video_id = extract_youtube_video_id(url)
    if detected_platform == "youtube" and video_id is not None:
        return f"https://www.youtube.com/watch?v={video_id}"
    return canonicalize_url(url)


def _image_urls_from_metadata(metadata: object) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    values: list[object] = []
    for key in ("imageUrls", "images"):
        value = metadata.get(key)
        if isinstance(value, list):
            values.extend(value)
    for key in ("imageUrl", "photoUrl", "thumbnailUrl"):
        value = metadata.get(key)
        if value:
            values.append(value)

    urls: list[str] = []
    for value in values:
        candidate = value
        if isinstance(value, dict):
            candidate = value.get("url") or value.get("imageUrl")
        if (
            isinstance(candidate, str)
            and candidate.startswith(("https://", "http://"))
            and candidate not in urls
        ):
            urls.append(candidate)
    return urls[:5]


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
        candidate_reviews: list[PlaceCandidateReview] | None = None,
        url_results: list[UrlReelExtractionResult] | None = None,
    ) -> None:
        self.session.add(
            ExplorerIntake(
                id=intake_id,
                user_id=user_id,
                destination=destination,
                candidate_reviews=[
                    review.model_dump(mode="json", by_alias=True)
                    for review in (candidate_reviews or [])
                ],
            )
        )
        self._save_url_cache(url_results or [])
        self._save_url_source_artifacts(url_results or [])
        for resolution in resolutions:
            if not _is_persistable_resolution(
                resolution,
                destination=destination,
            ):
                continue
            candidate = resolution.candidate
            resolved_category = canonical_place_category(
                resolution.place_type
            )
            source_url = _candidate_source_url(candidate)
            candidate_key = _shared_candidate_key(candidate, destination)
            must_place = self._find_shared_place(
                source_url=source_url,
                candidate_key=candidate_key,
                candidate_name=candidate.name,
            )
            if must_place is None:
                catalog_place_id = self._catalog_place_id(resolution.place_id)
                must_place = UserMustPlace(
                    id=str(uuid4()),
                    intake_id=intake_id,
                    user_id=user_id,
                    destination=destination,
                    candidate_key=candidate_key,
                    candidate_name=candidate.name,
                    category=resolved_category,
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
                    # Provider identities belong in external_id. place_id is
                    # an internal FK and must never contain a stale/external
                    # provider identifier.
                    place_id=catalog_place_id,
                    name=resolution.name,
                    place_type=resolution.place_type or "other",
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
            else:
                # Repair cached rows created before provider/database category
                # became authoritative.
                must_place.category = resolved_category
                if resolution.place_type:
                    must_place.place_type = resolution.place_type
            self._link_user(
                must_place=must_place,
                intake_id=intake_id,
                user_id=user_id,
            )
        self.session.commit()

    def load_candidate_reviews(self, intake_id: str | None) -> list[PlaceCandidateReview]:
        if intake_id is None:
            return []
        row = self.session.get(ExplorerIntake, intake_id)
        if row is None:
            return []
        return [
            PlaceCandidateReview.model_validate(value)
            for value in row.candidate_reviews
        ]

    def replace_candidate_reviews(
        self,
        intake_id: str,
        reviews: list[PlaceCandidateReview],
    ) -> None:
        row = self.session.get(ExplorerIntake, intake_id)
        if row is None:
            return
        row.candidate_reviews = [
            review.model_dump(mode="json", by_alias=True) for review in reviews
        ]

    def _catalog_place_id(self, place_id: str | None) -> str | None:
        if place_id is None:
            return None
        return self.session.scalar(
            select(Place.id).where(Place.id == place_id)
        )

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
                        [
                            canonical_place_category(must_place.place_type),
                            *(must_place.attributes_json or []),
                        ]
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
                imageUrls=_image_urls_from_metadata(must_place.metadata_json),
                rating=(
                    float(must_place.rating)
                    if must_place.rating is not None
                    else None
                ),
                reviewCount=must_place.review_count,
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
            # Resolved snapshots do not contain the current extraction schema,
            # entity types or coverage. Reusing them as an extraction cache
            # would bypass schema-version invalidation and preserve old parser
            # mistakes indefinitely.
            return None
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

    def load_url_source_artifacts(
        self,
        url: str,
        *,
        artifact_types: set[str] | None = None,
    ) -> list[UrlSourceArtifact]:
        """Return normalized source text for future RAG and note consumers."""

        source_url = _artifact_source_url(url)
        statement = select(UrlSourceArtifact).where(
            UrlSourceArtifact.source_url == source_url
        )
        if artifact_types:
            statement = statement.where(
                UrlSourceArtifact.artifact_type.in_(artifact_types)
            )
        return list(
            self.session.scalars(
                statement.order_by(
                    UrlSourceArtifact.artifact_type,
                    UrlSourceArtifact.language,
                )
            ).all()
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
        verified_aliases, verified_vietnamese_aliases = _cached_verified_aliases(row)
        return PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider=row.provider or row.source_platform or "shared_url_cache",
            externalId=row.external_id,
            placeId=row.place_id,
            name=row.name or row.resolved_name,
            verifiedAliases=verified_aliases,
            verifiedVietnameseAliases=verified_vietnamese_aliases,
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

    def _save_url_source_artifacts(
        self,
        results: list[UrlReelExtractionResult],
    ) -> None:
        for result in results:
            source_url = _artifact_source_url(
                result.metadata.canonical_url or result.url,
                result.platform,
            )
            speech = result.speech_to_text
            if speech.status == "ok" and speech.text.strip():
                is_web_page = speech.source == "web_page_text"
                artifact_type = (
                    "webpage"
                    if is_web_page
                    else "caption"
                    if speech.source.startswith("youtube_captions")
                    else "stt"
                )
                content_text = (
                    "\n".join(
                        observation.evidence.strip()
                        for observation in speech.observations
                        if observation.evidence.strip()
                    )
                    if is_web_page
                    else speech.text
                )
                if not content_text:
                    continue
                self._upsert_url_source_artifact(
                    source_url=source_url,
                    platform=result.platform,
                    artifact_type=artifact_type,
                    content_text=content_text,
                    language=speech.language or "",
                    source=speech.source or artifact_type,
                    metadata={
                        "observations": [
                            observation.model_dump(mode="json", by_alias=True)
                            for observation in speech.observations
                        ],
                        "audioDurationSeconds": speech.audio_duration_seconds,
                        "chunkCount": speech.chunk_count,
                    },
                )

            vision = result.frame_vision
            if vision.status in {"ok", "partial"} and vision.text.strip():
                self._upsert_url_source_artifact(
                    source_url=source_url,
                    platform=result.platform,
                    artifact_type="ocr",
                    content_text=vision.text,
                    language="",
                    source="frame_vision",
                    metadata={
                        "places": list(vision.places),
                        "observations": [
                            observation.model_dump(mode="json", by_alias=True)
                            for observation in vision.observations
                        ],
                    },
                )

    def _upsert_url_source_artifact(
        self,
        *,
        source_url: str,
        platform: str,
        artifact_type: str,
        content_text: str,
        language: str,
        source: str,
        metadata: dict,
    ) -> None:
        row = self.session.scalar(
            select(UrlSourceArtifact).where(
                UrlSourceArtifact.source_url == source_url,
                UrlSourceArtifact.artifact_type == artifact_type,
                UrlSourceArtifact.language == language,
            )
        )
        fetched_at = datetime.now(timezone.utc)
        if row is None:
            self.session.add(
                UrlSourceArtifact(
                    id=str(uuid4()),
                    source_url=source_url,
                    platform=platform,
                    artifact_type=artifact_type,
                    content_text=content_text.strip(),
                    language=language,
                    source=source,
                    metadata_json=metadata,
                    fetched_at=fetched_at,
                )
            )
            return
        row.platform = platform
        row.content_text = content_text.strip()
        row.source = source
        row.metadata_json = metadata
        row.fetched_at = fetched_at

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


def _cached_verified_aliases(row: UserMustPlace) -> tuple[list[str], list[str]]:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    aliases = [row.name or row.resolved_name]
    vietnamese: list[str] = []
    for value in metadata.get("verifiedAliases", []):
        if isinstance(value, dict):
            name = str(value.get("name") or "").strip()
            language = str(value.get("language") or "")
        else:
            name = str(value or "").strip()
            language = ""
        if not name:
            continue
        aliases.append(name)
        if language == "vi" or _looks_vietnamese(name):
            vietnamese.append(name)
    aliases = [value for value in aliases if value]
    for name in aliases:
        if _looks_vietnamese(name):
            vietnamese.append(name)
    return list(dict.fromkeys(aliases)), list(dict.fromkeys(vietnamese))


def _looks_vietnamese(value: str) -> bool:
    decomposed = unicodedata.normalize("NFD", value)
    return "đ" in value.casefold() or any(
        unicodedata.combining(character) for character in decomposed
    )


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
