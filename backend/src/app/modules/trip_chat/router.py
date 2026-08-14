from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.dependencies import get_graph
from app.modules.auth.public import AuthUser, require_current_user
from app.modules.trip_chat.contract import (
    CreateTripChatInput,
    SendTripChatMessageInput,
    TripChat,
    TripChatMessageResponse,
    TripChatSummary,
)
from app.modules.trip_chat.service import TripChatService
from app.modules.conversation_memory.public import UserPreferenceMemory


router = APIRouter(prefix="/v1/trip-chats", tags=["trip-chat"])


def _service(request: Request, graph = Depends(get_graph)) -> TripChatService:
    memory_service = getattr(request.app.state, "conversation_memory_service", None)
    return TripChatService(
        repository=request.app.state.trip_chat_repository,
        graph=graph,
        memory_service=memory_service,
    )


def _not_found() -> None:
    raise HTTPException(
        status_code=404,
        detail={"code": "TRIP_CHAT_NOT_FOUND", "message": "Không tìm thấy trip chat."},
    )


@router.get("", response_model=list[TripChatSummary])
async def list_chats(
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    return await service.list(user.id)


@router.post("", response_model=TripChat, status_code=201)
async def create_chat(
    payload: CreateTripChatInput,
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    return await service.create(user.id, payload.title)


@router.get("/memory/preferences", response_model=UserPreferenceMemory)
async def get_user_preferences(
    request: Request,
    user: AuthUser = Depends(require_current_user),
):
    memory_service = getattr(request.app.state, "conversation_memory_service", None)
    if memory_service is None:
        raise HTTPException(status_code=503, detail="Conversation memory is unavailable.")
    return await memory_service.load_user_preferences(user.id)


@router.delete("/memory/preferences", status_code=204)
async def delete_user_preferences(
    request: Request,
    user: AuthUser = Depends(require_current_user),
):
    memory_service = getattr(request.app.state, "conversation_memory_service", None)
    if memory_service is None:
        raise HTTPException(status_code=503, detail="Conversation memory is unavailable.")
    await memory_service.delete_user_preferences(user.id)
    return Response(status_code=204)


@router.get("/{chat_id}", response_model=TripChat)
async def get_chat(
    chat_id: str,
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    chat = await service.get(user.id, chat_id)
    if not chat:
        _not_found()
    return chat


@router.post("/{chat_id}/messages", response_model=TripChatMessageResponse)
async def send_message(
    chat_id: str,
    payload: SendTripChatMessageInput,
    request: Request,
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    started_at = perf_counter()
    request_id = str(uuid4())
    observability = request.app.state.observability_service
    trace_callback = observability.start_trace(
        request_id=request_id,
        metadata={
            "requestId": request_id,
            "threadId": chat_id,
            "messageLength": len(payload.content),
            "input": {"message": payload.content, "chatId": chat_id},
        },
    )
    try:
        chat = await service.send(
            user.id,
            chat_id,
            payload.content,
            graph_config={"callbacks": [trace_callback]},
        )
        if not chat:
            _not_found()
        assistant_message = chat.messages[-1]
        await observability.record_agent_invoke(
            request_id=request_id,
            route=assistant_message.route,
            success=True,
            message_length=len(payload.content),
            warning_count=len(assistant_message.warnings),
            source_count=len(assistant_message.sources),
            has_itinerary=(
                chat.current_itinerary is not None
                or chat.current_planner_output is not None
            ),
            output={
                "content": assistant_message.content,
                "route": assistant_message.route,
                "clarificationQuestion": assistant_message.clarification_question,
                "warnings": assistant_message.warnings,
                "sources": assistant_message.sources,
                "itinerary": chat.current_itinerary,
                "plannerOutput": chat.current_planner_output,
            },
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return TripChatMessageResponse(chat=chat, assistant_message=assistant_message)
    except HTTPException:
        await observability.record_agent_invoke(
            request_id=request_id, route=None, success=False,
            message_length=len(payload.content), warning_count=0,
            source_count=0, has_itinerary=False, error_code="TRIP_CHAT_NOT_FOUND",
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise
    except Exception as exc:
        await observability.record_agent_invoke(
            request_id=request_id, route=None, success=False,
            message_length=len(payload.content), warning_count=0,
            source_count=0, has_itinerary=False, error_code=type(exc).__name__,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise
    finally:
        await trace_callback.flush()


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    if not await service.repository.delete_chat(user.id, chat_id):
        _not_found()
    return Response(status_code=204)


@router.delete("", status_code=204)
async def delete_all_chats(
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    await service.repository.delete_all_chats(user.id)
    return Response(status_code=204)
