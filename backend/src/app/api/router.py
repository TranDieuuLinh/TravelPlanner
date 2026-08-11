from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.api.dependencies import get_explorer_graph, get_graph
from app.api.schemas import InvokeRequest, InvokeResponse
from app.modules.auth.public import router as auth_router
from app.modules.knowledge_graph.public import router as knowledge_graph_router
from app.modules.observability.public import router as observability_router
from app.modules.observability.service import ObservabilityService
from app.modules.explorer.public import ExplorerInput, ExplorerOutput
from app.modules.supervisor.public import SupervisorClassificationError
from app.modules.trip_chat.public import router as trip_chat_router


router = APIRouter()
router.include_router(auth_router)
router.include_router(knowledge_graph_router)
router.include_router(observability_router)
router.include_router(trip_chat_router)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/explorer/invoke", response_model=ExplorerOutput)
async def invoke_explorer(
    payload: Annotated[
        ExplorerInput,
        Body(openapi_examples={
            "prompt": {
                "summary": "Prompt only",
                "value": {
                    "rawPrompt": "Lập kế hoạch ở Huế trong 3 ngày",
                    "urls": [],
                    "images": [],
                },
            },
            "tiktok": {
                "summary": "TikTok URL only",
                "value": {
                    "rawPrompt": None,
                    "urls": ["https://www.tiktok.com/@creator/video/123"],
                    "images": [],
                },
            },
            "ocr": {
                "summary": "Supplied image OCR",
                "value": {
                    "rawPrompt": None,
                    "urls": [],
                    "images": [{
                        "fileName": "capture.png",
                        "mimeType": "image/png",
                        "ocrText": "Du lịch ở Đà Nẵng, tham quan Cầu Rồng",
                    }],
                },
            },
        }),
    ],
    graph=Depends(get_explorer_graph),
) -> ExplorerOutput:
    result = await graph.ainvoke({"payload": payload})
    return result["output"]


@router.post("/v1/agent/invoke", response_model=InvokeResponse)
async def invoke_agent(
    payload: InvokeRequest,
    request: Request,
    graph=Depends(get_graph),
) -> InvokeResponse:
    request_id = str(uuid4())
    graph_input = {
        "request_id": request_id,
        "message": payload.message or "",
        "urls": payload.urls,
        "images": payload.images,
        "existing_itinerary": payload.existing_itinerary,
        "edit_operation": payload.edit_operation,
    }
    observability: ObservabilityService = request.app.state.observability_service
    try:
        result = await graph.ainvoke(
            graph_input,
            config={"configurable": {"thread_id": payload.thread_id}},
        )
    except SupervisorClassificationError as exc:
        await observability.record_agent_invoke(
            request_id=request_id,
            route=None,
            success=False,
            message_length=len(payload.message),
            warning_count=0,
            source_count=0,
            has_itinerary=payload.existing_itinerary is not None,
            error_code="SUPERVISOR_UNAVAILABLE",
        )
        raise HTTPException(status_code=503, detail=str(exc)) from None
    information_output = result.get("information_output")
    response = InvokeResponse(
        request_id=request_id,
        route=result["decision"].route,
        response=result.get("response", "Request completed."),
        itinerary=result.get("itinerary"),
        clarification_question=result.get("clarification_question"),
        warnings=result.get("warnings", []),
        sources=information_output.sources if information_output else [],
    )
    await observability.record_agent_invoke(
        request_id=request_id,
        route=response.route,
        success=True,
        message_length=len(payload.message),
        warning_count=len(response.warnings),
        source_count=len(response.sources),
        has_itinerary=response.itinerary is not None,
    )
    return response

