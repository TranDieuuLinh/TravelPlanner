import asyncio

import pytest

from app.modules.supervisor.contract import ClassifierResult, SupervisorInput
from app.modules.supervisor.errors import SupervisorClassificationError
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


@pytest.mark.parametrize(
    ("message", "route"),
    [
        ("Xin chào, bạn là ai vậy?", "finish"),
        ("Tôi muốn biết thêm về Hà Nội", "information_finder"),
        ("Lập kế hoạch Đà Nẵng 3 ngày", "explorer"),
        ("Hoàn Kiếm Lake thì sao?", "information_finder"),
        ("Đổi kế hoạch trên sang Nha Trang", "explorer"),
    ],
)
def test_every_intent_is_delegated_to_the_llm(message, route):
    classifier = FakeClassifier(
        ClassifierResult(
            route=route,
            confidence=0.95,
            reason="LLM classified the user request",
            response="Penguin xin chào!" if route == "finish" else None,
        )
    )
    decision = decide(
        SupervisorService(classifier),
        message,
        conversation_context=["Tôi muốn biết thêm về Hà Nội."],
    )
    assert decision.route == route
    assert classifier.calls == 1


def test_plan_editor_requires_structured_state_after_llm_classification():
    decision = decide(
        SupervisorService(
            FakeClassifier(
                ClassifierResult(route="plan_editor", confidence=0.99, reason="edit")
            )
        ),
        "Tôi muốn chỉnh sửa lịch trình",
    )
    assert decision.route == "finish"
    assert decision.clarification_question


def test_natural_plan_edit_is_validated_and_accepted_from_one_classifier_call():
    classifier = FakeClassifier(
        ClassifierResult(
            route="plan_editor",
            confidence=0.99,
            reason="edit",
            plan_edit={
                "action": "update",
                "confidence": 0.99,
                "day": 1,
                "itemId": "lake",
                "item": {"durationMinutes": 90},
                "response": "Đã đổi thành 90 phút.",
            },
        )
    )
    decision = decide(
        SupervisorService(classifier),
        "Cho Hồ Gươm 90 phút",
        current_plan={
            "days": [{"day": 1, "items": [{"itemId": "lake", "name": "Hồ Gươm"}]}]
        },
    )

    assert decision.route == "plan_editor"
    assert decision.plan_edit.item.duration_minutes == 90
    assert classifier.calls == 1


def test_llm_finish_response_is_preserved():
    response = "Xin chào, mình là Penguin."
    decision = decide(
        SupervisorService(
            FakeClassifier(
                ClassifierResult(
                    route="finish", confidence=0.9, reason="greeting", response=response
                )
            )
        ),
        "Xin chào",
    )
    assert decision.response == response


def test_llm_failure_asks_for_clarification_instead_of_explorer():
    decision = decide(
        SupervisorService(FakeClassifier(error=TimeoutError())),
        "Một yêu cầu chưa rõ",
    )
    assert decision.route == "finish"
    assert decision.clarification_question
    assert decision.warnings


def test_llm_failure_can_be_disabled():
    with pytest.raises(SupervisorClassificationError, match="fallback is disabled"):
        decide(
            SupervisorService(
                FakeClassifier(error=TimeoutError()), fallback_enabled=False
            ),
            "Một yêu cầu chưa rõ",
        )


def test_low_confidence_llm_result_asks_for_clarification():
    decision = decide(
        SupervisorService(
            FakeClassifier(
                ClassifierResult(route="explorer", confidence=0.2, reason="uncertain")
            )
        ),
        "Một yêu cầu chưa rõ",
    )
    assert decision.route == "finish"
    assert decision.clarification_question


def test_unconfigured_llm_never_guesses_trip_intent():
    decision = decide(
        SupervisorService(classifier=None),
        "đi Hà Nội 2 ngày",
    )

    assert decision.route == "finish"
    assert decision.clarification_question
    assert decision.warnings == ["Supervisor LLM chưa được cấu hình."]


def test_pending_review_patch_is_accepted_only_from_llm_output():
    classifier = FakeClassifier(
        ClassifierResult(
            route="explorer",
            confidence=0.99,
            reason="User requested the most luxurious budget tier.",
            tripContextPatch={
                "budget": {
                    "operation": "set",
                    "value": {"level": "high", "currency": "VND"},
                }
            },
        )
    )

    decision = decide(
        SupervisorService(classifier),
        "tui muốn đi giàu sang mắc nhất vô lên plan dì",
        pending_review_kind="defaults_proposed",
        pending_review_fields=["budget"],
    )

    assert decision.route == "explorer"
    assert decision.trip_context_patch.budget.value.level == "high"
    assert decision.trip_context_patch.input_adm is None
