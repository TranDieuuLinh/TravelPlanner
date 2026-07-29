from __future__ import annotations

import re
import unicodedata
from typing import Protocol

from app.modules.places.auto_statistics.service import (
    PlannerRegionStatisticsResult,
)
from app.modules.plans.domain.entities import RegionSnapshotReference
from app.modules.plans.dto.agent_contracts import RegionStatisticsContext


_HANOI_CORE_SLUGS = {
    "ha-noi",
    "hanoi",
    "hn",
}
_VIETNAM_QUALIFIERS = (
    "viet-nam",
    "vietnam",
    "vn",
)
_CITY_QUALIFIERS = (
    "thanh-pho",
    "city",
    "tp",
)


class PlannerStatisticsProvider(Protocol):
    def get_for_planner(
        self,
        region_key: str,
        *,
        force: bool = False,
    ) -> PlannerRegionStatisticsResult: ...


def normalize_region_key(destination: str, explicit_region_key: str | None = None) -> str:
    if explicit_region_key:
        region_key = _canonicalize_explicit_region_key(
            explicit_region_key.strip().lower()
        )
        _validate_region_key(region_key)
        return region_key

    slug = _slugify(destination)
    if not slug:
        raise ValueError("destination cannot be normalized to a region_key")
    if _is_hanoi_alias(slug):
        return "vn,ha-noi"
    return f"vn,{slug}"


def _canonicalize_explicit_region_key(region_key: str) -> str:
    parts = region_key.split(",")
    if len(parts) >= 2 and parts[0] == "vn" and _is_hanoi_alias(parts[1]):
        parts[1] = "ha-noi"
    return ",".join(parts)


def _is_hanoi_alias(slug: str) -> bool:
    candidate = slug
    previous = None
    while candidate != previous:
        previous = candidate
        candidate = _strip_prefix(candidate, _VIETNAM_QUALIFIERS)
        candidate = _strip_suffix(candidate, _VIETNAM_QUALIFIERS)
        candidate = _strip_prefix(candidate, _CITY_QUALIFIERS)
        candidate = _strip_suffix(candidate, _CITY_QUALIFIERS)
    return candidate in _HANOI_CORE_SLUGS


def _strip_prefix(value: str, qualifiers: tuple[str, ...]) -> str:
    for qualifier in qualifiers:
        prefix = f"{qualifier}-"
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _strip_suffix(value: str, qualifiers: tuple[str, ...]) -> str:
    for qualifier in qualifiers:
        suffix = f"-{qualifier}"
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().lower())
    ascii_text = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def load_region_statistics_context(
    provider: PlannerStatisticsProvider,
    region_key: str,
) -> tuple[RegionStatisticsContext, str]:
    result = provider.get_for_planner(region_key)
    root_metrics = next(
        (
            region
            for region in result.regions
            if region.get("regionKey") == region_key
        ),
        None,
    )
    if root_metrics is None:
        root_metrics = {"regionKey": region_key}

    snapshot_ref = RegionSnapshotReference(
        regionKey=region_key,
        snapshotId=result.snapshot_id,
        catalogVersion=result.catalog_version,
        algorithmVersion=result.algorithm_version,
        generatedAt=result.generated_at,
    )
    context = RegionStatisticsContext.model_validate(
        {
            **root_metrics,
            "regionKey": region_key,
            "snapshotRef": snapshot_ref.model_dump(by_alias=True),
        }
    )
    return context, result.status


def _validate_region_key(region_key: str) -> None:
    parts = region_key.split(",")
    if (
        len(parts) < 2
        or parts[0] != "vn"
        or any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", part) for part in parts)
    ):
        raise ValueError(
            "regionKey must use comma-separated slugs, for example vn,ha-noi"
        )
