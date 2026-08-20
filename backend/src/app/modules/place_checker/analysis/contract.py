from decimal import Decimal

from pydantic import Field

from app.modules.place_checker.contract import CapacityRange, ContractModel
from app.modules.place_checker.enums import (
    BudgetAssessmentStatus,
    BudgetMode,
    CapacityLoadStatus,
    CoverageLevel,
    GapStatus,
    GapType,
    GeographicSpread,
    IssueSeverity,
)


class AmountRangeAnalysis(ContractModel):
    minimum: Decimal | None = Field(default=None, ge=0)
    typical: Decimal | None = Field(default=None, ge=0)
    maximum: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    complete: bool = False


class CostGroupAnalysis(ContractModel):
    place_count: int = Field(ge=0)
    known_amount_count: int = Field(ge=0)
    unknown_amount_count: int = Field(ge=0)
    amount_range: AmountRangeAnalysis
    tier_distribution: dict[str, int] = Field(default_factory=dict)


class BudgetAnalysis(ContractModel):
    mode: BudgetMode
    status: BudgetAssessmentStatus
    target_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    mandatory: CostGroupAnalysis
    optional: CostGroupAnalysis
    total: CostGroupAnalysis
    warnings: list[str] = Field(default_factory=list)


class DurationLoadAnalysis(ContractModel):
    place_count: int = Field(ge=0)
    known_duration_count: int = Field(ge=0)
    unknown_duration_count: int = Field(ge=0)
    minimum_minutes: int = Field(default=0, ge=0)
    typical_minutes: int = Field(default=0, ge=0)
    maximum_minutes: int = Field(default=0, ge=0)


class GeographicOverheadAnalysis(ContractModel):
    known_coordinate_count: int = Field(ge=0)
    unknown_coordinate_count: int = Field(ge=0)
    spread: GeographicSpread
    radius_km: float | None = Field(default=None, ge=0)
    estimated_minutes: int = Field(default=0, ge=0)


class CapacityAnalysis(ContractModel):
    status: CapacityLoadStatus
    available_minutes: CapacityRange
    mandatory: DurationLoadAnalysis
    preferred: DurationLoadAnalysis
    optional: DurationLoadAnalysis
    total: DurationLoadAnalysis
    geographic_overhead: GeographicOverheadAnalysis
    typical_utilization: float | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)


class CoverageAnalysis(ContractModel):
    level: CoverageLevel
    planner_eligible_place_count: int = Field(ge=0)
    mandatory_place_count: int = Field(ge=0)
    category_distribution: dict[str, int] = Field(default_factory=dict)
    resolved_item_count: int = Field(ge=0)
    unresolved_item_count: int = Field(ge=0)
    food_covered: bool
    experience_covered: bool
    time_hints: list[str] = Field(default_factory=list)


class AnalysisGap(ContractModel):
    gap_id: str = Field(min_length=1, max_length=120)
    gap_type: GapType
    severity: IssueSeverity
    status: GapStatus = GapStatus.open
    trigger: str = Field(min_length=1, max_length=500)
    suggested_action: str = Field(min_length=1, max_length=500)
    related_place_ids: list[str] = Field(default_factory=list)
    related_item_indexes: list[int] = Field(default_factory=list)
    resolved_place_ids: list[str] = Field(default_factory=list)


class GapAnalysis(ContractModel):
    gaps: list[AnalysisGap] = Field(default_factory=list)
    open_count: int = Field(default=0, ge=0)
    critical_count: int = Field(default=0, ge=0)


class TripAggregateAnalysis(ContractModel):
    budget: BudgetAnalysis
    capacity: CapacityAnalysis
    coverage: CoverageAnalysis
    gaps: GapAnalysis
