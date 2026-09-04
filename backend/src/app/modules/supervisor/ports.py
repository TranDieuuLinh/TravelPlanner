from typing import Protocol

from app.modules.supervisor.contract import ClassifierResult, ComposedAnswer, SupervisorInput


class IntentClassifier(Protocol):
    async def classify(self, payload: SupervisorInput) -> ClassifierResult:
        """Classify a request that did not match a deterministic rule."""


class ResponseComposer(Protocol):
    async def compose(self, payload: dict) -> ComposedAnswer:
        """Compose the final user-facing response from agent output."""
