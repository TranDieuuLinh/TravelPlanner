from pydantic import Field

from app.modules.place_checker.contract import ContractModel, InputItem
from app.modules.place_checker.enums import CostTier, ItemResolutionStatus
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import ProviderAttempt
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence


class ItemPlaceOption(ContractModel):
    place_id: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=80)
    provider_id: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=500)
    coordinates: Coordinates | None = None
    tags: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    cost_tier: CostTier = CostTier.unknown
    cost_currency: str | None = Field(default=None, min_length=3, max_length=3)
    minimum_cost: float | None = Field(default=None, ge=0)
    typical_cost: float | None = Field(default=None, ge=0)
    maximum_cost: float | None = Field(default=None, ge=0)
    opening_hours: list[str] | None = None
    relationships: list[PlaceRelationshipEvidence] = Field(default_factory=list)
    children_suitable: bool | None = None
    infants_suitable: bool | None = None
    minimum_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    typical_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    maximum_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    anchor_distance_km: float | None = Field(default=None, ge=0)
    proximity_status: str | None = Field(
        default=None,
        pattern="^(nearby|acceptable|far|unknown)$",
    )
    score: float = Field(ge=0, le=1)
    rejection_reasons: list[str] = Field(default_factory=list)


class SpecialExperience(ContractModel):
    requirement: str = Field(min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=80)
    anchor_place_id: str = Field(min_length=1, max_length=300)
    evidence: str = Field(min_length=1, max_length=4000)


class ResolvedInputItem(ContractModel):
    item_index: int = Field(ge=0)
    item: InputItem
    normalized_requirement: str = Field(min_length=1, max_length=200)
    status: ItemResolutionStatus
    selected: ItemPlaceOption | None = None
    alternatives: list[ItemPlaceOption] = Field(default_factory=list, max_length=4)
    confidence: float | None = Field(default=None, ge=0, le=1)
    selection_reason: str | None = None
    evidence: str = Field(min_length=1, max_length=4000)
    special_experience: SpecialExperience | None = None
    provider_attempts: list[ProviderAttempt] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ItemResolutionBatch(ContractModel):
    items: list[ResolvedInputItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
