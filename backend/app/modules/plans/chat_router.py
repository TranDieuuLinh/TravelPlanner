from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_csrf
from app.modules.knowledge_graph.place_repository import KnowledgeGraphPlaceRepository
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_schema import (
    RetryCandidateResolutionsRequest,
    TripChatCreate,
    TripChatRead,
    TripChatSummaryRead,
    TripChatTurnCreate,
    TripChatTurnRead,
)
from app.modules.plans.chat_service import TripChatService
from app.modules.plans.conversation_service import ConversationTurnService
from app.modules.plans.dependencies import (
    get_conversation_turn_service,
    get_plan_mutation_service,
    get_plan_service,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.plan_mutation_schema import (
    AddItemForm,
    AddItemRequest,
    ReorderItemsRequest,
    SelectTransportOptionRequest,
    UpdateItemForm,
    UpdateItemRequest,
)
from app.modules.plans.router import (
    _extract_urls,
    _normalize_urls,
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
        KnowledgeGraphPlaceRepository(db),
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


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_trip_chats(
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> None:
    service.delete_all_for_user(current_user)


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


@router.post(
    "/{chat_id}/messages",
    response_model=TripChatTurnRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def amend_trip_chat(
    chat_id: str,
    request: Request,
    turn_service: Annotated[ConversationTurnService, Depends(get_conversation_turn_service)],
    legacy_service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
    content: Annotated[str, Form(min_length=1, max_length=10_000)],
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    client_turn_id: Annotated[
        str | None, Form(alias="clientTurnId", max_length=72)
    ] = None,
    attachment_names: Annotated[
        list[str] | None, Form(alias="attachmentNames")
    ] = None,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> TripChatTurnRead:
    """Submit a conversational message.

    By default the request flows through the Conversation Supervisor so the
    client can render the full ``awaiting_confirmation`` lifecycle. Set the
    env ``CONVERSATION_SUPERVISOR_ENABLED=false`` (or send header
    ``X-Bypass-Supervisor: 1``) to fall back to the legacy explorer pipeline
    in case the supervisor needs to be rolled out without code changes.
    """
    use_legacy = (
        not settings.conversation_supervisor_enabled
        or request.headers.get("X-Bypass-Supervisor", "").lower() in {"1", "true", "yes"}
    )
    image_payloads: list[ImageUploadPayload] = []
    image_names: list[str] = []
    try:
        for image in images or []:
            image_payloads.append(
                ImageUploadPayload(
                    file_name=image.filename or "uploaded-image",
                    mime_type=image.content_type,
                    data=await image.read(),
                )
            )
            if image.filename:
                image_names.append(image.filename)
        if attachment_names:
            image_names.extend(attachment_names)

        if use_legacy:
            chat = await legacy_service.amend(
                chat_id,
                current_user,
                content=content.strip(),
                expected_revision=expected_revision,
                initial_destination="unspecified",
                urls=list(_normalize_urls(_extract_urls(content))),
                images=image_payloads,
            )
            return TripChatTurnRead(
                id=f"legacy-{chat.id}-{chat.revision}",
                chatId=chat.id,
                clientTurnId=client_turn_id or f"legacy-{chat.revision}",
                status="completed",
                content=content.strip(),
                attachmentNames=image_names,
                baseRevision=expected_revision,
                assistantBlocks=[
                    {
                        "type": "planDiff",
                        "beforeRevision": expected_revision,
                        "afterRevision": chat.revision,
                        "affectedDays": (
                            list(range(1, len(chat.current_plan.days) + 1))
                            if chat.current_plan
                            else []
                        ),
                        "undoAvailable": chat.revision > 1,
                    }
                ],
                resultSummary={"planRevision": chat.revision},
                createdAt=chat.updated_at,
                updatedAt=chat.updated_at,
                planRevision=chat.revision,
            )

        turn = turn_service.start(
            chat_id,
            current_user,
            content=content.strip(),
            expected_revision=expected_revision,
            client_turn_id=client_turn_id,
            attachment_names=image_names,
        )
        executed = await turn_service.execute(
            chat_id,
            current_user,
            turn.id,
            images=image_payloads or None,
        )
        return TripChatTurnRead.model_validate(executed)
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
    payload: Annotated[AddItemForm, Form()],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    item_payload = AddItemRequest.model_validate(
        payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
    )
    return await service.add_item(
        chat_id,
        current_user,
        expected_revision=payload.expected_revision,
        payload=item_payload,
    )


@router.patch("/{chat_id}/plan/days/{day}/items/{item_id}", response_model=TripChatRead)
async def update_trip_chat_item(
    chat_id: str,
    day: int,
    item_id: str,
    payload: Annotated[UpdateItemForm, Form()],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatRead:
    item_payload = UpdateItemRequest.model_validate(
        payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
    )
    return await service.update_item(
        chat_id,
        current_user,
        expected_revision=payload.expected_revision,
        day=day,
        item_id=item_id,
        payload=item_payload,
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


@router.delete("/{chat_id}/plan/unscheduled-places", response_model=TripChatRead)
def remove_trip_chat_unscheduled_place(
    chat_id: str,
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    name: Annotated[str, Form(min_length=1, max_length=255)],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
    place_id: Annotated[str | None, Form(alias="placeId")] = None,
) -> TripChatRead:
    return service.remove_unscheduled_place(
        chat_id,
        current_user,
        expected_revision=expected_revision,
        name=name,
        place_id=place_id,
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


@router.put(
    "/{chat_id}/plan/days/{day}/transport-legs/{leg_index}/selection",
    response_model=TripChatRead,
)
def select_trip_chat_transport_option(
    chat_id: str,
    day: int,
    leg_index: int,
    expected_revision: Annotated[int, Form(alias="expectedRevision", ge=0)],
    mode: Annotated[str, Form(min_length=1, max_length=40)],
    service: Annotated[TripChatService, Depends(get_trip_chat_service)],
    current_user: Annotated[User, Depends(require_csrf)],
    option_key: Annotated[
        str | None,
        Form(alias="optionKey", min_length=1, max_length=4000),
    ] = None,
    source: Annotated[str | None, Form(min_length=1, max_length=80)] = None,
    distance_meters: Annotated[
        int | None,
        Form(alias="distanceMeters", ge=0),
    ] = None,
    estimated_duration_minutes: Annotated[
        int | None,
        Form(alias="estimatedDurationMinutes", ge=0),
    ] = None,
) -> TripChatRead:
    return service.select_transport_option(
        chat_id,
        current_user,
        expected_revision=expected_revision,
        day=day,
        leg_index=leg_index,
        payload=SelectTransportOptionRequest(
            mode=mode,
            optionKey=option_key,
            source=source,
            distanceMeters=distance_meters,
            estimatedDurationMinutes=estimated_duration_minutes,
        ),
    )


# ---------------------------------------------------------------------------
# Conversation turn supervisor (conversational planner)
# ---------------------------------------------------------------------------


@router.post(
    "/{chat_id}/turns",
    response_model=TripChatTurnRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trip_chat_turn(
    chat_id: str,
    payload: TripChatTurnCreate,
    service: Annotated[ConversationTurnService, Depends(get_conversation_turn_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatTurnRead:
    """Create a queued turn without executing it. Useful when the frontend
    wants to render a pending placeholder before the supervisor runs."""
    turn = service.start(
        chat_id,
        current_user,
        content=payload.content,
        expected_revision=payload.expected_revision,
        client_turn_id=payload.client_turn_id,
        attachment_names=payload.attachment_names,
    )
    return TripChatTurnRead.model_validate(turn)


@router.get(
    "/{chat_id}/turns/{turn_id}",
    response_model=TripChatTurnRead,
)
def get_trip_chat_turn(
    chat_id: str,
    turn_id: str,
    service: Annotated[ConversationTurnService, Depends(get_conversation_turn_service)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TripChatTurnRead:
    turn = service.get_turn(chat_id, current_user, turn_id)
    return TripChatTurnRead.model_validate(turn)


@router.post(
    "/{chat_id}/turns/{turn_id}/execute",
    response_model=TripChatTurnRead,
)
async def execute_trip_chat_turn(
    chat_id: str,
    turn_id: str,
    service: Annotated[ConversationTurnService, Depends(get_conversation_turn_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatTurnRead:
    """Run the supervisor on this turn. Polled by the frontend until status
    reaches a terminal state (completed, awaiting_confirmation, failed,
    cancelled)."""
    turn = await service.execute(chat_id, current_user, turn_id)
    return TripChatTurnRead.model_validate(turn)


@router.post(
    "/{chat_id}/turns/{turn_id}/confirm",
    response_model=TripChatTurnRead,
)
async def confirm_trip_chat_turn(
    chat_id: str,
    turn_id: str,
    service: Annotated[ConversationTurnService, Depends(get_conversation_turn_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatTurnRead:
    turn = await service.confirm(chat_id, current_user, turn_id)
    return TripChatTurnRead.model_validate(turn)


@router.post(
    "/{chat_id}/turns/{turn_id}/cancel",
    response_model=TripChatTurnRead,
)
def cancel_trip_chat_turn(
    chat_id: str,
    turn_id: str,
    service: Annotated[ConversationTurnService, Depends(get_conversation_turn_service)],
    current_user: Annotated[User, Depends(require_csrf)],
) -> TripChatTurnRead:
    turn = service.cancel(chat_id, current_user, turn_id)
    return TripChatTurnRead.model_validate(turn)
