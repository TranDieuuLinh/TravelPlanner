"""Knowledge Graph research package.

Read-only tools for analyzing and querying the knowledge graph.
"""

from app.modules.knowledge_graph.research.experience_fit_tool import (
    EntityNotFoundError,
    ExperienceFitInput,
    ExperienceFitOutput,
    kg_evaluate_experience_fit,
)
from app.modules.knowledge_graph.research.repository import (
    ScopeResolutionRepository,
)
from app.modules.knowledge_graph.research.schema import (
    AREA_TYPES,
    AreaRef,
    AreaType,
    BudgetLevel,
    CheckStatus,
    DimensionCheck,
    EntitySummary,
    GraphStats,
    ScopeResolveInput,
    ScopeResolveOutput,
    TransportMode,
)
from app.modules.knowledge_graph.research.scope_tool import (
    LegacyAreaWarning,
    kg_resolve_scope,
)

__all__ = [
    # Repository
    "ScopeResolutionRepository",
    # Scopes
    "kg_resolve_scope",
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
    "EntitySummary",
    "BudgetLevel",
    "TransportMode",
    "EntityNotFoundError",
]
