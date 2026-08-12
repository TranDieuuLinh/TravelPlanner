from pydantic import Field

from app.modules.place_checker.contract import ContractModel
from app.modules.place_checker.retrieval_contract import RetrievedCandidate


class CandidateScoreComponents(ContractModel):
    intent_match: float = Field(ge=0, le=1)
    preference_match: float = Field(ge=0, le=1)
    gap_value: float = Field(ge=0, le=1)
    budget_fit: float = Field(ge=0, le=1)
    geo_fit: float = Field(ge=0, le=1)
    people_fit: float = Field(ge=0, le=1)
    time_fit: float = Field(ge=0, le=1)
    quality: float = Field(ge=0, le=1)
    uniqueness: float = Field(ge=0, le=1)
    data_confidence: float = Field(ge=0, le=1)


class ScoredCandidate(ContractModel):
    candidate: RetrievedCandidate
    components: CandidateScoreComponents
    base_score: float = Field(ge=0, le=1)
    penalties: dict[str, float] = Field(default_factory=dict)
    penalty_total: float = Field(ge=0, le=0.65)
    final_score: float = Field(ge=0, le=1)
    rerank_score: float = Field(ge=0, le=1)
    distance_from_anchor_km: float | None = Field(default=None, ge=0)
    rank: int | None = Field(default=None, ge=1)
    eligible: bool
    exclusion_reasons: list[str] = Field(default_factory=list)
    rerank_reasons: list[str] = Field(default_factory=list)


class CandidateRankingBatch(ContractModel):
    ranked: list[ScoredCandidate] = Field(default_factory=list)
    excluded: list[ScoredCandidate] = Field(default_factory=list)
    reserve_limit_per_gap: int = Field(default=10, ge=1, le=20)
    pool_target: int = Field(default=20, ge=1, le=120)
