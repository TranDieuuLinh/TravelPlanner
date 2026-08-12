from pydantic import Field

from app.modules.place_checker.contract import ContractModel
from app.modules.place_checker.enums import (
    EvaluationDimension,
    IssueSeverity,
    PlaceLifecycleState,
)
from app.modules.place_checker.resolution_contract import EnrichedIdentityPlace


class EvaluationFinding(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    dimension: EvaluationDimension
    severity: IssueSeverity
    hard: bool = False
    message: str = Field(min_length=1, max_length=500)


class PlannerConstraint(ContractModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)


class DataQualityEvaluation(ContractModel):
    completeness_score: float = Field(ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    stale: bool = False


class PeopleSuitabilityEvaluation(ContractModel):
    adults: bool | None = True
    children: bool | None = None
    infants: bool | None = None
    accessibility: list[str] = Field(default_factory=list)


class PlaceEvaluation(ContractModel):
    place: EnrichedIdentityPlace
    state: PlaceLifecycleState
    planner_eligible: bool
    destination_compatible: bool | None = None
    preference_matches: list[str] = Field(default_factory=list)
    avoid_conflicts: list[str] = Field(default_factory=list)
    people_suitability: PeopleSuitabilityEvaluation
    data_quality: DataQualityEvaluation
    findings: list[EvaluationFinding] = Field(default_factory=list)
    planner_constraints: list[PlannerConstraint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlaceEvaluationBatch(ContractModel):
    places: list[PlaceEvaluation] = Field(default_factory=list)
    planner_eligible_place_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
