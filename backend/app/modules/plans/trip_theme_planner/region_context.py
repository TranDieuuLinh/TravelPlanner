from __future__ import annotations

import re
import unicodedata
from typing import Protocol

from app.modules.places.auto_statistics.service import (
    PlannerRegionStatisticsResult,
)
from app.modules.plans.domain.entities import RegionSnapshotReference
from app.modules.plans.dto.agent_contracts import RegionStatisticsContext


_ROOT_REGION_ALIASES = {
    "ha-noi": "ha-noi",
    "hanoi": "ha-noi",
    "hn": "ha-noi",
    "hai-phong": "hai-phong",
    "haiphong": "hai-phong",
    "hung-yen": "hung-yen",
    "hungyen": "hung-yen",
    "ho-chi-minh": "ho-chi-minh",
    "ho-chi-minh-city": "ho-chi-minh",
    "hcmc": "ho-chi-minh",
    "sai-gon": "ho-chi-minh",
    "saigon": "ho-chi-minh",
    "da-nang": "da-nang",
    "danang": "da-nang",
    "ninh-binh": "ninh-binh",
    "ninhbinh": "ninh-binh",
    "hoi-an": "hoi-an",
    "hoian": "hoi-an",
    "hue": "hue",
    "thua-thien-hue": "hue",
    "da-lat": "da-lat",
    "dalat": "da-lat",
    "sa-pa": "sa-pa",
    "sapa": "sa-pa",
}
_CANONICAL_VIETNAMESE_DESTINATIONS = {
    "ha-noi": "Hà Nội",
    "hai-phong": "Hải Phòng",
    "hung-yen": "Hưng Yên",
    "ho-chi-minh": "TP. Hồ Chí Minh",
    "da-nang": "Đà Nẵng",
    "ninh-binh": "Ninh Bình",
    "hoi-an": "Hội An",
    "hue": "Huế",
    "da-lat": "Đà Lạt",
    "sa-pa": "Sa Pa",
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
    return f"vn,{_canonical_root_slug(slug) or slug}"


def canonical_destination_name(destination: str) -> str:
    """Return the Vietnamese display name for a recognized destination.

    Region keys remain the identity used for matching. This function only
    stabilizes the user-facing label so aliases such as ``Hanoi`` do not
    replace ``Hà Nội`` in a later URL-backed revision.
    """

    cleaned = destination.strip()
    if not cleaned:
        return cleaned
    region_key = normalize_region_key(cleaned)
    root_slug = region_key.split(",", maxsplit=2)[1]
    return _CANONICAL_VIETNAMESE_DESTINATIONS.get(root_slug, cleaned)


def normalize_search_region_key(search_region: str, destination: str) -> str:
    """Resolve a stop region to a canonical catalog hierarchy.

    Known cities/provinces remain roots, which preserves day trips. A district
    or neighborhood is scoped beneath the trip destination so names such as
    ``Tây Hồ`` search ``vn,ha-noi,tay-ho`` instead of the nonexistent
    ``vn,tay-ho`` root.
    """
    destination_key = normalize_region_key(destination)
    search_slug = _slugify(search_region)
    if not search_slug:
        return destination_key

    root_slug, area_slug = _split_root_and_area(search_slug)
    if root_slug:
        return ",".join(
            part for part in ("vn", root_slug, area_slug) if part
        )

    area_slug = _strip_administrative_qualifiers(search_slug)
    destination_root = destination_key.split(",", maxsplit=2)[1]
    if area_slug == destination_root:
        return destination_key
    return f"{destination_key},{area_slug}"


def _canonicalize_explicit_region_key(region_key: str) -> str:
    parts = region_key.split(",")
    if len(parts) >= 2 and parts[0] == "vn":
        parts[1] = _canonical_root_slug(parts[1]) or parts[1]
    return ",".join(parts)


def _canonical_root_slug(slug: str) -> str | None:
    candidate = slug
    previous = None
    while candidate != previous:
        previous = candidate
        candidate = _strip_prefix(candidate, _VIETNAM_QUALIFIERS)
        candidate = _strip_suffix(candidate, _VIETNAM_QUALIFIERS)
        candidate = _strip_prefix(candidate, _CITY_QUALIFIERS)
        candidate = _strip_suffix(candidate, _CITY_QUALIFIERS)
    return _ROOT_REGION_ALIASES.get(candidate)


def _split_root_and_area(slug: str) -> tuple[str | None, str | None]:
    canonical_root = _canonical_root_slug(slug)
    if canonical_root:
        return canonical_root, None
    for alias in sorted(_ROOT_REGION_ALIASES, key=len, reverse=True):
        canonical_root = _ROOT_REGION_ALIASES[alias]
        for prefix, suffix in (
            (f"{alias}-", ""),
            ("", f"-{alias}"),
        ):
            if prefix and slug.startswith(prefix):
                area = slug[len(prefix) :]
            elif suffix and slug.endswith(suffix):
                area = slug[: -len(suffix)]
            else:
                continue
            area = _strip_administrative_qualifiers(area)
            if area:
                return canonical_root, area
    return None, None


def _strip_administrative_qualifiers(slug: str) -> str:
    qualifiers = (
        "district",
        "quan",
        "huyen",
        "thi-xa",
        "phuong",
        "xa",
        "ward",
    )
    candidate = slug
    previous = None
    while candidate != previous:
        previous = candidate
        candidate = _strip_prefix(candidate, qualifiers)
        candidate = _strip_suffix(candidate, qualifiers)
    return candidate


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
