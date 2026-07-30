from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.modules.plans.chat_model import TripChat, TripChatMessage, TripChatPlanRevision
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
            .options(selectinload(TripChat.messages))
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
        intake_id: str,
        destination: str,
        title: str,
        revision: int,
    ) -> TripChat:
        now = datetime.now(UTC)
        next_sequence = (revision * 2) - 1
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
