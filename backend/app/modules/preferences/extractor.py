from __future__ import annotations

import json
import re
import unicodedata
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.integrations.llm.base import LLMClient
from app.modules.preferences.schema import (
    PreferenceDimension,
    PreferenceSignal,
    PreferenceSnapshot,
)


class PreferenceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dimension: PreferenceDimension
    value: str = Field(min_length=1, max_length=80)
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    scope: Literal["trip", "destination", "global"] = "global"
    destination: str | None = Field(default=None, max_length=255)
    explicitness: Literal["explicit", "inferred"] = "inferred"
    action: Literal["upsert", "none"] = "upsert"


class PreferenceObservationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    observations: list[PreferenceObservation] = Field(default_factory=list, max_length=8)


class PreferenceExtractor(Protocol):
    async def extract(
        self,
        message: str,
        *,
        destination: str | None = None,
    ) -> PreferenceObservationResult: ...


class StructuredLLMPreferenceExtractor:
    """Extract normalized traveler signals without granting write access."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def extract(
        self,
        message: str,
        *,
        destination: str | None = None,
    ) -> PreferenceObservationResult:
        payload = {
            "userMessage": message,
            "destination": destination,
        }
        try:
            raw = await self.llm.generate_structured_json(
                _SYSTEM_PROMPT,
                json.dumps(payload, ensure_ascii=False),
                response_schema=PreferenceObservationResult.model_json_schema(
                    by_alias=True
                ),
            )
            return PreferenceObservationResult.model_validate_json(raw)
        except (RuntimeError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise PreferenceExtractionError(
                "Preference observer did not return schema-valid output."
            ) from exc


class DeterministicPreferenceExtractor:
    """Narrow local/test adapter; production uses structured extraction."""

    async def extract(
        self,
        message: str,
        *,
        destination: str | None = None,
    ) -> PreferenceObservationResult:
        del destination
        normalized = _normalize_text(message)
        if not (_DISLIKE_PATTERN.search(normalized) and _CROWD_PATTERN.search(normalized)):
            return PreferenceObservationResult()
        return PreferenceObservationResult(
            observations=[
                PreferenceObservation(
                    dimension=PreferenceDimension.setting,
                    value="uncrowded",
                    score=1.0,
                    confidence=0.98,
                    scope="global",
                    explicitness="explicit",
                )
            ]
        )


class PreferencePolicy:
    minimum_confidence = 0.35
    sensitive_value_tokens = {
        "religion",
        "religious_belief",
        "medical_condition",
        "health_condition",
        "sexual_orientation",
        "political_view",
        "ethnicity",
        "disability",
        "income",
        "ton_giao",
        "suc_khoe",
        "khuyet_tat",
        "thu_nhap",
        "chinh_tri",
        "dan_toc",
    }

    def to_snapshot(
        self,
        result: PreferenceObservationResult,
    ) -> PreferenceSnapshot:
        signals: list[PreferenceSignal] = []
        for observation in result.observations:
            if observation.action != "upsert":
                continue
            # Trip-scoped instructions belong to the versioned TripIntent. The
            # long-term profile must never silently promote them to global.
            if observation.scope != "global":
                continue
            if observation.confidence < self.minimum_confidence:
                continue
            normalized_value = _normalize_value(observation.value)
            if self._is_sensitive(normalized_value):
                continue
            signals.append(
                PreferenceSignal(
                    dimension=observation.dimension,
                    value=normalized_value,
                    score=observation.score,
                    confidence=observation.confidence,
                    scope="global",
                    destination=None,
                    origin=observation.explicitness,
                    sourceTypes=["trip_chat"],
                )
            )
        return PreferenceSnapshot(signals=signals)

    def _is_sensitive(self, value: str) -> bool:
        return any(
            value == token
            or value.startswith(f"{token}_")
            or value.endswith(f"_{token}")
            for token in self.sensitive_value_tokens
        )


class PreferenceExtractionError(RuntimeError):
    pass


_DISLIKE_PATTERN = re.compile(
    r"\b(?:khong|cha|chang)\s+(?:he\s+)?(?:thich|muon)\b|"
    r"\b(?:ghet|tranh|ne)\b|"
    r"\b(?:do\s+not|don\s+t)\s+(?:like|want)\b|"
    r"\b(?:hate|avoid)\b"
)
_CROWD_PATTERN = re.compile(
    r"\b(?:noi\s+)?dong\s+(?:nguoi|nguo|duc)\b|"
    r"\bchen\s+chuc\b|\bxep\s+hang\b|"
    r"\bcrowd(?:ed|s)?\b"
)


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _normalize_value(value: str) -> str:
    return _normalize_text(value).replace(" ", "_")


_SYSTEM_PROMPT = """Bạn là PreferenceObserver của TravelPlanner.
Chỉ trích xuất sở thích du lịch thực sự được user thể hiện trong userMessage.
Một message có thể vừa hỏi thông tin vừa chứa nhiều preference; không phân loại
conversation intent và không trả lời user. Không suy luận trait nhạy cảm.
Phân biệt nhận xét tình huống (không lưu) với preference của user. Preference
nói rõ dùng explicit; suy đoán yếu dùng inferred hoặc bỏ qua. Chuẩn hóa value
thành token ngắn tiếng Anh snake_case. Ví dụ không thích nơi đông người trở
thành dimension=setting, value=uncrowded, score dương. Dùng scope=global khi
user nói như sở thích chung; scope=destination/trip chỉ khi họ giới hạn rõ.
Chỉ trả JSON khớp schema."""
