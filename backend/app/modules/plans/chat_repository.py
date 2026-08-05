from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.modules.plans.chat_model import (
    PROCESSING_TURN_STATUSES,
    TripChat,
    TripChatMessage,
    TripRevision,
)
from app.modules.knowledge_graph.model import KnowledgeGraphImport
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.trip_intent import TripIntent
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

    def delete_all_for_user(self, user_id: int) -> None:
        chats = self.list_for_user(user_id)
        for chat in chats:
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
        trip_intent: TripIntent,
        candidate_reviews: list[PlaceCandidateReview],
        explorer_timing_payload: dict | None,
        planner_timing_payload: dict | None,
        intake_id: str,
        destination: str,
        title: str,
        revision: int,
        turn_id: str | None = None,
    ) -> TripChat:
        now = datetime.now(UTC)
        next_sequence = max(
            (msg.sequence for msg in chat.messages),
            default=0,
        ) + 1
        intake = self.db.get(KnowledgeGraphImport, intake_id)
        if intake is None:
            intake = KnowledgeGraphImport(
                id=intake_id,
                import_kind="explorer_intake",
                created_by=chat.user_id,
                source_label=destination,
                source_content="",
                status="needs_review",
                schema_version="explorer-place-proposal-v1",
                ontology_version="knowledge-graph-v2",
                dataset_hash="",
                destination=destination,
                candidate_reviews=[],
            )
            self.db.add(intake)
            self.db.flush()
        intake.candidate_reviews = [
            review.model_dump(mode="json", by_alias=True)
            for review in candidate_reviews
        ]
        trip_intent_payload = trip_intent.model_dump(mode="json", by_alias=True)
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
                latest_explorer_timing=explorer_timing_payload,
                latest_planner_timing=planner_timing_payload,
                current_intake_id=intake_id,
                current_trip_intent=trip_intent_payload,
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
        records: list[TripChatMessage | TripRevision] = []
        if turn_id is None:
            records.append(
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="user",
                    content=user_content,
                    sequence=next_sequence,
                    attachment_names=attachment_names,
                    plan_revision=revision,
                    created_at=now,
                )
            )
        records.extend(
            [
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="assistant",
                    content=assistant_content,
                    sequence=next_sequence + (0 if turn_id is not None else 1),
                    attachment_names=[],
                    plan_revision=revision,
                    turn_id=turn_id,
                    message_kind=("turn_response" if turn_id else "text"),
                    created_at=now,
                ),
                TripRevision(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    revision=revision,
                    intake_id=intake_id,
                    plan_payload=plan_payload,
                    trip_intent_payload=trip_intent_payload,
                    created_at=now,
                ),
            ]
        )
        self.db.add_all(records)
        self.db.commit()
        return self.get(chat.id, chat.user_id)

    def save_intent_draft(
        self,
        chat: TripChat,
        *,
        user_content: str,
        attachment_names: list[str],
        assistant_content: str,
        trip_intent: TripIntent,
        candidate_reviews: list[PlaceCandidateReview],
        explorer_timing_payload: dict | None,
        intake_id: str,
        turn_id: str | None = None,
    ) -> TripChat:
        """Persist a destination-less Explorer draft without creating a plan revision."""
        now = datetime.now(UTC)
        next_sequence = max(
            (message.sequence for message in chat.messages), default=0
        ) + 1
        intake = self.db.get(KnowledgeGraphImport, intake_id)
        if intake is None:
            intake = KnowledgeGraphImport(
                id=intake_id,
                import_kind="explorer_intake",
                created_by=chat.user_id,
                source_label="Trip intent draft",
                source_content="",
                status="needs_review",
                schema_version="explorer-place-proposal-v1",
                ontology_version="knowledge-graph-v2",
                dataset_hash="",
                destination="",
                candidate_reviews=[],
            )
            self.db.add(intake)
            self.db.flush()
        intake.candidate_reviews = [
            review.model_dump(mode="json", by_alias=True)
            for review in candidate_reviews
        ]
        result = self.db.execute(
            update(TripChat)
            .where(
                TripChat.id == chat.id,
                TripChat.user_id == chat.user_id,
                TripChat.revision == chat.revision,
            )
            .values(
                current_trip_intent=trip_intent.model_dump(
                    mode="json", by_alias=True
                ),
                current_intake_id=intake_id,
                latest_explorer_timing=explorer_timing_payload,
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
        records: list[TripChatMessage] = []
        if turn_id is None:
            records.append(
                TripChatMessage(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    role="user",
                    content=user_content,
                    sequence=next_sequence,
                    attachment_names=attachment_names,
                    plan_revision=chat.revision,
                    created_at=now,
                )
            )
        records.append(
            TripChatMessage(
                id=str(uuid4()),
                chat_id=chat.id,
                role="assistant",
                content=assistant_content,
                sequence=next_sequence + (0 if turn_id else 1),
                attachment_names=[],
                plan_revision=chat.revision,
                turn_id=turn_id,
                message_kind="turn_response" if turn_id else "text",
                content_blocks=[{"type": "text", "text": assistant_content}],
                created_at=now,
            )
        )
        self.db.add_all(records)
        self.db.commit()
        return self.get(chat.id, chat.user_id)

    def save_plan_mutation(
        self,
        chat: TripChat,
        *,
        action_summary: str | None,
        plan_payload: dict,
        revision: int,
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
        records: list[TripChatMessage | TripRevision] = [
            TripRevision(
                id=str(uuid4()),
                chat_id=chat.id,
                revision=revision,
                intake_id=chat.current_intake_id,
                plan_payload=plan_payload,
                trip_intent_payload=chat.current_trip_intent,
                created_at=now,
            ),
        ]
        if action_summary is not None:
            records.insert(
                0,
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
            )
        self.db.add_all(records)
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
        commit: bool = True,
    ) -> TripChatMessage:
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
            select(TripChatMessage).where(
                TripChatMessage.chat_id == chat.id,
                TripChatMessage.client_turn_id == client_turn_id,
            )
        )
        if existing is not None:
            return existing
        now = datetime.now(UTC)
        next_sequence = max(
            (message.sequence for message in chat.messages), default=0
        ) + 1
        turn_id = str(uuid4())
        turn = TripChatMessage(
            id=turn_id,
            chat_id=chat.id,
            role="user",
            sequence=next_sequence,
            turn_id=turn_id,
            message_kind="turn_request",
            content_blocks=[],
            client_turn_id=client_turn_id,
            content=content.strip(),
            attachment_names=list(attachment_names or []),
            base_revision=expected_revision,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        chat.updated_at = now
        self.db.add(turn)
        if commit:
            self.db.commit()
            self.db.refresh(turn)
        else:
            self.db.flush()
        return turn

    def get_turn(
        self, chat_id: str, user_id: int, turn_id: str
    ) -> TripChatMessage:
        turn = self.db.scalar(
            select(TripChatMessage)
            .join(TripChat, TripChat.id == TripChatMessage.chat_id)
            .where(
                (TripChatMessage.id == turn_id) | (TripChatMessage.turn_id == turn_id),
                TripChatMessage.chat_id == chat_id,
                TripChat.user_id == user_id,
                TripChatMessage.client_turn_id.is_not(None),
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
                select(TripChatMessage).where(
                    TripChatMessage.chat_id == chat_id,
                    TripChatMessage.status.in_(PROCESSING_TURN_STATUSES),
                    TripChatMessage.processing_started_at.is_not(None),
                    TripChatMessage.processing_started_at < cutoff,
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
        return [turn.lifecycle_id for turn in stuck]

    def update_turn(
        self,
        turn: TripChatMessage,
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
    ) -> TripChatMessage:
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
            plan_revision = result_summary.get("planRevision")
            if isinstance(plan_revision, int):
                turn.plan_revision = plan_revision
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
        turn: TripChatMessage,
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
                turn_id=turn.lifecycle_id,
                message_kind="turn_response",
                content_blocks=list(assistant_blocks),
                created_at=now,
            ),
        ]
        del include_request  # the request row is created when the turn starts
        self.db.add_all(messages)
        self.db.commit()

    def save_conversation_mutation(
        self,
        chat: TripChat,
        *,
        turn: TripChatMessage,
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
                    role="assistant",
                    content=assistant_content,
                    sequence=next_sequence,
                    attachment_names=[],
                    plan_revision=revision,
                    turn_id=turn.lifecycle_id,
                    message_kind="turn_response",
                    content_blocks=list(assistant_blocks),
                    created_at=now,
                ),
                TripRevision(
                    id=str(uuid4()),
                    chat_id=chat.id,
                    revision=revision,
                    intake_id=chat.current_intake_id,
                    plan_payload=plan_payload,
                    trip_intent_payload=chat.current_trip_intent,
                    created_at=now,
                ),
            ]
        )
        self.db.commit()
        return self.get(chat.id, chat.user_id)

    def load_trip_intent(self, chat: TripChat) -> TripIntent | None:
        if chat.current_trip_intent is None:
            return None
        return TripIntent.model_validate(chat.current_trip_intent)

    def load_candidate_reviews(self, chat: TripChat) -> list[PlaceCandidateReview]:
        intake_ids = list(
            dict.fromkeys(
                intake_id
                for intake_id in [
                    *(revision.intake_id for revision in chat.plan_revisions),
                    chat.current_intake_id,
                ]
                if intake_id is not None
            )
        )
        reviews: list[PlaceCandidateReview] = []
        for intake_id in intake_ids:
            intake = self.db.get(KnowledgeGraphImport, intake_id)
            if intake is None or intake.import_kind != "explorer_intake":
                continue
            reviews.extend(
                PlaceCandidateReview.model_validate(value)
                for value in intake.candidate_reviews
            )
        return reviews

    def replace_candidate_reviews(
        self,
        chat: TripChat,
        reviews: list[PlaceCandidateReview],
    ) -> None:
        if chat.current_intake_id is None:
            return
        intake = self.db.get(KnowledgeGraphImport, chat.current_intake_id)
        if intake is None or intake.import_kind != "explorer_intake":
            return
        intake.candidate_reviews = [
            review.model_dump(mode="json", by_alias=True) for review in reviews
        ]

    def get_revision(
        self, chat_id: str, revision: int
    ) -> TripRevision | None:
        return self.db.scalar(
            select(TripRevision).where(
                TripRevision.chat_id == chat_id,
                TripRevision.revision == revision,
            )
        )

    def list_recent_turns(
        self, chat_id: str, user_id: int, limit: int = 5
    ) -> list[TripChatMessage]:
        statement = (
            select(TripChatMessage)
            .join(TripChat, TripChat.id == TripChatMessage.chat_id)
            .where(
                TripChatMessage.chat_id == chat_id,
                TripChat.user_id == user_id,
                TripChatMessage.client_turn_id.is_not(None),
            )
            .order_by(TripChatMessage.created_at.desc(), TripChatMessage.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement))
