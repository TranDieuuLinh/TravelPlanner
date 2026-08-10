from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_graph
from app.api.schemas import InvokeRequest, InvokeResponse
from app.modules.supervisor.public import SupervisorClassificationError


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/agent/invoke", response_model=InvokeResponse)
async def invoke_agent(payload: InvokeRequest, graph=Depends(get_graph)) -> InvokeResponse:
    request_id = str(uuid4())
    graph_input = {
        "request_id": request_id,
        "message": payload.message,
        "supplied_candidates": payload.supplied_candidates,
        "existing_itinerary": payload.existing_itinerary,
        "edit_operation": payload.edit_operation,
    }
    try:
        result = await graph.ainvoke(
            graph_input,
            config={"configurable": {"thread_id": payload.thread_id}},
        )
    except SupervisorClassificationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    information_output = result.get("information_output")
    return InvokeResponse(
        request_id=request_id,
        route=result["decision"].route,
        response=result.get("response", "Request completed."),
        itinerary=result.get("itinerary"),
        clarification_question=result.get("clarification_question"),
        warnings=result.get("warnings", []),
        sources=information_output.sources if information_output else [],
    )

