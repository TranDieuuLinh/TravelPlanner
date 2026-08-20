from typing import Annotated
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.api.dependencies import get_explorer_graph, get_graph
from app.api.schemas import InvokeRequest, InvokeResponse
from app.modules.auth.public import router as auth_router
from app.modules.knowledge_graph.public import (
    public_router as knowledge_graph_public_router,
    router as knowledge_graph_router,
)
from app.modules.observability.public import router as observability_router
from app.modules.observability.service import ObservabilityService
from app.modules.itinerary_planner.public import router as itinerary_planner_router
from app.modules.place_checker.public import manual_search_router
from app.modules.explorer.public import (
    ExplorerApiOutput,
    ExplorerInput,
    to_explorer_api_output,
)
from app.modules.supervisor.public import SupervisorClassificationError
from app.modules.trip_chat.public import plan_mutations_router, router as trip_chat_router


router = APIRouter()
router.include_router(auth_router)
router.include_router(knowledge_graph_router)
router.include_router(knowledge_graph_public_router)
router.include_router(observability_router)
router.include_router(trip_chat_router)
router.include_router(plan_mutations_router)
router.include_router(itinerary_planner_router)
router.include_router(manual_search_router)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/explorer/invoke", response_model=ExplorerApiOutput)
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
    request: Request,
    graph=Depends(get_explorer_graph),
) -> ExplorerApiOutput:
    request_id = (
        request.headers.get("x-trace-id")
        or request.headers.get("x-request-id")
        or str(uuid4())
    )
    request.state.trace_id = request_id
    started_at = perf_counter()
    observability: ObservabilityService = request.app.state.observability_service
    trace_callback = observability.start_trace(
        request_id=request_id,
        metadata={
            "requestId": request_id,
            "threadId": request_id,
            "entryPoint": "explorer.invoke",
            "messageLength": len(payload.raw_prompt or ""),
            "input": {
                "promptChars": len(payload.raw_prompt or ""),
                "urlCount": len(payload.urls),
                "imageCount": len(payload.images),
                "forceRefresh": payload.force_refresh,
            },
        },
    )
    try:
        result = await graph.ainvoke(
            {"payload": payload},
            config={"callbacks": [trace_callback]},
        )
        output = result["output"]
        source_count = len(payload.urls) + len(payload.images)
        await observability.record_agent_invoke(
            request_id=request_id,
            route="explorer",
            success=True,
            message_length=len(payload.raw_prompt or ""),
            warning_count=len(output.warnings),
            source_count=source_count,
            has_itinerary=False,
            output={
                "status": output.status,
                "placeCount": len(output.places or []),
                "warningCount": len(output.warnings),
                "sourceCount": source_count,
            },
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return to_explorer_api_output(output)
    except Exception as exc:
        await observability.record_agent_invoke(
            request_id=request_id,
            route="explorer",
            success=False,
            message_length=len(payload.raw_prompt or ""),
            warning_count=0,
            source_count=0,
            has_itinerary=False,
            error_code=type(exc).__name__,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise
    finally:
        await trace_callback.flush()


@router.post("/v1/agent/invoke", response_model=InvokeResponse)
async def invoke_agent(
    payload: InvokeRequest,
    request: Request,
    graph=Depends(get_graph),
) -> InvokeResponse:
    request_id = (
        request.headers.get("x-trace-id")
        or request.headers.get("x-request-id")
        or str(uuid4())
    )
    request.state.trace_id = request_id
    started_at = perf_counter()
    graph_input = {
        "request_id": request_id,
        "message": payload.message or "",
        "urls": payload.urls,
        "images": payload.images,
        "force_refresh": payload.force_refresh,
        "existing_itinerary": payload.existing_itinerary,
        "edit_operation": payload.edit_operation,
    }
    observability: ObservabilityService = request.app.state.observability_service
    trace_callback = observability.start_trace(
        request_id=request_id,
        metadata={
            "requestId": request_id,
            "threadId": payload.thread_id,
            "entryPoint": "agent.invoke",
            "messageLength": len(payload.message or ""),
            "input": {
                "messageChars": len(payload.message or ""),
                "urlCount": len(payload.urls),
                "imageCount": len(payload.images),
                "forceRefresh": payload.force_refresh,
                "hasExistingItinerary": payload.existing_itinerary is not None,
                "hasEditOperation": payload.edit_operation is not None,
            },
        },
    )
    graph_config = {"configurable": {"thread_id": payload.thread_id}}
    if trace_callback is not None:
        graph_config["callbacks"] = [trace_callback]
    try:
        result = await graph.ainvoke(
            graph_input,
            config=graph_config,
        )
    except SupervisorClassificationError as exc:
        await observability.record_agent_invoke(
            request_id=request_id, route=None, success=False,
            message_length=len(payload.message or ""), warning_count=0,
            source_count=0, has_itinerary=payload.existing_itinerary is not None,
            error_code="SUPERVISOR_UNAVAILABLE",
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception as exc:
        await observability.record_agent_invoke(
            request_id=request_id, route=None, success=False,
            message_length=len(payload.message or ""), warning_count=0,
            source_count=0, has_itinerary=payload.existing_itinerary is not None,
            error_code=type(exc).__name__,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise
    finally:
        if trace_callback is not None:
            await trace_callback.flush()
    if planner_error_code := result.get("planner_error_code"):
        retryable = planner_error_code in {
            "solver_unknown",
            "route_repair_unknown",
            "matrix_timeout",
            "matrix_provider_error",
        }
        status_code = 503 if retryable else 422
        message = result.get("response", "Itinerary planning failed.")
        await observability.record_agent_invoke(
            request_id=request_id,
            route=result["decision"].route,
            success=False,
            message_length=len(payload.message or ""),
            warning_count=len(result.get("warnings", [])),
            source_count=0,
            has_itinerary=False,
            error_code=planner_error_code.upper(),
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": planner_error_code.upper(),
                "message": message,
                "retryable": retryable,
            },
        )
    information_output = result.get("information_output")
    response = InvokeResponse(
        request_id=request_id,
        route=result["decision"].route,
        response=result.get("response", "Request completed."),
        itinerary=result.get("itinerary"),
        planner_output=result.get("planner_output"),
        clarification_question=result.get("clarification_question"),
        warnings=result.get("warnings", []),
        content_blocks=(
            information_output.content_blocks if information_output else []
        ),
        sources=information_output.sources if information_output else [],
        suggestions=(
            information_output.suggestions
            if information_output and information_output.suggestions
            else result.get("suggestions", [])
        ),
    )
    await observability.record_agent_invoke(
        request_id=request_id, route=response.route, success=True,
        message_length=len(payload.message or ""),
        warning_count=len(response.warnings), source_count=len(response.sources),
        has_itinerary=(
            response.itinerary is not None or response.planner_output is not None
        ),
        output={
            "response": response.response,
            "route": response.route,
            "itinerary": response.itinerary,
            "plannerOutput": response.planner_output,
            "warnings": response.warnings,
            "sources": response.sources,
        },
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return response
