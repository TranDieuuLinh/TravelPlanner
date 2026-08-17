from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app.api.dependencies import get_graph
from app.modules.auth.public import AuthUser, require_current_user
from app.modules.trip_chat.contract import TripChat
from app.modules.trip_chat.service import TripChatService


router = APIRouter(prefix="/v1/trip-chats", tags=["trip-chat-plan"])


def _service(request: Request, graph=Depends(get_graph)) -> TripChatService:
    return TripChatService(
        repository=request.app.state.trip_chat_repository,
        graph=graph,
        memory_service=getattr(request.app.state, "conversation_memory_service", None),
    )


@router.post("/{chat_id}/plan/items", response_model=TripChat)
async def add_item(
    chat_id: str,
    expected_revision: int = Form(alias="expectedRevision", ge=0),
    day: int = Form(ge=1),
    name: str = Form(min_length=1, max_length=500),
    place_id: str | None = Form(default=None, alias="placeId", max_length=500),
    address: str | None = Form(default=None, max_length=1000),
    place_type: str | None = Form(default=None, alias="placeType", max_length=100),
    time_window: str | None = Form(default=None, alias="timeWindow", max_length=100),
    duration_minutes: int | None = Form(default=None, alias="durationMinutes", ge=0),
    latitude: float | None = Form(default=None, ge=-90, le=90),
    longitude: float | None = Form(default=None, ge=-180, le=180),
    personal_notes: str | None = Form(default=None, alias="personalNotes", max_length=4000),
    position: int | None = Form(default=None, ge=0),
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    item = {
        "placeId": place_id,
        "name": name.strip(),
        "address": address.strip() if address else None,
        "placeType": place_type,
        "timeWindow": time_window,
        "durationMinutes": duration_minutes,
        "latitude": latitude,
        "longitude": longitude,
        "personalNotes": personal_notes.strip() if personal_notes else None,
    }
    status, chat = await service.add_plan_item(
        user.id, chat_id, expected_revision=expected_revision,
        day=day, item=item, position=position,
    )
    if status == "chat_not_found":
        raise HTTPException(404, {"code": "TRIP_CHAT_NOT_FOUND", "message": "Không tìm thấy trip chat."})
    if status == "revision_conflict":
        raise HTTPException(409, {"code": "TRIP_CHAT_REVISION_CONFLICT", "message": "Lịch trình đã thay đổi; vui lòng tải lại trước khi lưu."})
    if status == "day_not_found":
        raise HTTPException(404, {"code": "TRIP_CHAT_PLAN_DAY_NOT_FOUND", "message": "Không tìm thấy ngày trong lịch trình."})
    return chat
