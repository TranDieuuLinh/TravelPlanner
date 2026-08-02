from __future__ import annotations

import asyncio
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
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.modules.plans.destination_inference import usable_destination
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


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


class PlaceResolution(BaseModel):
    candidate: UnifiedPlaceCandidate
    status: Literal["resolved", "provisional", "unresolved"]
    resolution_reason: str | None = Field(
        default=None,
        alias="resolutionReason",
    )
    provider: str | None = None
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
    ) -> None:
        self.primary = primary
        self.fallback = fallback

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
        if (
            primary_result.resolution_reason == "ambiguous_name"
            and not _has_source_location_evidence(candidate)
        ):
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
                ]
            }
        )
        if _is_usable_resolution(fallback_result):
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
            if not _is_usable_resolution(result)
            and not (
                result.resolution_reason == "ambiguous_name"
                and not _has_source_location_evidence(candidates[index])
            )
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
                    ]
                }
            )
            if _is_usable_resolution(fallback_result):
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


class DatabasePlaceResolver(PlaceResolver):
    provider_name = "database"

    def __init__(self, repository: PlaceLookupRepository) -> None:
        self.repository = repository

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        started_at = time.perf_counter()
        search_region = _effective_search_region(candidate, destination)
        matches = self._matching_records(candidate, destination=destination)
        if not matches:
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="not_found",
                    provider=self.provider_name,
                ),
                provider=self.provider_name,
                started_at=started_at,
            )
        record = _select_unique_best_name_match(candidate, matches)
        record = record or _select_record_from_source_evidence(candidate, matches)
        if record is None and len(matches) > 1:
            return _with_provider_attempt(
                _unresolved(
                    candidate,
                    search_region,
                    reason="ambiguous_name",
                    provider=self.provider_name,
                ),
                provider=self.provider_name,
                started_at=started_at,
            )
        record = record or matches[0]
        return _with_provider_attempt(
            _database_resolution(
                candidate,
                record,
                search_region=search_region,
                reason=("matched_source_location" if len(matches) > 1 else None),
            ),
            provider=self.provider_name,
            started_at=started_at,
        )

    async def resolve_many(
        self,
        candidates: list[UnifiedPlaceCandidate],
        *,
        destination: str,
    ) -> list[PlaceResolution]:
        results = [
            await self.resolve(candidate, destination=destination)
            for candidate in candidates
        ]
        for index, result in enumerate(results):
            if result.resolution_reason != "ambiguous_name":
                continue
            candidate = candidates[index]
            matches = self._matching_records(candidate, destination=destination)
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
                reason="matched_route_context",
            ).model_copy(
                update={
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

    def _matching_records(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> list[PlaceLookupRecord]:
        from app.modules.plans.planner.region_context import normalize_region_key

        search_region = _effective_search_region(candidate, destination)
        region_key = normalize_region_key(search_region) if search_region else None
        candidate_names = _candidate_lookup_names(candidate)
        records = self.repository.list_active_for_planner_research(region_key)
        matches = [
            record
            for record in records
            if _database_record_matches(candidate_names, record)
        ]
        if matches:
            return matches
        global_matches = [
            record
            for record in self.repository.search_active_by_names(candidate_names)
            if _database_record_matches(candidate_names, record)
        ]
        regional_global_matches = [
            record
            for record in global_matches
            if region_key and _record_is_in_region(record, region_key)
        ]
        return regional_global_matches or global_matches


def _database_resolution(
    candidate: UnifiedPlaceCandidate,
    record: PlaceLookupRecord,
    *,
    search_region: str,
    reason: str | None = None,
) -> PlaceResolution:
    metadata = (
        record.metadata_json
        if isinstance(record.metadata_json, dict)
        else {}
    )
    return PlaceResolution(
        candidate=candidate,
        status="resolved",
        resolutionReason=reason,
        provider="database",
        externalId=record.id,
        placeId=record.id,
        name=record.name,
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


class GoogleMapsScraperPlaceResolver(PlaceResolver):
    """Resolve aliases with the Playwright google-maps-scraper worker."""

    provider_name = "google_maps_scraper"

    def __init__(
        self,
        *,
        executable: str | None = None,
        work_dir: Path | None = None,
        timeout_seconds: float = 45.0,
        max_alias_queries: int = 1,
        max_concurrency: int = 2,
    ) -> None:
        if not executable and work_dir is None:
            raise ValueError(
                "google-maps-scraper needs an executable or shared work_dir"
            )
        self.executable = executable
        self.work_dir = work_dir
        self.timeout_seconds = timeout_seconds
        self.max_alias_queries = max_alias_queries
        self.max_concurrency = max(1, max_concurrency)

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
            address_hint=candidate.address_hint,
            context_hint=_candidate_context_hint(candidate),
            search_region=search_region,
            limit=self.max_alias_queries,
        )
        attempted_query_count = 0
        queue_wait_seconds = 0.0
        execution_seconds = 0.0
        provider_started_at = time.perf_counter()
        try:
            # Query the strongest canonical/context combination first so a
            # successful lookup does not pay for every bilingual alias. Keep
            # the remaining aliases as a quality-preserving fallback.
            first_queries = queries[:1]
            attempted_query_count += len(first_queries)
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
            ):
                fallback_queries = queries[1:]
                attempted_query_count += len(fallback_queries)
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
        title = _optional_text(result.get("title")) or candidate.name
        address = _google_maps_address(result) or candidate.address_hint
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
        )
        status = "resolved" if not rejection_reasons else "unresolved"
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
                externalId=(
                    _optional_text(result.get("place_id"))
                    or _optional_text(result.get("cid"))
                    or _optional_text(result.get("data_id"))
                ),
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
                latitude=latitude,
                longitude=longitude,
                description=_google_maps_description(result),
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
                        "website": result.get("website"),
                        "phone": result.get("phone"),
                    }
                ),
                dataConfidence="medium" if status == "resolved" else "low",
                fetchedAt=datetime.now(timezone.utc),
                attribution="Google Maps data via gosom/google-maps-scraper",
            ),
            provider=self.provider_name,
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
    return (
        usable_destination(candidate.search_region)
        or usable_destination(destination)
        or ""
    )


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


def _database_name_keys(record: PlaceLookupRecord) -> set[str]:
    return {_normalized(value) for value in _database_names(record)}


def _database_record_matches(
    candidate_names: list[str],
    record: PlaceLookupRecord,
) -> bool:
    if record.latitude is None or record.longitude is None:
        return False
    candidate_keys = {
        _normalized(name) for name in candidate_names if _normalized(name)
    }
    if candidate_keys.intersection(_database_name_keys(record)):
        return True
    for candidate_name in candidate_names:
        candidate_tokens = _name_tokens(candidate_name)
        if len(candidate_tokens) < 2:
            continue
        for record_name in _database_names(record):
            record_tokens = _name_tokens(record_name)
            if (
                record_tokens[: len(candidate_tokens)] == candidate_tokens
                and len(record_tokens) - len(candidate_tokens) <= 5
            ):
                return True
    return False


def _select_unique_best_name_match(
    candidate: UnifiedPlaceCandidate,
    records: list[PlaceLookupRecord],
) -> PlaceLookupRecord | None:
    candidate_names = _candidate_lookup_names(candidate)
    scored = [
        (
            max(
                (
                    _name_match_score(candidate_name, record_name)
                    for candidate_name in candidate_names
                    for record_name in _database_names(record)
                ),
                default=0,
            ),
            record,
        )
        for record in records
    ]
    best_score = max((score for score, _ in scored), default=0)
    winners = [record for score, record in scored if score == best_score]
    return winners[0] if best_score >= 95 and len(winners) == 1 else None


def _name_match_score(candidate_name: str, record_name: str) -> int:
    candidate_tokens = _name_tokens(candidate_name)
    record_tokens = _name_tokens(record_name)
    if not candidate_tokens or not record_tokens:
        return 0
    if candidate_tokens == record_tokens:
        return 100
    if _contains_token_sequence(record_tokens, candidate_tokens):
        return 90 - min(20, len(record_tokens) - len(candidate_tokens))
    if _contains_token_sequence(candidate_tokens, record_tokens):
        return 85 - min(20, len(candidate_tokens) - len(record_tokens))
    return 0


def _select_record_from_source_evidence(
    candidate: UnifiedPlaceCandidate,
    records: list[PlaceLookupRecord],
) -> PlaceLookupRecord | None:
    raw_hints = [
        candidate.address_hint,
        _candidate_context_hint(candidate),
    ]
    region_key = _normalized(candidate.search_region or "")
    hints = [
        hint
        for hint in raw_hints
        if hint
        and len(_name_tokens(hint)) >= 2
        and _normalized(hint) != region_key
    ]
    if not hints:
        return None

    scored: list[tuple[int, PlaceLookupRecord]] = []
    for record in records:
        location_text = " ".join(
            str(value)
            for value in (
                record.name,
                record.address,
                record.primary_area,
                record.city,
            )
            if value
        )
        location_key = _normalized(location_text)
        score = sum(
            1 for hint in hints if _normalized(hint) in location_key
        )
        scored.append((score, record))
    best_score = max((score for score, _ in scored), default=0)
    winners = [record for score, record in scored if score == best_score]
    return winners[0] if best_score > 0 and len(winners) == 1 else None


def _has_source_location_evidence(
    candidate: UnifiedPlaceCandidate,
) -> bool:
    return bool(
        candidate.address_hint
        or _candidate_context_hint(candidate)
    )


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
    """Return lookup names with Vietnamese provider queries first."""
    return list(
        dict.fromkeys(
            name
            for name in (
                *candidate.vietnamese_names,
                candidate.original_name,
                candidate.name,
                *candidate.english_names,
                *candidate.alternate_names,
                *candidate.search_names,
            )
            if name
        )
    )


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
    queries: list[str] = []
    if candidate_names and context_hint:
        queries.append(
            ", ".join(
                _single_line(part)
                for part in (
                    candidate_names[0],
                    address_hint,
                    context_hint,
                    search_region,
                )
                if part and _single_line(part)
            )
        )
    queries.extend(
        ", ".join(
            _single_line(part)
            for part in (name, address_hint, search_region)
            if part and _single_line(part)
        )
        for name in candidate_names[:limit]
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
    def score(result: dict[str, Any]) -> tuple[int, int, int, float]:
        title = _optional_text(result.get("title")) or ""
        matches_name = any(
            _token_names_match(_name_tokens(name), _name_tokens(title))
            for name in candidate_names
        )
        matches_region = _google_maps_result_matches_region(
            result,
            search_region=search_region,
        )
        category_compatible = _category_compatible(
            candidate_category,
            result,
        )
        return (
            int(matches_name),
            int(matches_region is not False),
            int(category_compatible is not False),
            _as_float(
                result.get("review_rating", result.get("rating"))
            ),
        )

    return max(payload, key=score)


def _google_maps_payload_is_usable(
    payload: list[dict[str, Any]],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
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
    )


def _google_maps_rejection_reasons(
    result: dict[str, Any],
    *,
    candidate_names: list[str],
    search_region: str,
    candidate_category: str,
    coordinates_valid: bool,
) -> list[str]:
    title = _optional_text(result.get("title")) or ""
    name_matches = any(
        _token_names_match(_name_tokens(name), _name_tokens(title))
        for name in candidate_names
    )
    region_matches = _google_maps_result_matches_region(
        result,
        search_region=search_region,
    )
    category_compatible = _category_compatible(
        candidate_category,
        result,
    )
    return [
        reason
        for condition, reason in (
            (not name_matches, "name_mismatch"),
            (region_matches is False, "region_mismatch"),
            (category_compatible is False, "category_mismatch"),
            (not coordinates_valid, "coordinates_missing"),
        )
        if condition
    ]


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
