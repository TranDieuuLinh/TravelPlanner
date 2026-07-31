from __future__ import annotations

import asyncio
import json
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

import httpx
from pydantic import BaseModel, Field

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
    source_fetched_at: datetime | None
    metadata_json: dict


class PlaceLookupRepository(Protocol):
    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
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

    model_config = {"populate_by_name": True}


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
            city=candidate.search_region or destination,
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

        fallback_result = await self.fallback.resolve(
            candidate,
            destination=destination,
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
            if _is_usable_resolution(fallback_result):
                combined_results[index] = fallback_result
                continue
            primary_result = primary_results[index]
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
        from app.modules.plans.planner.region_context import normalize_region_key

        search_region = candidate.search_region or destination
        region_key = normalize_region_key(search_region)
        records = self.repository.list_active_for_planner_research(region_key)
        candidate_names = _candidate_lookup_names(candidate)
        candidate_keys = {
            _normalized(name)
            for name in candidate_names
            if _normalized(name)
        }
        matches = [
            record
            for record in records
            if record.latitude is not None
            and record.longitude is not None
            and candidate_keys.intersection(_database_name_keys(record))
        ]
        if not matches:
            return _unresolved(
                candidate,
                search_region,
                reason="not_found",
                provider=self.provider_name,
            )

        record = max(
            matches,
            key=lambda item: (
                _database_confidence_score(item.data_confidence),
                bool(item.source_fetched_at),
            ),
        )
        metadata = (
            record.metadata_json
            if isinstance(record.metadata_json, dict)
            else {}
        )
        return PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider=self.provider_name,
            externalId=record.id,
            name=record.name,
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
        max_alias_queries: int = 3,
    ) -> None:
        if not executable and work_dir is None:
            raise ValueError(
                "google-maps-scraper needs an executable or shared work_dir"
            )
        self.executable = executable
        self.work_dir = work_dir
        self.timeout_seconds = timeout_seconds
        self.max_alias_queries = max_alias_queries

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        search_region = candidate.search_region or destination
        candidate_names = _candidate_lookup_names(candidate)
        queries = _google_maps_alias_queries(
            candidate_names,
            address_hint=candidate.address_hint,
            search_region=search_region,
            limit=self.max_alias_queries,
        )
        try:
            payload = await self._search(queries)
        except (
            OSError,
            ValueError,
            TypeError,
            asyncio.TimeoutError,
        ):
            return _unresolved(
                candidate,
                search_region,
                reason="provider_error",
                provider=self.provider_name,
            )

        if not payload:
            return _unresolved(
                candidate,
                search_region,
                reason="not_found",
                provider=self.provider_name,
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
        name_matches = any(
            _token_names_match(_name_tokens(name), _name_tokens(title))
            for name in candidate_names
        )
        region_matches = _google_maps_result_matches_region(
            result,
            search_region=search_region,
        )
        category_compatible = _category_compatible(
            candidate.category.value,
            result,
        )
        coordinates_valid = _coordinates_valid(latitude, longitude)
        rejection_reasons = [
            reason
            for condition, reason in (
                (not name_matches, "name_mismatch"),
                (region_matches is False, "region_mismatch"),
                (category_compatible is False, "category_mismatch"),
                (not coordinates_valid, "coordinates_missing"),
            )
            if condition
        ]
        status = "resolved" if not rejection_reasons else "unresolved"
        complete_address = result.get("complete_address")
        complete_address_dict = (
            complete_address
            if isinstance(complete_address, dict)
            else {}
        )
        return PlaceResolution(
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
            name=title,
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
            dataConfidence="medium" if status == "resolved" else "low",
            fetchedAt=datetime.now(timezone.utc),
            attribution="Google Maps data via gosom/google-maps-scraper",
        )

    async def _search(
        self,
        queries: list[str],
    ) -> list[dict[str, Any]]:
        if not queries:
            return []
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
                raise
            if process.returncode != 0:
                raise ValueError(
                    "Google Maps scraper CLI exited unsuccessfully."
                )
            if not results_path.exists():
                return []
            return _load_google_maps_output(
                results_path.read_text(encoding="utf-8")
            )

    async def _search_via_worker(
        self,
        queries: list[str],
    ) -> list[dict[str, Any]]:
        if self.work_dir is None:
            raise ValueError("Google Maps scraper work directory is missing.")

        request_id = uuid.uuid4().hex
        requests_dir = self.work_dir / "requests"
        responses_dir = self.work_dir / "responses"
        errors_dir = self.work_dir / "errors"
        for directory in (requests_dir, responses_dir, errors_dir):
            directory.mkdir(parents=True, exist_ok=True)

        temporary_request_path = requests_dir / f".{request_id}.tmp"
        request_path = requests_dir / f"{request_id}.txt"
        response_path = responses_dir / f"{request_id}.json"
        error_path = errors_dir / f"{request_id}.txt"
        temporary_request_path.write_text(
            "\n".join(queries) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_request_path, request_path)

        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        try:
            while asyncio.get_running_loop().time() < deadline:
                if response_path.exists():
                    payload = _load_google_maps_output(
                        response_path.read_text(encoding="utf-8")
                    )
                    response_path.unlink(missing_ok=True)
                    return payload
                if error_path.exists():
                    error_path.unlink(missing_ok=True)
                    raise ValueError(
                        "Google Maps scraper worker exited unsuccessfully."
                    )
                await asyncio.sleep(0.1)
        finally:
            temporary_request_path.unlink(missing_ok=True)
            request_path.unlink(missing_ok=True)

        raise asyncio.TimeoutError


class NominatimPlaceResolver(PlaceResolver):
    provider_name = "nominatim"
    _request_lock = asyncio.Lock()
    _last_request_at = 0.0
    _response_cache: dict[str, list[dict[str, Any]]] = {}

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        timeout_seconds: float = 15.0,
        min_interval_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = max(min_interval_seconds, 1.0)

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        search_region = candidate.search_region or destination
        query = ", ".join(
            part for part in (
                candidate.name,
                candidate.address_hint,
                search_region,
            )
            if part
        )
        try:
            payload = await self._search(query)
            candidate_names = _candidate_lookup_names(candidate)
            if (
                candidate.search_names
                and not _payload_matches_any_name(payload, candidate_names)
            ):
                for search_name in candidate.search_names[:2]:
                    alias_query = ", ".join(
                        part
                        for part in (
                            search_name,
                            candidate.address_hint,
                            search_region,
                        )
                        if part
                    )
                    payload.extend(await self._search(alias_query))
        except (httpx.HTTPError, ValueError, TypeError):
            return _unresolved(
                candidate,
                search_region,
                reason="provider_error",
                provider=self.provider_name,
            )
        if not payload:
            return _unresolved(
                candidate,
                search_region,
                reason="not_found",
                provider=self.provider_name,
            )

        result = _best_result(
            payload,
            candidate_names=candidate_names,
            search_region=search_region,
            candidate_category=candidate.category.value,
        )
        address = result.get("address") if isinstance(result.get("address"), dict) else {}
        display_name = _optional_text(result.get("display_name"))
        external_id = _external_id(result)
        namedetails = (
            result.get("namedetails")
            if isinstance(result.get("namedetails"), dict)
            else {}
        )
        name = _localized_name(namedetails, result) or candidate.name
        importance = _as_float(result.get("importance"))
        name_matches = _any_name_matches(
            candidate_names,
            display_name=display_name,
            provider_name=name,
            namedetails=namedetails,
        )
        region_matches = _result_matches_region(
            result,
            search_region=search_region,
        )
        category_compatible = _category_compatible(
            candidate.category.value,
            result,
        )
        rejection_reasons = [
            reason
            for condition, reason in (
                (not name_matches, "name_mismatch"),
                (region_matches is False, "region_mismatch"),
                (category_compatible is False, "category_mismatch"),
            )
            if condition
        ]
        status = "resolved" if not rejection_reasons else "unresolved"
        resolution_reason = (
            None
            if status == "resolved"
            else "+".join(rejection_reasons)
        )
        confidence = (
            "high"
            if status == "resolved" and importance >= 0.3
            else "medium"
            if status == "resolved"
            else "low"
        )
        extra_tags = result.get("extratags")
        description = (
            _optional_text(extra_tags.get("description"))
            if isinstance(extra_tags, dict)
            else None
        )
        return PlaceResolution(
            candidate=candidate,
            status=status,
            resolutionReason=resolution_reason,
            provider=self.provider_name,
            externalId=external_id,
            name=name,
            address=display_name or candidate.address_hint,
            city=_first_address_value(
                address,
                "city",
                "town",
                "municipality",
                "village",
            )
            or search_region,
            country=_optional_text(address.get("country")),
            countryCode=(
                _optional_text(address.get("country_code")) or ""
            ).upper()
            or None,
            primaryArea=_first_address_value(
                address,
                "suburb",
                "quarter",
                "neighbourhood",
                "city_district",
            ),
            latitude=_as_decimal(result.get("lat")),
            longitude=_as_decimal(result.get("lon")),
            description=description,
            dataConfidence=confidence,
            fetchedAt=datetime.now(timezone.utc),
            attribution=_optional_text(result.get("licence")),
        )

    async def _search(self, query: str) -> list[dict[str, Any]]:
        cache_key = _normalized(query)
        cached = self._response_cache.get(cache_key)
        if cached is not None:
            return cached
        async with self._request_lock:
            cached = self._response_cache.get(cache_key)
            if cached is not None:
                return cached
            elapsed = time.monotonic() - self._last_request_at
            wait_for = self.min_interval_seconds - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    f"{self.base_url}/search",
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept-Language": "vi,en",
                    },
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "accept-language": "vi,en",
                        "addressdetails": 1,
                        "extratags": 1,
                        "namedetails": 1,
                        "limit": 5,
                    },
                )
            self.__class__._last_request_at = time.monotonic()
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Nominatim search response must be a list.")
        results = [item for item in data if isinstance(item, dict)]
        self._response_cache[cache_key] = results
        return results


def _unresolved(
    candidate: UnifiedPlaceCandidate,
    search_region: str,
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


def _external_id(result: dict[str, Any]) -> str | None:
    osm_type = _optional_text(result.get("osm_type"))
    osm_id = _optional_text(result.get("osm_id"))
    if osm_type and osm_id:
        return f"{osm_type}:{osm_id}"
    return _optional_text(result.get("place_id"))


def _first_address_value(address: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _optional_text(address.get(key))
        if value:
            return value
    return None


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


def _database_name_keys(record: PlaceLookupRecord) -> set[str]:
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
    return {
        _normalized(str(value))
        for value in (record.name, *raw_aliases)
        if value and _normalized(str(value))
    }


def _candidate_lookup_names(
    candidate: UnifiedPlaceCandidate,
) -> list[str]:
    return list(
        dict.fromkeys(
            name
            for name in (
                candidate.original_name,
                candidate.name,
                *candidate.english_names,
                *candidate.vietnamese_names,
                *candidate.alternate_names,
                *candidate.search_names,
            )
            if name
        )
    )


def _database_confidence_score(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(value, 0)


def _google_maps_alias_queries(
    candidate_names: list[str],
    *,
    address_hint: str | None,
    search_region: str,
    limit: int,
) -> list[str]:
    return [
        ", ".join(
            _single_line(part)
            for part in (name, address_hint, search_region)
            if part and _single_line(part)
        )
        for name in candidate_names[:limit]
    ]


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
            _as_float(result.get("review_rating")),
        )

    return max(payload, key=score)


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
    descriptions = result.get("descriptions")
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
    return re.findall(r"[a-z0-9]+", without_marks)


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
                "tourism",
                "historic",
                "peak",
                "cave_entrance",
                "attraction",
                "viewpoint",
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
