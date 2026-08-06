from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import json
import math
import os
import re
import signal
import tempfile
import time
import unicodedata
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, ContextManager, Literal, Protocol

from pydantic import BaseModel, Field

from app.modules.places.category import canonical_place_category
from app.modules.knowledge_graph.text import repair_cp437_utf8_mojibake
from app.modules.plans.destination_inference import usable_destination
from app.modules.plans.explorer.schema import PlaceMatchOption, UnifiedPlaceCandidate


DEFAULT_PLACE_RESOLUTION_MINIMUM_SCORE = 0.82
DEFAULT_DATABASE_NAME_CANDIDATE_LIMIT = 100

GENERIC_VENUE_NAMES = {
    "banh cuon",
    "banh cuon nong",
    "banh mi",
    "bun cha",
    "cafe",
    "coffee",
    "pho",
    "restaurant",
}


class PlaceLookupRecord(Protocol):
    id: str
    name: str
    place_type: str
    address: str | None
    city: str | None
    country: str | None
    country_code: str | None
    primary_area: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    data_confidence: str
    region_key: str
    status: str
    opening_hours: list[dict]
    typical_duration_minutes: int | None
    source_platform: str | None
    source_link: str | None
    plus_code: str | None
    rating: Decimal | None
    review_count: int | None
    revision: int
    source_fetched_at: datetime | None
    metadata_json: dict


class PlaceLookupRepository(Protocol):
    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[PlaceLookupRecord]: ...

    def search_active_by_names(
        self,
        names: list[str],
        *,
        limit: int = 100,
    ) -> list[PlaceLookupRecord]: ...

    def search_active_for_autocomplete(
        self,
        query: str,
        region_key: str | None = None,
        *,
        limit: int = 200,
    ) -> list[PlaceLookupRecord]: ...


class VerifiedPlaceAliasRepository(Protocol):
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
    ) -> bool: ...


class PlaceResolution(BaseModel):
    candidate: UnifiedPlaceCandidate
    status: Literal["resolved", "provisional", "unresolved"]
    resolution_reason: str | None = Field(
        default=None,
        alias="resolutionReason",
    )
    provider: str | None = None
    provider_match_name: str | None = Field(
        default=None,
        alias="providerMatchName",
        exclude=True,
    )
    verified_aliases: list[str] = Field(
        default_factory=list,
        alias="verifiedAliases",
    )
    verified_vietnamese_aliases: list[str] = Field(
        default_factory=list,
        alias="verifiedVietnameseAliases",
    )
    match_options: list[PlaceMatchOption] = Field(
        default_factory=list,
        alias="matchOptions",
    )
    external_id: str | None = Field(default=None, alias="externalId")
    name: str
    address: str | None = None
    city: str | None = None
    country: str | None = None
    country_code: str | None = Field(default=None, alias="countryCode")
    primary_area: str | None = Field(default=None, alias="primaryArea")
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    description: str | None = None
    data_confidence: Literal["low", "medium", "high"] = Field(
        default="low",
        alias="dataConfidence",
    )
    fetched_at: datetime | None = Field(default=None, alias="fetchedAt")
    attribution: str | None = None
    place_id: str | None = Field(default=None, alias="placeId")
    place_type: str | None = Field(default=None, alias="placeType")
    region_key: str | None = Field(default=None, alias="regionKey")
    place_status: str | None = Field(default=None, alias="placeStatus")
    opening_hours: list[dict] = Field(default_factory=list, alias="openingHours")
    typical_duration_minutes: int | None = Field(
        default=None, alias="typicalDurationMinutes"
    )
    source_platform: str | None = Field(default=None, alias="sourcePlatform")
    source_link: str | None = Field(default=None, alias="sourceLink")
    plus_code: str | None = Field(default=None, alias="plusCode")
    rating: Decimal | None = None
    review_count: int | None = Field(default=None, alias="reviewCount")
    place_revision: int = Field(default=1, alias="placeRevision")
    place_metadata: dict = Field(default_factory=dict, alias="placeMetadata")
    provider_attempts: list["PlaceResolutionAttempt"] = Field(
        default_factory=list,
        alias="providerAttempts",
        exclude=True,
    )

    model_config = {"populate_by_name": True}


class PlaceResolutionAttempt(BaseModel):
    candidate: str
    provider: str
    attempted_queries: list[str] = Field(
        default_factory=list,
        alias="attemptedQueries",
    )
    alias_query_count: int = Field(default=0, alias="aliasQueryCount")
    queue_wait_seconds: float = Field(default=0.0, alias="queueWaitSeconds")
    execution_seconds: float = Field(default=0.0, alias="executionSeconds")
    outcome: Literal["resolved", "unresolved", "error", "timeout", "cache_hit"]
    rejection_reason: str | None = Field(default=None, alias="rejectionReason")

    model_config = {"populate_by_name": True}


class GoogleMapsSearchBatch(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)
    queue_wait_seconds: float = 0.0
    execution_seconds: float = 0.0


class GoogleMapsSearchTimeout(asyncio.TimeoutError):
    def __init__(
        self,
        *,
        queue_wait_seconds: float,
        execution_seconds: float,
    ) -> None:
        super().__init__("Google Maps worker job exceeded its deadline.")
        self.queue_wait_seconds = queue_wait_seconds
        self.execution_seconds = execution_seconds


class GoogleMapsSearchClient:
    """Lightweight client for searching Google Maps (autocomplete fallback)."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        work_dir: Path | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not executable and work_dir is None:
            raise ValueError(
                "google-maps-scraper needs an executable or shared work_dir"
            )
        self.executable = executable
        self.work_dir = work_dir
        self.timeout_seconds = timeout_seconds

    async def search(
        self,
        query: str,
        *,
        region: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Search Google Maps for a query and return raw results."""
        if not query.strip():
            return []

        search_query = query
        if region:
            search_query = f"{query}, {region}"

        if self.work_dir is not None:
            return await self._search_via_worker(search_query, limit)
        return await self._search_via_cli(search_query, limit)

    async def _search_via_cli(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not self.executable:
            raise ValueError("Google Maps scraper executable is missing.")
        with tempfile.TemporaryDirectory(
            prefix="vsf-gmaps-search-"
        ) as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "queries.txt"
            results_path = temp_path / "results.json"
            input_path.write_text(query + "\n", encoding="utf-8")
            started_at = time.perf_counter()
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-input",
                str(input_path),
                "-results",
                str(results_path),
                "-json",
                "-depth",
                "1",
                "-c",
                "1",
                "-lang",
                "vi",
                "-exit-on-inactivity",
                "10s",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    "DISABLE_TELEMETRY": "1",
                },
                start_new_session=True,
            )
            try:
                _, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.communicate()
                return []
            if process.returncode != 0 or not results_path.exists():
                return []
            batch = GoogleMapsSearchBatch(
                results=_load_google_maps_output(
                    results_path.read_text(encoding="utf-8")
                ),
                execution_seconds=time.perf_counter() - started_at,
            )
            return batch.results[:limit]

    async def _search_via_worker(
        self,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if self.work_dir is None:
            raise ValueError("Google Maps scraper work directory is missing.")

        request_id = uuid.uuid4().hex
        requests_dir = self.work_dir / "requests"
        responses_dir = self.work_dir / "responses"
        errors_dir = self.work_dir / "errors"
        cancellations_dir = self.work_dir / "cancellations"
        for directory in (
            requests_dir,
            responses_dir,
            errors_dir,
            cancellations_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        temporary_request_path = requests_dir / f".{request_id}.tmp"
        request_path = requests_dir / f"{request_id}.json"
        response_path = responses_dir / f"{request_id}.json"
        error_path = errors_dir / f"{request_id}.txt"
        cancellation_path = cancellations_dir / f"{request_id}.cancel"
        created_at_ms = int(time.time() * 1000)
        deadline_at_ms = created_at_ms + int(self.timeout_seconds * 1000)
        temporary_request_path.write_text(
            json.dumps(
                {
                    "queries": [query],
                    "createdAtMs": created_at_ms,
                    "deadlineAtMs": deadline_at_ms,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.replace(temporary_request_path, request_path)

        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        try:
            while asyncio.get_running_loop().time() < deadline:
                if response_path.exists():
                    try:
                        batch = _load_google_maps_worker_response(
                            response_path.read_text(encoding="utf-8")
                        )
                        response_path.unlink(missing_ok=True)
                        return batch.results[:limit]
                    except Exception:
                        return []
                if error_path.exists():
                    error_path.unlink(missing_ok=True)
                    return []
                await asyncio.sleep(0.1)
            _write_google_maps_cancellation(cancellation_path)
            return []
        except Exception:
            _write_google_maps_cancellation(cancellation_path)
            return []
        finally:
            for path in (request_path,):
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass


class PlaceResolver(ABC):
    @abstractmethod
    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        raise NotImplementedError

    async def resolve_many(
        self,
        candidates: list[UnifiedPlaceCandidate],
        *,
        destination: str,
    ) -> list[PlaceResolution]:
        return [
            await self.resolve(candidate, destination=destination)
            for candidate in candidates
        ]


class ProvisionalPlaceResolver(PlaceResolver):
    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        return PlaceResolution(
            candidate=candidate,
            status="unresolved",
            resolutionReason="provider_not_configured",
            name=candidate.name,
            address=candidate.address_hint,
            city=_effective_search_region(candidate, destination) or None,
            dataConfidence="low",
        )


class FallbackPlaceResolver(PlaceResolver):
    def __init__(
        self,
        primary: PlaceResolver,
        fallback: PlaceResolver,
        *,
        verified_alias_repository: VerifiedPlaceAliasRepository | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.verified_alias_repository = verified_alias_repository

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        primary_result = await self.primary.resolve(
            candidate,
            destination=destination,
        )
        if _is_usable_resolution(primary_result):
            return primary_result
        if not _should_fallback_to_provider(primary_result):
            return primary_result

        fallback_result = await self.fallback.resolve(
            candidate,
            destination=destination,
        )
        fallback_result = fallback_result.model_copy(
            update={
                "provider_attempts": [
                    *primary_result.provider_attempts,
                    *fallback_result.provider_attempts,
                ],
                "match_options": _merge_match_options(
                    primary_result.match_options,
                    fallback_result.match_options,
                ),
            }
        )
        if _is_usable_resolution(fallback_result):
            self._learn_verified_google_aliases(fallback_result)
            return fallback_result

        reasons = [
            reason
            for reason in (
                _provider_reason(primary_result, "primary_unresolved"),
                _provider_reason(fallback_result, "fallback_unresolved"),
            )
            if reason
        ]
        return fallback_result.model_copy(
            update={"resolution_reason": ";".join(reasons)}
        )

    async def resolve_many(
        self,
        candidates: list[UnifiedPlaceCandidate],
        *,
        destination: str,
    ) -> list[PlaceResolution]:
        primary_results = await self.primary.resolve_many(
            candidates,
            destination=destination,
        )
        fallback_indexes = [
            index
            for index, result in enumerate(primary_results)
            if _should_fallback_to_provider(result)
        ]
        if not fallback_indexes:
            return primary_results

        fallback_results = await self.fallback.resolve_many(
            [candidates[index] for index in fallback_indexes],
            destination=destination,
        )
        combined_results = list(primary_results)
        for index, fallback_result in zip(
            fallback_indexes,
            fallback_results,
            strict=True,
        ):
            primary_result = primary_results[index]
            fallback_result = fallback_result.model_copy(
                update={
                    "provider_attempts": [
                        *primary_result.provider_attempts,
                        *fallback_result.provider_attempts,
                    ],
                    "match_options": _merge_match_options(
                        primary_result.match_options,
                        fallback_result.match_options,
                    ),
                }
            )
            if _is_usable_resolution(fallback_result):
                self._learn_verified_google_aliases(fallback_result)
                combined_results[index] = fallback_result
                continue
            reasons = [
                reason
                for reason in (
                    _provider_reason(primary_result, "primary_unresolved"),
                    _provider_reason(fallback_result, "fallback_unresolved"),
                )
                if reason
            ]
            combined_results[index] = fallback_result.model_copy(
                update={"resolution_reason": ";".join(reasons)}
            )
        return combined_results

    def _learn_verified_google_aliases(
        self,
        resolution: PlaceResolution,
    ) -> None:
        repository = self.verified_alias_repository
        if (
            repository is None
            or resolution.provider != "google_maps_scraper"
            or not resolution.external_id
            or not resolution.verified_aliases
            or resolution.latitude is None
            or resolution.longitude is None
            or resolution.fetched_at is None
        ):
            return
        try:
            repository.upsert_verified_google_aliases(
                external_id=resolution.external_id,
                canonical_name=(
                    resolution.provider_match_name or resolution.name
                ),
                aliases=resolution.verified_aliases,
                place_type=resolution.place_type or "other",
                address=resolution.address,
                city=resolution.city,
                country=resolution.country,
                country_code=resolution.country_code,
                primary_area=resolution.primary_area,
                latitude=resolution.latitude,
                longitude=resolution.longitude,
                region_key=(
                    resolution.region_key
                    or _region_key_for_catalog(resolution.city or "")
                ),
                source_link=resolution.source_link,
                fetched_at=resolution.fetched_at,
                attribution=resolution.attribution,
            )
        except Exception:
            # Catalog learning is opportunistic and must never turn a verified
            # place resolution into a failed Explorer intake.
            return


def _merge_match_options(
    *groups: list[PlaceMatchOption],
    limit: int = 5,
) -> list[PlaceMatchOption]:
    unique: dict[tuple[str, str, str], PlaceMatchOption] = {}
    for option in (option for group in groups for option in group):
        key = (
            option.provider,
            option.external_id or option.place_id or "",
            _normalized(option.name),
        )
        previous = unique.get(key)
        if previous is None or option.score > previous.score:
            unique[key] = option
    ranked = sorted(
        unique.values(),
        key=lambda option: (
            not option.selected,
            -option.score,
            option.provider,
            option.name,
        ),
    )[:limit]
    return [
        option.model_copy(update={"rank": rank})
        for rank, option in enumerate(ranked, start=1)
    ]


class DatabasePlaceResolver(PlaceResolver):
    provider_name = "database"

    def __init__(
        self,
        repository: PlaceLookupRepository,
        *,
        top_k: int = 5,
        minimum_score: float = DEFAULT_PLACE_RESOLUTION_MINIMUM_SCORE,
        minimum_margin: float = 0.08,
        max_concurrency: int = 1,
        repository_context_factory: (
            Callable[[], ContextManager[PlaceLookupRepository]] | None
        ) = None,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not 0.0 <= minimum_score <= 1.0:
            raise ValueError("minimum_score must be between 0 and 1")
        if not 0.0 <= minimum_margin <= 1.0:
            raise ValueError("minimum_margin must be between 0 and 1")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if max_concurrency > 1 and repository_context_factory is None:
            raise ValueError(
                "repository_context_factory is required for concurrent database resolution"
            )
        self.repository = repository
        self.top_k = top_k
        self.minimum_score = minimum_score
        self.minimum_margin = minimum_margin
        self.max_concurrency = max_concurrency
        self.repository_context_factory = repository_context_factory

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        return self._resolve_sync(candidate, destination=destination)

    def _resolve_sync(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        started_at = time.perf_counter()
        search_region = _effective_search_region(candidate, destination)
        lookup_queries = _candidate_lookup_names(candidate)
        ranked = self._ranked_records(candidate, destination=destination)
        if not ranked:
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="not_found",
                    provider=self.provider_name,
                ),
                provider=self.provider_name,
                started_at=started_at,
                attempted_queries=lookup_queries,
            )
        match_options = _database_match_options(
            candidate,
            ranked,
            destination=destination,
            provider=self.provider_name,
        )
        equivalent_duplicate = _select_equivalent_duplicate_record(
            candidate,
            ranked,
            minimum_margin=self.minimum_margin,
        )
        best_score, record = ranked[0]
        if (
            len(ranked) > 1
            and best_score - ranked[1][0] < self.minimum_margin
            and equivalent_duplicate is None
        ):
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="ambiguous_name",
                    provider=self.provider_name,
                ).model_copy(update={"match_options": match_options}),
                provider=self.provider_name,
                started_at=started_at,
                attempted_queries=lookup_queries,
            )
        if equivalent_duplicate is not None:
            record = equivalent_duplicate
        if best_score <= self.minimum_score:
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="low_database_score",
                    provider=self.provider_name,
                ).model_copy(update={"match_options": match_options}),
                provider=self.provider_name,
                started_at=started_at,
                attempted_queries=lookup_queries,
            )
        if (
            _database_candidate_is_generic(candidate)
            and _database_source_location_score(candidate, record) <= 0
        ):
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="generic_name_without_source_location",
                    provider=self.provider_name,
                ).model_copy(update={"match_options": match_options}),
                provider=self.provider_name,
                started_at=started_at,
                attempted_queries=lookup_queries,
            )
        used_source_location = _database_source_location_score(
            candidate,
            record,
        ) > 0
        return _with_provider_attempt(
            _database_resolution(
                candidate,
                record,
                search_region=search_region,
                provider=self.provider_name,
                reason=(
                    "collapsed_equivalent_duplicate"
                    if equivalent_duplicate is not None
                    else (
                        "matched_source_location"
                        if used_source_location and len(ranked) > 1
                        else None
                    )
                ),
            ).model_copy(
                update={
                    "match_options": _mark_selected_match(
                        match_options,
                        place_id=record.id,
                    )
                }
            ),
            provider=self.provider_name,
            started_at=started_at,
            attempted_queries=lookup_queries,
        )

    async def resolve_many(
        self,
        candidates: list[UnifiedPlaceCandidate],
        *,
        destination: str,
    ) -> list[PlaceResolution]:
        if self.max_concurrency == 1 or self.repository_context_factory is None:
            results = [
                await self.resolve(candidate, destination=destination)
                for candidate in candidates
            ]
        else:
            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def resolve_one(
                candidate: UnifiedPlaceCandidate,
            ) -> PlaceResolution:
                async with semaphore:
                    return await asyncio.to_thread(
                        self._resolve_with_fresh_repository,
                        candidate,
                        destination,
                    )

            results = list(
                await asyncio.gather(
                    *(resolve_one(candidate) for candidate in candidates)
                )
            )
        for index, result in enumerate(results):
            if result.resolution_reason != "ambiguous_name":
                continue
            candidate = candidates[index]
            matches = self._matching_records(candidate, destination=destination)
            if _database_candidate_is_generic(candidate):
                matches = [
                    record
                    for record in matches
                    if _database_source_location_score(candidate, record) > 0
                ]
            elif _candidate_has_authoritative_address(candidate):
                matches = [
                    record
                    for record in matches
                    if _database_source_location_score(candidate, record) > 0
                ]
            record = _select_record_from_route_context(
                index,
                candidates=candidates,
                results=results,
                records=matches,
            )
            if record is None:
                continue
            results[index] = _database_resolution(
                candidate,
                record,
                search_region=_effective_search_region(candidate, destination),
                provider=self.provider_name,
                reason="matched_route_context",
            ).model_copy(
                update={
                    "match_options": _mark_selected_match(
                        result.match_options,
                        place_id=record.id,
                    ),
                    "provider_attempts": [
                        result.provider_attempts[0].model_copy(
                            update={
                                "outcome": "resolved",
                                "rejection_reason": None,
                            }
                        )
                    ]
                }
            )
        return results

    def _resolve_with_fresh_repository(
        self,
        candidate: UnifiedPlaceCandidate,
        destination: str,
    ) -> PlaceResolution:
        if self.repository_context_factory is None:
            return self._resolve_sync(candidate, destination=destination)
        with self.repository_context_factory() as repository:
            worker = type(self)(
                repository,
                top_k=self.top_k,
                minimum_score=self.minimum_score,
                minimum_margin=self.minimum_margin,
            )
            return worker._resolve_sync(candidate, destination=destination)

    def _matching_records(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> list[PlaceLookupRecord]:
        return [
            record
            for score, record in self._ranked_records(
                candidate,
                destination=destination,
            )
            if score > self.minimum_score
            and _database_name_similarity(candidate, record) >= 0.70
        ]

    def _ranked_records(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> list[tuple[float, PlaceLookupRecord]]:
        from app.modules.plans.trip_theme_planner.region_context import (
            normalize_search_region_key,
        )

        search_region = _effective_search_region(candidate, destination)
        region_key = (
            normalize_search_region_key(search_region, destination)
            if search_region
            else None
        )
        candidate_names = _candidate_lookup_names(candidate)
        name_matches = self.repository.search_active_by_names(
            candidate_names,
            limit=DEFAULT_DATABASE_NAME_CANDIDATE_LIMIT,
        )
        candidates_by_id = {
            record.id: record
            for record in name_matches
        }
        ranked = [
            (
                _database_candidate_score(
                    candidate,
                    record,
                    search_region=search_region,
                    region_key=region_key,
                ),
                record,
            )
            for record in candidates_by_id.values()
            if _database_record_is_eligible(candidate, record)
        ]
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return ranked[: self.top_k]


class KnowledgeGraphPlaceResolver(DatabasePlaceResolver):
    """Resolve places from the canonical Knowledge Graph catalog."""

    provider_name = "knowledge_graph"


def _database_resolution(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
    *,
    search_region: str,
    provider: str = "database",
    reason: str | None = None,
) -> PlaceResolution:
    metadata = (
        record.metadata_json
        if isinstance(record.metadata_json, dict)
        else {}
    )
    verified_aliases, verified_vietnamese_aliases = _verified_aliases_from_metadata(
        metadata
    )
    verified_aliases = list(
        dict.fromkeys(
            [record.name, *verified_aliases, *candidate.vietnamese_names]
        )
    )
    verified_vietnamese_aliases = list(
        dict.fromkeys(
            [*verified_vietnamese_aliases, *candidate.vietnamese_names]
        )
    )
    return PlaceResolution(
        candidate=candidate,
        status="resolved",
        resolutionReason=reason,
        provider=provider,
        externalId=record.id,
        placeId=record.id,
        name=record.name,
        verifiedAliases=verified_aliases,
        verifiedVietnameseAliases=verified_vietnamese_aliases,
        placeType=record.place_type,
        address=record.address or candidate.address_hint,
        city=record.city or search_region,
        country=record.country,
        countryCode=(
            record.country_code.upper()
            if record.country_code
            else None
        ),
        primaryArea=record.primary_area,
        latitude=record.latitude,
        longitude=record.longitude,
        description=_optional_text(metadata.get("description")),
        dataConfidence=(
            record.data_confidence
            if record.data_confidence in {"low", "medium", "high"}
            else "medium"
        ),
        regionKey=getattr(record, "region_key", None),
        placeStatus=getattr(record, "status", "active"),
        openingHours=list(getattr(record, "opening_hours", []) or []),
        typicalDurationMinutes=getattr(
            record, "typical_duration_minutes", None
        ),
        sourcePlatform=getattr(record, "source_platform", None),
        sourceLink=getattr(record, "source_link", None),
        plusCode=getattr(record, "plus_code", None),
        rating=getattr(record, "rating", None),
        reviewCount=getattr(record, "review_count", None),
        placeRevision=getattr(record, "revision", 1),
        placeMetadata=metadata,
        fetchedAt=record.source_fetched_at,
        attribution=(
            _optional_text(metadata.get("attribution"))
            or "VSF Travel place catalog"
        ),
    )


def _database_match_options(
    candidate: UnifiedPlaceCandidate,
    ranked: list[tuple[float, PlaceLookupRecord]],
    *,
    destination: str,
    provider: str = "database",
) -> list[PlaceMatchOption]:
    search_region = _effective_search_region(candidate, destination)
    options: list[PlaceMatchOption] = []
    for rank, (score, record) in enumerate(ranked, start=1):
        name_score = _database_name_similarity(candidate, record)
        region_score = (
            1.0
            if _database_record_matches_region(
                record,
                search_region=search_region,
                region_key=None,
            )
            else 0.0
        )
        options.append(
            PlaceMatchOption(
                rank=rank,
                matchSource="knowledge_graph" if provider == "knowledge_graph" else "places_db",
                provider=provider,
                placeId=record.id,
                externalId=record.id,
                name=record.name,
                address=record.address,
                latitude=(float(record.latitude) if record.latitude is not None else None),
                longitude=(float(record.longitude) if record.longitude is not None else None),
                score=round(max(0.0, min(1.0, score)), 4),
                scoreComponents={
                    "nameSimilarity": round(max(0.0, min(1.0, name_score)), 4),
                    "regionMatch": region_score,
                },
                fetchedAt=(
                    record.source_fetched_at.isoformat()
                    if record.source_fetched_at is not None
                    else None
                ),
            )
        )
    return options


def _mark_selected_match(
    options: list[PlaceMatchOption],
    *,
    place_id: str | None = None,
    external_id: str | None = None,
) -> list[PlaceMatchOption]:
    return [
        option.model_copy(
            update={
                "selected": bool(
                    (place_id and option.place_id == place_id)
                    or (external_id and option.external_id == external_id)
                )
            }
        )
        for option in options
    ]


def _verified_aliases_from_metadata(metadata: dict) -> tuple[list[str], list[str]]:
    verified: list[str] = []
    vietnamese: list[str] = []
    for value in metadata.get("verifiedAliases", []):
        if isinstance(value, dict):
            name = _optional_text(value.get("name"))
            language = _optional_text(value.get("language"))
        else:
            name = _optional_text(value)
            language = None
        if not name:
            continue
        verified.append(name)
        if language == "vi" or _looks_vietnamese(name):
            vietnamese.append(name)
    for value in metadata.get("vietnameseNames", []):
        name = _optional_text(value)
        if name:
            verified.append(name)
            vietnamese.append(name)
    return list(dict.fromkeys(verified)), list(dict.fromkeys(vietnamese))


def _looks_vietnamese(value: str) -> bool:
    return any(character in "ăâđêôơưĂÂĐÊÔƠƯ" for character in value) or any(
        unicodedata.combining(character)
        for character in unicodedata.normalize("NFD", value)
    )


class GoogleMapsScraperPlaceResolver(PlaceResolver):
    """Resolve aliases with the Playwright google-maps-scraper worker."""

    provider_name = "google_maps_scraper"

    def __init__(
        self,
        *,
        executable: str | None = None,
        work_dir: Path | None = None,
        timeout_seconds: float = 45.0,
        max_alias_queries: int = 2,
        max_concurrency: int = 2,
        minimum_score: float = DEFAULT_PLACE_RESOLUTION_MINIMUM_SCORE,
    ) -> None:
        if not executable and work_dir is None:
            raise ValueError(
                "google-maps-scraper needs an executable or shared work_dir"
            )
        self.executable = executable
        self.work_dir = work_dir
        self.timeout_seconds = timeout_seconds
        # Explorer may try one observed name and one contextual fallback only.
        self.max_alias_queries = max(1, min(2, max_alias_queries))
        self.max_concurrency = max(1, max_concurrency)
        if not 0.0 <= minimum_score <= 1.0:
            raise ValueError("minimum_score must be between 0 and 1")
        self.minimum_score = minimum_score

    async def resolve_many(
        self,
        candidates: list[UnifiedPlaceCandidate],
        *,
        destination: str,
    ) -> list[PlaceResolution]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def resolve_one(
            candidate: UnifiedPlaceCandidate,
        ) -> PlaceResolution:
            async with semaphore:
                return await self.resolve(candidate, destination=destination)

        results = list(
            await asyncio.gather(*(resolve_one(candidate) for candidate in candidates))
        )
        return _reject_duplicate_google_identities(results)

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        search_region = _effective_search_region(candidate, destination)
        candidate_names = _candidate_lookup_names(candidate)
        queries = _google_maps_alias_queries(
            candidate_names,
            address_hint=_effective_candidate_address_hint(candidate),
            context_hint=_candidate_context_hint(candidate),
            search_region=search_region,
            limit=self.max_alias_queries,
        )
        attempted_query_count = 0
        attempted_queries: list[str] = []
        queue_wait_seconds = 0.0
        execution_seconds = 0.0
        provider_started_at = time.perf_counter()
        try:
            # Query the strongest canonical/context combination first so a
            # successful lookup does not pay for every bilingual alias. Keep
            # the remaining aliases as a quality-preserving fallback.
            first_queries = queries[:1]
            attempted_query_count += len(first_queries)
            attempted_queries.extend(first_queries)
            first_batch = _as_google_maps_search_batch(
                await self._search(first_queries)
            )
            payload = list(first_batch.results)
            queue_wait_seconds += first_batch.queue_wait_seconds
            execution_seconds += first_batch.execution_seconds
            if len(queries) > 1 and not _google_maps_payload_is_usable(
                payload,
                candidate_names=candidate_names,
                search_region=search_region,
                candidate_category=candidate.category.value,
                minimum_score=self.minimum_score,
            ):
                fallback_queries = queries[1:]
                attempted_query_count += len(fallback_queries)
                attempted_queries.extend(fallback_queries)
                fallback_batch = _as_google_maps_search_batch(
                    await self._search(fallback_queries)
                )
                payload.extend(fallback_batch.results)
                queue_wait_seconds += fallback_batch.queue_wait_seconds
                execution_seconds += fallback_batch.execution_seconds
        except GoogleMapsSearchTimeout as exc:
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="timeout",
                    provider=self.provider_name,
                ),
                provider=self.provider_name,
                attempted_queries=attempted_queries,
                alias_query_count=attempted_query_count,
                queue_wait_seconds=queue_wait_seconds + exc.queue_wait_seconds,
                execution_seconds=execution_seconds + exc.execution_seconds,
                outcome="timeout",
            )
        except (
            OSError,
            ValueError,
            TypeError,
            asyncio.TimeoutError,
        ):
            execution_seconds = max(
                execution_seconds,
                time.perf_counter() - provider_started_at - queue_wait_seconds,
            )
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="provider_error",
                    provider=self.provider_name,
                ),
                provider=self.provider_name,
                attempted_queries=attempted_queries,
                alias_query_count=attempted_query_count,
                queue_wait_seconds=queue_wait_seconds,
                execution_seconds=execution_seconds,
                outcome="error",
            )

        if not payload:
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="not_found",
                    provider=self.provider_name,
                ),
                provider=self.provider_name,
                attempted_queries=attempted_queries,
                alias_query_count=attempted_query_count,
                queue_wait_seconds=queue_wait_seconds,
                execution_seconds=execution_seconds,
            )

        result = _best_google_maps_result(
            payload,
            candidate_names=candidate_names,
            search_region=search_region,
            candidate_category=candidate.category.value,
        )
        match_options = _google_maps_match_options(
            payload,
            candidate_names=candidate_names,
            search_region=search_region,
            candidate_category=candidate.category.value,
            minimum_score=self.minimum_score,
        )
        title = _optional_text(result.get("title")) or candidate.name
        address = _google_maps_address(result) or _effective_candidate_address_hint(candidate)
        latitude = _as_decimal(result.get("latitude"))
        longitude = _as_decimal(
            result.get("longitude", result.get("longtitude"))
        )
        coordinates_valid = _coordinates_valid(latitude, longitude)
        rejection_reasons = _google_maps_rejection_reasons(
            result,
            candidate_names=candidate_names,
            search_region=search_region,
            candidate_category=candidate.category.value,
            coordinates_valid=coordinates_valid,
            minimum_score=self.minimum_score,
        )
        status = "resolved" if not rejection_reasons else "unresolved"
        external_identity = (
            _optional_text(result.get("place_id"))
            or _optional_text(result.get("cid"))
            or _optional_text(result.get("data_id"))
        )
        complete_address = result.get("complete_address")
        complete_address_dict = (
            complete_address
            if isinstance(complete_address, dict)
            else {}
        )
        return _with_provider_attempt(
            PlaceResolution(
                candidate=candidate,
                status=status,
                resolutionReason=(
                    None if status == "resolved" else "+".join(rejection_reasons)
                ),
                provider=self.provider_name,
                providerMatchName=title,
                verifiedAliases=(
                    list(
                        dict.fromkeys(
                            name
                            for name in (
                                candidate.name,
                                candidate.original_name,
                                *candidate.vietnamese_names,
                                title,
                            )
                            if name and _normalized(name)
                        )
                    )
                    if status == "resolved"
                    else []
                ),
                verifiedVietnameseAliases=(
                    list(
                        dict.fromkeys(
                            name
                            for name in (
                                *candidate.vietnamese_names,
                                title if _looks_vietnamese(title) else None,
                            )
                            if name
                        )
                    )
                    if status == "resolved"
                    else []
                ),
                matchOptions=(
                    _mark_selected_match(
                        match_options,
                        external_id=external_identity,
                    )
                    if status == "resolved"
                    else match_options
                ),
                externalId=external_identity,
                name=(
                    candidate.vietnamese_names[0]
                    if candidate.vietnamese_names
                    else title
                ),
                placeType=(
                    _optional_text(result.get("category"))
                    or candidate.category.value
                ),
                address=address,
                city=(
                    _optional_text(complete_address_dict.get("city"))
                    or search_region
                ),
                country=_optional_text(complete_address_dict.get("country")),
                countryCode=(
                    _optional_text(complete_address_dict.get("country_code"))
                    or ""
                ).upper()
                or None,
                primaryArea=(
                    _optional_text(complete_address_dict.get("borough"))
                    or _optional_text(complete_address_dict.get("neighborhood"))
                ),
                regionKey=_region_key_for_search(search_region, destination),
                latitude=latitude,
                longitude=longitude,
                description=repair_cp437_utf8_mojibake(
                    _google_maps_description(result) or ""
                ) or None,
                placeStatus="active" if status == "resolved" else "unverified",
                openingHours=_normalized_opening_hours(
                    result.get("opening_hours")
                ),
                sourcePlatform=self.provider_name,
                sourceLink=_optional_text(result.get("link")),
                plusCode=_optional_text(result.get("plus_code")),
                rating=_rating_decimal(
                    result.get("review_rating", result.get("rating"))
                ),
                reviewCount=_non_negative_int(
                    result.get("reviews", result.get("review_count"))
                ),
                placeMetadata=_compact_metadata(
                    {
                        "category": result.get("category"),
                        "imageUrl": result.get("image_url"),
                    }
                ),
                dataConfidence="medium" if status == "resolved" else "low",
                fetchedAt=datetime.now(timezone.utc),
                attribution="Google Maps data via gosom/google-maps-scraper",
            ),
            provider=self.provider_name,
            attempted_queries=attempted_queries,
            alias_query_count=attempted_query_count,
            queue_wait_seconds=queue_wait_seconds,
            execution_seconds=execution_seconds,
        )

    async def _search(
        self,
        queries: list[str],
    ) -> GoogleMapsSearchBatch | list[dict[str, Any]]:
        if not queries:
            return GoogleMapsSearchBatch()
        if self.work_dir is not None:
            return await self._search_via_worker(queries)
        if not self.executable:
            raise ValueError("Google Maps scraper executable is missing.")
        with tempfile.TemporaryDirectory(
            prefix="vsf-google-maps-"
        ) as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "queries.txt"
            results_path = temp_path / "results.json"
            input_path.write_text(
                "\n".join(queries) + "\n",
                encoding="utf-8",
            )
            started_at = time.perf_counter()
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-input",
                str(input_path),
                "-results",
                str(results_path),
                "-json",
                "-depth",
                "1",
                "-c",
                "1",
                "-lang",
                "vi",
                "-exit-on-inactivity",
                "15s",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    "DISABLE_TELEMETRY": "1",
                },
                start_new_session=True,
            )
            try:
                _, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.communicate()
                raise GoogleMapsSearchTimeout(
                    queue_wait_seconds=0.0,
                    execution_seconds=time.perf_counter() - started_at,
                )
            if process.returncode != 0:
                raise ValueError(
                    "Google Maps scraper CLI exited unsuccessfully."
                )
            if not results_path.exists():
                return GoogleMapsSearchBatch(
                    execution_seconds=time.perf_counter() - started_at
                )
            return GoogleMapsSearchBatch(
                results=_load_google_maps_output(
                    results_path.read_text(encoding="utf-8")
                ),
                execution_seconds=time.perf_counter() - started_at,
            )

    async def _search_via_worker(
        self,
        queries: list[str],
    ) -> GoogleMapsSearchBatch:
        if self.work_dir is None:
            raise ValueError("Google Maps scraper work directory is missing.")

        request_id = uuid.uuid4().hex
        requests_dir = self.work_dir / "requests"
        responses_dir = self.work_dir / "responses"
        errors_dir = self.work_dir / "errors"
        cancellations_dir = self.work_dir / "cancellations"
        status_dir = self.work_dir / "status"
        for directory in (
            requests_dir,
            responses_dir,
            errors_dir,
            cancellations_dir,
            status_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        temporary_request_path = requests_dir / f".{request_id}.tmp"
        request_path = requests_dir / f"{request_id}.json"
        response_path = responses_dir / f"{request_id}.json"
        error_path = errors_dir / f"{request_id}.txt"
        cancellation_path = cancellations_dir / f"{request_id}.cancel"
        status_path = status_dir / f"{request_id}.json"
        created_at_ms = int(time.time() * 1000)
        deadline_at_ms = created_at_ms + int(self.timeout_seconds * 1000)
        temporary_request_path.write_text(
            json.dumps(
                {
                    "queries": queries,
                    "createdAtMs": created_at_ms,
                    "deadlineAtMs": deadline_at_ms,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.replace(temporary_request_path, request_path)

        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        try:
            while asyncio.get_running_loop().time() < deadline:
                if response_path.exists():
                    batch = _load_google_maps_worker_response(
                        response_path.read_text(encoding="utf-8")
                    )
                    response_path.unlink(missing_ok=True)
                    return batch
                if error_path.exists():
                    error_path.unlink(missing_ok=True)
                    raise ValueError(
                        "Google Maps scraper worker exited unsuccessfully."
                    )
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            _write_google_maps_cancellation(cancellation_path)
            raise
        finally:
            temporary_request_path.unlink(missing_ok=True)
            request_path.unlink(missing_ok=True)

        queue_wait_seconds, execution_seconds = _worker_timeout_timings(
            status_path,
            created_at_ms=created_at_ms,
        )
        _write_google_maps_cancellation(cancellation_path)
        response_path.unlink(missing_ok=True)
        error_path.unlink(missing_ok=True)
        raise GoogleMapsSearchTimeout(
            queue_wait_seconds=queue_wait_seconds,
            execution_seconds=execution_seconds,
        )


def _unresolved(
    candidate: UnifiedPlaceCandidate,
    search_region: str | None,
    *,
    reason: str,
    provider: str | None = None,
) -> PlaceResolution:
    return PlaceResolution(
        candidate=candidate,
        status="unresolved",
        resolutionReason=reason,
        provider=provider,
        name=candidate.name,
        address=candidate.address_hint,
        city=search_region,
        dataConfidence="low",
    )


def _as_google_maps_search_batch(
    value: GoogleMapsSearchBatch | list[dict[str, Any]],
) -> GoogleMapsSearchBatch:
    if isinstance(value, GoogleMapsSearchBatch):
        return value
    return GoogleMapsSearchBatch(results=value)


def _write_google_maps_cancellation(path: Path) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text("cancelled\n", encoding="utf-8")
    os.replace(temporary, path)


def _worker_timeout_timings(
    status_path: Path,
    *,
    created_at_ms: int,
) -> tuple[float, float]:
    now_ms = int(time.time() * 1000)
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return max(0.0, (now_ms - created_at_ms) / 1000), 0.0
    started_at_ms = status.get("startedAtMs")
    if not isinstance(started_at_ms, (int, float)):
        return max(0.0, (now_ms - created_at_ms) / 1000), 0.0
    return (
        max(0.0, (started_at_ms - created_at_ms) / 1000),
        max(0.0, (now_ms - started_at_ms) / 1000),
    )


def _with_provider_attempt(
    resolution: PlaceResolution,
    *,
    provider: str,
    attempted_queries: list[str] | None = None,
    started_at: float | None = None,
    alias_query_count: int = 0,
    queue_wait_seconds: float = 0.0,
    execution_seconds: float = 0.0,
    outcome: Literal[
        "resolved", "unresolved", "error", "timeout", "cache_hit"
    ] | None = None,
) -> PlaceResolution:
    if started_at is not None:
        execution_seconds += max(0.0, time.perf_counter() - started_at)
    effective_outcome = outcome or (
        "resolved" if _is_usable_resolution(resolution) else "unresolved"
    )
    attempt = PlaceResolutionAttempt(
        candidate=resolution.candidate.name,
        provider=provider,
        attemptedQueries=attempted_queries or [],
        aliasQueryCount=alias_query_count,
        queueWaitSeconds=round(max(0.0, queue_wait_seconds), 3),
        executionSeconds=round(max(0.0, execution_seconds), 3),
        outcome=effective_outcome,
        rejectionReason=(
            None if effective_outcome == "resolved" else resolution.resolution_reason
        ),
    )
    return resolution.model_copy(
        update={"provider_attempts": [*resolution.provider_attempts, attempt]}
    )


def _effective_search_region(
    candidate: UnifiedPlaceCandidate,
    destination: str,
) -> str:
    candidate_region = usable_destination(candidate.search_region)
    destination_region = usable_destination(destination)
    if not candidate_region:
        return destination_region or ""
    if not destination_region:
        return candidate_region

    from app.modules.plans.trip_theme_planner.region_context import (
        normalize_region_key,
        normalize_search_region_key,
    )

    search_key = normalize_search_region_key(
        candidate_region,
        destination_region,
    )
    destination_key = normalize_region_key(destination_region)
    if (
        search_key.startswith(f"{destination_key},")
        and _normalized(destination_region) not in _normalized(candidate_region)
    ):
        return f"{candidate_region}, {destination_region}"
    if search_key == destination_key:
        return destination_region
    return candidate_region


def _reject_duplicate_google_identities(
    results: list[PlaceResolution],
) -> list[PlaceResolution]:
    identities: dict[str, list[int]] = {}
    for index, result in enumerate(results):
        if not _is_usable_resolution(result):
            continue
        if result.external_id:
            identity = f"id:{result.external_id}"
        else:
            identity = (
                f"coord:{round(float(result.latitude), 5)}:"
                f"{round(float(result.longitude), 5)}"
            )
        identities.setdefault(identity, []).append(index)

    rejected = list(results)
    for indexes in identities.values():
        if len(indexes) < 2:
            continue
        candidate_keys = {
            _normalized(results[index].candidate.name) for index in indexes
        }
        if len(candidate_keys) < 2:
            continue
        duplicate_results = [results[index] for index in indexes]
        if _duplicate_results_share_provider_name(duplicate_results):
            merged_candidate = _merge_identity_alias_candidates(
                [result.candidate for result in duplicate_results]
            )
            for index in indexes:
                rejected[index] = results[index].model_copy(
                    update={
                        "candidate": merged_candidate,
                        "verified_aliases": list(
                            dict.fromkeys(
                                alias
                                for result in duplicate_results
                                for alias in result.verified_aliases
                            )
                        ),
                        "verified_vietnamese_aliases": list(
                            dict.fromkeys(
                                alias
                                for result in duplicate_results
                                for alias in result.verified_vietnamese_aliases
                            )
                        ),
                        "match_options": _merge_match_options(
                            *(result.match_options for result in duplicate_results)
                        ),
                    }
                )
            continue
        for index in indexes:
            attempts = [
                attempt.model_copy(
                    update={
                        "outcome": "unresolved",
                        "rejection_reason": "duplicate_provider_identity",
                    }
                )
                for attempt in results[index].provider_attempts
            ]
            rejected[index] = results[index].model_copy(
                update={
                    "status": "unresolved",
                    "resolution_reason": "duplicate_provider_identity",
                    "data_confidence": "low",
                    "provider_attempts": attempts,
                }
            )
    return rejected


def _duplicate_results_share_provider_name(
    results: list[PlaceResolution],
) -> bool:
    """Allow spelling aliases only when the provider names one canonical POI.

    Equal coordinates alone are not sufficient: a scraper can accidentally
    return the same map centre for unrelated candidates. The resolved provider
    name must therefore agree across the duplicate group before downstream
    canonical dedupe may merge it.
    """
    provider_names = {
        _normalized(result.provider_match_name or result.name)
        for result in results
    }
    provider_names.discard("")
    return len(provider_names) == 1


def _merge_identity_alias_candidates(
    candidates: list[UnifiedPlaceCandidate],
) -> UnifiedPlaceCandidate:
    preferred = max(
        enumerate(candidates),
        key=lambda item: (*_candidate_identity_authority(item[1]), -item[0]),
    )[1]
    sources = []
    seen_sources: set[tuple[str, str | None]] = set()
    for candidate in candidates:
        for source in candidate.sources:
            key = (source.type.value, source.url)
            if key not in seen_sources:
                sources.append(source)
                seen_sources.add(key)

    alias_names = list(
        dict.fromkeys(
            name
            for candidate in candidates
            for name in (
                candidate.name,
                candidate.original_name,
                *candidate.search_names,
                *candidate.alternate_names,
            )
            if name and name != preferred.name
        )
    )
    return preferred.model_copy(
        update={
            "search_names": list(
                dict.fromkeys([*preferred.search_names, *alias_names])
            ),
            "alternate_names": list(
                dict.fromkeys([*preferred.alternate_names, *alias_names])
            ),
            "observed_aliases": list(
                {
                    (alias.value.casefold(), alias.source): alias
                    for candidate in candidates
                    for alias in candidate.observed_aliases
                }.values()
            ),
            "generated_lookup_aliases": list(
                {
                    (alias.value.casefold(), alias.language): alias
                    for candidate in candidates
                    for alias in candidate.generated_lookup_aliases
                }.values()
            ),
            "sources": sources,
            "source_evidence": {
                key: value
                for candidate in candidates
                for key, value in candidate.source_evidence.items()
            },
            "confidence": max(candidate.confidence for candidate in candidates),
            "priority": min(candidate.priority for candidate in candidates),
            "source_order": min(
                (
                    candidate.source_order
                    for candidate in candidates
                    if candidate.source_order is not None
                ),
                default=None,
            ),
            "source_day": min(
                (
                    candidate.source_day
                    for candidate in candidates
                    if candidate.source_day is not None
                ),
                default=None,
            ),
        }
    )


def _candidate_identity_authority(
    candidate: UnifiedPlaceCandidate,
) -> tuple[int, int, float]:
    source_rank = next(
        (
            rank
            for source, rank in (
                ("metadata", 4),
                ("caption", 3),
                ("ocr", 2),
                ("stt", 1),
            )
            if candidate.source_evidence.get(source)
        ),
        0,
    )
    return source_rank, {"low": 0, "medium": 1, "high": 2}[candidate.authority], candidate.confidence


def _region_key_for_catalog(value: str) -> str:
    from app.modules.plans.trip_theme_planner.region_context import normalize_region_key

    normalized = normalize_region_key(value) if value.strip() else ""
    return normalized or "vn,unmapped"


def _region_key_for_search(search_region: str, destination: str) -> str:
    from app.modules.plans.trip_theme_planner.region_context import (
        normalize_region_key,
        normalize_search_region_key,
    )

    region = usable_destination(search_region)
    trip_destination = usable_destination(destination)
    if region and trip_destination:
        return normalize_search_region_key(region, trip_destination)
    if region:
        return normalize_region_key(region)
    if trip_destination:
        return normalize_region_key(trip_destination)
    return "vn,unmapped"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _as_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _non_negative_int(value: Any) -> int | None:
    parsed = _as_int(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _rating_decimal(value: Any) -> Decimal | None:
    parsed = _as_decimal(value)
    if parsed is None or parsed < Decimal("0") or parsed > Decimal("5"):
        return None
    return parsed


def _normalized_opening_hours(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _compact_metadata(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: normalized
        for key, value in values.items()
        if (normalized := _optional_text(value)) is not None
    }


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_usable_resolution(result: PlaceResolution) -> bool:
    return (
        result.status == "resolved"
        and result.latitude is not None
        and result.longitude is not None
    )


def _should_fallback_to_provider(result: PlaceResolution) -> bool:
    """Use an external provider only when the catalog has no safe identity.

    An ambiguous catalog result already contains real Knowledge Graph options.
    Sending the same ambiguous name to Google is both wasteful and can replace
    reviewed catalog identities with an unrelated provider result.
    """
    return (
        not _is_usable_resolution(result)
        and result.resolution_reason != "ambiguous_name"
    )


def _provider_reason(
    result: PlaceResolution,
    default_reason: str,
) -> str:
    provider = result.provider or "unknown"
    reason = result.resolution_reason or default_reason
    return f"{provider}:{reason}"

def _localized_name(
    namedetails: dict[str, Any],
    result: dict[str, Any],
) -> str | None:
    for key in (
        "name:vi",
        "official_name:vi",
        "short_name:vi",
        "name",
    ):
        value = _optional_text(namedetails.get(key))
        if value:
            return value
    return _optional_text(result.get("name"))


def _resolved_display_name(
    candidate: UnifiedPlaceCandidate,
    *,
    namedetails: dict[str, Any],
    result: dict[str, Any],
    search_region: str,
) -> str:
    if candidate.vietnamese_names:
        return candidate.vietnamese_names[0]
    provider_name = _localized_name(namedetails, result)
    candidate_names = _candidate_lookup_names(candidate)
    provider_has_candidate_match = _any_name_matches(
        candidate_names,
        display_name=_optional_text(result.get("display_name")),
        provider_name=provider_name or "",
        namedetails=namedetails,
    )
    if (
        provider_name
        and provider_has_candidate_match
        and _normalized(provider_name) != _normalized(search_region)
    ):
        return provider_name
    return next(
        iter(
            candidate.vietnamese_names
            or candidate.english_names
            or [candidate.name]
        )
    )


def _database_names(record: PlaceLookupRecord) -> list[str]:
    metadata = (
        record.metadata_json
        if isinstance(record.metadata_json, dict)
        else {}
    )
    raw_aliases: list[Any] = []
    for key in (
        "aliases",
        "searchNames",
        "englishNames",
        "vietnameseNames",
        "alternateNames",
    ):
        value = metadata.get(key)
        if isinstance(value, list):
            raw_aliases.extend(value)
    for key in (
        "originalName",
        "officialName",
        "nameEn",
        "nameVi",
    ):
        value = metadata.get(key)
        if value:
            raw_aliases.append(value)
    return list(dict.fromkeys(
        str(value)
        for value in (record.name, *raw_aliases)
        if value and _normalized(str(value))
    ))


def _database_candidate_score(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
    *,
    search_region: str,
    region_key: str | None,
) -> float:
    name_score = _database_name_similarity(candidate, record)
    region_score = 0.08 if _database_record_matches_region(
        record,
        search_region=search_region,
        region_key=region_key,
    ) else 0.0
    location_score = _database_source_location_score(candidate, record)
    category_score = _database_category_score(candidate, record)
    confidence_score = {
        "medium": 0.01,
        "high": 0.02,
    }.get(record.data_confidence, 0.0)
    return max(
        0.0,
        min(
            1.0,
            name_score * 0.80
            + region_score
            + location_score
            + category_score
            + confidence_score,
        ),
    )


def _database_name_similarity(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
) -> float:
    return max(
        (
            _name_match_score(candidate_name, record_name) / 100.0
            for candidate_name in _candidate_lookup_names(candidate)
            for record_name in _database_names(record)
        ),
        default=0.0,
    )


def _select_equivalent_duplicate_record(
    candidate: UnifiedPlaceCandidate,
    ranked: list[tuple[float, PlaceLookupRecord]],
    *,
    minimum_margin: float,
    maximum_distance_km: float = 0.2,
) -> PlaceLookupRecord | None:
    """Collapse duplicate catalog rows for one physical place.

    This intentionally does not collapse brand branches: the candidate and all
    tied rows must share the exact normalized canonical name, place type,
    region and a sub-200m coordinate cluster.
    """
    if len(ranked) < 2 or _database_candidate_is_generic(candidate):
        return None
    best_score = ranked[0][0]
    tied = [
        record
        for score, record in ranked
        if best_score - score < minimum_margin
    ]
    if len(tied) < 2:
        return None

    canonical_name = _normalized(tied[0].name)
    candidate_names = {
        _normalized(name) for name in _candidate_lookup_names(candidate)
    }
    if not canonical_name or canonical_name not in candidate_names:
        return None
    if any(_normalized(record.name) != canonical_name for record in tied[1:]):
        return None

    place_type = _normalized(tied[0].place_type)
    region_key = getattr(tied[0], "region_key", "")
    if any(
        _normalized(record.place_type) != place_type
        or getattr(record, "region_key", "") != region_key
        for record in tied[1:]
    ):
        return None
    localities = [
        _normalized(record.primary_area or record.address or "")
        for record in tied
    ]
    if any(
        left and right and left not in right and right not in left
        for index, left in enumerate(localities)
        for right in localities[index + 1 :]
    ):
        return None

    coordinates = [
        (float(record.latitude), float(record.longitude))
        for record in tied
        if record.latitude is not None and record.longitude is not None
    ]
    if len(coordinates) != len(tied) or any(
        _haversine_km(left, right) > maximum_distance_km
        for index, left in enumerate(coordinates)
        for right in coordinates[index + 1 :]
    ):
        return None

    def quality(record: PlaceLookupRecord) -> tuple[int, int, int, int, str]:
        return (
            len(_database_names(record)),
            _database_confidence_score(record.data_confidence),
            int(getattr(record, "review_count", None) or 0),
            int(getattr(record, "revision", 1) or 1),
            record.id,
        )

    return max(tied, key=quality)


def _database_record_is_eligible(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
) -> bool:
    if record.latitude is None or record.longitude is None:
        return False
    if getattr(record, "status", "active") != "active":
        return False
    if _authoritative_address_conflicts(candidate, record):
        return False
    candidate_category = candidate.category.value
    record_category = canonical_place_category(record.place_type)
    clear_conflicts = (
        ({"food", "cafe"}, {"nature", "beach", "adventure"}),
        ({"nature", "beach", "adventure"}, {"food", "cafe", "hotel"}),
        ({"hotel"}, {"nature", "beach", "adventure", "transport"}),
    )
    return not any(
        candidate_category in candidate_group
        and record_category in record_group
        for candidate_group, record_group in clear_conflicts
    )


def _authoritative_address_conflicts(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
) -> bool:
    """Reject a catalog branch that contradicts an evidenced source address."""
    source_address = _effective_candidate_address_hint(candidate)
    if not source_address or not candidate.source_evidence.get("metadata"):
        return False
    record_address = str(getattr(record, "address", None) or "")
    if not record_address:
        return False

    source_numbers = set(re.findall(r"\b\d+[A-Za-z]?\b", source_address))
    record_numbers = set(re.findall(r"\b\d+[A-Za-z]?\b", record_address))
    if source_numbers and record_numbers and source_numbers.isdisjoint(record_numbers):
        return True

    source_tokens = set(_name_tokens(source_address))
    record_tokens = set(_name_tokens(record_address))
    meaningful_source_tokens = {
        token for token in source_tokens if len(token) >= 4
    }
    return bool(
        meaningful_source_tokens
        and record_tokens
        and not meaningful_source_tokens.intersection(record_tokens)
    )


def _effective_candidate_address_hint(
    candidate: UnifiedPlaceCandidate,
) -> str | None:
    if candidate.address_hint:
        return candidate.address_hint
    # Keep this conservative: only accept an explicit address introduced by
    # "ở/tại" (or "at/on"), never a free-form place description.
    texts = [*candidate.source_evidence.values(), candidate.source_activity or ""]
    pattern = re.compile(
        r"(?:^|[;,.]\s*|\b(?:ở|tại|at|on)\s+)"
        r"(?P<address>\d{1,4}\s+[A-Za-zÀ-ỹĐđ0-9][^;,.]{3,80})",
        flags=re.IGNORECASE,
    )
    for value in texts:
        if not isinstance(value, str):
            continue
        match = pattern.search(value)
        if match:
            return " ".join(match.group("address").split()).strip()
    return None


def _database_record_matches_region(
    record: PlaceLookupRecord,
    *,
    search_region: str,
    region_key: str | None,
) -> bool:
    if region_key and _record_is_in_region(record, region_key):
        return True
    search_key = _normalized(search_region)
    if not search_key:
        return False
    location_key = _normalized(
        " ".join(
            str(value)
            for value in (
                getattr(record, "primary_area", None),
                getattr(record, "city", None),
                getattr(record, "address", None),
            )
            if value
        )
    )
    return bool(search_key and search_key in location_key)


def _database_source_location_score(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
) -> float:
    region_key = _normalized(candidate.search_region or "")
    hints = [
        hint
        for hint in (_effective_candidate_address_hint(candidate), _candidate_context_hint(candidate))
        if hint
        and len(_name_tokens(hint)) >= 2
        and _normalized(hint) != region_key
    ]
    if not hints:
        return 0.0
    location_key = _normalized(
        " ".join(
            str(value)
            for value in (
                record.name,
                record.address,
                record.primary_area,
                record.city,
            )
            if value
        )
    )
    return 0.12 if any(_normalized(hint) in location_key for hint in hints) else 0.0


def _candidate_has_authoritative_address(
    candidate: UnifiedPlaceCandidate,
) -> bool:
    return bool(
        _effective_candidate_address_hint(candidate)
        and candidate.source_evidence.get("metadata")
    )


def _database_candidate_is_generic(
    candidate: UnifiedPlaceCandidate,
) -> bool:
    return " ".join(_name_tokens(candidate.name)) in GENERIC_VENUE_NAMES


def _database_category_score(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
) -> float:
    candidate_category = candidate.category.value
    record_category = canonical_place_category(record.place_type)
    if candidate_category == "other" or record_category == "other":
        return 0.0
    compatible_groups = (
        {"food", "cafe", "nightlife"},
        {"culture", "attraction"},
        {"nature", "beach", "adventure"},
    )
    if candidate_category == record_category or any(
        candidate_category in group and record_category in group
        for group in compatible_groups
    ):
        return 0.03
    return -0.02


def _name_match_score(candidate_name: str, record_name: str) -> int:
    candidate_tokens = _name_tokens(candidate_name)
    record_tokens = _name_tokens(record_name)
    if not candidate_tokens or not record_tokens:
        return 0
    if candidate_tokens == record_tokens:
        return 100
    if (
        len(candidate_tokens) >= 2
        and _contains_token_sequence(record_tokens, candidate_tokens)
    ):
        return 90 - min(10, len(record_tokens) - len(candidate_tokens))
    if (
        len(record_tokens) >= 2
        and _contains_token_sequence(candidate_tokens, record_tokens)
    ):
        return 86 - min(10, len(candidate_tokens) - len(record_tokens))
    ratio = SequenceMatcher(
        None,
        " ".join(candidate_tokens),
        " ".join(record_tokens),
    ).ratio()
    return round(ratio * 100)


def _select_record_from_route_context(
    index: int,
    *,
    candidates: list[UnifiedPlaceCandidate],
    results: list[PlaceResolution],
    records: list[PlaceLookupRecord],
) -> PlaceLookupRecord | None:
    if len(records) < 2:
        return records[0] if records else None
    anchors = _neighbor_route_anchors(index, candidates, results)
    if not anchors:
        return None

    scores: list[tuple[float, PlaceLookupRecord]] = []
    for record in records:
        if record.latitude is None or record.longitude is None:
            continue
        coordinate = (float(record.latitude), float(record.longitude))
        if len(anchors) == 2:
            left, right = anchors
            score = max(
                0.0,
                _haversine_km(left, coordinate)
                + _haversine_km(coordinate, right)
                - _haversine_km(left, right),
            )
        else:
            score = _haversine_km(anchors[0], coordinate)
        scores.append((score, record))
    if not scores:
        return None
    scores.sort(key=lambda item: item[0])
    best_score, best_record = scores[0]
    if best_score > 15.0:
        return None
    if len(scores) == 1:
        return best_record
    second_score = scores[1][0]
    required_margin = max(0.75, second_score * 0.30)
    if second_score - best_score < required_margin:
        return None
    return best_record


def _neighbor_route_anchors(
    index: int,
    candidates: list[UnifiedPlaceCandidate],
    results: list[PlaceResolution],
) -> list[tuple[float, float]]:
    target = candidates[index]

    def usable(other_index: int) -> tuple[float, float] | None:
        other = candidates[other_index]
        result = results[other_index]
        if result.status != "resolved" or result.latitude is None or result.longitude is None:
            return None
        if target.source_day is not None and other.source_day != target.source_day:
            return None
        target_urls = {source.url for source in target.sources if source.url}
        other_urls = {source.url for source in other.sources if source.url}
        if target_urls and other_urls and target_urls.isdisjoint(other_urls):
            return None
        return float(result.latitude), float(result.longitude)

    previous = next(
        (
            coordinate
            for other_index in range(index - 1, -1, -1)
            if (coordinate := usable(other_index)) is not None
        ),
        None,
    )
    following = next(
        (
            coordinate
            for other_index in range(index + 1, len(candidates))
            if (coordinate := usable(other_index)) is not None
        ),
        None,
    )
    return [coordinate for coordinate in (previous, following) if coordinate]


def _haversine_km(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    left_latitude, left_longitude = left
    right_latitude, right_longitude = right
    latitude_delta = math.radians(right_latitude - left_latitude)
    longitude_delta = math.radians(right_longitude - left_longitude)
    left_latitude_radians = math.radians(left_latitude)
    right_latitude_radians = math.radians(right_latitude)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(left_latitude_radians)
        * math.cos(right_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 6_371.0 * 2 * math.asin(math.sqrt(value))


def _candidate_lookup_names(
    candidate: UnifiedPlaceCandidate,
) -> list[str]:
    """Return at most one Vietnamese and one canonical/source lookup name."""
    has_authoritative_location_anchor = bool(
        candidate.address_hint
        and candidate.source_evidence.get("metadata")
    )
    ordered_names = (
        (
            candidate.name,
            *(alias.value for alias in candidate.observed_aliases),
            candidate.original_name,
        )
        if has_authoritative_location_anchor
        else (
            *candidate.vietnamese_names[:1],
            *candidate.english_names[:1],
            candidate.name,
            *(alias.value for alias in candidate.observed_aliases),
            *(alias.value for alias in candidate.generated_lookup_aliases),
            candidate.original_name,
            *candidate.search_names,
        )
    )

    names: list[str] = []
    seen: set[str] = set()
    for raw_name in ordered_names:
        name = _single_line(raw_name or "")
        key = _normalized(name)
        if not name or not key or key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) == 2:
            break
    # A short alias fully contained in the selected canonical name does not
    # add a useful lookup. For example, searching both "Nhà tù Hỏa Lò" and
    # "Hỏa Lò" repeats the same KG work; retain the more specific name.
    if len(names) == 2:
        long_name, short_name = sorted(names, key=lambda value: len(_lookup_tokens(value)), reverse=True)
        long_tokens = _lookup_tokens(long_name)
        short_tokens = _lookup_tokens(short_name)
        if (
            len(short_tokens) < len(long_tokens)
            and any(
                long_tokens[index:index + len(short_tokens)] == short_tokens
                for index in range(len(long_tokens) - len(short_tokens) + 1)
            )
        ):
            return [long_name]
    return names


def _lookup_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.findall(r"[a-z0-9]+", without_marks)


def _database_confidence_score(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(value, 0)


def _record_is_in_region(
    record: PlaceLookupRecord,
    region_key: str,
) -> bool:
    record_region = getattr(record, "region_key", "")
    return record_region == region_key or record_region.startswith(
        f"{region_key},"
    )


def _google_maps_alias_queries(
    candidate_names: list[str],
    *,
    address_hint: str | None,
    context_hint: str | None = None,
    search_region: str,
    limit: int,
) -> list[str]:
    queries = [
        ", ".join(
            _single_line(part)
            for part in (
                name,
                address_hint,
                context_hint if index == 0 else None,
                search_region,
            )
            if part and _single_line(part)
        )
        for index, name in enumerate(candidate_names[: min(limit, 2)])
    ]
    # A video may name only an activity (for example "egg coffee") while its
    # caption/OCR contains a usable street address.  Name + address queries can
    # still be biased toward the activity text, so keep one final address-only
    # lookup.  The result must still pass the normal identity policy; when it
    # does not, its coordinates are only representative context for the later
    # route-aware recommendation pass.
    if address_hint:
        queries.append(
            ", ".join(
                _single_line(part)
                for part in (address_hint, search_region)
                if part and _single_line(part)
            )
        )
    return list(dict.fromkeys(queries))


def _candidate_context_hint(
    candidate: UnifiedPlaceCandidate,
) -> str | None:
    """Extract a short nearby-place hint from evidenced location wording."""
    texts = [
        *candidate.source_evidence.values(),
        candidate.source_activity or "",
    ]
    place_suffix = (
        r"(?:train\s+street|walking\s+street|night\s+market|old\s+quarter|"
        r"street|lake|market|cathedral|temple|museum|station)"
    )
    for text in texts:
        match = re.search(
            rf"\b(?:along|near|beside|by|next\s+to|around|on)\s+(?:the\s+)?"
            rf"(?P<hint>[a-z0-9À-ỹĐđ'’-]+(?:\s+[a-z0-9À-ỹĐđ'’-]+){{0,3}}\s+"
            rf"{place_suffix})\b",
            text,
            flags=re.IGNORECASE,
        )
        if match is not None:
            return _single_line(match.group("hint"))
    return None


def _load_google_maps_output(value: str) -> list[dict[str, Any]]:
    text = value.strip()
    if not text:
        return []
    try:
        return _google_maps_results(json.loads(text))
    except json.JSONDecodeError:
        results: list[dict[str, Any]] = []
        for line in text.splitlines():
            try:
                results.extend(_google_maps_results(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return results


def _load_google_maps_worker_response(value: str) -> GoogleMapsSearchBatch:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return GoogleMapsSearchBatch(results=_load_google_maps_output(value))
    if not isinstance(payload, dict) or "results" not in payload:
        return GoogleMapsSearchBatch(results=_google_maps_results(payload))
    telemetry = payload.get("telemetry")
    telemetry_dict = telemetry if isinstance(telemetry, dict) else {}
    return GoogleMapsSearchBatch(
        results=_google_maps_results(payload.get("results")),
        queue_wait_seconds=max(
            0.0,
            _as_float(telemetry_dict.get("queueWaitSeconds")),
        ),
        execution_seconds=max(
            0.0,
            _as_float(telemetry_dict.get("executionSeconds")),
        ),
    )


def _google_maps_results(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and (
        "title" in value
        or "latitude" in value
        or "longitude" in value
        or "longtitude" in value
    ):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("places", "results", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [
                    item for item in nested if isinstance(item, dict)
                ]
    return []


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _best_google_maps_result(
    payload: list[dict[str, Any]],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
) -> dict[str, Any]:
    def score(result: dict[str, Any]) -> tuple[float, float, str, str]:
        latitude = _as_decimal(result.get("latitude"))
        longitude = _as_decimal(
            result.get("longitude", result.get("longtitude"))
        )
        resolution_score, _components = _google_maps_resolution_score(
            result,
            candidate_names=candidate_names,
            search_region=search_region,
            candidate_category=candidate_category,
            coordinates_valid=_coordinates_valid(latitude, longitude),
        )
        return (
            resolution_score,
            _as_float(
                result.get("review_rating", result.get("rating"))
            ),
            _optional_text(result.get("place_id")) or "",
            _optional_text(result.get("title")) or "",
        )

    return max(payload, key=score)


def _google_maps_match_options(
    payload: list[dict[str, Any]],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
    minimum_score: float = DEFAULT_PLACE_RESOLUTION_MINIMUM_SCORE,
    limit: int = 5,
) -> list[PlaceMatchOption]:
    scored: list[tuple[float, dict[str, Any], dict[str, float], list[str]]] = []
    for result in payload:
        latitude = _as_decimal(result.get("latitude"))
        longitude = _as_decimal(
            result.get("longitude", result.get("longtitude"))
        )
        coordinates_valid = _coordinates_valid(latitude, longitude)
        reasons = _google_maps_rejection_reasons(
            result,
            candidate_names=candidate_names,
            search_region=search_region,
            candidate_category=candidate_category,
            coordinates_valid=coordinates_valid,
            minimum_score=minimum_score,
        )
        score, components = _google_maps_resolution_score(
            result,
            candidate_names=candidate_names,
            search_region=search_region,
            candidate_category=candidate_category,
            coordinates_valid=coordinates_valid,
        )
        scored.append((score, result, components, reasons))
    scored.sort(
        key=lambda item: (
            -item[0],
            _optional_text(item[1].get("place_id")) or "",
            _optional_text(item[1].get("title")) or "",
        )
    )
    return [
        PlaceMatchOption(
            rank=rank,
            matchSource="external_provider",
            provider="google_maps_scraper",
            externalId=(
                _optional_text(result.get("place_id"))
                or _optional_text(result.get("cid"))
                or _optional_text(result.get("data_id"))
            ),
            name=_optional_text(result.get("title")) or "Unknown place",
            address=_google_maps_address(result),
            latitude=(
                float(value)
                if (value := _as_decimal(result.get("latitude"))) is not None
                else None
            ),
            longitude=(
                float(value)
                if (
                    value := _as_decimal(
                        result.get("longitude", result.get("longtitude"))
                    )
                ) is not None
                else None
            ),
            score=round(max(0.0, min(1.0, score)), 4),
            scoreComponents=components,
            rejectionReasons=reasons,
        )
        for rank, (score, result, components, reasons) in enumerate(
            scored[:limit], start=1
        )
    ]


def _google_maps_payload_is_usable(
    payload: list[dict[str, Any]],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
    minimum_score: float = DEFAULT_PLACE_RESOLUTION_MINIMUM_SCORE,
) -> bool:
    if not payload:
        return False
    result = _best_google_maps_result(
        payload,
        candidate_names=candidate_names,
        search_region=search_region,
        candidate_category=candidate_category,
    )
    return not _google_maps_rejection_reasons(
        result,
        candidate_names=candidate_names,
        search_region=search_region,
        candidate_category=candidate_category,
        coordinates_valid=_coordinates_valid(
            _as_decimal(result.get("latitude")),
            _as_decimal(result.get("longitude", result.get("longtitude"))),
        ),
        minimum_score=minimum_score,
    )


def _google_maps_rejection_reasons(
    result: dict[str, Any],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
    coordinates_valid: bool,
    minimum_score: float = DEFAULT_PLACE_RESOLUTION_MINIMUM_SCORE,
) -> list[str]:
    resolution_score, _components = _google_maps_resolution_score(
        result,
        candidate_names=candidate_names,
        search_region=search_region,
        candidate_category=candidate_category,
        coordinates_valid=coordinates_valid,
    )
    region_matches = _google_maps_result_matches_region(
        result,
        search_region=search_region,
    )
    category_compatible = _category_compatible(
        candidate_category,
        result,
    )
    reasons = [
        reason
        for condition, reason in (
            (region_matches is False, "region_mismatch"),
            (category_compatible is False, "category_mismatch"),
            (not coordinates_valid, "coordinates_missing"),
        )
        if condition
    ]
    if not reasons and resolution_score <= minimum_score:
        reasons.append("low_resolution_score")
    return reasons


def _google_maps_resolution_score(
    result: dict[str, Any],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
    coordinates_valid: bool,
) -> tuple[float, dict[str, float]]:
    title = _optional_text(result.get("title")) or ""
    name_score = max(
        (
            _name_match_score(name, title) / 100.0
            for name in candidate_names
        ),
        default=0.0,
    )
    region_match = _google_maps_result_matches_region(
        result,
        search_region=search_region,
    )
    category_match = _category_compatible(candidate_category, result)
    components = {
        "nameSimilarity": round(name_score, 4),
        "regionMatch": (
            1.0 if region_match is True else 0.5 if region_match is None else 0.0
        ),
        "categoryCompatibility": (
            1.0
            if category_match is True
            else 0.5
            if category_match is None
            else 0.0
        ),
        "coordinatesValid": 1.0 if coordinates_valid else 0.0,
    }
    score = (
        components["nameSimilarity"] * 0.65
        + components["regionMatch"] * 0.15
        + components["categoryCompatibility"] * 0.10
        + components["coordinatesValid"] * 0.10
    )
    return score, components


def _google_maps_address(result: dict[str, Any]) -> str | None:
    address = _optional_text(result.get("address"))
    if address:
        return address
    complete_address = result.get("complete_address")
    if isinstance(complete_address, str):
        return _optional_text(complete_address)
    if isinstance(complete_address, dict):
        return _optional_text(
            complete_address.get("full_address")
            or complete_address.get("address")
        )
    return None


def _google_maps_description(result: dict[str, Any]) -> str | None:
    descriptions = result.get("descriptions", result.get("description"))
    if isinstance(descriptions, list):
        return next(
            (
                text
                for value in descriptions
                if (text := _optional_text(value))
            ),
            None,
        )
    return _optional_text(descriptions)


def _google_maps_result_matches_region(
    result: dict[str, Any],
    *,
    search_region: str,
) -> bool | None:
    region_key = _normalized(search_region)
    if not region_key:
        return None
    complete_address = result.get("complete_address")
    location_parts: list[Any] = [
        result.get("address"),
        result.get("link"),
    ]
    if isinstance(complete_address, dict):
        location_parts.extend(complete_address.values())
    elif complete_address:
        location_parts.append(complete_address)
    location_text = " ".join(
        str(value) for value in location_parts if value
    )
    if not location_text:
        return None
    return region_key in _normalized(location_text)


def _coordinates_valid(
    latitude: Decimal | None,
    longitude: Decimal | None,
) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and Decimal("-90") <= latitude <= Decimal("90")
        and Decimal("-180") <= longitude <= Decimal("180")
    )


def _name_matches(
    candidate_name: str,
    *,
    display_name: str | None,
    provider_name: str,
    namedetails: dict[str, Any],
) -> bool:
    candidate_tokens = _name_tokens(candidate_name)
    if not candidate_tokens:
        return False
    provider_values = [
        provider_name,
        *(
            str(value)
            for key, value in namedetails.items()
            if key.startswith(("name", "official_name", "short_name", "alt_name"))
            and value
        ),
    ]
    if not provider_name and display_name:
        provider_values.append(display_name.split(",", 1)[0])
    return any(
        _token_names_match(
            candidate_tokens,
            _name_tokens(value),
        )
        for value in provider_values
        if _name_tokens(value)
    )


def _best_result(
    payload: list[dict[str, Any]],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
) -> dict[str, Any]:
    def score(result: dict[str, Any]) -> tuple[int, int, int, float]:
        namedetails = (
            result.get("namedetails")
            if isinstance(result.get("namedetails"), dict)
            else {}
        )
        provider_name = _localized_name(namedetails, result) or ""
        display_name = _optional_text(result.get("display_name"))
        matches_name = _any_name_matches(
            candidate_names,
            display_name=display_name,
            provider_name=provider_name,
            namedetails=namedetails,
        )
        matches_region = _result_matches_region(
            result,
            search_region=search_region,
        )
        category_compatible = _category_compatible(
            candidate_category,
            result,
        )
        return (
            int(category_compatible is not False),
            int(matches_name),
            int(matches_region is not False),
            _as_float(result.get("importance")),
        )

    return max(payload, key=score)


def _any_name_matches(
    candidate_names: list[str],
    *,
    display_name: str | None,
    provider_name: str,
    namedetails: dict[str, Any],
) -> bool:
    return any(
        _name_matches(
            candidate_name,
            display_name=display_name,
            provider_name=provider_name,
            namedetails=namedetails,
        )
        for candidate_name in candidate_names
    )


def _payload_matches_any_name(
    payload: list[dict[str, Any]],
    candidate_names: list[str],
) -> bool:
    for result in payload:
        namedetails = (
            result.get("namedetails")
            if isinstance(result.get("namedetails"), dict)
            else {}
        )
        if _any_name_matches(
            candidate_names,
            display_name=_optional_text(result.get("display_name")),
            provider_name=_localized_name(namedetails, result) or "",
            namedetails=namedetails,
        ):
            return True
    return False


def _token_names_match(
    candidate_tokens: list[str],
    provider_tokens: list[str],
) -> bool:
    if not candidate_tokens or not provider_tokens:
        return False
    provider_core = _strip_provider_prefix(provider_tokens)
    if candidate_tokens == provider_core:
        return True
    if provider_core == candidate_tokens:
        return True
    if _contains_token_sequence(provider_core, candidate_tokens):
        return len(provider_core) - len(candidate_tokens) <= 1
    if _contains_token_sequence(candidate_tokens, provider_core):
        return len(candidate_tokens) - len(provider_core) <= 1
    return False


def _strip_provider_prefix(tokens: list[str]) -> list[str]:
    for prefix in (
        ["nha", "hang"],
        ["cua", "hang"],
        ["quan", "an"],
        ["restaurant"],
        ["cafe"],
    ):
        if tokens[: len(prefix)] == prefix and len(tokens) > len(prefix):
            return tokens[len(prefix) :]
    return tokens


def _contains_token_sequence(
    values: list[str],
    expected: list[str],
) -> bool:
    if len(expected) > len(values):
        return False
    return any(
        values[index : index + len(expected)] == expected
        for index in range(len(values) - len(expected) + 1)
    )


def _name_tokens(value: str) -> list[str]:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    tokens = re.findall(r"[a-z0-9]+", without_marks)
    return [
        "theater" if token == "theatre" else token
        for token in tokens
        if token != "s"
    ]


def _result_matches_region(
    result: dict[str, Any],
    *,
    search_region: str,
) -> bool | None:
    region_key = _normalized(search_region)
    if not region_key:
        return None
    address = (
        result.get("address")
        if isinstance(result.get("address"), dict)
        else {}
    )
    location_text = " ".join(
        str(value)
        for value in (
            result.get("display_name"),
            *address.values(),
        )
        if value
    )
    if not location_text:
        return None
    return region_key in _normalized(location_text)


def _category_compatible(
    candidate_category: str,
    result: dict[str, Any],
) -> bool | None:
    provider_class = (
        _optional_text(result.get("category"))
        or _optional_text(result.get("class"))
        or ""
    ).casefold()
    provider_type = (
        _optional_text(result.get("type")) or ""
    ).casefold()
    if not provider_class and not provider_type:
        return None

    provider_values = {provider_class, provider_type}
    if candidate_category in {"nature", "adventure", "beach"}:
        if provider_class in {"shop", "office", "craft"}:
            return False
        return bool(
            provider_values
            & {
                "natural",
                "water",
                "tourism",
                "historic",
                "peak",
                "cave_entrance",
                "attraction",
                "viewpoint",
                "lake",
            }
        )
    if candidate_category in {"culture", "attraction"}:
        if provider_class in {"shop", "office"} and provider_type not in {
            "art",
            "books",
        }:
            return False
    if candidate_category in {"food", "cafe"} and provider_class == "natural":
        return False
    return None


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", without_marks)
