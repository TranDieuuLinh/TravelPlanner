from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.core.config import get_settings
from app.modules.knowledge_graph.adapters.postgres import PostgresKnowledgeGraphStore
from app.modules.knowledge_graph.contract import (
    AliasDetail,
    AliasUpsert,
    AutoAttachRule,
    AutoAttachRuleList,
    AutoAttachAlias,
    AutoAttachAliasList,
    DeleteResponse,
    EntityCopy,
    EntityCreate,
    EntityDetail,
    EntityFilterOptions,
    EntityListPage,
    EntitySummary,
    EntityUpdate,
    KGStats,
    LowReviewResponse,
    PropertyDetail,
    PropertyUpsert,
    RelationshipSummary,
    RelationshipUpsert,
)
from app.modules.knowledge_graph.ontology import ontology_payload
from app.modules.knowledge_graph.security import require_admin, require_admin_write
from app.modules.knowledge_graph.service import KnowledgeGraphError, KnowledgeGraphService


router = APIRouter(prefix="/admin/knowledge-graph", tags=["admin-knowledge-graph"])


def get_service(request: Request) -> KnowledgeGraphService:
    service = getattr(request.app.state, "knowledge_graph_service", None)
    if service is None:
        settings = get_settings()
        if not settings.database_url:
            raise HTTPException(status_code=503, detail={"code": "DATABASE_NOT_CONFIGURED", "message": "Knowledge Graph cần DATABASE_URL."})
        service = KnowledgeGraphService(PostgresKnowledgeGraphStore(settings.database_url))
        request.app.state.knowledge_graph_service = service
    return service


def handle(error: KnowledgeGraphError) -> None:
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message}) from None


@router.get("/stats", response_model=KGStats)
async def stats(_: Annotated[object, Depends(require_admin)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> KGStats:
    return KGStats.model_validate(await service.stats())


@router.get("/ontology")
async def ontology(_: Annotated[object, Depends(require_admin)]) -> dict[str, object]:
    return ontology_payload()


@router.get("/auto-attach/rules", response_model=AutoAttachRuleList)
async def list_auto_attach_rules(
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[KnowledgeGraphService, Depends(get_service)],
) -> AutoAttachRuleList:
    rules = [AutoAttachRule.model_validate(rule) for rule in await service.auto_attach_rules()]
    return AutoAttachRuleList(items=rules, total=len(rules))


@router.put("/auto-attach/rules/{rule_id}", response_model=AutoAttachRule)
async def upsert_auto_attach_rule(
    rule_id: str,
    payload: AutoAttachRule,
    _: Annotated[object, Depends(require_admin_write)],
    service: Annotated[KnowledgeGraphService, Depends(get_service)],
) -> AutoAttachRule:
    if payload.rule_id != rule_id:
        raise HTTPException(status_code=422, detail={"code": "KG_AUTO_ATTACH_ID_MISMATCH", "message": "Rule ID khÃ´ng khá»›p URL."})
    try:
        return AutoAttachRule.model_validate(await service.upsert_auto_attach_rule(payload))
    except KnowledgeGraphError as error:
        handle(error)


@router.delete("/auto-attach/rules/{rule_id}", status_code=204)
async def delete_auto_attach_rule(
    rule_id: str,
    _: Annotated[object, Depends(require_admin_write)],
    service: Annotated[KnowledgeGraphService, Depends(get_service)],
) -> Response:
    try:
        await service.delete_auto_attach_rule(rule_id)
    except KnowledgeGraphError as error:
        handle(error)
    return Response(status_code=204)


@router.get("/auto-attach/aliases", response_model=AutoAttachAliasList)
async def list_auto_attach_aliases(
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[KnowledgeGraphService, Depends(get_service)],
) -> AutoAttachAliasList:
    aliases = [AutoAttachAlias.model_validate(item) for item in await service.auto_attach_aliases()]
    return AutoAttachAliasList(items=aliases, total=len(aliases))


@router.put("/auto-attach/aliases/{keyword}", response_model=AutoAttachAlias)
async def upsert_auto_attach_alias(
    keyword: str,
    payload: AutoAttachAlias,
    _: Annotated[object, Depends(require_admin_write)],
    service: Annotated[KnowledgeGraphService, Depends(get_service)],
) -> AutoAttachAlias:
    if payload.keyword != keyword:
        raise HTTPException(status_code=422, detail={"code": "KG_AUTO_ATTACH_KEYWORD_MISMATCH", "message": "Keyword khÃ´ng khá»›p URL."})
    return AutoAttachAlias.model_validate(
        await service.upsert_auto_attach_alias(payload.keyword, payload.aliases, payload.source)
    )


@router.get("/entities", response_model=EntityListPage)
async def list_entities(
    _: Annotated[object, Depends(require_admin)], service: Annotated[KnowledgeGraphService, Depends(get_service)],
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), search: str | None = None,
    entity_type: str | None = Query(None), status: str | None = None, exclude_names: str | None = Query(None, alias="excludeNames"),
    missing_properties: str | None = Query(None, alias="missingProperties"),
    sort_by: str = Query("name", alias="sortBy"), sort_direction: str = Query("asc", alias="sortDirection"),
) -> EntityListPage:
    items, total = await service.entities(limit=limit, offset=offset, search=search, entity_type=entity_type, status=status, exclude_names=exclude_names, missing_properties=missing_properties, sort_by=sort_by, sort_direction=sort_direction)
    return EntityListPage(items=[EntitySummary.model_validate(item) for item in items], total=total, limit=limit, offset=offset, has_more=offset + len(items) < total)


@router.get("/entities/filters", response_model=EntityFilterOptions)
async def entity_filter_options(
    _: Annotated[object, Depends(require_admin)],
    service: Annotated[KnowledgeGraphService, Depends(get_service)],
) -> EntityFilterOptions:
    return EntityFilterOptions.model_validate(await service.entity_filter_options())


@router.post("/entities", response_model=EntityDetail, status_code=201)
async def create_entity(payload: EntityCreate, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.create_entity(payload))
    except KnowledgeGraphError as error:
        handle(error)


@router.get("/entities/low-review-count", response_model=LowReviewResponse)
async def low_review_count(_: Annotated[object, Depends(require_admin)], service: Annotated[KnowledgeGraphService, Depends(get_service)], threshold: int = Query(50, ge=0, le=100000)) -> LowReviewResponse:
    return LowReviewResponse.model_validate(await service.low_review_count(threshold))


@router.delete("/entities/low-review-count", response_model=LowReviewResponse)
async def delete_low_review(_: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)], threshold: int = Query(50, ge=0, le=100000)) -> LowReviewResponse:
    return LowReviewResponse.model_validate(await service.delete_low_review(threshold))


@router.get("/entities/{entity_id}", response_model=EntityDetail)
async def get_entity(
    entity_id: str, _: Annotated[object, Depends(require_admin)], service: Annotated[KnowledgeGraphService, Depends(get_service)],
    alias_offset: int = Query(0, ge=0), alias_limit: int = Query(100, ge=0, le=500), property_offset: int = Query(0, ge=0),
    property_limit: int = Query(100, ge=0, le=500), relationship_offset: int = Query(0, ge=0), relationship_limit: int = Query(100, ge=0, le=500),
) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.entity(entity_id, alias_offset=alias_offset, alias_limit=alias_limit, property_offset=property_offset, property_limit=property_limit, relationship_offset=relationship_offset, relationship_limit=relationship_limit))
    except KnowledgeGraphError as error:
        handle(error)


@router.patch("/entities/{entity_id}", response_model=EntityDetail)
async def update_entity(entity_id: str, payload: EntityUpdate, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.update_entity(entity_id, payload))
    except KnowledgeGraphError as error:
        handle(error)


@router.post("/entities/{entity_id}/copy", response_model=EntityDetail, status_code=201)
async def copy_entity(entity_id: str, payload: EntityCopy, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.copy_entity(entity_id, payload.entity_id, payload.canonical_name))
    except KnowledgeGraphError as error:
        handle(error)


@router.delete("/entities/{entity_id}", response_model=DeleteResponse, status_code=200)
async def delete_entity(entity_id: str, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> DeleteResponse:
    try:
        await service.delete_entity(entity_id)
    except KnowledgeGraphError as error:
        handle(error)
    return DeleteResponse(deleted_entity_id=entity_id)


@router.post("/entities/{entity_id}/aliases", response_model=EntityDetail)
async def create_alias(entity_id: str, payload: AliasUpsert, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.alias(entity_id, payload))
    except KnowledgeGraphError as error:
        handle(error)


@router.put("/entities/{entity_id}/aliases/{alias_id}", response_model=EntityDetail)
async def update_alias(entity_id: str, alias_id: int, payload: AliasUpsert, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.alias(entity_id, payload, alias_id))
    except KnowledgeGraphError as error:
        handle(error)


@router.delete("/entities/{entity_id}/aliases/{alias_id}", response_model=DeleteResponse)
async def delete_alias(entity_id: str, alias_id: int, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> DeleteResponse:
    try:
        await service.delete_alias(entity_id, alias_id)
    except KnowledgeGraphError as error:
        handle(error)
    return DeleteResponse(deleted_alias_id=alias_id)


@router.post("/entities/{entity_id}/properties", response_model=EntityDetail)
async def create_property(entity_id: str, payload: PropertyUpsert, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.property(entity_id, payload))
    except KnowledgeGraphError as error:
        handle(error)


@router.put("/entities/{entity_id}/properties/{property_id}", response_model=EntityDetail)
async def update_property(entity_id: str, property_id: int, payload: PropertyUpsert, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.property(entity_id, payload, property_id))
    except KnowledgeGraphError as error:
        handle(error)


@router.delete("/entities/{entity_id}/properties/{property_id}", response_model=DeleteResponse)
async def delete_property(entity_id: str, property_id: int, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> DeleteResponse:
    try:
        await service.delete_property(entity_id, property_id)
    except KnowledgeGraphError as error:
        handle(error)
    return DeleteResponse(deleted_property_id=property_id)


@router.post("/entities/{entity_id}/relationships", response_model=EntityDetail)
async def create_relationship(entity_id: str, payload: RelationshipUpsert, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.relationship(entity_id, payload))
    except KnowledgeGraphError as error:
        handle(error)


@router.put("/entities/{entity_id}/relationships/{relationship_id}", response_model=EntityDetail)
async def update_relationship(entity_id: str, relationship_id: int, payload: RelationshipUpsert, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> EntityDetail:
    try:
        return EntityDetail.model_validate(await service.relationship(entity_id, payload, relationship_id))
    except KnowledgeGraphError as error:
        handle(error)


@router.delete("/entities/{entity_id}/relationships/{relationship_id}", response_model=DeleteResponse)
async def delete_relationship(entity_id: str, relationship_id: int, _: Annotated[object, Depends(require_admin_write)], service: Annotated[KnowledgeGraphService, Depends(get_service)]) -> DeleteResponse:
    try:
        await service.delete_relationship(entity_id, relationship_id)
    except KnowledgeGraphError as error:
        handle(error)
    return DeleteResponse(deleted_relationship_id=relationship_id)


@router.get("/relationships", response_model=dict)
async def list_relationships(
    _: Annotated[object, Depends(require_admin)], service: Annotated[KnowledgeGraphService, Depends(get_service)],
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), relationship: str | None = None,
    from_entity_id: str | None = Query(None), to_entity_id: str | None = Query(None), search: str | None = None,
    sort_by: str = Query("id", alias="sortBy"), sort_direction: str = Query("asc", alias="sortDirection"),
) -> dict:
    items, total = await service.relationships(limit=limit, offset=offset, relationship=relationship, from_entity_id=from_entity_id, to_entity_id=to_entity_id, search=search, sort_by=sort_by, sort_direction=sort_direction)
    return {"items": [RelationshipSummary.model_validate(item).model_dump(by_alias=True) for item in items], "total": total, "limit": limit, "offset": offset, "hasMore": offset + len(items) < total}
