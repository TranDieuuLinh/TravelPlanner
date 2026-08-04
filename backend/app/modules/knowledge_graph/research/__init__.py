"""Knowledge Graph research package.

Read-only tools for analyzing and querying the knowledge graph.
"""

from app.modules.knowledge_graph.research.repository import (
    ScopeResolutionRepository,
)
from app.modules.knowledge_graph.research.schema import (
    AREA_TYPES,
    AreaRef,
    AreaType,
    GraphStats,
    ScopeResolveInput,
    ScopeResolveOutput,
)
from app.modules.knowledge_graph.research.scope_tool import (
    LegacyAreaWarning,
    kg_resolve_scope,
)

__all__ = [
    "ScopeResolutionRepository",
    "kg_resolve_scope",
    "ScopeResolveInput",
    "ScopeResolveOutput",
    "AreaRef",
    "AreaType",
    "AREA_TYPES",
    "GraphStats",
    "LegacyAreaWarning",
]
