from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.dependencies import get_explorer_graph, get_graph
from app.api.schemas import InvokeRequest, InvokeResponse
from app.modules.explorer.public import ExplorerInput, ExplorerOutput
from app.modules.supervisor.public import SupervisorClassificationError


router = APIRouter()


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
async def invoke_agent(payload: InvokeRequest, graph=Depends(get_graph)) -> InvokeResponse:
    request_id = str(uuid4())
    graph_input = {
        "request_id": request_id,
        "message": payload.message or "",
        "urls": payload.urls,
        "images": payload.images,
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
