from datetime import datetime

from pydantic import Field, model_validator

from app.modules.place_checker.contract import ContractModel
from app.modules.place_checker.enums import (
    GapType,
    IssueSeverity,
    PromotionEventStatus,
    RetrievalSourceKind,
    VerificationStatus,
)
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.shared.contracts.place import Coordinates


class TargetedRetrievalQuery(ContractModel):
    gap_id: str = Field(min_length=1, max_length=120)
    gap_type: GapType
    severity: IssueSeverity
    query_text: str = Field(min_length=1, max_length=300)
    adm_id: str = Field(min_length=1, max_length=200)
    adm_name: str = Field(min_length=1, max_length=200)
    country_code: str = Field(min_length=2, max_length=3)
    category_hint: str | None = Field(default=None, max_length=120)
    budget_level: str = Field(min_length=1, max_length=20)
    people_tags: list[str] = Field(default_factory=list)
    time_hints: list[str] = Field(default_factory=list)
    anchor_place_ids: list[str] = Field(default_factory=list, max_length=10)
    relation_terms: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=10, ge=1, le=60)


class RetrievalEvidence(ContractModel):
    provider: str = Field(min_length=1, max_length=80)
    source_kind: RetrievalSourceKind
    provider_id: str | None = Field(default=None, max_length=300)
    entity_id: str | None = Field(default=None, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    adm_id: str | None = Field(default=None, max_length=200)
    region_key: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    experience_type: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=500)
    coordinates: Coordinates | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    relationship_score: float = Field(default=0, ge=0, le=1)
    fetched_at: datetime | None = None
    metadata: PlaceMetadata | None = None


class RetrievalAttempt(ContractModel):
    provider: str
    source_kind: RetrievalSourceKind
    outcome: str = Field(pattern="^(candidates|empty|error|timeout|skipped)$")
    candidate_count: int = Field(default=0, ge=0)
    error_code: str | None = None


class RetrievedCandidate(ContractModel):
    candidate_key: str = Field(min_length=1, max_length=300)
    gap_id: str = Field(min_length=1, max_length=120)
    gap_type: GapType
    gap_severity: IssueSeverity
    canonical_name: str = Field(min_length=1, max_length=200)
    place_id: str | None = Field(default=None, max_length=200)
    adm_id: str | None = Field(default=None, max_length=200)
    region_key: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    # Nhóm mà PlaceChecker đang bổ sung cho pool. Giữ riêng với category gốc
    # từ catalog để không biến dữ liệu phân loại thật thành nhãn tìm kiếm.
    pool_category: str | None = Field(default=None, max_length=120)
    experience_type: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=500)
    coordinates: Coordinates | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: PlaceMetadata | None = None
    verification_status: VerificationStatus
    planner_eligible: bool
    evidence: list[RetrievalEvidence] = Field(min_length=1)
    conflicts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    relationship_score: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def eligibility_requires_verification(self) -> "RetrievedCandidate":
        verified = {
            VerificationStatus.verified_kg,
            VerificationStatus.verified_external,
        }
        if self.planner_eligible and self.verification_status not in verified:
            raise ValueError("planner eligibility requires verified identity")
        return self


class GapRetrievalResult(ContractModel):
    gap_id: str
    query: TargetedRetrievalQuery
    candidates: list[RetrievedCandidate] = Field(default_factory=list)
    attempts: list[RetrievalAttempt] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RetrievalBatch(ContractModel):
    gaps: list[GapRetrievalResult] = Field(default_factory=list)
    promotion_event_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PromotionEvent(ContractModel):
    event_id: str = Field(min_length=1, max_length=200)
    candidate: RetrievedCandidate
    status: PromotionEventStatus = PromotionEventStatus.pending
    promoted_entity_id: str | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def only_verified_external_is_promoted(self) -> "PromotionEvent":
        if self.candidate.verification_status != VerificationStatus.verified_external:
            raise ValueError("only verified external candidate can be promoted")
        return self


class PromotionWorkResult(ContractModel):
    event_id: str
    status: PromotionEventStatus
    entity_id: str | None = None
    duplicate: bool = False
    error_code: str | None = None
