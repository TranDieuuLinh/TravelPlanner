import asyncio

import pytest

from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.errors import SupervisorClassificationError
from app.modules.supervisor.rules import (
    information_rule,
    planning_rule,
    structured_edit_rule,
)
from app.modules.supervisor.service import SupervisorService


class FakeClassifier:
    def __init__(
        self, result: ClassifierResult | None = None, error: Exception | None = None
    ):
        self.result = result
        self.error = error
        self.calls = 0

    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        self.calls += 1
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def decide(service: SupervisorService, message: str, **flags):
    return asyncio.run(service.decide(SupervisorInput(message=message, **flags)))


def test_configured_classifier_handles_structured_edit():
    classifier = FakeClassifier(
        ClassifierResult(route="plan_editor", confidence=1, reason="Structured edit")
    )
    decision = decide(
        SupervisorService(classifier),
        "Lập kế hoạch rồi thêm điểm đến",
        has_itinerary=True,
        has_edit_operation=True,
    )
    assert decision.route == "plan_editor"
    assert classifier.calls == 1


def test_edit_operation_without_itinerary_never_routes_to_editor():
    decision = decide(
        SupervisorService(), "Cập nhật lịch trình", has_edit_operation=True
    )
    assert decision.route == "finish"
    assert decision.clarification_question


def test_existing_itinerary_with_information_question_routes_to_information():
    decision = decide(
        SupervisorService(), "Giờ mở cửa và giá vé bảo tàng?", has_itinerary=True
    )
    assert decision.route == "information_finder"


@pytest.mark.parametrize(
    "message",
    ["Lập kế hoạch Đà Nẵng 3 ngày", "Plan a three-day trip to Kyoto"],
)
def test_planning_requests_route_to_explorer(message):
    assert decide(SupervisorService(), message).route == "explorer"


@pytest.mark.parametrize(
    "message",
    ["Giá vé và giờ mở cửa bảo tàng?", "What is the ticket price and opening hours?"],
)
def test_information_requests_route_to_information_finder(message):
    assert decide(SupervisorService(), message).route == "information_finder"


def test_greeting_has_meaningful_finish_response():
    decision = decide(SupervisorService(), "Xin chào")
    assert decision.route == "finish"
    assert decision.response


def test_out_of_scope_request_finishes_honestly():
    decision = decide(SupervisorService(), "Write a poem about databases")
    assert decision.route == "finish"
    assert "travel" in decision.response.casefold()


def test_narrow_rules_avoid_common_substring_false_positives():
    assert information_rule(SupervisorInput(message="The address is useful"))
    assert planning_rule(
        SupervisorInput(message="What should I do in Da Nang for 3 days")
    )
    assert structured_edit_rule(SupervisorInput(message="addendum")) is None
    assert decide(SupervisorService(), "The addendum is ready").route == "explorer"


def test_multi_intent_uses_planning_action_after_structured_precedence():
    decision = decide(SupervisorService(), "Lập kế hoạch Đà Nẵng và cho biết giá vé")
    assert decision.route == "explorer"


def test_valid_llm_result_is_parsed_and_used_for_ambiguous_message():
    classifier = FakeClassifier(
        ClassifierResult(
            route="information_finder", confidence=0.9, reason="A focused fact request"
        )
    )
    decision = decide(SupervisorService(classifier), "Can you help with this place?")
    assert decision.route == "information_finder"
    assert classifier.calls == 1


def test_configured_classifier_runs_before_free_text_rules():
    classifier = FakeClassifier(
        ClassifierResult(
            route="information_finder",
            confidence=0.95,
            reason="Historical destination information",
        )
    )
    decision = decide(
        SupervisorService(classifier), "Cho tôi lịch sửa Hồ Chí Minh"
    )
    assert decision.route == "information_finder"
    assert classifier.calls == 1


def test_contextual_follow_up_uses_conversation_context():
    decision = decide(
        SupervisorService(),
        "Còn chỗ này thì sao?",
        conversation_context=["Tôi muốn biết thêm về Hải Phòng."],
    )
    assert decision.route == "information_finder"


def test_destination_follow_up_without_context_is_still_information():
    assert decide(SupervisorService(), "Còn Hà Nội thì sao.").route == (
        "information_finder"
    )


def test_llm_finish_response_uses_the_users_language():
    classifier = FakeClassifier(
        ClassifierResult(
            route="finish",
            confidence=0.9,
            reason="Meta question",
            response="Tôi là trợ lý lập kế hoạch du lịch của bạn.",
        )
    )
    decision = decide(SupervisorService(classifier), "Bạn là ai vậy?")
    assert decision.route == "finish"
    assert decision.response == "Tôi là trợ lý lập kế hoạch du lịch của bạn."


def test_llm_failure_uses_safe_fallback_when_enabled():
    decision = decide(
        SupervisorService(FakeClassifier(error=TimeoutError())),
        "Can you help with this place?",
    )
    assert decision.route == "explorer"
    assert decision.warnings
    assert "completed" not in (decision.response or "").casefold()


def test_llm_failure_is_explicit_when_fallback_disabled():
    with pytest.raises(SupervisorClassificationError, match="fallback is disabled"):
        decide(
            SupervisorService(
                FakeClassifier(error=TimeoutError()), fallback_enabled=False
            ),
            "Can you help with this place?",
        )


def test_low_confidence_llm_result_falls_back():
    decision = decide(
        SupervisorService(
            FakeClassifier(
                ClassifierResult(route="finish", confidence=0.2, reason="uncertain")
            )
        ),
        "Can you help with this place?",
    )
    assert decision.route == "explorer"
    assert decision.warnings


def test_llm_plan_editor_result_is_rejected_without_both_preconditions():
    decision = decide(
        SupervisorService(
            FakeClassifier(
                ClassifierResult(route="plan_editor", confidence=0.99, reason="edit")
            )
        ),
        "Can you help with this place?",
    )
    assert decision.route == "explorer"
    assert "structured state" in decision.warnings[0]
