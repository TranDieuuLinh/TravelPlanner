from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.dependencies import get_graph
from app.modules.auth.public import AuthUser, require_current_user
from app.modules.trip_chat.adapters.postgres import PostgresTripChatRepository
from app.modules.trip_chat.contract import (
    CreateTripChatInput,
    SendTripChatMessageInput,
    TripChat,
    TripChatMessageResponse,
    TripChatSummary,
)
from app.modules.trip_chat.service import TripChatService


router = APIRouter(prefix="/v1/trip-chats", tags=["trip-chat"])


def _service(request: Request) -> TripChatService:
    return TripChatService(request.app.state.trip_chat_repository, get_graph())


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
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    chat = await service.send(user.id, chat_id, payload.content)
    if not chat:
        _not_found()
    return TripChatMessageResponse(chat=chat, assistant_message=chat.messages[-1])


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
