from app.modules.supervisor.contract import (
    ClassifierResult,
    SupervisorDecision,
    SupervisorInput,
)
from app.modules.supervisor.errors import SupervisorClassificationError
from app.modules.supervisor.ports import IntentClassifier
from app.modules.supervisor.rules import (
    deterministic_decision,
    fallback_decision,
)


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
        # Các rule biên an toàn của Supervisor phải thắng dự đoán LLM:
        # đặc biệt là câu hỏi kiến thức và yêu cầu chỉnh sửa thiếu trạng thái.
        deterministic = deterministic_decision(payload)
        if deterministic is not None:
            return deterministic
        if self._classifier is None:
            return fallback_decision(payload)
        try:
            result = await self._classifier.classify(payload)
            return self._accept_classifier_result(payload, result)
        except Exception:
            if not self._fallback_enabled:
                raise SupervisorClassificationError(
                    "Supervisor intent classification failed and fallback is disabled."
                ) from None
            return fallback_decision(
                payload,
                warning="LLM intent classification failed; deterministic fallback used.",
            )

    def _accept_classifier_result(
        self, payload: SupervisorInput, result: ClassifierResult
    ) -> SupervisorDecision:
        if result.confidence < self._confidence_threshold:
            if not self._fallback_enabled:
                raise SupervisorClassificationError(
                    "Supervisor intent confidence is below the configured threshold."
                )
            return fallback_decision(
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
            return fallback_decision(
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
