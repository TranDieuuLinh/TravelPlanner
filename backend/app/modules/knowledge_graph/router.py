from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.auth.dependencies import require_csrf, require_role
from app.modules.knowledge_graph.dependencies import get_knowledge_graph_import_service
from app.modules.knowledge_graph.schema import (
    DeleteEdgeResponse,
    DeleteImportResponse,
    DeleteNodeResponse,
    GraphImportCreate,
    GraphImportDetail,
    GraphImportList,
    GraphImportListQuery,
    GraphImportMeta,
    GraphImportSummary,
    ProposedEdgeMutation,
    ProposedEdgePage,
    ProposedEdgePageQuery,
    ProposedEdgeUpdate,
    ProposedNodeMutation,
    ProposedNodePage,
    ProposedNodePageQuery,
    ProposedNodeRead,
    ProposedEdgeRead,
    ProposedNodeUpdate,
)
from app.modules.knowledge_graph.service import KnowledgeGraphImportService
from app.modules.users.model import User

router = APIRouter(prefix="/admin/knowledge-graph/imports", tags=["admin-knowledge-graph"])


@router.get("", response_model=GraphImportList)
def list_imports(
    query: Annotated[GraphImportListQuery, Depends()],
    _: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> GraphImportList:
    items, total = service.list(
        limit=query.limit,
        offset=query.offset,
        status=query.status,
        search=query.search,
    )
    has_more = query.offset + len(items) < total
    return GraphImportList(
        items=[GraphImportSummary.model_validate(item) for item in items],
        total=total,
        limit=query.limit,
        offset=query.offset,
        has_more=has_more,
    )


@router.post("", response_model=GraphImportMeta)
async def create_import(
    payload: GraphImportCreate,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> GraphImportMeta:
    require_role("admin")(admin)
    job = await service.create(payload, user_id=admin.id)
    return GraphImportMeta.model_validate(service._meta_dict(job))


@router.get("/{import_id}/meta", response_model=GraphImportMeta)
def get_import_meta(
    import_id: str,
    _: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> GraphImportMeta:
    return GraphImportMeta.model_validate(service.get_meta(import_id))


@router.get("/{import_id}", response_model=GraphImportDetail)
def get_import(
    import_id: str,
    _: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> GraphImportDetail:
    return GraphImportDetail.model_validate(service.get(import_id))


@router.get("/{import_id}/nodes", response_model=ProposedNodePage)
def list_proposed_nodes(
    import_id: str,
    query: Annotated[ProposedNodePageQuery, Depends()],
    _: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> ProposedNodePage:
    items, total = service.list_nodes(import_id, limit=query.limit, offset=query.offset)
    has_more = query.offset + len(items) < total
    return ProposedNodePage(
        items=[ProposedNodeRead.model_validate(item) for item in items],
        total=total,
        limit=query.limit,
        offset=query.offset,
        has_more=has_more,
    )


@router.get("/{import_id}/edges", response_model=ProposedEdgePage)
def list_proposed_edges(
    import_id: str,
    query: Annotated[ProposedEdgePageQuery, Depends()],
    _: Annotated[User, Depends(require_role("admin"))],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> ProposedEdgePage:
    items, total = service.list_edges(import_id, limit=query.limit, offset=query.offset)
    has_more = query.offset + len(items) < total
    return ProposedEdgePage(
        items=[ProposedEdgeRead.model_validate(item) for item in items],
        total=total,
        limit=query.limit,
        offset=query.offset,
        has_more=has_more,
    )


def _node_mutation(service: KnowledgeGraphImportService, job: dict, temp_id: str) -> ProposedNodeMutation:
    node = next((item for item in job["nodes"] if item.get("temp_id") == temp_id), None)
    if node is None:
        from app.shared.errors import AppError
        raise AppError(404, "PROPOSED_NODE_NOT_FOUND", "Không tìm thấy node proposal.")
    return ProposedNodeMutation(
        summary=GraphImportSummary.model_validate(service._summary_dict(job)),
        meta=GraphImportMeta.model_validate(service._meta_dict(job)),
        node=ProposedNodeRead.model_validate(node),
    )


def _edge_mutation(service: KnowledgeGraphImportService, job: dict, temp_id: str) -> ProposedEdgeMutation:
    edge = next((item for item in job["edges"] if item.get("temp_id") == temp_id), None)
    if edge is None:
        from app.shared.errors import AppError
        raise AppError(404, "PROPOSED_EDGE_NOT_FOUND", "Không tìm thấy edge proposal.")
    return ProposedEdgeMutation(
        summary=GraphImportSummary.model_validate(service._summary_dict(job)),
        meta=GraphImportMeta.model_validate(service._meta_dict(job)),
        edge=ProposedEdgeRead.model_validate(edge),
    )


@router.put("/{import_id}/nodes/{temp_id}", response_model=ProposedNodeMutation)
def update_node(
    import_id: str,
    temp_id: str,
    payload: ProposedNodeUpdate,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> ProposedNodeMutation:
    require_role("admin")(admin)
    job = service.update_node(import_id, temp_id, payload)
    return _node_mutation(service, job, temp_id)


@router.delete("/{import_id}/nodes/{temp_id}", response_model=DeleteNodeResponse)
def delete_node(
    import_id: str,
    temp_id: str,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> DeleteNodeResponse:
    require_role("admin")(admin)
    service.delete_node(import_id, temp_id)
    return DeleteNodeResponse.model_validate({"deleted_temp_id": temp_id})


@router.put("/{import_id}/edges/{temp_id}", response_model=ProposedEdgeMutation)
def update_edge(
    import_id: str,
    temp_id: str,
    payload: ProposedEdgeUpdate,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> ProposedEdgeMutation:
    require_role("admin")(admin)
    job = service.update_edge(import_id, temp_id, payload)
    return _edge_mutation(service, job, temp_id)


@router.delete("/{import_id}/edges/{temp_id}", response_model=DeleteEdgeResponse)
def delete_edge(
    import_id: str,
    temp_id: str,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> DeleteEdgeResponse:
    require_role("admin")(admin)
    service.delete_edge(import_id, temp_id)
    return DeleteEdgeResponse.model_validate({"deleted_temp_id": temp_id})


@router.post("/{import_id}/apply", response_model=GraphImportMeta)
def apply_import(
    import_id: str,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> GraphImportMeta:
    require_role("admin")(admin)
    job = service.apply(import_id)
    return GraphImportMeta.model_validate(service._meta_dict(job))


@router.post("/{import_id}/revalidate", response_model=GraphImportMeta)
def revalidate_import(
    import_id: str,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> GraphImportMeta:
    require_role("admin")(admin)
    job = service.revalidate(import_id)
    return GraphImportMeta.model_validate(service._meta_dict(job))


@router.delete("/{import_id}", response_model=DeleteImportResponse)
def delete_import(
    import_id: str,
    admin: Annotated[User, Depends(require_csrf)],
    service: Annotated[KnowledgeGraphImportService, Depends(get_knowledge_graph_import_service)],
) -> DeleteImportResponse:
    require_role("admin")(admin)
    deleted_id = service.delete_import(import_id)
    return DeleteImportResponse.model_validate({"deleted_import_id": deleted_id})
