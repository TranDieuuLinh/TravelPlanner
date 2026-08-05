from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.core.config import settings
from app.modules.plans.chat_model import TripChat, TripChatTurn
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_service import TripChatService
from app.integrations.llm.factory import get_llm_client
from app.modules.plans.conversation_supervisor import (
    ConstrainedConversationSupervisor,
    ConversationDecision,
    ConversationSupervisorError,
)
from app.modules.plans.domain.entities import Plan
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    UpdateItemRequest,
)
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.router import (
    _extract_urls,
    _infer_destination,
    _infer_destination_from_urls,
    _normalize_urls,
    _remove_urls,
)
from app.modules.users.model import User
from app.shared.errors import AppError

logger = logging.getLogger(__name__)


class ConversationTurnService:
    """Bounded execution layer for conversational TripChat turns.

    The supervisor proposes one schema-shaped local operation. This service owns
    revision checks, lock policy, deterministic mutation tools, validation and
    persistence; the model/classifier never receives a database handle.
    """

    def __init__(
        self,
        repository: TripChatRepository,
        trip_chat_service: TripChatService,
        mutation_service: PlanMutationService,
        supervisor: ConstrainedConversationSupervisor | None = None,
    ) -> None:
        self.repository = repository
        self.trip_chat_service = trip_chat_service
        self.mutation_service = mutation_service
        self.supervisor = supervisor or ConstrainedConversationSupervisor(get_llm_client())
        self.turn_timeout_seconds = settings.conversation_turn_timeout_seconds
        self.turn_stale_after_seconds = settings.conversation_turn_stale_after_seconds

    def get_turn(self, chat_id: str, user: User, turn_id: str) -> TripChatTurn:
        self._recover_stale_turns(chat_id)
        return self.repository.get_turn(chat_id, user.id, turn_id)

    def _recover_stale_turns(self, chat_id: str) -> None:
        expire = getattr(self.repository, "expire_stale_turns", None)
        if expire is None:
            return
        try:
            expire(chat_id, self.turn_stale_after_seconds)
        except Exception:
            logger.exception(
                "Failed to recover stale conversation turns",
                extra={"chat_id": chat_id},
            )
            raise

    def start(
        self,
        chat_id: str,
        user: User,
        content: str,
        expected_revision: int,
        client_turn_id: str | None = None,
        attachment_names: list[str] = [],
    ) -> TripChatTurn:
        if not content.strip():
            raise AppError(
                422,
                "VALIDATION_ERROR",
                "Nội dung không được để trống.",
            )
        chat = self.repository.get(chat_id, user.id)
        self._recover_stale_turns(chat_id)
        return self.repository.create_turn(
            chat,
            client_turn_id=client_turn_id or str(uuid4()),
            content=content.strip(),
            attachment_names=attachment_names,
            expected_revision=expected_revision,
        )

    async def execute(
        self,
        chat_id: str,
        user: User,
        turn_id: str,
        images: list[ImageUploadPayload] | None = None,
    ) -> TripChatTurn:
        self._recover_stale_turns(chat_id)
        turn = self.repository.get_turn(chat_id, user.id, turn_id)
        if turn.status in {"completed", "awaiting_confirmation", "cancelled"}:
            return turn
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != turn.base_revision:
            return self.repository.update_turn(
                turn,
                status="failed",
                error_code="VERSION_CONFLICT",
                error_message="Lịch trình đã thay đổi; hãy tải lại trước khi gửi lại yêu cầu.",
            )
        plan = (
            Plan.model_validate(chat.current_plan)
            if chat.current_plan
            else None
        )

        self.repository.update_turn(turn, status="classifying")
        try:
            decision = await asyncio.wait_for(
                self.supervisor.decide(
                    turn.content,
                    plan,
                    conversation_context=_conversation_context(chat),
                ),
                timeout=self.turn_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.exception(
                "Conversation turn timed out",
                extra={"chat_id": chat.id, "turn_id": turn.id},
            )
            return self._save_failed_turn(
                chat,
                turn,
                "TURN_TIMEOUT",
                "Lượt xử lý đã hết thời gian chờ. Bạn có thể thử lại.",
            )
        except ConversationSupervisorError:
            logger.exception(
                "Conversation supervisor failed",
                extra={"chat_id": chat.id, "turn_id": turn.id},
            )
            message = "Mình chưa thể hiểu yêu cầu một cách an toàn. Hãy diễn đạt lại hoặc thử lại sau; lịch trình chưa thay đổi."
            return self._save_failed_turn(chat, turn, "SUPERVISOR_DECISION_FAILED", message)
        except AppError as error:
            logger.exception(
                "Conversation turn rejected by application policy",
                extra={"chat_id": chat.id, "turn_id": turn.id, "error_code": error.code},
            )
            return self._save_failed_turn(chat, turn, error.code, error.message)

        self.repository.update_turn(
            turn,
            status="classifying",
            intent=decision.intent,
            confidence=decision.confidence,
            requires_confirmation=decision.requires_confirmation,
            proposed_operations=(
                [decision.operation] if decision.operation else []
            ),
        )

        if decision.requires_confirmation:
            preview = _confirmation_preview(decision, plan)
            blocks = [
                {
                    "type": "planDiff",
                    "requiresConfirmation": True,
                    "summary": preview,
                }
            ]
            self.repository.save_conversation_response(
                chat,
                turn,
                assistant_content=preview,
                assistant_blocks=blocks,
                include_request=False,
            )
            return self.repository.update_turn(
                turn,
                status="awaiting_confirmation",
                assistant_blocks=blocks,
                result_summary={"planRevision": chat.revision},
            )

        try:
            return await asyncio.wait_for(
                self._run_decision(
                    chat, turn, decision, plan, images or []
                ),
                timeout=self.turn_timeout_seconds,
            )
        except AppError as error:
            logger.exception(
                "Conversation turn failed during execution",
                extra={"chat_id": chat.id, "turn_id": turn.id, "error_code": error.code},
            )
            return self._save_failed_turn(chat, turn, error.code, error.message)

    async def confirm(
        self,
        chat_id: str,
        user: User,
        turn_id: str,
    ) -> TripChatTurn:
        self._recover_stale_turns(chat_id)
        turn = self.repository.get_turn(chat_id, user.id, turn_id)
        if turn.status != "awaiting_confirmation":
            raise AppError(
                409,
                "TURN_NOT_PENDING",
                "Lượt hội thoại này không chờ xác nhận.",
            )
        chat = self.repository.get(chat_id, user.id)
        if chat.revision != turn.base_revision:
            raise AppError(
                409,
                "VERSION_CONFLICT",
                "Lịch trình đã thay đổi; hãy gửi lại yêu cầu.",
            )
        plan = (
            Plan.model_validate(chat.current_plan)
            if chat.current_plan
            else None
        )
        decision = ConversationDecision(
            intent=turn.intent or "unsupported",
            confidence=turn.confidence or 0,
            operation=(
                turn.proposed_operations[0]
                if turn.proposed_operations
                else None
            ),
            # A confirmed turn has already passed the confirmation gate.  The
            # remaining fields are only used while presenting the proposal.
            requires_confirmation=False,
            message=None,
            options=(),
        )
        try:
            return await self._run_decision(
                chat,
                turn,
                decision,
                plan,
                [],
                confirmed=True,
            )
        except AppError as error:
            logger.exception(
                "Confirmed conversation turn failed during execution",
                extra={"chat_id": chat.id, "turn_id": turn.id, "error_code": error.code},
            )
            return self._save_failed_turn(chat, turn, error.code, error.message)

    def cancel(
        self,
        chat_id: str,
        user: User,
        turn_id: str,
    ) -> TripChatTurn:
        self._recover_stale_turns(chat_id)
        turn = self.repository.get_turn(chat_id, user.id, turn_id)
        if turn.status == "completed":
            raise AppError(
                409,
                "TURN_ALREADY_COMPLETED",
                "Lượt hội thoại đã hoàn tất.",
            )
        return self.repository.update_turn(
            turn,
            status="cancelled",
            assistant_blocks=[
                {"type": "text", "text": "Đã hủy thao tác; lịch trình không thay đổi."}
            ],
        )

    async def _run_decision(
        self,
        chat: TripChat,
        turn: TripChatTurn,
        decision: ConversationDecision,
        plan: Plan | None,
        images: list[ImageUploadPayload],
        *,
        confirmed: bool = False,
    ) -> TripChatTurn:
        self.repository.update_turn(turn, status="executing")
        if decision.intent in {"create_plan", "regenerate_plan"}:
            return await self._create_plan(chat, turn, images)

        if decision.intent == "clarify":
            blocks = _clarification_blocks(decision, plan, turn.content)
            return self._save_response(
                chat,
                turn,
                decision.message or "Mình cần bạn chọn một phương án trước khi tiếp tục.",
                blocks,
            )

        if decision.intent == "travel_advice":
            response_text = decision.message or "Mình có thể hỗ trợ tư vấn hành trình trước khi tạo plan."
            blocks = [{"type": "text", "text": response_text}]
            if decision.options:
                blocks.append(
                    {
                        "type": "options",
                        "options": list(decision.options),
                    }
                )
            return self._save_response(chat, turn, response_text, blocks)

        if plan is None:
            raise AppError(
                400,
                "NO_ACTIVE_PLAN",
                "Chưa có lịch trình để thực hiện yêu cầu này.",
            )

        if decision.intent == "validate_plan":
            report = self.mutation_service.checker.check(plan)
            return self._save_response(
                chat,
                turn,
                report.summary,
                [
                    {
                        "type": "validationReport",
                        "report": report.model_dump(mode="json", by_alias=True),
                    }
                ],
            )

        if decision.intent == "explain_plan":
            source_count = sum(
                len(item.source_refs)
                for day in plan.days
                for item in day.items
            )
            text = decision.message or (
                f"Lịch trình {plan.destination} hiện có {len(plan.days)} ngày và "
                f"{source_count} tham chiếu nguồn. Bạn có thể chọn một địa điểm cụ thể để xem lý do và nguồn đã dùng."
            )
            return self._save_response(
                chat,
                turn,
                text,
                [{"type": "text", "text": text}],
            )

        if decision.intent == "create_backup":
            from app.modules.plans.schema import BackupPlanCreate

            avoid_outdoor = any(
                word in turn.content.casefold()
                for word in ("mưa", "rain")
            )
            bundle = await self.trip_chat_service.plan_service.create_backup_plan(
                plan.id,
                BackupPlanCreate(
                    reason="conversation_request",
                    avoidOutdoor=avoid_outdoor,
                ),
            )
            block = {
                "type": "backupComparison",
                "mainPlanId": plan.id,
                "backupPlanId": bundle.backup_plan.get("id"),
                "validation": bundle.validation,
            }
            return self._save_response(
                chat,
                turn,
                "Đã tạo phương án dự phòng riêng.",
                [block],
            )

        if decision.intent == "undo":
            return self._undo(chat, turn)

        if decision.confidence < 0.85 and decision.operation is None:
            raise AppError(
                422,
                "LOW_CONFIDENCE",
                "Mình cần bạn nói rõ địa điểm và ngày cần thay đổi.",
            )

        return await self._mutate(
            chat,
            turn,
            plan,
            decision,
            allow_locked_change=confirmed,
        )

    async def _create_plan(
        self,
        chat: TripChat,
        turn: TripChatTurn,
        images: list[ImageUploadPayload],
    ) -> TripChatTurn:
        urls = list(
            dict.fromkeys(
                _normalize_urls([]) + _extract_urls(turn.content)
            )
        )
        initial_destination = (
            _infer_destination(_remove_urls(turn.content))
            or _infer_destination_from_urls(urls)
            or "unspecified"
        )
        if _is_context_only_plan_request(turn.content):
            initial_destination = "unspecified"
        from app.modules.users.model import User as _User

        try:
            result = await self.trip_chat_service.generate_plan_revision(
                chat_id=chat.id,
                user=_User(
                    id=chat.user_id,
                ),
                content=turn.content,
                expected_revision=turn.base_revision,
                initial_destination=initial_destination,
                urls=urls,
                images=images,
            )
        except ValueError as exc:
            if "region_key" in str(exc):
                raise AppError(
                    422,
                    "DESTINATION_UNRECOGNIZED",
                    (
                        "Mình chưa nhận diện được điểm đến trong yêu cầu của bạn. "
                        "Hãy nhập tên thành phố hoặc tỉnh cụ thể hơn (ví dụ: Hà Nội, Đà Nẵng, Hội An)."
                    ),
                ) from exc
            raise
        return self.repository.update_turn(
            turn,
            status="completed",
            assistant_blocks=[
                {
                    "type": "planDiff",
                    "beforeRevision": turn.base_revision,
                    "afterRevision": result.revision,
                    "affectedDays": (
                        list(range(1, len(result.current_plan.days) + 1))
                        if result.current_plan
                        else []
                    ),
                    "undoAvailable": result.revision > 1,
                }
            ],
            result_summary={"planRevision": result.revision},
        )

    async def _mutate(
        self,
        chat: TripChat,
        turn: TripChatTurn,
        plan: Plan,
        decision: ConversationDecision,
        *,
        allow_locked_change: bool = False,
    ) -> TripChatTurn:
        operation = decision.operation or {}
        day = int(operation.get("day") or 1)
        item_id = str(operation.get("itemId") or "")
        existing = _find_item(plan, item_id)

        if existing and existing.locked and decision.intent not in {"lock_item", "unlock_item"} and not allow_locked_change:
            raise AppError(
                409,
                "LOCKED_ITEM",
                "Địa điểm này đang được khóa; hãy xác nhận hoặc mở khóa trước.",
            )

        if decision.intent == "add_place":
            result = await self.mutation_service.add_item(
                plan,
                AddItemRequest(day=day, name=str(operation["name"])),
            )
            summary = f"Đã thêm {operation['name']} vào Ngày {day}."
        elif decision.intent == "update_place":
            result = await self.mutation_service.update_item(
                plan,
                day,
                item_id,
                UpdateItemRequest(name=str(operation["name"])),
            )
            summary = "Đã cập nhật địa điểm."
        elif decision.intent in {"lock_item", "unlock_item"}:
            result = await self.mutation_service.update_item(
                plan,
                day,
                item_id,
                UpdateItemRequest(locked=decision.intent == "lock_item"),
            )
            summary = (
                "Đã khóa địa điểm."
                if decision.intent == "lock_item"
                else "Đã mở khóa địa điểm."
            )
        elif decision.intent == "remove_place":
            result = self.mutation_service.remove_item(plan, day, item_id)
            summary = "Đã xóa địa điểm."
        elif decision.intent == "move_place":
            result = self.mutation_service.move_item(
                plan,
                day,
                item_id,
                MoveItemRequest(toDay=int(operation["toDay"])),
            )
            summary = f"Đã chuyển địa điểm sang Ngày {operation['toDay']}."
        else:
            raise AppError(
                422,
                "UNSUPPORTED_OPERATION",
                "Yêu cầu này chưa có thao tác an toàn tương ứng.",
            )

        before_errors = _error_codes(
            self.mutation_service.checker.check(plan)
        )
        after_errors = _error_codes(result.check_report)
        new_errors = sorted(after_errors - before_errors)
        if new_errors:
            raise AppError(
                422,
                "MUTATION_VALIDATION_FAILED",
                "Thay đổi tạo lỗi kiểm tra mới nên chưa được áp dụng.",
                {"newErrors": new_errors},
            )

        revision = chat.revision + 1
        diff = _plan_diff(
            plan,
            result.plan,
            result.affected_days,
            chat.revision,
            revision,
        )
        saved = self.repository.save_conversation_mutation(
            chat,
            turn=turn,
            user_content=turn.content,
            assistant_content=summary,
            assistant_blocks=[
                {"type": "planDiff", **diff}
            ],
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self.repository.update_turn(
            turn,
            status="completed",
            assistant_blocks=[{"type": "planDiff", **diff}],
            result_summary={
                "planRevision": saved.revision,
                "affectedDays": result.affected_days,
            },
        )

    def _undo(self, chat: TripChat, turn: TripChatTurn) -> TripChatTurn:
        if chat.revision < 2:
            raise AppError(
                409,
                "UNDO_UNAVAILABLE",
                "Chưa có bản sửa đổi trước đó để hoàn tác.",
            )
        previous = self.repository.get_revision(chat.id, chat.revision - 1)
        if previous is None:
            raise AppError(
                409,
                "UNDO_UNAVAILABLE",
                "Không tìm thấy snapshot để hoàn tác.",
            )
        plan = Plan.model_validate(previous.plan_payload)
        revision = chat.revision + 1
        diff = {
            "beforeRevision": chat.revision,
            "afterRevision": revision,
            "affectedDays": [day.day for day in plan.days],
            "undoAvailable": True,
            "summary": "Đã tạo bản sửa đổi mới từ snapshot trước đó.",
        }
        saved = self.repository.save_conversation_mutation(
            chat,
            turn=turn,
            user_content=turn.content,
            assistant_content="Đã hoàn tác thay đổi gần nhất.",
            assistant_blocks=[{"type": "planDiff", **diff}],
            plan_payload=plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self.repository.update_turn(
            turn,
            status="completed",
            assistant_blocks=[{"type": "planDiff", **diff}],
            result_summary={"planRevision": saved.revision},
        )

    def _save_failed_turn(
        self,
        chat: TripChat,
        turn: TripChatTurn,
        error_code: str,
        message: str,
    ) -> TripChatTurn:
        try:
            self.repository.db.rollback()
        except Exception:
            logger.exception(
                "Failed to rollback database after conversation turn failure",
                extra={"chat_id": chat.id, "turn_id": turn.id, "error_code": error_code},
            )
        blocks = [{"type": "errorRecovery", "message": message}]
        try:
            self.repository.save_conversation_response(
                chat, turn, assistant_content=message, assistant_blocks=blocks
            )
            return self.repository.update_turn(
                turn,
                status="failed",
                error_code=error_code,
                error_message=message,
                assistant_blocks=blocks,
            )
        except Exception:
            logger.exception(
                "Failed to persist failed conversation turn",
                extra={"chat_id": chat.id, "turn_id": turn.id, "error_code": error_code},
            )
            raise

    def _save_response(
        self,
        chat: TripChat,
        turn: TripChatTurn,
        content: str,
        blocks: list[dict],
    ) -> TripChatTurn:
        self.repository.save_conversation_response(
            chat, turn, assistant_content=content, assistant_blocks=blocks
        )
        return self.repository.update_turn(
            turn,
            status="completed",
            assistant_blocks=blocks,
            result_summary={"planRevision": chat.revision},
        )


def _clarification_blocks(
    decision: ConversationDecision,
    plan: Plan | None,
    request: str,
) -> list[dict]:
    del plan, request  # kept for signature parity with the original bytecode
    blocks: list[dict] = [
        {
            "type": "text",
            "text": decision.message or "Bạn muốn làm gì tiếp?",
        }
    ]
    if decision.options:
        blocks.append(
            {
                "type": "optionSelector",
                "options": list(decision.options),
            }
        )
    return blocks


def _conversation_context(chat: TripChat) -> dict:
    """Build a small, bounded context instead of sending the whole chat/plan.

    The current message is supplied separately. Only recent text turns and
    stable trip metadata are exposed to the LLM; attachments and content blocks
    are deliberately excluded.
    """
    recent_messages = [
        {"role": message.role, "content": message.content[:1000]}
        for message in list(chat.messages)[-8:]
        if message.role in {"assistant", "user"} and message.content.strip()
    ]
    stored_context = chat.conversation_context or {}
    requirements = stored_context.get("requirements")
    action_history = [
        _turn_action_summary(turn)
        for turn in list(getattr(chat, "turns", ()))[-8:]
        if turn.status != "queued"
    ]
    return {
        "phase": chat.conversation_phase,
        "destination": chat.destination,
        "planRevision": chat.revision,
        "requirements": requirements if isinstance(requirements, dict) else {},
        "recentMessages": recent_messages,
        "recentActionHistory": action_history,
    }


def _turn_action_summary(turn: TripChatTurn) -> dict:
    status = turn.status
    outcome = {
        "completed": "success",
        "failed": "failed",
        "cancelled": "rejected",
        "awaiting_confirmation": "awaiting_confirmation",
        "queued": "queued",
        "classifying": "in_progress",
        "executing": "in_progress",
    }.get(status, "unknown")
    proposed_operations = getattr(turn, "proposed_operations", None) or []
    operation = proposed_operations[0] if proposed_operations else {}
    safe_operation = {
        key: operation[key]
        for key in ("type", "itemId", "day", "toDay", "name")
        if key in operation and operation[key] is not None
    }
    result = {
        "turnId": turn.id,
        "status": status,
        "outcome": outcome,
        # Keep the bounded user request available even for turns created by
        # older builds that did not persist a turn_request message.
        "request": getattr(turn, "content", "")[:1000],
        "intent": turn.intent,
        "operation": safe_operation,
        "planRevision": (getattr(turn, "result_summary", None) or {}).get("planRevision"),
    }
    error_code = getattr(turn, "error_code", None)
    if error_code:
        result["errorCode"] = error_code
        error_message = getattr(turn, "error_message", None)
        if error_message:
            result["errorMessage"] = error_message[:300]
    return result


def _confirmation_preview(
    decision: ConversationDecision,
    plan: Plan | None,
) -> str:
    if decision.intent in {"create_plan", "regenerate_plan"} and plan is not None:
        return "Yêu cầu này sẽ tạo lại lịch trình hiện tại. Hãy xác nhận để tiếp tục."
    operation = decision.operation or {}
    item_id = str(operation.get("itemId") or "")
    item = _find_item(plan, item_id) if plan is not None and item_id else None
    if item is not None and item.locked:
        return f"{item.name} đang được khóa. Hãy xác nhận nếu bạn vẫn muốn thay đổi địa điểm này."
    return "Thay đổi này có phạm vi lớn hoặc khó hoàn tác. Hãy xác nhận để tiếp tục."


def _find_item(plan: Plan, item_id: str):
    for day in plan.days:
        for item in day.items:
            if item.item_id == item_id:
                return item
    return None


def _is_context_only_plan_request(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    return any(
        phrase in normalized
        for phrase in (
            "theo thông tin bên trên",
            "theo thông tin ở trên",
            "lên plan cho tôi",
            "lên plan đi",
            "tạo plan cho tôi",
            "tạo lịch trình cho tôi",
            "có lên plan",
        )
    )


def _error_codes(report) -> set[str]:
    return {issue.code for issue in report.issues if issue.severity == "error"}


def _plan_diff(
    before: Plan,
    after: Plan,
    affected_days: list[int],
    before_revision: int,
    after_revision: int,
) -> dict:
    before_items = {
        item.item_id: item
        for day in before.days
        for item in day.items
        if item.item_id
    }
    after_items = {
        item.item_id: item
        for day in after.days
        for item in day.items
        if item.item_id
    }
    added = [
        item.name
        for item_id, item in after_items.items()
        if item_id not in before_items
    ]
    removed = [
        item.name
        for item_id, item in before_items.items()
        if item_id not in after_items
    ]
    updated = [
        after_items[item_id].name
        for item_id in before_items.keys() & after_items.keys()
        if before_items[item_id] != after_items[item_id]
    ]
    warnings: list[str] = []
    if getattr(after, "check_report", None) is not None:
        warnings = [
            issue.message
            for issue in after.check_report.issues
            if issue.severity == "warning"
        ]
    return {
        "beforeRevision": before_revision,
        "afterRevision": after_revision,
        "affectedDays": affected_days,
        "added": added,
        "removed": removed,
        "updated": updated,
        "warnings": warnings,
        "undoAvailable": True,
    }
