import asyncio
import time
from dataclasses import dataclass

from app.shared.llm.errors import (
    LlmAllKeysUnavailable,
    LlmConfigurationError,
    LlmUnauthorizedError,
)


@dataclass
class _KeyState:
    value: str
    blocked_until: float = 0.0
    in_flight: int = 0
    disabled: bool = False


@dataclass(frozen=True)
class GeminiKeyLease:
    index: int
    value: str


def parse_api_keys(api_key_value: str | None) -> list[str]:
    if not api_key_value:
        raise LlmConfigurationError(
            "GEMINI_API_KEY must contain at least one comma-separated API key."
        )
    keys: list[str] = []
    seen: set[str] = set()
    for raw_key in api_key_value.split(","):
        key = raw_key.strip()
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    if not keys:
        raise LlmConfigurationError(
            "GEMINI_API_KEY must contain at least one comma-separated API key."
        )
    return keys


class GeminiKeyPool:
    """Shared key leases so text, vision, and audio cannot reuse one key at once."""

    def __init__(
        self,
        api_key_value: str | None,
        *,
        default_cooldown_seconds: float = 60.0,
        per_key_max_in_flight: int = 1,
    ) -> None:
        if default_cooldown_seconds < 0:
            raise LlmConfigurationError("LLM key cooldown cannot be negative.")
        if per_key_max_in_flight < 1:
            raise LlmConfigurationError("Per-key concurrency must be at least one.")
        self._keys = [_KeyState(value=key) for key in parse_api_keys(api_key_value)]
        self.default_cooldown_seconds = default_cooldown_seconds
        self.per_key_max_in_flight = per_key_max_in_flight
        self._next_key_index = 0
        self._condition = asyncio.Condition()

    @property
    def key_count(self) -> int:
        return len(self._keys)

    async def acquire(self) -> GeminiKeyLease:
        while True:
            async with self._condition:
                now = time.monotonic()
                for offset in range(len(self._keys)):
                    index = (self._next_key_index + offset) % len(self._keys)
                    state = self._keys[index]
                    if (
                        not state.disabled
                        and state.blocked_until <= now
                        and state.in_flight < self.per_key_max_in_flight
                    ):
                        state.in_flight += 1
                        self._next_key_index = (index + 1) % len(self._keys)
                        return GeminiKeyLease(index=index, value=state.value)

                enabled = [state for state in self._keys if not state.disabled]
                if not enabled:
                    raise LlmUnauthorizedError("All Gemini API keys were rejected.")
                retry_delays = [
                    state.blocked_until - now
                    for state in enabled
                    if state.blocked_until > now
                    and state.in_flight < self.per_key_max_in_flight
                ]
                if retry_delays:
                    retry_after = max(0.0, min(retry_delays))
                    try:
                        await asyncio.wait_for(
                            self._condition.wait(), timeout=retry_after
                        )
                    except TimeoutError:
                        continue
                elif any(
                    state.in_flight >= self.per_key_max_in_flight
                    for state in enabled
                ):
                    await self._condition.wait()
                else:
                    raise LlmAllKeysUnavailable(self.default_cooldown_seconds)

    async def release(
        self,
        lease: GeminiKeyLease,
        *,
        cooldown_seconds: float = 0,
        disable: bool = False,
    ) -> None:
        async with self._condition:
            state = self._keys[lease.index]
            state.in_flight = max(0, state.in_flight - 1)
            state.disabled = state.disabled or disable
            if cooldown_seconds > 0:
                state.blocked_until = max(
                    state.blocked_until,
                    time.monotonic() + cooldown_seconds,
                )
            self._condition.notify_all()
