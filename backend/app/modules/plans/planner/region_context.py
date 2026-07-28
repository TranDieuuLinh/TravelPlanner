from __future__ import annotations

import re
import unicodedata
from typing import Protocol

from app.modules.places.auto_statistics.service import (
    PlannerRegionStatisticsResult,
)
from app.modules.plans.domain.entities import RegionSnapshotReference
from app.modules.plans.dto.agent_contracts import RegionStatisticsContext


class PlannerStatisticsProvider(Protocol):
    def get_for_planner(
        self,
        region_key: str,
        *,
        force: bool = False,
    ) -> PlannerRegionStatisticsResult: ...


def normalize_region_key(destination: str, explicit_region_key: str | None = None) -> str:
    if explicit_region_key:
        region_key = explicit_region_key.strip().lower()
        _validate_region_key(region_key)
        return region_key

    normalized = unicodedata.normalize("NFD", destination.strip().lower())
    ascii_text = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not slug:
        raise ValueError("destination cannot be normalized to a region_key")
    return f"vn,{slug}"


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
