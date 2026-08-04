"""Knowledge Graph research package.

Read-only tools for analyzing and querying the knowledge graph.
"""

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
    EdgeEvidence,
    EntitySummary,
    ExperienceDiscoveryInput,
    GraphEvidenceBundle,
    GraphEvidenceClaim,
    GraphSnapshot,
    GraphStats,
    PLACE_TYPES,
    Recommendation,
    RecommendationPriority,
    ScopeResolveInput,
    ScopeResolveOutput,
    TrustLevel,
    UnknownClaim,
)
from app.modules.knowledge_graph.research.scope_tool import (
    LegacyAreaWarning,
    kg_resolve_scope,
)

__all__ = [
    # Repository
    "ScopeResolutionRepository",
    "KnowledgeGraphResearchRepository",
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
]
