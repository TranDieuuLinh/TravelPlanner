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


def _raise_unscheduled_mutation_error(status: str) -> None:
    if status == "chat_not_found":
        raise HTTPException(404, {"code": "TRIP_CHAT_NOT_FOUND", "message": "Không tìm thấy trip chat."})
    if status == "revision_conflict":
        raise HTTPException(409, {"code": "TRIP_CHAT_REVISION_CONFLICT", "message": "Lịch trình đã thay đổi; vui lòng tải lại trước khi lưu."})
    if status == "day_not_found":
        raise HTTPException(404, {"code": "TRIP_CHAT_PLAN_DAY_NOT_FOUND", "message": "Không tìm thấy ngày trong lịch trình."})
    if status == "unscheduled_not_found":
        raise HTTPException(404, {"code": "TRIP_CHAT_UNSCHEDULED_NOT_FOUND", "message": "Không tìm thấy địa điểm chưa xếp."})


def _selected_item(
    *,
    name: str,
    place_id: str | None,
    address: str | None,
    place_type: str | None,
    duration_minutes: int | None,
    latitude: float | None,
    longitude: float | None,
    rating: float | None,
    review_count: int | None,
    image_url: str | None,
    source_refs: list[str],
    source_provider: str | None,
    source_activity: str | None,
) -> dict:
    return {
        "placeId": place_id,
        "name": name.strip(),
        "address": address.strip() if address else None,
        "placeType": place_type,
        "durationMinutes": duration_minutes,
        "latitude": latitude,
        "longitude": longitude,
        "rating": rating,
        "reviewCount": review_count,
        "imageUrls": [image_url] if image_url else [],
        "sourceRefs": source_refs[:20],
        "sourceProvider": source_provider,
        "sourceActivity": source_activity,
    }


@router.post("/{chat_id}/plan/unscheduled-places/confirm", response_model=TripChat)
async def confirm_unscheduled_place(
    chat_id: str,
    expected_revision: int = Form(alias="expectedRevision", ge=0),
    name: str = Form(min_length=1, max_length=500),
    day: int = Form(ge=1),
    place_id: str | None = Form(default=None, alias="placeId", max_length=500),
    candidate_id: str | None = Form(default=None, alias="candidateId", max_length=500),
    selected_name: str = Form(min_length=1, alias="selectedName", max_length=500),
    selected_place_id: str | None = Form(default=None, alias="selectedPlaceId", max_length=500),
    address: str | None = Form(default=None, max_length=1000),
    place_type: str | None = Form(default=None, alias="placeType", max_length=100),
    duration_minutes: int | None = Form(default=None, alias="durationMinutes", ge=0),
    latitude: float | None = Form(default=None, ge=-90, le=90),
    longitude: float | None = Form(default=None, ge=-180, le=180),
    rating: float | None = Form(default=None, ge=0, le=5),
    review_count: int | None = Form(default=None, alias="reviewCount", ge=0),
    image_url: str | None = Form(default=None, alias="imageUrl", max_length=2000),
    source_refs: list[str] = Form(default_factory=list, alias="sourceRefs", max_length=20),
    source_provider: str | None = Form(default=None, alias="sourceProvider", max_length=120),
    source_activity: str | None = Form(default=None, alias="sourceActivity", max_length=500),
    position: int | None = Form(default=None, ge=0),
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    status, chat = await service.confirm_unscheduled_place(
        user.id,
        chat_id,
        expected_revision=expected_revision,
        name=name,
        place_id=place_id,
        candidate_id=candidate_id,
        day=day,
        item=_selected_item(
            name=selected_name,
            place_id=selected_place_id or place_id,
            address=address,
            place_type=place_type,
            duration_minutes=duration_minutes,
            latitude=latitude,
            longitude=longitude,
            rating=rating,
            review_count=review_count,
            image_url=image_url,
            source_refs=source_refs,
            source_provider=source_provider,
            source_activity=source_activity,
        ),
        position=position,
    )
    _raise_unscheduled_mutation_error(status)
    if chat is None:
        raise HTTPException(404, {"code": "TRIP_CHAT_NOT_FOUND", "message": "Không tìm thấy trip chat."})
    return chat


@router.delete("/{chat_id}/plan/unscheduled-places", response_model=TripChat)
async def delete_unscheduled_place(
    chat_id: str,
    expected_revision: int = Form(alias="expectedRevision", ge=0),
    name: str = Form(min_length=1, max_length=500),
    place_id: str | None = Form(default=None, alias="placeId", max_length=500),
    candidate_id: str | None = Form(default=None, alias="candidateId", max_length=500),
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    status, chat = await service.remove_unscheduled_place(
        user.id,
        chat_id,
        expected_revision=expected_revision,
        name=name,
        place_id=place_id,
        candidate_id=candidate_id,
    )
    _raise_unscheduled_mutation_error(status)
    if chat is None:
        raise HTTPException(404, {"code": "TRIP_CHAT_NOT_FOUND", "message": "Không tìm thấy trip chat."})
    return chat


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


@router.put("/{chat_id}/plan/days/{day}/items/reorder", response_model=TripChat)
async def reorder_items(
    chat_id: str,
    day: int,
    expected_revision: int = Form(alias="expectedRevision", ge=0),
    item_ids: list[str] = Form(alias="itemIds", min_length=1),
    user: AuthUser = Depends(require_current_user),
    service: TripChatService = Depends(_service),
):
    status, chat = await service.reorder_plan_items(
        user.id, chat_id, expected_revision=expected_revision,
        day=day, item_ids=item_ids,
    )
    if status == "chat_not_found":
        raise HTTPException(404, {"code": "TRIP_CHAT_NOT_FOUND", "message": "Không tìm thấy trip chat."})
    if status == "revision_conflict":
        raise HTTPException(409, {"code": "TRIP_CHAT_REVISION_CONFLICT", "message": "Lịch trình đã thay đổi; vui lòng tải lại trước khi lưu."})
    if status == "day_not_found":
        raise HTTPException(404, {"code": "TRIP_CHAT_PLAN_DAY_NOT_FOUND", "message": "Không tìm thấy ngày trong lịch trình."})
    return chat
