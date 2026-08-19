from app.modules.supervisor.contract import (
    ClassifierResult,
    SupervisorDecision,
    SupervisorInput,
)
from app.modules.supervisor.errors import SupervisorClassificationError
from app.modules.supervisor.fallback import build_fallback_decision
from app.modules.supervisor.ports import IntentClassifier


class SupervisorService:
    def __init__(
        self,
        classifier: IntentClassifier | None = None,
        *,
        fallback_enabled: bool = True,
        confidence_threshold: float = 0.65,
    ) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("Supervisor confidence threshold must be between 0 and 1.")
        self._classifier = classifier
        self._fallback_enabled = fallback_enabled
        self._confidence_threshold = confidence_threshold

    async def decide(self, payload: SupervisorInput) -> SupervisorDecision:
        if payload.clarification_required:
            places_str = (
                ", ".join(payload.mentioned_places[:3])
                if payload.mentioned_places
                else "các địa điểm đã đề cập"
            )
            question = f"Bạn đang muốn tham chiếu đến địa điểm nào trong {places_str}?"
            return SupervisorDecision(
                route="finish",
                confidence=1.0,
                reason="Ambiguous reference requires clarification from user.",
                clarification_question=question,
                response=question,
            )

        if self._classifier is None:
            return build_fallback_decision(
                payload,
                warning="Supervisor LLM chưa được cấu hình."
            )
        try:
            result = await self._classifier.classify(payload)
            return self._accept_classifier_result(payload, result)
        except Exception:
            if not self._fallback_enabled:
                raise SupervisorClassificationError(
                    "Supervisor intent classification failed and fallback is disabled."
                ) from None
            return build_fallback_decision(
                payload,
                warning="Không thể gọi Supervisor LLM; đã dùng câu hỏi làm rõ.",
            )

    def _accept_classifier_result(
        self, payload: SupervisorInput, result: ClassifierResult
    ) -> SupervisorDecision:
        if result.confidence < self._confidence_threshold:
            if not self._fallback_enabled:
                raise SupervisorClassificationError(
                    "Supervisor intent confidence is below the configured threshold."
                )
            return build_fallback_decision(
                payload,
                warning="LLM intent confidence was below the configured threshold.",
            )
        if result.route == "plan_editor" and not (
            payload.has_itinerary and payload.has_edit_operation
        ):
            if not self._fallback_enabled:
                raise SupervisorClassificationError(
                    "Supervisor returned plan_editor without required structured state."
                )
            return build_fallback_decision(
                payload,
                warning="LLM plan_editor result lacked required structured state.",
            )
        if result.route == "finish" and not result.response:
            raise SupervisorClassificationError(
                "Supervisor finish result did not include a user response."
            )
        decision = SupervisorDecision(
            route=result.route,
            confidence=result.confidence,
            reason={
                "explorer": "Structured classifier selected trip planning.",
                "information_finder": "Structured classifier selected travel information.",
                "plan_editor": "Structured classifier selected a structured edit.",
                "finish": "Structured classifier selected a completed response.",
            }[result.route],
            response=result.response if result.route == "finish" else None,
        )
        return decision
