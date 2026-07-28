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
            name=candidate.name,
            address=candidate.address_hint,
            city=destination,
            dataConfidence="low",
        )


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
        query = ", ".join(
            part
            for part in (candidate.name, candidate.address_hint, destination)
            if part
        )
        try:
            payload = await self._search(query)
        except (httpx.HTTPError, ValueError, TypeError):
            return _unresolved(candidate, destination)
        if not payload:
            return _unresolved(candidate, destination)

        result = payload[0]
        address = result.get("address") if isinstance(result.get("address"), dict) else {}
        display_name = _optional_text(result.get("display_name"))
        external_id = _external_id(result)
        name = (
            _optional_text(result.get("namedetails", {}).get("name"))
            if isinstance(result.get("namedetails"), dict)
            else None
        ) or _optional_text(result.get("name")) or candidate.name
        importance = _as_float(result.get("importance"))
        name_matches = _normalized(candidate.name) in _normalized(display_name or name)
        status = "resolved" if name_matches else "provisional"
        confidence = (
            "high"
            if name_matches and importance >= 0.3
            else "medium"
            if name_matches
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
            or destination,
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
                        "addressdetails": 1,
                        "extratags": 1,
                        "namedetails": 1,
                        "limit": 1,
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
    destination: str,
) -> PlaceResolution:
    return PlaceResolution(
        candidate=candidate,
        status="unresolved",
        name=candidate.name,
        address=candidate.address_hint,
        city=destination,
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


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", without_marks)
