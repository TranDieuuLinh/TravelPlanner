"""Pydantic schemas for Knowledge Graph research tools."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AreaType(str, Enum):
    """Allowed Area entity types."""

    LEGACY_AREA = "Area"
    AREA_ADM0 = "AreaAdm0"
    AREA_ADM1 = "AreaAdm1"
    AREA_ADM2 = "AreaAdm2"


AREA_TYPES: frozenset[str] = frozenset({t.value for t in AreaType})


class AreaRef(BaseModel):
    """Reference to an Area entity with its hierarchy context."""

    id: str = Field(description="Entity identifier")
    name: str = Field(description="Canonical name")
    normalizedName: str = Field(description="Case/diacritic-normalized name")
    type: str = Field(description="Entity type (Area, AreaAdm0, AreaAdm1, AreaAdm2)")
    depth: int = Field(description="Depth in hierarchy (0 = root)")


class ScopeResolveInput(BaseModel):
    """Input schema for kg_resolve_scope tool."""

    destination: str = Field(min_length=1, description="Destination name to resolve")
    selectedPlaceIds: list[str] | None = Field(
        default=None,
        description="Optional list of Place entity IDs to map to Areas",
    )
    maxDepth: int = Field(default=4, ge=1, le=10, description="Maximum PART_OF traversal depth")
    resultLimit: int = Field(default=100, ge=1, le=1000, description="Maximum areas to return")


class ScopeResolveOutput(BaseModel):
    """Output schema for kg_resolve_scope tool."""

    rootArea: AreaRef | None = Field(
        default=None,
        description="The resolved root Area entity",
    )
    ancestors: list[AreaRef] = Field(
        default_factory=list,
        description="Ancestor Areas (parent, grandparent, etc.)",
    )
    includedAreas: list[AreaRef] = Field(
        default_factory=list,
        description="All Areas within the scope including descendants",
    )
    selectedPlaceAreas: list[AreaRef] = Field(
        default_factory=list,
        description="Areas mapped from selected Place entities via LOCATED_IN",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings (legacy types, empty graph, etc.)",
    )


class GraphStats(BaseModel):
    """Statistics about the knowledge graph."""

    entityCount: int = Field(description="Total number of entities")
    aliasCount: int = Field(description="Total number of aliases")
    relationshipCount: int = Field(description="Total number of relationships")
    areaCount: int = Field(description="Number of Area entities")
    areaAdm0Count: int = Field(description="Number of AreaAdm0 entities")
    areaAdm1Count: int = Field(description="Number of AreaAdm1 entities")
    areaAdm2Count: int = Field(description="Number of AreaAdm2 entities")


# ---------------------------------------------------------------------------
# Experience Fit Evaluation schemas
# ---------------------------------------------------------------------------


class BudgetLevel(str, Enum):
    """Budget level classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    LUXURY = "luxury"


class TransportMode(str, Enum):
    """Preferred or avoided transport modes."""

    WALKING = "walking"
    CYCLING = "cycling"
    PUBLIC_TRANSIT = "public_transit"
    TAXI = "taxi"
    CAR = "car"
    BOAT = "boat"
    MOTORBIKE = "motorbike"


class CheckStatus(str, Enum):
    """Status for each evaluation dimension."""

    SUPPORTED = "supported"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"


class DimensionCheck(BaseModel):
    """Result of a single dimension evaluation."""

    dimension: str = Field(
        description="Dimension name (e.g. 'opening_hours', 'admission_fee')"
    )
    status: CheckStatus = Field(description="Evaluation result for this dimension")
    reason: str = Field(
        description="Human-readable explanation of why this status was assigned"
    )
    evidenceClaimIds: list[str] = Field(
        default_factory=list,
        description="IDs of evidence claims that support this check",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Source labels that provided evidence for this check",
    )


class EntitySummary(BaseModel):
    """Minimal entity representation returned in fit evaluation."""

    id: str = Field(description="Entity identifier")
    name: str = Field(description="Canonical name")
    type: str = Field(description="Entity type")
    status: str = Field(description="Entity status (verified, draft, etc.)")


class ExperienceFitInput(BaseModel):
    """Input schema for kg_evaluate_experience_fit tool."""

    entityId: str | None = Field(
        default=None,
        description="Entity ID to evaluate (mutually exclusive with claimId)",
    )
    claimId: str | None = Field(
        default=None,
        description="Claim/Experience ID to evaluate (mutually exclusive with entityId)",
    )
    destination: str = Field(min_length=1, description="Destination name for scope check")
    days: int = Field(ge=1, le=30, description="Number of trip days")
    partySize: int = Field(ge=1, le=20, default=1, description="Number of travelers")
    startDate: str | None = Field(
        default=None,
        description="Optional trip start date (ISO 8601)",
    )
    endDate: str | None = Field(
        default=None,
        description="Optional trip end date (ISO 8601)",
    )
    budgetLevel: BudgetLevel | None = Field(
        default=None,
        description="Budget level preference",
    )
    budgetTargetAmount: float | None = Field(
        default=None,
        ge=0,
        description="Target total budget in VND",
    )
    excludedPlaceTypes: list[str] = Field(
        default_factory=list,
        description="Place types to exclude (e.g. 'Restaurant', 'Accommodation')",
    )
    preferredTransportModes: list[TransportMode] = Field(
        default_factory=list,
        description="Preferred transport modes",
    )
    avoidedTransportModes: list[TransportMode] = Field(
        default_factory=list,
        description="Transport modes to avoid",
    )
    accessibilityRequirements: list[str] = Field(
        default_factory=list,
        description="Accessibility requirements (e.g. 'wheelchair', 'hearing_aid')",
    )
    userConstraints: list[str] = Field(
        default_factory=list,
        description="Additional user-defined constraints",
    )


class ExperienceFitOutput(BaseModel):
    """Output schema for kg_evaluate_experience_fit tool."""

    entity: EntitySummary | None = Field(
        default=None,
        description="Summary of the evaluated entity",
    )
    overallStatus: CheckStatus = Field(
        description="Aggregated status across all dimensions"
    )
    checks: list[DimensionCheck] = Field(
        default_factory=list,
        description="Per-dimension evaluation results",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings and recommendations",
    )
