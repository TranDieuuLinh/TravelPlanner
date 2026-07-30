from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


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


class HerePlaceResolver(PlaceResolver):
    provider_name = "here"

    def __init__(
        self,
        *,
        base_url: str,
        geocode_base_url: str = "https://geocode.search.hereapi.com",
        api_key: str,
        timeout_seconds: float = 10.0,
        country_code: str = "VNM",
        language: str = "vi-VN",
        min_interval_seconds: float = 0.2,
        max_concurrency: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.geocode_base_url = geocode_base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.country_code = country_code.strip().upper()
        self.language = language
        self.min_interval_seconds = max(min_interval_seconds, 0.2)
        self.max_concurrency = max(1, min(max_concurrency, 4))
        self._request_lock = asyncio.Lock()
        self._region_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._response_cache: dict[str, list[dict[str, Any]]] = {}
        self._region_cache: dict[str, tuple[float, float]] = {}

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
                return await self.resolve(
                    candidate,
                    destination=destination,
                )

        return list(
            await asyncio.gather(
                *(resolve_one(candidate) for candidate in candidates)
            )
        )

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        search_region = candidate.search_region or destination
        query = ", ".join(
            part
            for part in (
                candidate.name,
                candidate.address_hint,
                search_region,
            )
            if part
        )
        try:
            payload = await self._search(query, search_region=search_region)
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

        candidate_names = [candidate.name, *candidate.search_names]
        result = _best_here_result(
            payload,
            candidate_names=candidate_names,
            search_region=search_region,
        )
        title = _optional_text(result.get("title")) or candidate.name
        address = (
            result.get("address")
            if isinstance(result.get("address"), dict)
            else {}
        )
        position = (
            result.get("position")
            if isinstance(result.get("position"), dict)
            else {}
        )
        latitude = _as_decimal(position.get("lat"))
        longitude = _as_decimal(position.get("lng"))
        name_matches = _here_name_matches(candidate_names, title)
        region_matches = _here_result_matches_region(
            result,
            search_region=search_region,
        )
        result_type = (_optional_text(result.get("resultType")) or "").casefold()
        rejection_reasons = [
            reason
            for condition, reason in (
                (not name_matches, "name_mismatch"),
                (region_matches is False, "region_mismatch"),
                (result_type != "place", "not_a_place"),
                (
                    latitude is None or longitude is None,
                    "coordinates_missing",
                ),
            )
            if condition
        ]
        status = "resolved" if not rejection_reasons else "unresolved"
        exact_name_match = _name_tokens(candidate.name) == _name_tokens(title)
        return PlaceResolution(
            candidate=candidate,
            status=status,
            resolutionReason=(
                None if status == "resolved" else "+".join(rejection_reasons)
            ),
            provider=self.provider_name,
            externalId=_optional_text(result.get("id")),
            name=title,
            address=_optional_text(address.get("label"))
            or candidate.address_hint,
            city=_first_address_value(
                address,
                "city",
                "county",
                "state",
            )
            or search_region,
            country=_optional_text(address.get("countryName")),
            countryCode=(
                _optional_text(address.get("countryCode")) or ""
            ).upper()
            or None,
            primaryArea=_first_address_value(
                address,
                "district",
                "subdistrict",
                "county",
            ),
            latitude=latitude,
            longitude=longitude,
            dataConfidence=(
                "high"
                if status == "resolved" and exact_name_match
                else "medium"
                if status == "resolved"
                else "low"
            ),
            fetchedAt=datetime.now(timezone.utc),
            attribution="© HERE",
        )

    async def _search(
        self,
        query: str,
        *,
        search_region: str,
    ) -> list[dict[str, Any]]:
        cache_key = "|".join(
            (_normalized(query), self.country_code, self.language)
        )
        cached = self._response_cache.get(cache_key)
        if cached is not None:
            return cached
        latitude, longitude = await self._region_position(search_region)
        data = await self._request_json(
            f"{self.base_url}/v1/discover",
            params={
                "q": query,
                "at": f"{latitude},{longitude}",
                "limit": 5,
                "lang": self.language,
                "apiKey": self.api_key,
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("HERE discover response must contain an items list.")
        results = [item for item in data["items"] if isinstance(item, dict)]
        self._response_cache[cache_key] = results
        return results

    async def _region_position(
        self,
        search_region: str,
    ) -> tuple[float, float]:
        cache_key = "|".join(
            (_normalized(search_region), self.country_code, self.language)
        )
        cached = self._region_cache.get(cache_key)
        if cached is not None:
            return cached
        async with self._region_lock:
            cached = self._region_cache.get(cache_key)
            if cached is not None:
                return cached
            query = search_region
            if self.country_code == "VNM":
                query = f"{search_region}, Việt Nam"
            data = await self._request_json(
                f"{self.geocode_base_url}/v1/geocode",
                params={
                    "q": query,
                    "limit": 1,
                    "lang": self.language,
                    "apiKey": self.api_key,
                },
            )
            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list) or not items:
                raise ValueError(
                    "HERE geocode response did not resolve the region."
                )
            first = items[0] if isinstance(items[0], dict) else {}
            position = (
                first.get("position")
                if isinstance(first.get("position"), dict)
                else {}
            )
            latitude = _as_float_or_none(position.get("lat"))
            longitude = _as_float_or_none(position.get("lng"))
            if latitude is None or longitude is None:
                raise ValueError(
                    "HERE geocode response is missing coordinates."
                )
            result = (latitude, longitude)
            self._region_cache[cache_key] = result
            return result

    async def _request_json(
        self,
        url: str,
        *,
        params: dict[str, str | int],
    ) -> Any:
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait_for = self.min_interval_seconds - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_at = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


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
            candidate_names = [candidate.name, *candidate.search_names]
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


def _as_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _best_here_result(
    payload: list[dict[str, Any]],
    *,
    candidate_names: list[str],
    search_region: str,
) -> dict[str, Any]:
    def score(result: dict[str, Any]) -> tuple[int, int, int]:
        title = _optional_text(result.get("title")) or ""
        matches_name = _here_name_matches(candidate_names, title)
        matches_region = _here_result_matches_region(
            result,
            search_region=search_region,
        )
        is_place = (
            (_optional_text(result.get("resultType")) or "").casefold()
            == "place"
        )
        return (
            int(matches_name),
            int(matches_region is not False),
            int(is_place),
        )

    return max(payload, key=score)


def _here_result_matches_region(
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
        str(value) for value in address.values() if value
    )
    if not location_text:
        return None
    return region_key in _normalized(location_text)


def _here_name_matches(
    candidate_names: list[str],
    provider_title: str,
) -> bool:
    title_variants = [provider_title]
    prefix = provider_title.split("(", 1)[0].strip()
    if prefix and prefix != provider_title:
        title_variants.append(prefix)
    title_variants.extend(
        match.strip()
        for match in re.findall(r"\(([^()]*)\)", provider_title)
        if match.strip()
    )
    return any(
        _token_names_match(
            _name_tokens(candidate_name),
            _name_tokens(title_variant),
        )
        for candidate_name in candidate_names
        for title_variant in title_variants
    )


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
