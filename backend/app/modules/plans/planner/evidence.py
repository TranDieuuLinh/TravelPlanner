from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.modules.plans.dto.agent_contracts import (
    PlannerAgentInput,
    RegionStatisticsContext,
    TourismZoneEvidence,
)
from app.modules.plans.planner.tourism_zone_research import (
    EmptyTourismZoneResearchTool,
    TourismZoneResearchTool,
)


logger = logging.getLogger(__name__)


class CatalogCapabilityEvidence(BaseModel):
    """Small, operational view of catalog capacity used by Planner.

    Semantic meaning belongs to the travel knowledge graph. This model only
    describes whether the current Place catalog can support a plan and how
    trustworthy that operational data is.
    """

    region_key: str = Field(alias="regionKey")
    snapshot_id: str = Field(alias="snapshotId")
    catalog_version: int = Field(alias="catalogVersion")
    active_place_count: int = Field(alias="activePlaceCount")
    category_counts: dict[str, int] = Field(
        default_factory=dict,
        alias="categoryCounts",
    )
    time_of_day_coverage: dict[str, int] = Field(
        default_factory=dict,
        alias="timeOfDayCoverage",
    )
    typical_duration_by_type: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        alias="typicalDurationByType",
    )
    data_quality: dict[str, Any] = Field(default_factory=dict, alias="dataQuality")
    price_coverage: dict[str, int] = Field(
        default_factory=dict,
        alias="priceCoverage",
    )
    geographic_summary: dict[str, Any] = Field(
        default_factory=dict,
        alias="geographicSummary",
    )
    candidate_areas: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="candidateAreas",
    )

    model_config = {"populate_by_name": True}

    @classmethod
    def from_region_context(
        cls,
        context: RegionStatisticsContext,
    ) -> "CatalogCapabilityEvidence":
        eligible = context.planner_eligible
        return cls(
            regionKey=context.region_key,
            snapshotId=context.snapshot_ref.snapshot_id,
            catalogVersion=context.snapshot_ref.catalog_version,
            activePlaceCount=context.active_place_count,
            categoryCounts=eligible.get("countsByType", context.counts_by_type),
            timeOfDayCoverage=eligible.get(
                "timeOfDayCoverage",
                context.time_of_day_coverage,
            ),
            typicalDurationByType=eligible.get(
                "typicalDurationByType",
                context.typical_duration_by_type,
            ),
            dataQuality=eligible.get("dataQuality", context.data_quality),
            priceCoverage=eligible.get("priceCoverage", context.price_coverage),
            geographicSummary=eligible.get(
                "geographicSummary",
                context.geographic_summary,
            ),
            candidateAreas=[
                {
                    "regionKey": area.get("regionKey"),
                    "activePlaceCount": area.get(
                        "activePlaceCount",
                        area.get("placeCount", 0),
                    ),
                    "geographicSummary": area.get("geographicSummary", {}),
                }
                for area in context.area_profiles
                if area.get("regionKey")
            ],
        )


class PlannerEvidenceBundle(BaseModel):
    catalog: CatalogCapabilityEvidence
    tourism_zones: list[TourismZoneEvidence] = Field(
        default_factory=list,
        alias="tourismZones",
    )
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @property
    def can_plan(self) -> bool:
        return self.catalog.active_place_count > 0

    def apply_to(self, planner_input: PlannerAgentInput) -> PlannerAgentInput:
        """Attach verified tourism zones to the Planner/Finder hand-off."""

        return planner_input.model_copy(
            update={
                "tourism_zones": self.tourism_zones,
            }
        )


class PlannerEvidenceCollector:
    def __init__(
        self,
        *,
        tourism_zone_tool: TourismZoneResearchTool | None = None,
    ) -> None:
        self.tourism_zone_tool = (
            tourism_zone_tool or EmptyTourismZoneResearchTool()
        )

    def collect(self, planner_input: PlannerAgentInput) -> PlannerEvidenceBundle:
        catalog = CatalogCapabilityEvidence.from_region_context(
            planner_input.region_context
        )
        tourism_zones: list[TourismZoneEvidence] = []
        warnings = self._catalog_warnings(catalog)

        try:
            tourism_zones = self.tourism_zone_tool.research(
                root_region_key=planner_input.region_context.region_key,
                interests=planner_input.intent.interests,
            )
        except Exception:
            logger.exception("tourism_zone_research tool failed")
            warnings.append("Không thể tải tourism-zone evidence cho Planner.")

        return PlannerEvidenceBundle(
            catalog=catalog,
            tourismZones=tourism_zones,
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _catalog_warnings(catalog: CatalogCapabilityEvidence) -> list[str]:
        if catalog.active_place_count == 0:
            return [
                f"Không có Place active cho {catalog.region_key}; Finder chỉ "
                "có thể dùng các địa điểm người dùng đã chọn."
            ]
        warnings: list[str] = []
        missing_hours = int(catalog.data_quality.get("missingOpeningHours", 0))
        if missing_hours > catalog.active_place_count / 2:
            warnings.append(
                "Hơn một nửa Place active chưa có giờ mở cửa; Finder phải "
                "xác minh tính khả thi theo thời gian."
            )
        stale_data = int(catalog.data_quality.get("staleOperationalData", 0))
        if stale_data:
            warnings.append(f"{stale_data} Place active có dữ liệu vận hành đã cũ.")
        return warnings
