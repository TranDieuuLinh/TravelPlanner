"""Tests for the ConversationTurnService orchestration layer.

These tests focus on the pure helpers, validation paths, and the
predictable parts of ConversationTurnService that don't need a real
database. Heavier paths (execute, _mutate, _create_plan) are covered
by integration tests / manual testing.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import settings
from app.modules.plans.chat_model import TripChatMessage
from app.modules.plans.conversation_service import (
    ConversationTurnService,
    _clarification_blocks,
    _confirmation_preview,
    _conversation_context,
    _error_codes,
    _find_item,
    _plan_diff,
    _turn_action_summary,
)
from app.modules.plans.conversation_supervisor import (
    ConversationDecision,
)
from app.modules.plans.domain.entities import (
    CheckIssue,
    CheckReport,
    Plan,
    PlanDay,
    PlanItem,
    PlanKind,
    PlanStatus,
    TravelIntent,
    BudgetLevel,
    TravelPace,
)
from app.shared.errors import AppError


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _make_plan(*, item_specs: list[tuple[str, bool]] | None = None) -> Plan:
    items: list[PlanItem] = []
    for idx, (item_id, locked) in enumerate(item_specs or []):
        items.append(
            PlanItem(
                itemId=item_id,
                name=f"Place {idx}",
                timeWindow="morning",
                placeType="restaurant",
                timelineCategory="food",
                locked=locked,
            )
        )
    days = [
        PlanDay(day=1, theme="Day 1", items=items),
        PlanDay(day=2, theme="Day 2", items=[]),
    ]
    return Plan(
        id="plan-1",
        kind=PlanKind.main,
        status=PlanStatus.draft,
        title="Trip",
        destination="Đà Lạt",
        intent=TravelIntent(
            destination="Đà Lạt",
            days=2,
            budget=BudgetLevel.medium,
            travelStyle="local",
            pace=TravelPace.balanced,
        ),
        macroPlan={"title": "Trip", "destination": "Đà Lạt"},
        days=days,
    )


def _decision(
    *,
    intent: str = "travel_advice",
    confidence: float = 0.9,
    operation: dict[str, Any] | None = None,
    message: str | None = None,
    options: tuple[dict[str, str], ...] = (),
    requires_confirmation: bool = False,
) -> ConversationDecision:
    return ConversationDecision(
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,
        operation=operation,
        requires_confirmation=requires_confirmation,
        message=message,
        options=options,
    )


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


class TestFindItem:
    def test_returns_none_for_none_plan(self):
        # _find_item is only meaningful on a Plan; passing None is invalid
        # at the type level. We just ensure no crash with an empty plan.
        plan = _make_plan()
        assert _find_item(plan, "x") is None

    def test_finds_item(self):
        plan = _make_plan(item_specs=[("a", False), ("b", True)])
        item = _find_item(plan, "b")
        assert item is not None
        assert item.item_id == "b"
        assert item.locked is True

    def test_returns_none_when_missing(self):
        plan = _make_plan(item_specs=[("a", False)])
        assert _find_item(plan, "ghost") is None


class TestErrorCodes:
    def test_collects_only_error_severity(self):
        report = CheckReport(
            status="issues",
            issues=[
                CheckIssue(code="E1", severity="error", message="bad"),
                CheckIssue(code="W1", severity="warning", message="meh"),
                CheckIssue(code="E2", severity="error", message="worse"),
            ],
            summary="mixed",
        )
        assert _error_codes(report) == {"E1", "E2"}


class TestPlanDiff:
    def test_added_removed_updated_warnings(self):
        before = _make_plan(item_specs=[("a", False), ("b", False)])
        # After: removed b, kept a unchanged, added c, kept day 1+2
        after_items = [
            PlanItem(
                itemId="a", name="Place 0",
                timeWindow="morning", placeType="restaurant",
                timelineCategory="food",
            ),
            PlanItem(
                itemId="c", name="Place New",
                timeWindow="afternoon", placeType="restaurant",
                timelineCategory="food",
            ),
        ]
        after = before.model_copy(deep=True)
        after.days[0].items = after_items
        after.check_report = CheckReport(
            status="ok",
            issues=[CheckIssue(code="W1", severity="warning", message="mild")],
            summary="ok",
        )
        diff = _plan_diff(before, after, affected_days=[1], before_revision=1, after_revision=2)
        assert diff["beforeRevision"] == 1
        assert diff["afterRevision"] == 2
        assert diff["affectedDays"] == [1]
        assert "Place New" in diff["added"]
        assert diff["removed"] == ["Place 1"]
        # `a` is unchanged so updated is empty
        assert diff["updated"] == []
        assert diff["warnings"] == ["mild"]
        assert diff["undoAvailable"] is True

    def test_collects_warnings_only_when_check_report_present(self):
        before = _make_plan()
        after = before.model_copy(deep=True)
        diff = _plan_diff(before, after, [], 0, 0)
        assert diff["warnings"] == []
        assert diff["added"] == []
        assert diff["removed"] == []


class TestClarificationBlocks:
    def test_uses_fallback_message(self):
        decision = _decision(intent="clarify", message=None)
        blocks = _clarification_blocks(decision, None, "request")
        assert blocks[0]["type"] == "text"
        assert blocks[0]["text"] == "Bạn muốn làm gì tiếp?"

    def test_appends_options_when_present(self):
        decision = _decision(
            intent="clarify",
            message="Bạn muốn chọn?",
            options=({"label": "Tư vấn", "value": "Tư vấn"},),
        )
        blocks = _clarification_blocks(decision, None, "x")
        assert len(blocks) == 2
        assert blocks[1]["type"] == "optionSelector"
        assert blocks[1]["options"] == [{"label": "Tư vấn", "value": "Tư vấn"}]


class TestConfirmationPreview:
    def test_regenerate_with_plan_message(self):
        plan = _make_plan()
        text = _confirmation_preview(
            _decision(intent="regenerate_plan"), plan,
        )
        assert "tạo lại lịch trình" in text

    def test_locked_item_message(self):
        plan = _make_plan(item_specs=[("locked-1", True)])
        text = _confirmation_preview(
            _decision(
                intent="remove_place",
                operation={"type": "remove_place", "itemId": "locked-1", "day": 1},
            ),
            plan,
        )
        assert "Place 0" in text
        assert "khóa" in text

    def test_generic_message(self):
        plan = _make_plan()
        text = _confirmation_preview(
            _decision(
                intent="add_place",
                operation={"type": "add_place", "day": 1, "name": "x"},
            ),
            plan,
        )
        assert "phạm vi lớn" in text


class TestTurnActionSummary:
    def _turn(self, **kwargs) -> TripChatMessage:
        return TripChatMessage(
            id="t1", chat_id="c1", role="user", sequence=1,
            turn_id="t1", message_kind="turn_request",
            client_turn_id="ct-1", content="hi", attachment_names=[],
            base_revision=0, **kwargs,
        )

    def test_status_to_outcome_mapping(self):
        for status, expected in [
            ("completed", "success"),
            ("failed", "failed"),
            ("cancelled", "rejected"),
            ("awaiting_confirmation", "awaiting_confirmation"),
            ("queued", "queued"),
            ("classifying", "in_progress"),
            ("executing", "in_progress"),
            ("unknown_state", "unknown"),
        ]:
            t = self._turn(status=status)
            summary = _turn_action_summary(t)
            assert summary["outcome"] == expected, (status, summary)

    def test_collects_error_code_and_message(self):
        t = self._turn(
            status="failed",
            error_code="SUPERVISOR_DECISION_FAILED",
            error_message="Couldn't process",
        )
        summary = _turn_action_summary(t)
        assert summary["errorCode"] == "SUPERVISOR_DECISION_FAILED"
        assert summary["errorMessage"] == "Couldn't process"

    def test_truncates_long_error_message(self):
        t = self._turn(
            status="failed",
            error_code="E",
            error_message="x" * 1000,
        )
        summary = _turn_action_summary(t)
        assert len(summary["errorMessage"]) == 300

    def test_safe_operation_filters_unwanted_keys(self):
        t = self._turn(
            status="completed",
            intent="add_place",
            proposed_operations=[{
                "type": "add_place",
                "itemId": "x",
                "name": "Cà phê",
                "day": 1,
                "toDay": None,  # explicitly null -> skipped
                "junk": "ignored",  # not in keep list -> skipped
            }],
            result_summary={"planRevision": 3},
        )
        summary = _turn_action_summary(t)
        op = summary["operation"]
        # keep-list is (type, itemId, day, toDay, name)
        assert op == {"type": "add_place", "itemId": "x", "name": "Cà phê", "day": 1}
        assert summary["planRevision"] == 3


class TestConversationContext:
    def _chat(self) -> SimpleNamespace:
        return SimpleNamespace(
            id="c1",
            messages=[
                SimpleNamespace(role="user", content="  hello  "),
                SimpleNamespace(role="assistant", content="hi back"),
                SimpleNamespace(role="system", content="sys"),  # filtered out
                SimpleNamespace(role="user", content=""),  # filtered out
            ],
            conversation_context={"requirements": {"theme": "food"}},
            conversation_phase="exploration",
            destination="Đà Lạt",
            revision=2,
            turns=[
                SimpleNamespace(
                    status="completed", id="t1",
                    intent=None, proposed_operations=None, result_summary=None,
                    error_code=None, error_message=None,
                ),
                SimpleNamespace(
                    status="queued", id="t2",
                    intent=None, proposed_operations=None, result_summary=None,
                    error_code=None, error_message=None,
                ),
            ],
        )

    def test_filters_queued_turns(self):
        ctx = _conversation_context(self._chat())
        assert ctx["phase"] == "exploration"
        assert ctx["destination"] == "Đà Lạt"
        assert ctx["planRevision"] == 2
        assert ctx["requirements"] == {"theme": "food"}
        # The service trims whitespace at the filter step but preserves the
        # raw content in the message dict, so we check role/content presence.
        assert len(ctx["recentMessages"]) == 2
        assert all("role" in m and "content" in m for m in ctx["recentMessages"])
        assert all(m["role"] in {"user", "assistant"} for m in ctx["recentMessages"])
        assert len(ctx["recentActionHistory"]) == 1  # only completed


# ---------------------------------------------------------------------------
# ConversationTurnService.start / cancel (no DB, no LLM)
# ---------------------------------------------------------------------------


class _FakeRepo:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.cancel_calls: list[Any] = []

    def get(self, chat_id, user_id):
        raise NotImplementedError

    def get_turn(self, chat_id, user_id, turn_id):
        raise NotImplementedError

    def create_turn(self, chat, *, client_turn_id, content, attachment_names, expected_revision):
        self.created.append(
            {
                "chat": chat,
                "client_turn_id": client_turn_id,
                "content": content,
                "attachment_names": attachment_names,
                "expected_revision": expected_revision,
            }
        )
        return SimpleNamespace(id="turn-new")

    def update_turn(self, turn, **kwargs):
        self.cancel_calls.append((turn, kwargs))
        return SimpleNamespace(**{**vars(turn), **kwargs}) if hasattr(turn, "__dict__") else turn


class _FakeTripChatService:
    pass


class _FakeMutationService:
    pass


def _make_service(repo: _FakeRepo | None = None) -> ConversationTurnService:
    return ConversationTurnService(
        repository=repo or _FakeRepo(),
        trip_chat_service=_FakeTripChatService(),  # type: ignore[arg-type]
        mutation_service=_FakeMutationService(),  # type: ignore[arg-type]
        supervisor=None,  # never used in start/cancel
    )


class TestStartValidation:
    def test_blank_content_raises(self):
        service = _make_service()
        user = SimpleNamespace(id=1)
        with pytest.raises(AppError) as exc:
            service.start("chat-1", user, "   ", expected_revision=1)
        assert exc.value.code == "VALIDATION_ERROR"
        assert exc.value.status_code == 422

    def test_blank_content_with_no_trim_raises(self):
        service = _make_service()
        user = SimpleNamespace(id=1)
        with pytest.raises(AppError):
            service.start("chat-1", user, "", expected_revision=1)

    def test_valid_content_proceeds_to_repo(self):
        repo = _FakeRepo()
        service = _make_service(repo)
        chat = SimpleNamespace(id="chat-1", user_id=1)
        repo.get = lambda *a, **k: chat  # type: ignore[assignment]
        user = SimpleNamespace(id=1)
        turn = service.start(
            "chat-1", user, "  thêm Phở Bò  ", expected_revision=3,
            client_turn_id="client-1", attachment_names=["a.png"],
        )
        assert turn.id == "turn-new"
        assert len(repo.created) == 1
        created = repo.created[0]
        assert created["content"] == "thêm Phở Bò"
        assert created["client_turn_id"] == "client-1"
        assert created["attachment_names"] == ["a.png"]
        assert created["expected_revision"] == 3

    def test_generates_client_turn_id_when_missing(self):
        repo = _FakeRepo()
        service = _make_service(repo)
        chat = SimpleNamespace(id="chat-1", user_id=1)
        repo.get = lambda *a, **k: chat  # type: ignore[assignment]
        user = SimpleNamespace(id=1)
        service.start("chat-1", user, "hi", expected_revision=0)
        cid = repo.created[0]["client_turn_id"]
        assert isinstance(cid, str)
        assert len(cid) > 0


# ---------------------------------------------------------------------------
# cancel()
# ---------------------------------------------------------------------------


class TestCancel:
    def _service_with(self, turn):
        repo = _FakeRepo()
        repo.get_turn = lambda *a, **k: turn  # type: ignore[assignment]
        return _make_service(repo), repo

    def test_cancelled_turn_raises(self):
        turn = SimpleNamespace(id="t1", status="completed")
        service, _ = self._service_with(turn)
        with pytest.raises(AppError) as exc:
            service.cancel("chat-1", SimpleNamespace(id=1), "t1")
        assert exc.value.code == "TURN_ALREADY_COMPLETED"
        assert exc.value.status_code == 409

    def test_pending_turn_cancels_with_message(self):
        turn = SimpleNamespace(id="t1", status="awaiting_confirmation")
        service, repo = self._service_with(turn)
        service.cancel("chat-1", SimpleNamespace(id=1), "t1")
        # service returns whatever update_turn returns
        assert repo.cancel_calls and repo.cancel_calls[0][1]["status"] == "cancelled"
        assert repo.cancel_calls[0][1]["assistant_blocks"] == [
            {"type": "text", "text": "Đã hủy thao tác; lịch trình không thay đổi."}
        ]


# ---------------------------------------------------------------------------
# confirm() and stale recovery
# ---------------------------------------------------------------------------


class _ChatRepo:
    def __init__(self, chat):
        self.chat = chat

    def get(self, chat_id, user_id):
        return self.chat


class TestConfirm:
    def _make_chat(self):
        return SimpleNamespace(
            id="chat-1",
            user_id=1,
            revision=3,
            current_plan={
                "id": "plan-1",
                "kind": "main",
                "status": "draft",
                "title": "Trip",
                "destination": "Đà Lạt",
                "intent": {
                    "destination": "Đà Lạt",
                    "days": 2,
                    "budget": "medium",
                    "travelStyle": "local",
                    "pace": "balanced",
                },
                "macroPlan": {"title": "Trip", "destination": "Đà Lạt"},
                "days": [
                    {"day": 1, "theme": "Day 1", "items": [], "transportLegs": []},
                    {"day": 2, "theme": "Day 2", "items": [], "transportLegs": []},
                ],
            },
        )

    def test_confirm_only_allows_awaiting_confirmation(self):
        repo = _FakeRepo()
        repo.get_turn = lambda *a, **k: SimpleNamespace(
            id="t1", status="completed", base_revision=3
        )
        service = _make_service(repo)
        with pytest.raises(AppError) as exc:
            import asyncio
            asyncio.run(service.confirm("chat-1", SimpleNamespace(id=1), "t1"))
        assert exc.value.code == "TURN_NOT_PENDING"
        assert exc.value.status_code == 409

    def test_confirm_rejects_stale_revision(self):
        chat = self._make_chat()
        repo = _ChatRepo(chat)
        repo.get_turn = lambda *a, **k: SimpleNamespace(
            id="t1",
            status="awaiting_confirmation",
            base_revision=2,
            intent="add_place",
            confidence=0.9,
            proposed_operations=[{"type": "add_place", "day": 1, "name": "Phở"}],
            content="thêm phở",
        )
        service = _make_service(repo)
        with pytest.raises(AppError) as exc:
            import asyncio
            asyncio.run(service.confirm("chat-1", SimpleNamespace(id=1), "t1"))
        assert exc.value.code == "VERSION_CONFLICT"


class TestStaleRecovery:
    def test_recover_invokes_repo_when_available(self):
        seen: dict[str, Any] = {}

        class _Repo(_FakeRepo):
            def expire_stale_turns(self, chat_id, ttl):
                seen["chat_id"] = chat_id
                seen["ttl"] = ttl
                return ["t-old"]

        repo = _Repo()
        repo.get_turn = lambda *a, **k: SimpleNamespace(id="t1")  # type: ignore[assignment]
        service = _make_service(repo)
        service.get_turn("chat-1", SimpleNamespace(id=1), "t1")
        assert seen["chat_id"] == "chat-1"
        assert seen["ttl"] == settings.conversation_turn_stale_after_seconds

    def test_recover_swallows_repo_missing(self):
        repo = _FakeRepo()
        repo.get_turn = lambda *a, **k: SimpleNamespace(id="t1")  # type: ignore[assignment]
        # No expire_stale_turns attribute -> no-op, must not raise.
        service = _make_service(repo)
        service.get_turn("chat-1", SimpleNamespace(id=1), "t1")  # should not raise
