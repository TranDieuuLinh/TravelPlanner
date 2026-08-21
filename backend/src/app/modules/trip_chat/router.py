from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.dependencies import get_graph
from app.modules.auth.public import AuthUser, require_current_user
from app.modules.trip_chat.contract import (
    CreateTripChatInput,
    SendTripChatMessageInput,
    SelectTransportOptionInput,
    TripChat,
    TripChatBootstrap,
    TripChatMessageResponse,
    TripChatSummary,
    UpdatePersonalNotesInput,
    UpdateAccommodationInput,
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
        plan_editor=getattr(request.app.state, "natural_language_plan_editor", None),
    )


def _not_found() -> None:
    raise HTTPException(
        status_code=404,
        detail={"code": "TRIP_CHAT_NOT_FOUND", "message": "Không tìm thấy trip chat."},
    )


def _raise_plan_mutation_error(status: str) -> None:
    if status == "chat_not_found":
        _not_found()
    if status == "revision_conflict":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRIP_CHAT_REVISION_CONFLICT",
                "message": "Lịch trình đã thay đổi; vui lòng tải lại trước khi lưu.",
            },
        )
    if status == "accommodation_not_found":
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TRIP_CHAT_ACCOMMODATION_NOT_FOUND",
                "message": "Không tìm thấy nơi lưu trú trong lịch trình.",
            },
        )
    if status in {"day_not_found", "leg_not_found"}:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TRIP_CHAT_TRANSPORT_LEG_NOT_FOUND",
                "message": "Không tìm thấy chặng di chuyển trong lịch trình.",
            },
        )


@router.get("", response_model=list[TripChatSummary])
async def list_chats(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    return await service.list(user.id, limit=limit, offset=offset)


@router.get("/bootstrap", response_model=TripChatBootstrap)
async def bootstrap_chats(
    chat_id: str | None = Query(default=None, max_length=120, alias="chatId"),
    limit: int = Query(default=30, ge=1, le=100),
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    return await service.bootstrap(user.id, chat_id=chat_id, limit=limit)


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
    request_id = (
        request.headers.get("x-trace-id")
        or request.headers.get("x-request-id")
        or str(uuid4())
    )
    request.state.trace_id = request_id
    observability = request.app.state.observability_service
    trace_callback = observability.start_trace(
        request_id=request_id,
        metadata={
            "requestId": request_id,
            "userId": str(user.id),
            "threadId": chat_id,
            "entryPoint": "trip_chat.message",
            "messageLength": len(payload.content),
            "input": {"messageChars": len(payload.content), "chatId": chat_id},
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


@router.patch(
    "/{chat_id}/plan/days/{day}/items/{item_id}/personal-notes",
    response_model=TripChat,
)
async def update_personal_notes(
    chat_id: str,
    day: int,
    item_id: str,
    payload: UpdatePersonalNotesInput,
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    status, chat = await service.update_personal_notes(
        user.id,
        chat_id,
        expected_revision=payload.expected_revision,
        day=day,
        item_id=item_id,
        personal_notes=payload.personal_notes,
    )
    if status == "chat_not_found":
        _not_found()
    if status == "revision_conflict":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRIP_CHAT_REVISION_CONFLICT",
                "message": "Lịch trình đã thay đổi; vui lòng tải lại trước khi lưu.",
            },
        )
    if status == "item_not_found":
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TRIP_CHAT_PLAN_ITEM_NOT_FOUND",
                "message": "Không tìm thấy địa điểm trong lịch trình.",
            },
        )
    if chat is None:
        _not_found()
    return chat


@router.patch("/{chat_id}/plan/accommodation", response_model=TripChat)
async def update_plan_accommodation(
    chat_id: str,
    payload: UpdateAccommodationInput,
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    changes = payload.model_dump(
        by_alias=True,
        exclude={"expected_revision"},
        exclude_unset=True,
    )
    status, chat = await service.update_accommodation(
        user.id,
        chat_id,
        expected_revision=payload.expected_revision,
        changes=changes,
    )
    _raise_plan_mutation_error(status)
    if chat is None:
        _not_found()
    return chat


@router.delete("/{chat_id}/plan/accommodation", response_model=TripChat)
async def delete_plan_accommodation(
    chat_id: str,
    expected_revision: int = Query(alias="expectedRevision", ge=0),
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    status, chat = await service.update_accommodation(
        user.id,
        chat_id,
        expected_revision=expected_revision,
        changes=None,
        delete=True,
    )
    _raise_plan_mutation_error(status)
    if chat is None:
        _not_found()
    return chat


@router.put(
    "/{chat_id}/plan/days/{day}/transport-legs/{leg_index}/selection",
    response_model=TripChat,
)
async def select_plan_transport_option(
    chat_id: str,
    day: int,
    leg_index: int,
    payload: SelectTransportOptionInput,
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    selection = payload.model_dump(
        mode="json",
        by_alias=True,
        exclude={"expected_revision"},
        exclude_none=True,
    )
    status, chat = await service.select_transport_option(
        user.id,
        chat_id,
        expected_revision=payload.expected_revision,
        day=day,
        leg_index=leg_index,
        selection=selection,
    )
    _raise_plan_mutation_error(status)
    if chat is None:
        _not_found()
    return chat


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
