"""Admin Knowledge Graph entity API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.auth.dependencies import require_csrf, require_role
from app.modules.knowledge_graph.dependencies import get_db, get_knowledge_graph_repository
from app.modules.knowledge_graph.model import KnowledgeAlias, KnowledgeProperty, KnowledgeRelationship
from app.modules.knowledge_graph.repositories import KnowledgeGraphRepository
from app.modules.users.model import User

router = APIRouter(prefix="/admin/knowledge-graph", tags=["admin-knowledge-graph"])


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class KnowledgeGraphResponse(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class KnowledgeGraphStats(KnowledgeGraphResponse):
    entity_count: int
    alias_count: int
    relationship_count: int


class EntitySummary(KnowledgeGraphResponse):
    id: str
    canonical_name: str
    entity_type: str
    status: str
    created_at: str
    updated_at: str
    review_count: int | None = None


class EntityListResponse(KnowledgeGraphResponse):
    items: list[EntitySummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class EntityDeleteResponse(KnowledgeGraphResponse):
    deleted_entity_id: str


class LowReviewEntityResponse(KnowledgeGraphResponse):
    threshold: int
    entity_count: int


class LowReviewEntityDeleteResponse(LowReviewEntityResponse):
    deleted_entity_count: int


class AliasDetail(KnowledgeGraphResponse):
    id: int
    alias: str
    language: str
    alias_type: str
    source: str | None
    provider: str | None
    status: str
    confidence: float | None
    verified_at: str | None
    created_at: str


class PropertyDetail(KnowledgeGraphResponse):
    id: int
    key: str
    value: str
    source: str | None
    updated_at: str


class RelationshipSummary(KnowledgeGraphResponse):
    id: int
    from_entity_id: str
    relationship: str
    to_entity_id: str
    source: str | None
    created_at: str


class EntityDetailResponse(KnowledgeGraphResponse):
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


class EntityUpdateRequest(KnowledgeGraphResponse):
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    entity_type: str | None = Field(default=None, alias="entityType")
    status: str | None = None


class EntityCreateRequest(KnowledgeGraphResponse):
    entity_id: str = Field(alias="entityId", min_length=1, max_length=96)
    canonical_name: str = Field(alias="canonicalName", min_length=1, max_length=255)
    entity_type: str = Field(alias="entityType", min_length=1, max_length=80)
    status: str = Field(default="draft", min_length=1, max_length=32)


class EntityCopyRequest(KnowledgeGraphResponse):
    entity_id: str = Field(alias="entityId", min_length=1, max_length=96)
    canonical_name: str | None = Field(default=None, alias="canonicalName", max_length=255)


class AliasUpsertRequest(KnowledgeGraphResponse):
    alias: str
    language: str = "en"
    alias_type: str = Field(default="alternate_name", alias="aliasType")
    source: str | None = None
    provider: str | None = None
    status: str = "imported"
    confidence: float | None = Field(default=None, ge=0, le=1)


class PropertyUpsertRequest(KnowledgeGraphResponse):
    key: str
    value: str
    source: str | None = None


class RelationshipUpsertRequest(KnowledgeGraphResponse):
    relationship: str
    to_entity_id: str = Field(alias="toEntityId")
    source: str | None = None
    recommendations: dict | None = None


class RelationshipListResponse(KnowledgeGraphResponse):
    items: list[RelationshipSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


def _entity_detail_response(
    repo: KnowledgeGraphRepository,
    entity_id: str,
    *,
    alias_offset: int = 0,
    alias_limit: int = 20,
    property_offset: int = 0,
    property_limit: int = 500,
    relationship_offset: int = 0,
    relationship_limit: int = 20,
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
                alias_type=a.alias_type,
                source=a.source,
                provider=a.provider,
                status=a.status,
                confidence=a.confidence,
                verified_at=a.verified_at.isoformat() if a.verified_at else None,
                created_at=a.created_at.isoformat() if a.created_at else "",
            )
            for a in detail["aliases"]
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
            for p in detail["properties"]
        ],
        property_total=detail["property_total"],
        property_has_more=detail["property_has_more"],
        relationships=[
            RelationshipSummary(
                id=r.id,
                from_entity_id=r.from_entity_id,
                relationship=r.relationship_type,
                to_entity_id=r.to_entity_id,
                source=r.source,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rels
        ],
        relationship_total=rel_total,
        relationship_has_more=relationship_offset + len(rels) < rel_total,
    )


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
    exclude_names: Annotated[str, Query(alias="excludeNames", max_length=500)] = "",
    sort_by: Annotated[str, Query(alias="sortBy")] = "name",
    sort_direction: Annotated[str, Query(alias="sortDirection", pattern="^(asc|desc)$")] = "asc",
) -> EntityListResponse:
    entities, total = repo.list_entities(
        limit=limit,
        offset=offset,
        search=search,
        entity_type=entity_type,
        status=status,
        exclude_names=[term.strip() for term in exclude_names.split(",") if term.strip()],
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    review_counts: dict[str, int] = {}
    if entities:
        for prop in repo.db.scalars(
            select(KnowledgeProperty).where(
                KnowledgeProperty.entity_id.in_([entity.id for entity in entities]),
                KnowledgeProperty.key == "review_count",
            )
        ):
            try:
                review_counts[prop.entity_id] = int(float(prop.value))
            except (TypeError, ValueError):
                continue
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
                review_count=review_counts.get(e.id),
            )
            for e in entities
        ],
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get("/entities/low-review-count", response_model=LowReviewEntityResponse)
def get_low_review_entity_count(
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    threshold: Annotated[int, Query(ge=1, le=1_000_000)] = 50,
) -> LowReviewEntityResponse:
    return LowReviewEntityResponse(
        threshold=threshold,
        entity_count=len(repo.entity_ids_below_review_count(threshold)),
    )


@router.post("/entities", response_model=EntityDetailResponse, status_code=201)
def create_entity(
    payload: EntityCreateRequest,
    user: Annotated[User, Depends(require_csrf)],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    require_role("admin")(user)
    entity_id = payload.entity_id.strip()
    if repo.get_entity(entity_id) is not None:
        raise AppError(409, "ENTITY_CONFLICT", "An entity with this ID already exists.")
    repo.upsert_entity(
        entity_id,
        payload.canonical_name.strip(),
        payload.entity_type.strip(),
        status=payload.status.strip(),
    )
    repo.db.commit()
    return _entity_detail_response(repo, entity_id)


@router.delete("/entities/low-review-count", response_model=LowReviewEntityDeleteResponse)
def delete_low_review_entities(
    user: Annotated[User, Depends(require_csrf)],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    threshold: Annotated[int, Query(ge=1, le=1_000_000)] = 50,
) -> LowReviewEntityDeleteResponse:
    require_role("admin")(user)
    entity_count = len(repo.entity_ids_below_review_count(threshold))
    deleted_entity_count = repo.delete_entities_below_review_count(threshold)
    repo.db.commit()
    return LowReviewEntityDeleteResponse(
        threshold=threshold,
        entity_count=entity_count,
        deleted_entity_count=deleted_entity_count,
    )


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse)
def get_entity_detail(
    entity_id: str,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    alias_offset: Annotated[int, Query(ge=0)] = 0,
    alias_limit: Annotated[int, Query(ge=0, le=50)] = 20,
    property_offset: Annotated[int, Query(ge=0)] = 0,
    property_limit: Annotated[int, Query(ge=0, le=500)] = 500,
    relationship_offset: Annotated[int, Query(ge=0)] = 0,
    relationship_limit: Annotated[int, Query(ge=0, le=50)] = 20,
) -> EntityDetailResponse:
    return _entity_detail_response(
        repo,
        entity_id,
        alias_offset=alias_offset,
        alias_limit=alias_limit,
        property_offset=property_offset,
        property_limit=property_limit,
        relationship_offset=relationship_offset,
        relationship_limit=relationship_limit,
    )


@router.patch("/entities/{entity_id}", response_model=EntityDetailResponse)
def update_entity(
    entity_id: str,
    payload: EntityUpdateRequest,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    if payload.canonical_name is None and payload.entity_type is None and payload.status is None:
        raise AppError(422, "ENTITY_UPDATE_EMPTY", "Hãy cung cấp ít nhất một trường để cập nhật.")
    if repo.update_entity(
        entity_id,
        canonical_name=payload.canonical_name,
        entity_type=payload.entity_type,
        status=payload.status,
    ) is None:
        raise AppError(404, "ENTITY_NOT_FOUND", "Entity not found.")
    try:
        repo.db.commit()
    except IntegrityError as exc:
        repo.db.rollback()
        raise AppError(409, "ENTITY_CONFLICT", "Không thể lưu entity vì dữ liệu đã trùng hoặc không hợp lệ.") from exc
    return _entity_detail_response(repo, entity_id)


@router.delete("/entities/{entity_id}", response_model=EntityDeleteResponse)
def delete_entity(
    entity_id: str,
    user: Annotated[User, Depends(require_csrf)],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDeleteResponse:
    """Delete an entity and every alias, property, and relationship attached to it."""
    from app.shared.errors import AppError

    require_role("admin")(user)
    if not repo.delete_entity(entity_id):
        raise AppError(404, "ENTITY_NOT_FOUND", "Entity not found.")
    repo.db.commit()
    return EntityDeleteResponse(deleted_entity_id=entity_id)


@router.post("/entities/{entity_id}/copy", response_model=EntityDetailResponse, status_code=201)
def copy_entity(
    entity_id: str,
    payload: EntityCopyRequest,
    user: Annotated[User, Depends(require_csrf)],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    require_role("admin")(user)
    new_entity_id = payload.entity_id.strip()
    if repo.get_entity(new_entity_id) is not None:
        raise AppError(409, "ENTITY_CONFLICT", "An entity with this ID already exists.")
    copied = repo.copy_entity(
        entity_id,
        new_entity_id,
        canonical_name=payload.canonical_name.strip() if payload.canonical_name else None,
    )
    if copied is None:
        raise AppError(404, "ENTITY_NOT_FOUND", "Entity not found.")
    repo.db.commit()
    return _entity_detail_response(repo, copied.id)


@router.post("/entities/{entity_id}/aliases", response_model=EntityDetailResponse)
def create_alias(
    entity_id: str,
    payload: AliasUpsertRequest,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    if not repo.entity_exists(entity_id):
        raise AppError(404, "ENTITY_NOT_FOUND", "Entity not found.")
    repo.upsert_alias(
        entity_id,
        payload.alias,
        payload.language,
        alias_type=payload.alias_type,
        source=payload.source,
        provider=payload.provider,
        status=payload.status,
        confidence=payload.confidence,
    )
    try:
        repo.db.commit()
    except IntegrityError as exc:
        repo.db.rollback()
        raise AppError(409, "ALIAS_CONFLICT", "Alias đã tồn tại cho entity này.") from exc
    return _entity_detail_response(repo, entity_id)


@router.put("/entities/{entity_id}/aliases/{alias_id}", response_model=EntityDetailResponse)
def update_alias(
    entity_id: str,
    alias_id: int,
    payload: AliasUpsertRequest,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    alias = repo.update_alias(alias_id, alias=payload.alias, language=payload.language)
    if alias is None or alias.entity_id != entity_id:
        raise AppError(404, "ALIAS_NOT_FOUND", "Không tìm thấy alias.")
    try:
        repo.db.commit()
    except IntegrityError as exc:
        repo.db.rollback()
        raise AppError(409, "ALIAS_CONFLICT", "Alias đã tồn tại cho entity này.") from exc
    return _entity_detail_response(repo, entity_id)


@router.delete("/entities/{entity_id}/aliases/{alias_id}")
def delete_alias(
    entity_id: str,
    alias_id: int,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> dict[str, int]:
    from app.shared.errors import AppError

    alias = repo.db.get(KnowledgeAlias, alias_id)
    if alias is None or alias.entity_id != entity_id:
        raise AppError(404, "ALIAS_NOT_FOUND", "Không tìm thấy alias.")
    if not repo.delete_alias(alias_id):
        raise AppError(404, "ALIAS_NOT_FOUND", "Không tìm thấy alias.")
    repo.db.commit()
    return {"deletedAliasId": alias_id}


@router.post("/entities/{entity_id}/properties", response_model=EntityDetailResponse)
def create_property(
    entity_id: str,
    payload: PropertyUpsertRequest,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    if not repo.entity_exists(entity_id):
        raise AppError(404, "ENTITY_NOT_FOUND", "Entity not found.")
    repo.upsert_property(entity_id, payload.key, payload.value, payload.source)
    try:
        repo.db.commit()
    except IntegrityError as exc:
        repo.db.rollback()
        raise AppError(409, "PROPERTY_CONFLICT", "Property key đã tồn tại cho entity này.") from exc
    return _entity_detail_response(repo, entity_id)


@router.put("/entities/{entity_id}/properties/{property_id}", response_model=EntityDetailResponse)
def update_property(
    entity_id: str,
    property_id: int,
    payload: PropertyUpsertRequest,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    prop = repo.update_property(property_id, key=payload.key, value=payload.value, source=payload.source)
    if prop is None or prop.entity_id != entity_id:
        raise AppError(404, "PROPERTY_NOT_FOUND", "Không tìm thấy property.")
    try:
        repo.db.commit()
    except IntegrityError as exc:
        repo.db.rollback()
        raise AppError(409, "PROPERTY_CONFLICT", "Property key đã tồn tại cho entity này.") from exc
    return _entity_detail_response(repo, entity_id)


@router.delete("/entities/{entity_id}/properties/{property_id}")
def delete_property(
    entity_id: str,
    property_id: int,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> dict[str, int]:
    from app.shared.errors import AppError

    prop = repo.db.get(KnowledgeProperty, property_id)
    if prop is None or prop.entity_id != entity_id:
        raise AppError(404, "PROPERTY_NOT_FOUND", "Không tìm thấy property.")
    if not repo.delete_property(property_id):
        raise AppError(404, "PROPERTY_NOT_FOUND", "Không tìm thấy property.")
    repo.db.commit()
    return {"deletedPropertyId": property_id}


@router.post("/entities/{entity_id}/relationships", response_model=EntityDetailResponse)
def create_relationship(
    entity_id: str,
    payload: RelationshipUpsertRequest,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    if not repo.entity_exists(entity_id):
        raise AppError(404, "ENTITY_NOT_FOUND", "Entity not found.")
    if not repo.entity_exists(payload.to_entity_id):
        raise AppError(404, "TARGET_ENTITY_NOT_FOUND", "Không tìm thấy entity đích.")
    repo.upsert_relationship(
        entity_id,
        payload.relationship,
        payload.to_entity_id,
        recommendations=payload.recommendations,
        source=payload.source,
    )
    try:
        repo.db.commit()
    except IntegrityError as exc:
        repo.db.rollback()
        raise AppError(409, "RELATIONSHIP_CONFLICT", "Relationship này đã tồn tại.") from exc
    return _entity_detail_response(repo, entity_id)


@router.put("/entities/{entity_id}/relationships/{relationship_id}", response_model=EntityDetailResponse)
def update_relationship(
    entity_id: str,
    relationship_id: int,
    payload: RelationshipUpsertRequest,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> EntityDetailResponse:
    from app.shared.errors import AppError

    if not repo.entity_exists(payload.to_entity_id):
        raise AppError(404, "TARGET_ENTITY_NOT_FOUND", "Không tìm thấy entity đích.")
    rel = repo.update_relationship(
        relationship_id,
        relationship=payload.relationship,
        to_entity_id=payload.to_entity_id,
        source=payload.source,
        recommendations=payload.recommendations,
    )
    if rel is None or rel.from_entity_id != entity_id:
        raise AppError(404, "RELATIONSHIP_NOT_FOUND", "Không tìm thấy relationship.")
    try:
        repo.db.commit()
    except IntegrityError as exc:
        repo.db.rollback()
        raise AppError(409, "RELATIONSHIP_CONFLICT", "Relationship này đã tồn tại.") from exc
    return _entity_detail_response(repo, entity_id)


@router.delete("/entities/{entity_id}/relationships/{relationship_id}")
def delete_relationship(
    entity_id: str,
    relationship_id: int,
    _: Annotated[User, Depends(require_role("admin"))],
    repo: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
) -> dict[str, int]:
    from app.shared.errors import AppError

    rel = repo.db.get(KnowledgeRelationship, relationship_id)
    if rel is None or rel.from_entity_id != entity_id:
        raise AppError(404, "RELATIONSHIP_NOT_FOUND", "Không tìm thấy relationship.")
    if not repo.delete_relationship(relationship_id):
        raise AppError(404, "RELATIONSHIP_NOT_FOUND", "Không tìm thấy relationship.")
    repo.db.commit()
    return {"deletedRelationshipId": relationship_id}


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
    sort_by: Annotated[str, Query(alias="sortBy")] = "id",
    sort_direction: Annotated[str, Query(alias="sortDirection", pattern="^(asc|desc)$")] = "asc",
) -> RelationshipListResponse:
    rels, total = repo.list_relationships(
        limit=limit,
        offset=offset,
        relationship=relationship,
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        search=search,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    has_more = offset + len(rels) < total
    return RelationshipListResponse(
        items=[
            RelationshipSummary(
                id=r.id,
                from_entity_id=r.from_entity_id,
                relationship=r.relationship_type,
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


class OntologyResponse(KnowledgeGraphResponse):
    node_types: list[str]
    relationship_types: list[str]
    node_type_properties: dict[str, dict[str, list[str]]]


@router.get("/ontology", response_model=OntologyResponse)
def get_ontology(
    _: Annotated[User, Depends(require_role("admin"))],
) -> OntologyResponse:
    """Return allowed node types, relationship types, and their property definitions."""
    from app.modules.knowledge_graph.ontology import (
        get_all_node_type_properties,
        get_node_types,
        get_relationship_types,
    )

    return OntologyResponse(
        node_types=get_node_types(),
        relationship_types=get_relationship_types(),
        node_type_properties=get_all_node_type_properties(),
    )
