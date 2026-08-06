from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.modules.plans.chat_model import TripChat, TripChatMessage
from app.modules.plans.chat_repository import TripChatRepository
from app.modules.plans.chat_service import TripChatService
from app.integrations.llm.factory import get_llm_client
from app.modules.plans.conversation_supervisor import (
    ConstrainedConversationSupervisor,
    ConversationDecision,
    ConversationSupervisorError,
)
from app.modules.plans.conversation_agents import (
    ConversationAgentContext,
    ConversationAgentDispatcher,
)
from app.modules.plans.domain.entities import Plan
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.information_finder import InformationFinderAgent, PlaceSearchReader
from app.modules.plans.plan_mutation_schema import (
    AddItemRequest,
    MoveItemRequest,
    UpdateItemRequest,
)
from app.modules.plans.plan_mutation_service import PlanMutationService
from app.modules.plans.plan_editor import (
    PlanEditorOperation,
    validate_operation_for_intent,
)
from app.modules.plans.plan_editor.agent import PlanEditorAgent
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
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
        information_finder_reader: PlaceSearchReader | None = None,
    ) -> None:
        self.repository = repository
        self.trip_chat_service = trip_chat_service
        self.mutation_service = mutation_service
        self.supervisor = supervisor or ConstrainedConversationSupervisor(get_llm_client())
        self.information_finder_agent = InformationFinderAgent(information_finder_reader)
        self.plan_editor_agent = (
            PlanEditorAgent(
                repository,
                ExplorerPersistenceRepository(repository.db),
                mutation_service,
            )
            if hasattr(repository, "db") else None
        )
        self.agent_dispatcher = ConversationAgentDispatcher(
            {
                "explorer": self._run_explorer_agent,
                "information_finder": self._run_information_finder_agent,
                "main_planner": self._run_main_planner_agent,
                "plan_editor": self._run_plan_editor_agent,
            }
        )
        self.turn_timeout_seconds = settings.conversation_turn_timeout_seconds
        self.plan_timeout_seconds = settings.conversation_plan_timeout_seconds
        self.turn_stale_after_seconds = settings.conversation_turn_stale_after_seconds

    def get_turn(self, chat_id: str, user: User, turn_id: str) -> TripChatMessage:
        self._recover_stale_turns(chat_id)
        return self.repository.get_turn(chat_id, user.id, turn_id)

    def list_active_turns(self, user: User) -> list[TripChatMessage]:
        return self.repository.list_active_turns_for_user(user.id)

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
    ) -> TripChatMessage:
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
    ) -> TripChatMessage:
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
                    conversation_context=_conversation_context(
                        chat, exclude_turn_id=_turn_lifecycle_id(turn)
                    ),
                ),
                timeout=self.turn_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.exception(
                "Conversation turn timed out",
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn)},
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
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn)},
            )
            message = "Mình chưa thể hiểu yêu cầu một cách an toàn. Hãy diễn đạt lại hoặc thử lại sau; lịch trình chưa thay đổi."
            return self._save_failed_turn(chat, turn, "SUPERVISOR_DECISION_FAILED", message)
        except AppError as error:
            logger.exception(
                "Conversation turn rejected by application policy",
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn), "error_code": error.code},
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
                timeout=self._execution_timeout_seconds(decision),
            )
        except asyncio.TimeoutError:
            logger.exception(
                "Conversation turn timed out during execution",
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn)},
            )
            return self._save_failed_turn(
                chat,
                turn,
                "TURN_TIMEOUT",
                "Lượt xử lý đã hết thời gian chờ. Bạn có thể thử lại.",
            )
        except AppError as error:
            logger.exception(
                "Conversation turn failed during execution",
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn), "error_code": error.code},
            )
            return self._save_failed_turn(chat, turn, error.code, error.message)

    async def confirm(
        self,
        chat_id: str,
        user: User,
        turn_id: str,
    ) -> TripChatMessage:
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
            return await asyncio.wait_for(
                self._run_decision(
                    chat,
                    turn,
                    decision,
                    plan,
                    [],
                    confirmed=True,
                ),
                timeout=self._execution_timeout_seconds(decision),
            )
        except asyncio.TimeoutError:
            logger.exception(
                "Confirmed conversation turn timed out during execution",
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn)},
            )
            return self._save_failed_turn(
                chat,
                turn,
                "TURN_TIMEOUT",
                "Lượt xử lý đã hết thời gian chờ. Bạn có thể thử lại.",
            )
        except AppError as error:
            logger.exception(
                "Confirmed conversation turn failed during execution",
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn), "error_code": error.code},
            )
            return self._save_failed_turn(chat, turn, error.code, error.message)

    def _execution_timeout_seconds(
        self,
        decision: ConversationDecision,
    ) -> float:
        if decision.intent in {"create_plan", "regenerate_plan"}:
            return self.plan_timeout_seconds
        return self.turn_timeout_seconds

    def cancel(
        self,
        chat_id: str,
        user: User,
        turn_id: str,
    ) -> TripChatMessage:
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
        turn: TripChatMessage,
        decision: ConversationDecision,
        plan: Plan | None,
        images: list[ImageUploadPayload],
        *,
        confirmed: bool = False,
    ) -> TripChatMessage:
        self.repository.update_turn(turn, status="executing")
        if decision.intent in {"create_plan", "regenerate_plan"}:
            context = ConversationAgentContext(
                chat=chat,
                turn=turn,
                decision=decision,
                plan=plan,
                images=images,
                confirmed=confirmed,
            )
            explorer_context = await self.agent_dispatcher.dispatch(
                "explorer", context
            )
            context.data["explorer"] = explorer_context
            return await self.agent_dispatcher.dispatch(
                decision.agent or "main_planner", context
            )

        if decision.intent == "clarify":
            blocks = _clarification_blocks(decision, plan, turn.content)
            return self._save_response(
                chat,
                turn,
                decision.message or "Mình cần bạn chọn một phương án trước khi tiếp tục.",
                blocks,
            )

        if decision.intent == "travel_advice":
            return await self.agent_dispatcher.dispatch(
                decision.agent or "information_finder",
                ConversationAgentContext(chat, turn, decision, plan, images, confirmed),
            )

        if decision.intent == "explain_plan":
            return await self.agent_dispatcher.dispatch(
                decision.agent or "information_finder",
                ConversationAgentContext(
                    chat=chat,
                    turn=turn,
                    decision=decision,
                    plan=plan,
                    images=images,
                    confirmed=confirmed,
                    data={"information_intent": "explain_plan"},
                ),
            )

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

        if decision.intent == "create_backup":
            raise AppError(
                422,
                "UNSUPPORTED_AGENT",
                "Luồng tạo phương án dự phòng trong chat đang tạm thời chưa được bật.",
            )

        if decision.intent == "undo":
            return self._undo(chat, turn)

        if decision.intent == "unsupported":
            message = decision.message or "Yêu cầu này hiện chưa được hỗ trợ trong Planner."
            return self._save_response(
                chat,
                turn,
                message,
                [{"type": "text", "text": message}],
            )

        if decision.confidence < 0.85 and decision.operation is None:
            raise AppError(
                422,
                "LOW_CONFIDENCE",
                "Mình cần bạn nói rõ địa điểm và ngày cần thay đổi.",
            )

        return await self.agent_dispatcher.dispatch(
            decision.agent or "plan_editor",
            ConversationAgentContext(
                chat=chat,
                turn=turn,
                decision=decision,
                plan=plan,
                images=images,
                confirmed=confirmed,
            ),
        )

    async def _run_explorer_agent(
        self, context: ConversationAgentContext
    ) -> dict[str, object]:
        """Prepare the normalized request handed to the planning agent.

        The existing TripChatService still owns the full persistence-safe
        Explorer pipeline. This adapter makes its boundary explicit while the
        lower-level Explorer implementation remains unchanged.
        """
        urls = list(dict.fromkeys(_extract_urls(context.turn.content)))
        destination = (
            _infer_destination(_remove_urls(context.turn.content))
            or _infer_destination_from_urls(urls)
            or "unspecified"
        )
        if _is_context_only_plan_request(context.turn.content):
            destination = "unspecified"
        return {"urls": urls, "initial_destination": destination}

    async def _run_main_planner_agent(
        self, context: ConversationAgentContext
    ) -> TripChatMessage:
        return await self._create_plan(
            context.chat,
            context.turn,
            context.images,
            planning_context=context.data.get("explorer"),
        )

    async def _run_information_finder_agent(
        self, context: ConversationAgentContext
    ) -> TripChatMessage:
        response = await self.information_finder_agent.run(context)
        summary = _information_result_summary(response.result)
        blocks = list(response.blocks)
        if "candidate_data_stale" in summary.get("warnings", []) and not any(
            block.get("code") == "candidate_data_stale" for block in blocks
        ):
            blocks.append({
                "type": "warning",
                "code": "candidate_data_stale",
                "message": "Một số dữ liệu địa điểm đã cũ; hãy xác minh trước khi dùng cho kế hoạch.",
                "freshness": "stale",
            })
        return self._save_response(
            context.chat,
            context.turn,
            response.message,
            blocks,
            result_summary=summary,
        )

    async def _run_plan_editor_agent(
        self, context: ConversationAgentContext
    ) -> TripChatMessage:
        if self.plan_editor_agent is None:
            raise AppError(500, "PLAN_EDITOR_UNAVAILABLE", "Plan editor is unavailable.")
        execution = await self.plan_editor_agent.execute(
            plan=context.plan,
            chat=context.chat,
            turn=context.turn,
            intent=context.decision.intent,
            operation=context.decision.operation or {},
            allow_locked_change=context.confirmed,
        )
        return self._persist_editor_execution(
            context.chat,
            context.turn,
            context.plan,
            execution,
        )

    def _persist_editor_execution(
        self,
        chat: TripChat,
        turn: TripChatMessage,
        plan: Plan,
        execution: Any,
    ) -> TripChatMessage:
        result = execution.result
        revision = _turn_base_revision(chat, turn) + 1
        diff = _plan_diff(
            plan,
            result.plan,
            result.affected_days,
            _turn_base_revision(chat, turn),
            revision,
        )
        diff["summary"] = execution.summary
        saved = self.repository.save_conversation_mutation(
            chat,
            turn=turn,
            user_content=turn.content,
            assistant_content=execution.summary,
            assistant_blocks=[{"type": "planDiff", **diff}],
            plan_payload=result.plan.model_dump(mode="json", by_alias=True),
            revision=revision,
        )
        return self.repository.update_turn(
            turn,
            status="completed",
            assistant_blocks=[{"type": "planDiff", **diff}],
            result_summary={
                "planRevision": saved.revision,
                "operationSummary": execution.summary,
                "affectedDays": result.affected_days,
                "warnings": execution.warnings,
            },
        )

    async def _create_plan(
        self,
        chat: TripChat,
        turn: TripChatMessage,
        images: list[ImageUploadPayload],
        planning_context: dict[str, object] | None = None,
    ) -> TripChatMessage:
        if (
            not chat.current_plan
            and _is_affirmative_start(turn.content)
            and _draft_has_no_destination(chat)
        ):
            message = (
                "Được, mình bắt đầu nhé. Bạn muốn đi tỉnh hoặc thành phố nào? "
                "Ví dụ: Hà Nội, Đà Nẵng hoặc Hội An."
            )
            return self._save_response(
                chat,
                turn,
                message,
                [{"type": "text", "text": message}],
            )

        planning_context = planning_context or {}
        urls = list(planning_context.get("urls") or [])
        initial_destination = str(
            planning_context.get("initial_destination") or "unspecified"
        )
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
                turn_id=_turn_lifecycle_id(turn),
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
        except AppError as exc:
            if exc.code == "TRIP_THEME_INPUT_INSUFFICIENT":
                raise AppError(
                    422,
                    "DESTINATION_OR_PLACE_REQUIRED",
                    (
                        "Mình chưa đủ dữ liệu để lập lịch trình. "
                        "Bạn hãy cho mình biết thành phố/tỉnh muốn đi "
                        "hoặc ít nhất một địa điểm cụ thể."
                    ),
                    {"nextStep": "Cung cấp điểm đến hoặc địa điểm bắt buộc."},
                ) from exc
            raise
        except RuntimeError as exc:
            raise AppError(
                502,
                "PLAN_GENERATION_FAILED",
                (
                    "Mình chưa thể tạo lịch trình lúc này. "
                    "Bạn hãy thử lại sau ít phút; lịch trình hiện tại chưa bị thay đổi."
                ),
            ) from exc
        if (
            result.current_plan is None
            and result.current_trip_intent is not None
            and not result.current_trip_intent.destination.strip()
        ):
            blocks = [{"type": "text", "text": "Bạn muốn đi du lịch ở đâu?"}]
            return self.repository.update_turn(
                turn,
                status="completed",
                assistant_blocks=blocks,
                result_summary={"planRevision": result.revision},
            )
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
        turn: TripChatMessage,
        plan: Plan,
        decision: ConversationDecision,
        *,
        allow_locked_change: bool = False,
    ) -> TripChatMessage:
        operation_model = PlanEditorOperation.model_validate(decision.operation or {})
        validate_operation_for_intent(decision.intent, operation_model)
        hydration_warnings: list[str] = []
        if self.plan_editor_agent is not None and decision.intent in {"add_place", "update_place"}:
            hydrated = self.plan_editor_agent.hydrate_candidate(chat, turn, operation_model)
            operation_model = hydrated.operation
            hydration_warnings = hydrated.warnings
        if decision.intent == "update_place" and operation_model.item_id:
            current_item = _find_item(plan, operation_model.item_id)
            if current_item is not None:
                operation_model = operation_model.model_copy(update={
                    "source_refs": _merge_string_values(
                        current_item.source_refs, operation_model.source_refs
                    ),
                    "candidate_entity_ids": _merge_string_values(
                        current_item.candidate_entity_ids,
                        operation_model.candidate_entity_ids,
                    ),
                    "source_provider": (
                        operation_model.source_provider or current_item.source_provider
                    ),
                    "identity_confidence": (
                        operation_model.identity_confidence or current_item.identity_confidence
                    ),
                    "source_import_node_id": (
                        operation_model.source_import_node_id
                        or current_item.source_import_node_id
                    ),
                })
        operation = operation_model.model_dump(
            mode="python", by_alias=True, exclude_none=True
        )
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
            display_name = (
                operation.get("name")
                or operation.get("candidateId")
                or operation.get("placeId")
            )
            result = await self.mutation_service.add_item(
                plan,
                AddItemRequest(
                    day=day,
                    name=str(display_name),
                    candidateId=operation.get("candidateId"),
                    placeId=operation.get("placeId"),
                    sourceRefs=operation.get("sourceRefs", []),
                    sourceImportNodeId=operation.get("sourceImportNodeId"),
                    candidateEntityIds=operation.get("candidateEntityIds", []),
                    sourceProvider=operation.get("sourceProvider"),
                    identityConfidence=operation.get("identityConfidence"),
                ),
            )
            summary = f"Đã thêm {display_name} vào Ngày {day}."
        elif decision.intent == "update_place":
            result = await self.mutation_service.update_item(
                plan,
                day,
                item_id,
                UpdateItemRequest(
                    name=operation.get("name"),
                    placeId=operation.get("placeId"),
                    sourceRefs=operation.get("sourceRefs"),
                    sourceImportNodeId=operation.get("sourceImportNodeId"),
                    candidateEntityIds=operation.get("candidateEntityIds"),
                    sourceProvider=operation.get("sourceProvider"),
                    identityConfidence=operation.get("identityConfidence"),
                ),
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

        revision = _turn_base_revision(chat, turn) + 1
        diff = _plan_diff(
            plan,
            result.plan,
            result.affected_days,
            _turn_base_revision(chat, turn),
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
                "warnings": hydration_warnings,
            },
        )

    def _undo(self, chat: TripChat, turn: TripChatMessage) -> TripChatMessage:
        base_revision = _turn_base_revision(chat, turn)
        if base_revision < 2:
            raise AppError(
                409,
                "UNDO_UNAVAILABLE",
                "Chưa có bản sửa đổi trước đó để hoàn tác.",
            )
        previous = self.repository.get_revision(chat.id, base_revision - 1)
        if previous is None:
            raise AppError(
                409,
                "UNDO_UNAVAILABLE",
                "Không tìm thấy snapshot để hoàn tác.",
            )
        plan = Plan.model_validate(previous.plan_payload)
        revision = _turn_base_revision(chat, turn) + 1
        diff = {
            "beforeRevision": base_revision,
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
        turn: TripChatMessage,
        error_code: str,
        message: str,
    ) -> TripChatMessage:
        try:
            self.repository.db.rollback()
        except Exception:
            logger.exception(
                "Failed to rollback database after conversation turn failure",
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn), "error_code": error_code},
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
                extra={"chat_id": chat.id, "turn_id": _turn_lifecycle_id(turn), "error_code": error_code},
            )
            raise

    def _save_response(
        self,
        chat: TripChat,
        turn: TripChatMessage,
        content: str,
        blocks: list[dict],
        result_summary: dict | None = None,
    ) -> TripChatMessage:
        self.repository.save_conversation_response(
            chat, turn, assistant_content=content, assistant_blocks=blocks
        )
        return self.repository.update_turn(
            turn,
            status="completed",
            assistant_blocks=blocks,
            result_summary={
                "planRevision": chat.revision,
                **(result_summary or {}),
            },
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


def _conversation_context(
    chat: TripChat,
    *,
    exclude_turn_id: str | None = None,
) -> dict:
    """Build a small, bounded context instead of sending the whole chat/plan.

    The current message is supplied separately. Only recent text turns and
    stable trip metadata are exposed to the LLM; attachments and content blocks
    are deliberately excluded.
    """
    recent_messages = [
        {"role": message.role, "content": message.content[:1000]}
        for message in list(chat.messages)[-8:]
        if message.role in {"assistant", "user"}
        and message.content.strip()
        and (
            exclude_turn_id is None
            or getattr(message, "turn_id", None) != exclude_turn_id
        )
    ]
    stored_context = chat.conversation_context or {}
    requirements = stored_context.get("requirements")
    lifecycle_messages = getattr(chat, "turns", None)
    if lifecycle_messages is None:
        lifecycle_messages = [
            message
            for message in chat.messages
            if getattr(message, "client_turn_id", None)
        ]
    action_history = [
        _turn_action_summary(turn)
        for turn in list(lifecycle_messages)[-8:]
        if turn.status != "queued"
        and (
            exclude_turn_id is None
            or _turn_lifecycle_id(turn) != exclude_turn_id
        )
    ]
    return {
        "phase": chat.conversation_phase,
        "destination": chat.destination,
        "planRevision": chat.revision,
        "currentTripIntent": getattr(chat, "current_trip_intent", None) or {},
        "requirements": requirements if isinstance(requirements, dict) else {},
        "recentMessages": recent_messages,
        "recentActionHistory": action_history,
        "informationFinderReferences": [
            reference
            for turn in list(lifecycle_messages)[-8:]
            for reference in _turn_information_references(turn)
        ],
    }


def _information_result_summary(result: Any) -> dict:
    """Persist only stable candidate references, never provider payloads."""
    if result is None:
        return {}
    candidates = list(getattr(result, "candidates", []) or [])
    if not candidates:
        return {
            "warnings": list(getattr(result, "warnings", []) or []),
        }
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    source_refs = list(
        dict.fromkeys(
            ref
            for candidate in candidates
            for ref in candidate.source_refs
        )
    )
    selected_ids = [
        candidate.candidate_id
        for candidate in candidates
        if bool(getattr(candidate, "selected", False))
    ]
    selected_place_ids = [
        candidate.place_id
        for candidate in candidates
        if bool(getattr(candidate, "selected", False)) and candidate.place_id
    ]
    warnings = list(getattr(result, "warnings", []) or [])
    if any(
        _candidate_is_stale(getattr(candidate, "fetched_at", None), datetime.now(UTC))
        for candidate in candidates
    ) and "candidate_data_stale" not in warnings:
        warnings.append("candidate_data_stale")
    return {
        "candidateIds": candidate_ids,
        "sourceRefs": source_refs,
        "selectedCandidateIds": selected_ids,
        "selectedPlaceIds": selected_place_ids,
        "warnings": warnings,
    }


def _turn_information_references(turn: TripChatMessage) -> list[dict]:
    summary = getattr(turn, "result_summary", None) or {}
    candidate_ids = summary.get("candidateIds")
    if not isinstance(candidate_ids, list):
        return []
    return [{
        "candidateIds": [str(value) for value in candidate_ids],
        "sourceRefs": [str(value) for value in summary.get("sourceRefs", []) if value],
        "selectedCandidateIds": [
            str(value) for value in summary.get("selectedCandidateIds", []) if value
        ],
        "selectedPlaceIds": [
            str(value) for value in summary.get("selectedPlaceIds", []) if value
        ],
    }]


def _candidate_is_stale(fetched_at: Any, now: datetime) -> bool:
    if not isinstance(fetched_at, datetime):
        return True
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)
    return fetched_at < now - timedelta(days=30)


def _merge_string_values(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


def _turn_lifecycle_id(turn: TripChatMessage) -> str:
    return str(
        getattr(turn, "lifecycle_id", None)
        or getattr(turn, "turn_id", None)
        or turn.id
    )


def _turn_action_summary(turn: TripChatMessage) -> dict:
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
        "turnId": _turn_lifecycle_id(turn),
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


def _is_affirmative_start(content: str) -> bool:
    normalized = " ".join(content.casefold().split()).strip()
    return normalized in {
        "có",
        "ok",
        "được",
        "được chứ",
        "ừ",
        "uh",
        "yes",
        "bắt đầu",
        "lên đi",
    }


def _draft_has_no_destination(chat: TripChat) -> bool:
    intent = getattr(chat, "current_trip_intent", None) or {}
    destination = intent.get("destination") if isinstance(intent, dict) else None
    return not destination or str(destination).strip().casefold() in {
        "unspecified",
        "chưa xác định",
    }


def _error_codes(report) -> set[str]:
    return {issue.code for issue in report.issues if issue.severity == "error"}


def _turn_base_revision(chat: TripChat, turn: TripChatMessage) -> int:
    """Use the revision observed when the turn was created for all writes."""
    base_revision = getattr(turn, "base_revision", None)
    return chat.revision if base_revision is None else base_revision


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
