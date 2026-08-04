"""Admin Knowledge Graph entity API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.modules.auth.dependencies import require_role
from app.modules.knowledge_graph.dependencies import get_db, get_knowledge_graph_repository
from app.modules.knowledge_graph.repositories import KnowledgeGraphRepository
from app.modules.users.model import User

router = APIRouter(prefix="/admin/knowledge-graph", tags=["admin-knowledge-graph"])


class KnowledgeGraphStats(BaseModel):
    entity_count: int
    alias_count: int
    relationship_count: int


class EntitySummary(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    status: str
    created_at: str
    updated_at: str


class EntityListResponse(BaseModel):
    items: list[EntitySummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class AliasDetail(BaseModel):
    id: int
    alias: str
    language: str
    created_at: str


class PropertyDetail(BaseModel):
    id: int
    key: str
    value: str
    source: str | None
    updated_at: str


class RelationshipSummary(BaseModel):
    id: int
    from_entity_id: str
    relationship: str
    to_entity_id: str
    source: str | None
    created_at: str


class EntityDetailResponse(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    status: str
    created_at: str
    updated_at: str
    aliases: list[AliasDetail]
    alias_total: int
    alias_has_more: bool
    properties: list[PropertyDetail]
    property_total: int
    property_has_more: bool
    relationships: list[RelationshipSummary]
    relationship_total: int
    relationship_has_more: bool


class RelationshipListResponse(BaseModel):
    items: list[RelationshipSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


@router.get("/stats", response_model=KnowledgeGraphStats)
def get_stats(
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> KnowledgeGraphStats:
    stats = repo.stats()
    return KnowledgeGraphStats(
        entity_count=stats["entity_count"],
        alias_count=stats["alias_count"],
        relationship_count=stats["relationship_count"],
    )


@router.get("/entities", response_model=EntityListResponse)
def list_entities(
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
) -> EntityListResponse:
    entities, total = repo.list_entities(
        limit=limit,
        offset=offset,
        search=search,
        entity_type=entity_type,
        status=status,
    )
    has_more = offset + len(entities) < total
    return EntityListResponse(
        items=[
            EntitySummary(
                id=e.id,
                canonical_name=e.canonical_name,
                entity_type=e.entity_type,
                status=e.status,
                created_at=e.created_at.isoformat() if e.created_at else "",
                updated_at=e.updated_at.isoformat() if e.updated_at else "",
            )
            for e in entities
        ],
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse)
def get_entity_detail(
    entity_id: str,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    alias_offset: Annotated[int, Query(ge=0)] = 0,
    alias_limit: Annotated[int, Query(ge=1, le=50)] = 20,
    property_offset: Annotated[int, Query(ge=0)] = 0,
    property_limit: Annotated[int, Query(ge=1, le=50)] = 20,
    relationship_offset: Annotated[int, Query(ge=0)] = 0,
    relationship_limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> EntityDetailResponse:
    detail = repo.get_entity_detail(
        entity_id,
        alias_offset=alias_offset,
        alias_limit=alias_limit,
        property_offset=property_offset,
        property_limit=property_limit,
    )
    if detail is None:
        from app.shared.errors import AppError
        raise AppError(404, "ENTITY_NOT_FOUND", "Entity not found.")

    entity = detail["entity"]
    aliases_page = repo.get_aliases_for_entity(entity_id)
    properties_page = repo.get_properties_for_entity(entity_id)

    rels, rel_total = repo.list_relationships(
        limit=relationship_limit,
        offset=relationship_offset,
        from_entity_id=entity_id,
    )

    return EntityDetailResponse(
        id=entity.id,
        canonical_name=entity.canonical_name,
        entity_type=entity.entity_type,
        status=entity.status,
        created_at=entity.created_at.isoformat() if entity.created_at else "",
        updated_at=entity.updated_at.isoformat() if entity.updated_at else "",
        aliases=[
            AliasDetail(
                id=a.id,
                alias=a.alias,
                language=a.language,
                created_at=a.created_at.isoformat() if a.created_at else "",
            )
            for a in aliases_page
        ],
        alias_total=detail["alias_total"],
        alias_has_more=detail["alias_has_more"],
        properties=[
            PropertyDetail(
                id=p.id,
                key=p.key,
                value=p.value,
                source=p.source,
                updated_at=p.updated_at.isoformat() if p.updated_at else "",
            )
            for p in properties_page
        ],
        property_total=detail["property_total"],
        property_has_more=detail["property_has_more"],
        relationships=[
            RelationshipSummary(
                id=r.id,
                from_entity_id=r.from_entity_id,
                relationship=r.relationship,
                to_entity_id=r.to_entity_id,
                source=r.source,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rels
        ],
        relationship_total=rel_total,
        relationship_has_more=relationship_offset + len(rels) < rel_total,
    )


@router.get("/relationships", response_model=RelationshipListResponse)
def list_relationships(
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    relationship: str | None = None,
    from_entity_id: str | None = None,
    to_entity_id: str | None = None,
    search: str | None = None,
) -> RelationshipListResponse:
    rels, total = repo.list_relationships(
        limit=limit,
        offset=offset,
        relationship=relationship,
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        search=search,
    )
    has_more = offset + len(rels) < total
    return RelationshipListResponse(
        items=[
            RelationshipSummary(
                id=r.id,
                from_entity_id=r.from_entity_id,
                relationship=r.relationship,
                to_entity_id=r.to_entity_id,
                source=r.source,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rels
        ],
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )
