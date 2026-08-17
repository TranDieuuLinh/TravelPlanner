from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable


@runtime_checkable
class ObservabilityGeneration(Protocol):
    def end(
        self,
        *,
        output: Any = None,
        usage: dict[str, int] | None = None,
        level: Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"] | None = None,
        status_message: str | None = None,
        end_time: datetime | None = None,
    ) -> None:
        """Complete the generation observation."""


@runtime_checkable
class ObservabilitySpan(Protocol):
    def span(
        self,
        *,
        id: str | None = None,
        name: str,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        start_time: datetime | None = None,
    ) -> ObservabilitySpan:
        """Create a child span."""

    def generation(
        self,
        *,
        id: str | None = None,
        name: str,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        start_time: datetime | None = None,
    ) -> ObservabilityGeneration:
        """Create a child LLM generation."""

    def end(
        self,
        *,
        output: Any = None,
        level: Literal["DEBUG", "DEFAULT", "WARNING", "ERROR"] | None = None,
        status_message: str | None = None,
        end_time: datetime | None = None,
    ) -> None:
        """Complete the span observation."""


@runtime_checkable
class ObservabilityTrace(Protocol):
    @property
    def id(self) -> str:
        """Return the trace identifier."""

    def span(
        self,
        *,
        id: str | None = None,
        name: str,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        start_time: datetime | None = None,
    ) -> ObservabilitySpan:
        """Create a root span under the trace."""

    def generation(
        self,
        *,
        id: str | None = None,
        name: str,
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        start_time: datetime | None = None,
    ) -> ObservabilityGeneration:
        """Create an LLM generation under the trace."""

    def update(
        self,
        *,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Update trace level attributes."""

    def end(self) -> None:
        """Complete the root observation when the provider requires it."""


@runtime_checkable
class ObservabilityClient(Protocol):
    @property
    def is_enabled(self) -> bool:
        """Whether the client is actively recording."""

    def create_trace(
        self,
        *,
        trace_id: str,
        name: str,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        input_data: Any = None,
        release: str | None = None,
        environment: str | None = None,
    ) -> ObservabilityTrace:
        """Create or initialize a trace."""

    async def flush(self, timeout_seconds: float | None = None) -> None:
        """Flush pending observations."""

    async def shutdown(self, timeout_seconds: float | None = None) -> None:
        """Cleanly shutdown the client and flush buffers."""
