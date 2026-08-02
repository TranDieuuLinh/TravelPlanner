from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_csrf
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_schema import (
    RetryCandidateResolutionsRequest,
    TripChatCreate,
    TripChatRead,
    TripChatSummaryRead,
)
from app.modules.plans.chat_service import TripChatService
from app.modules.plans.dependencies import get_plan_mutation_service, get_plan_service
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.plan_mutation_schema import AddItemRequest, ReorderItemsRequest, UpdateItemRequest
from app.modules.places.repository import SqlAlchemyPlaceRepository
from app.modules.plans.router import (
    _extract_urls,
    _infer_destination,
    _infer_destination_from_urls,
    _normalize_urls,
    _remove_urls,
)
from app.modules.users.model import User

router = APIRouter(prefix="/trip-chats", tags=["trip-chats"])


def get_trip_chat_service(
    db: Annotated[Session, Depends(get_db)],
) -> TripChatService:
    return TripChatService(
        TripChatRepository(db),
        get_plan_service(db),
        get_plan_mutation_service(db),
        SqlAlchemyPlaceRepository(db),
    )



@router.post("", response_model=TripChatRead, status_code=status.HTTP_201_CREATED)
def create_trip_chat(
    payload: TripChatCreate,
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    return service.create(current_user, payload.title)


@router.get("", response_model=list[TripChatSummaryRead])
def list_trip_chats(
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[TripChatSummaryRead]:
    return service.list_for_user(current_user)


@router.get("/{chat_id}", response_model=TripChatRead)
def get_trip_chat(
    chat_id: str,
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TripChatRead:
    return service.get(chat_id, current_user)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip_chat(
    chat_id: str,
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> None:
    service.delete(chat_id, current_user)


@router.post("/{chat_id}/messages", response_model=TripChatRead)
async def amend_trip_chat(
    chat_id: str,
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
    content: Annotated[str, Form(min_length=1, max_length=10_000)],
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    urls: Annotated[list[str] | None, Form()] = None,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> TripChatRead:
    normalized_urls = list(
        dict.fromkeys(
            _normalize_urls(urls or []) + _extract_urls(content)
        )
    )
    initial_destination = (
        _infer_destination(_remove_urls(content))
        or _infer_destination_from_urls(normalized_urls)
        or "unspecified"
    )
    image_payloads: list[ImageUploadPayload] = []
    try:
        for image in images or []:
            image_payloads.append(
                ImageUploadPayload(
                    file_name=image.filename or "uploaded-image",
                    mime_type=image.content_type,
                    data=await image.read(),
                )
            )
        return await service.amend(
            chat_id,
            current_user,
            content=content.strip(),
            expected_revision=expected_revision,
            initial_destination=initial_destination,
            urls=normalized_urls,
            images=image_payloads,
        )
    finally:
        for image in images or []:
            await image.close()
        for payload in image_payloads:
            payload.clear_data()


@router.post(
    "/{chat_id}/candidate-resolutions/retry",
    response_model=TripChatRead,
)
async def retry_trip_chat_candidate_resolutions(
    chat_id: str,
    payload: RetryCandidateResolutionsRequest,
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    return await service.retry_candidate_resolutions(
        chat_id,
        current_user,
        expected_revision=payload.expected_revision,
    )


@router.post("/{chat_id}/plan/items", response_model=TripChatRead)
async def add_trip_chat_item(
    chat_id: str,
    payload: AddItemRequest,
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    return await service.add_item(
        chat_id,
        current_user,
        expected_revision=expected_revision,
        payload=payload,
    )


@router.patch("/{chat_id}/plan/days/{day}/items/{item_id}", response_model=TripChatRead)
async def update_trip_chat_item(
    chat_id: str,
    day: int,
    item_id: str,
    payload: UpdateItemRequest,
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    return await service.update_item(
        chat_id,
        current_user,
        expected_revision=expected_revision,
        day=day,
        item_id=item_id,
        payload=payload,
    )


@router.delete("/{chat_id}/plan/days/{day}/items/{item_id}", response_model=TripChatRead)
def remove_trip_chat_item(
    chat_id: str,
    day: int,
    item_id: str,
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    return service.remove_item(
        chat_id,
        current_user,
        expected_revision=expected_revision,
        day=day,
        item_id=item_id,
    )


@router.put("/{chat_id}/plan/days/{day}/items/reorder", response_model=TripChatRead)
def reorder_trip_chat_items(
    chat_id: str,
    day: int,
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    item_ids: Annotated[list[str], Form(alias="itemIds")],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    return service.reorder_items(
        chat_id,
        current_user,
        expected_revision=expected_revision,
        day=day,
        payload=ReorderItemsRequest(itemIds=item_ids),
    )
