from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.modules.plans.chat_model import (
    ACTIVE_TURN_STATUSES,
    PROCESSING_TURN_STATUSES,
    TripChat,
    TripChatMessage,
    TripChatPlanRevision,
    TripChatTurn,
)
from app.shared.errors import AppError


class TripChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user_id: int, title: str) -> TripChat:
        chat = TripChat(id=str(uuid4()), user_id=user_id, title=title)
        self.db.add(chat)
        self.db.commit()
        return self.get(chat.id, user_id)

    def list_for_user(self, user_id: int) -> list[TripChat]:
        statement = (
            select(TripChat)
            .where(TripChat.user_id == user_id)
            .order_by(TripChat.updated_at.desc(), TripChat.id.desc())
        )
        return list(self.db.scalars(statement))

    def get(self, chat_id: str, user_id: int) -> TripChat:
        statement = (
            select(TripChat)
            .options(
                selectinload(TripChat.messages),
                selectinload(TripChat.plan_revisions),
                selectinload(TripChat.turns),
            )
            .where(TripChat.id == chat_id, TripChat.user_id == user_id)
        )
        chat = self.db.scalar(statement)
        if chat is None:
            raise AppError(404, "TRIP_CHAT_NOT_FOUND", "Không tìm thấy cuộc trò chuyện chuyến đi.")
        return chat

    def delete(self, chat_id: str, user_id: int) -> None:
        chat = self.get(chat_id, user_id)
        self.db.delete(chat)
        self.db.commit()

    def save_revision(
        self,
        chat: TripChat,
        *,
        user_content: str,
        attachment_names: list[str],
        assistant_content: str,
        plan_payload: dict,
        explorer_payload: dict,
        explorer_timing_payload: dict | None,
        planner_timing_payload: dict | None,
        intake_id: str,
        destination: str,
        title: str,
        revision: int,
    ) -> TripChat:
        now = datetime.now(UTC)
        next_sequence = max(
            (msg.sequence for msg in chat.messages),
            default=0,
        ) + 1
        result = self.db.execute(
            update(TripChat)
            .where(
                TripChat.id == chat.id,
                TripChat.user_id == chat.user_id,
                TripChat.revision == revision - 1,
            )
            .values(
                title=title,
                destination=destination,
                current_plan=plan_payload,
                current_explorer=explorer_payload,
                latest_explorer_timing=explorer_timing_payload,
                latest_planner_timing=planner_timing_payload,
                current_intake_id=intake_id,
                revision=revision,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi gửi.",
            )
        self.db.add_all(
            [
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="user",
                    content=user_content,
                    sequence=next_sequence,
                    attachment_names=attachment_names,
                    plan_revision=revision,
                    created_at=now,
                ),
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="assistant",
                    content=assistant_content,
                    sequence=next_sequence + 1,
                    attachment_names=[],
                    plan_revision=revision,
                    created_at=now,
                ),
                TripChatPlanRevision(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    revision=revision,
                    intake_id=intake_id,
                    plan_payload=plan_payload,
                    explorer_payload=explorer_payload,
                    created_at=now,
                ),
            ]
        )
        self.db.commit()
        return self.get(chat.id, chat.user_id)

    def save_plan_mutation(
        self,
        chat: TripChat,
        *,
        action_summary: str,
        plan_payload: dict,
        revision: int,
        explorer_payload: dict | None = None,
        planner_timing_payload: dict | None = None,
    ) -> TripChat:
        now = datetime.now(UTC)
        next_sequence = max(
            (msg.sequence for msg in chat.messages),
            default=0,
        ) + 1
        updated_values = {
            "current_plan": plan_payload,
            "revision": revision,
            "updated_at": now,
        }
        if explorer_payload is not None:
            updated_values["current_explorer"] = explorer_payload
        if planner_timing_payload is not None:
            updated_values["latest_planner_timing"] = planner_timing_payload
        result = self.db.execute(
            update(TripChat)
            .where(
                TripChat.id == chat.id,
                TripChat.user_id == chat.user_id,
                TripChat.revision == revision - 1,
            )
            .values(**updated_values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi chỉnh sửa.",
            )
        self.db.add_all(
            [
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="assistant",
                    content=action_summary,
                    sequence=next_sequence,
                    attachment_names=[],
                    plan_revision=revision,
                    created_at=now,
                ),
                TripChatPlanRevision(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    revision=revision,
                    intake_id=chat.current_intake_id,
                    plan_payload=plan_payload,
                    explorer_payload=(
                        explorer_payload
                        if explorer_payload is not None
                        else chat.current_explorer or {}
                    ),
                    created_at=now,
                ),
            ]
        )
        self.db.commit()
        return self.get(chat.id, chat.user_id)

    # ----------------------------------------------------------------------
    # Conversation turn lifecycle (supervisor)
    # ----------------------------------------------------------------------

    def create_turn(
        self,
        chat: TripChat,
        *,
        client_turn_id: str,
        content: str,
        attachment_names: list[str],
        expected_revision: int,
    ) -> TripChatTurn:
        """Create a queued turn. The HTTP handler decides if execution starts
        immediately or returns the turn for client-driven polling."""
        if not content.strip():
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Nội dung không được để trống.",
            )
        # De-duplicate the same client_turn_id (idempotency for retries).
        existing = self.db.scalar(
            select(TripChatTurn).where(
                TripChatTurn.chat_id == chat.id,
                TripChatTurn.client_turn_id == client_turn_id,
            )
        )
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        turn = TripChatTurn(
            id=str(uuid4()),
            chat_id=chat.id,
            user_id=chat.user_id,
            client_turn_id=client_turn_id,
            content=content.strip(),
            attachment_names=list(attachment_names or []),
            base_revision=expected_revision,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self.db.add(turn)
        self.db.commit()
        self.db.refresh(turn)
        return turn

    def get_turn(
        self, chat_id: str, user_id: int, turn_id: str
    ) -> TripChatTurn:
        turn = self.db.scalar(
            select(TripChatTurn).where(
                TripChatTurn.id == turn_id,
                TripChatTurn.chat_id == chat_id,
                TripChatTurn.user_id == user_id,
            )
        )
        if turn is None:
            raise AppError(
                404,
                "TURN_NOT_FOUND",
                "Không tìm thấy lượt hội thoại.",
            )
        return turn

    def expire_stale_turns(
        self, chat_id: str, stale_after_seconds: float
    ) -> list[str]:
        """Mark stuck ``processing`` turns as failed so the supervisor can
        reclaim them. Returns the list of turn IDs that were reaped."""
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
        stuck = list(
            self.db.scalars(
                select(TripChatTurn).where(
                    TripChatTurn.chat_id == chat_id,
                    TripChatTurn.status.in_(PROCESSING_TURN_STATUSES),
                    TripChatTurn.processing_started_at.is_not(None),
                    TripChatTurn.processing_started_at < cutoff,
                )
            )
        )
        if not stuck:
            return []
        now = datetime.now(UTC)
        for turn in stuck:
            turn.status = "failed"
            turn.error_code = "TURN_STALE"
            turn.error_message = (
                "Lượt xử lý trước đó đã quá thời gian chờ; đã đánh dấu thất bại."
            )
            turn.updated_at = now
        self.db.commit()
        return [turn.id for turn in stuck]

    def update_turn(
        self,
        turn: TripChatTurn,
        *,
        status: str | None = None,
        intent: str | None = None,
        confidence: float | None = None,
        requires_confirmation: bool | None = None,
        proposed_operations: list[dict] | None = None,
        assistant_blocks: list[dict] | None = None,
        result_summary: dict | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        processing_started_at: datetime | None = None,
    ) -> TripChatTurn:
        now = datetime.now(UTC)
        if status is not None:
            turn.status = status
            if status in PROCESSING_TURN_STATUSES and turn.processing_started_at is None:
                turn.processing_started_at = now
        if intent is not None:
            turn.intent = intent
        if confidence is not None:
            turn.confidence = confidence
        if requires_confirmation is not None:
            turn.requires_confirmation = requires_confirmation
        if proposed_operations is not None:
            turn.proposed_operations = list(proposed_operations)
        if assistant_blocks is not None:
            turn.assistant_blocks = list(assistant_blocks)
        if result_summary is not None:
            turn.result_summary = dict(result_summary)
        if error_code is not None:
            turn.error_code = error_code
        if error_message is not None:
            turn.error_message = error_message
        if processing_started_at is not None:
            turn.processing_started_at = processing_started_at
        turn.updated_at = now
        self.db.commit()
        self.db.refresh(turn)
        return turn

    def save_conversation_response(
        self,
        chat: TripChat,
        turn: TripChatTurn,
        *,
        assistant_content: str,
        assistant_blocks: list[dict],
        include_request: bool = True,
    ) -> None:
        """Append a plain assistant message bound to this turn (no plan
        mutation, no revision bump)."""
        now = datetime.now(UTC)
        # Keep the request and response together in the persisted history.
        # The frontend refetches the chat after a turn completes; omitting the
        # request here makes its optimistic user bubble disappear and also
        # deprives the next supervisor decision of the conversation context.
        next_sequence = max(
            (msg.sequence for msg in chat.messages),
            default=0,
        ) + 1
        messages = [
            TripChatMessage(
                id=str(uuid4()),
                chat_id=chat.id,
                role="assistant",
                content=assistant_content,
                sequence=next_sequence,
                attachment_names=[],
                plan_revision=chat.revision,
                turn_id=turn.id,
                message_kind="turn_response",
                content_blocks=list(assistant_blocks),
                created_at=now,
            ),
        ]
        if include_request:
            messages.insert(
                0,
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="user",
                    content=turn.content,
                    sequence=next_sequence,
                    attachment_names=list(turn.attachment_names or []),
                    plan_revision=chat.revision,
                    turn_id=turn.id,
                    message_kind="turn_request",
                    content_blocks=[],
                    created_at=now,
                ),
            )
            messages[1].sequence = next_sequence + 1
        self.db.add_all(messages)
        self.db.commit()

    def save_conversation_mutation(
        self,
        chat: TripChat,
        *,
        turn: TripChatTurn,
        user_content: str,
        assistant_content: str,
        assistant_blocks: list[dict],
        plan_payload: dict,
        revision: int,
    ) -> TripChat:
        """Persist a plan mutation produced by a turn. Mirrors the structure
        of save_plan_mutation but stamps the authoring turn for audit."""
        now = datetime.now(UTC)
        next_sequence = max(
            (msg.sequence for msg in chat.messages),
            default=0,
        ) + 1
        result = self.db.execute(
            update(TripChat)
            .where(
                TripChat.id == chat.id,
                TripChat.user_id == chat.user_id,
                TripChat.revision == revision - 1,
            )
            .values(
                current_plan=plan_payload,
                revision=revision,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã được cập nhật ở phiên khác. Hãy tải lại chat trước khi gửi.",
            )
        self.db.add_all(
            [
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="user",
                    content=user_content,
                    sequence=next_sequence,
                    attachment_names=list(turn.attachment_names or []),
                    plan_revision=revision,
                    turn_id=turn.id,
                    message_kind="turn_request",
                    content_blocks=[],
                    created_at=now,
                ),
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="assistant",
                    content=assistant_content,
                    sequence=next_sequence + 1,
                    attachment_names=[],
                    plan_revision=revision,
                    turn_id=turn.id,
                    message_kind="turn_response",
                    content_blocks=list(assistant_blocks),
                    created_at=now,
                ),
                TripChatPlanRevision(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    revision=revision,
                    intake_id=chat.current_intake_id,
                    plan_payload=plan_payload,
                    explorer_payload=chat.current_explorer or {},
                    created_at=now,
                ),
            ]
        )
        self.db.commit()
        return self.get(chat.id, chat.user_id)

    def get_revision(
        self, chat_id: str, revision: int
    ) -> TripChatPlanRevision | None:
        return self.db.scalar(
            select(TripChatPlanRevision).where(
                TripChatPlanRevision.chat_id == chat_id,
                TripChatPlanRevision.revision == revision,
            )
        )

    def list_recent_turns(
        self, chat_id: str, user_id: int, limit: int = 5
    ) -> list[TripChatTurn]:
        statement = (
            select(TripChatTurn)
            .where(
                TripChatTurn.chat_id == chat_id,
                TripChatTurn.user_id == user_id,
            )
            .order_by(TripChatTurn.created_at.desc(), TripChatTurn.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement))
