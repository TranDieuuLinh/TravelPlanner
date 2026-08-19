from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from app.shared.observability.ports import (
    ObservabilityClient,
    ObservabilityGeneration,
    ObservabilitySpan,
    ObservabilityTrace,
)


class NoOpGeneration(ObservabilityGeneration):
    def end(
        self,
        *,
        output: Any = None,
        usage: dict[str, int] | None = None,
        level: Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"] | None = None,
        status_message: str | None = None,
        end_time: datetime | None = None,
    ) -> None:
        pass


class NoOpSpan(ObservabilitySpan):
    def span(self, *, id: str | None = None, name: str, input: Any = None,
             metadata: dict[str, Any] | None = None,
             start_time: datetime | None = None) -> ObservabilitySpan:
        return self

    def generation(self, *, id: str | None = None, name: str,
                   model: str | None = None,
                   model_parameters: dict[str, Any] | None = None,
                   input: Any = None,
                   metadata: dict[str, Any] | None = None,
                   start_time: datetime | None = None) -> ObservabilityGeneration:
        return NoOpGeneration()

    def end(self, *, output: Any = None,
            level: Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"] | None = None,
            status_message: str | None = None,
            end_time: datetime | None = None) -> None:
        pass


class NoOpTrace(ObservabilityTrace):
    def __init__(self, trace_id: str = "") -> None:
        self._trace_id = trace_id

    @property
    def id(self) -> str:
        return self._trace_id

    def span(self, *, id: str | None = None, name: str, input: Any = None,
             metadata: dict[str, Any] | None = None,
             start_time: datetime | None = None) -> ObservabilitySpan:
        return NoOpSpan()

    def generation(self, *, id: str | None = None, name: str,
                   model: str | None = None,
                   model_parameters: dict[str, Any] | None = None,
                   input: Any = None,
                   metadata: dict[str, Any] | None = None,
                   start_time: datetime | None = None) -> ObservabilityGeneration:
        return NoOpGeneration()

    def update(self, *, output: Any = None,
               metadata: dict[str, Any] | None = None,
               tags: list[str] | None = None) -> None:
        pass

    def end(self) -> None:
        pass


class NoOpObservabilityClient(ObservabilityClient):
    @property
    def is_enabled(self) -> bool:
        return False

    def create_trace(self, *, trace_id: str, name: str,
                     session_id: str | None = None,
                     user_id: str | None = None,
                     metadata: dict[str, Any] | None = None,
                     tags: list[str] | None = None,
                     input_data: Any = None,
                     release: str | None = None,
                     environment: str | None = None) -> ObservabilityTrace:
        return NoOpTrace(trace_id)

    async def flush(self, timeout_seconds: float | None = None) -> None:
        pass

    async def shutdown(self, timeout_seconds: float | None = None) -> None:
        pass
