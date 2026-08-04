"""Knowledge Graph research package.

Read-only tools for analyzing and querying the knowledge graph.
"""

from app.modules.knowledge_graph.research.experience_fit_tool import (
    EntityNotFoundError,
    ExperienceFitInput,
    ExperienceFitOutput,
    kg_evaluate_experience_fit,
)
from app.modules.knowledge_graph.research.experience_tool import (
    kg_discover_experiences,
)
from app.modules.knowledge_graph.research.repository import (
    KnowledgeGraphResearchRepository,
    ScopeResolutionRepository,
)
from app.modules.knowledge_graph.research.schema import (
    AREA_TYPES,
    ActivityTypes,
    AreaRef,
    AreaType,
    BudgetLevel,
    CheckStatus,
    ConflictedExperience,
    DimensionCheck,
    EntitySummary,
    EntitySummaryFit,
    EdgeEvidence,
    ExperienceDiscoveryInput,
    FitResult,
    GraphEvidenceBundle,
    GraphEvidenceClaim,
    GraphSnapshot,
    GraphStats,
    PLACE_TYPES,
    RankedExperience,
    Recommendation,
    RecommendationPriority,
    ResearchTrace,
    ScopeResolveInput,
    ScopeResolveOutput,
    TransportMode,
    TravelBudget,
    TripResearchBundle,
    TripResearchInput,
    TrustLevel,
    UnknownClaim,
)
from app.modules.knowledge_graph.research.orchestrator import (
    GraphResearchOrchestrator,
    GraphScopeError,
    orchestrate_trip_research,
)
from app.modules.knowledge_graph.research.scope_tool import (
    LegacyAreaWarning,
    kg_resolve_scope,
)

__all__ = [
    # Repository
    "ScopeResolutionRepository",
    # Scopes
    "KnowledgeGraphResearchRepository",
    # Orchestrator
    "GraphResearchOrchestrator",
    "GraphScopeError",
    "orchestrate_trip_research",
    # Tools
    "kg_resolve_scope",
    "kg_discover_experiences",
    # Scope resolution schemas
    "ScopeResolveInput",
    "ScopeResolveOutput",
    "AreaRef",
    "AreaType",
    "AREA_TYPES",
    "GraphStats",
    "LegacyAreaWarning",
    # Experience Fit
    "kg_evaluate_experience_fit",
    "ExperienceFitInput",
    "ExperienceFitOutput",
    "CheckStatus",
    "DimensionCheck",
    "EntitySummaryFit",
    "BudgetLevel",
    "TransportMode",
    "EntityNotFoundError",
    # Experience discovery schemas
    "ExperienceDiscoveryInput",
    "GraphEvidenceBundle",
    "GraphEvidenceClaim",
    "EdgeEvidence",
    "EntitySummary",
    "Recommendation",
    "RecommendationPriority",
    "TrustLevel",
    "UnknownClaim",
    "GraphSnapshot",
    "PLACE_TYPES",
    "ActivityTypes",
    # Trip Research Orchestrator
    "TravelBudget",
    "TripResearchInput",
    "TripResearchBundle",
    "RankedExperience",
    "ConflictedExperience",
    "FitResult",
    "ResearchTrace",
]
