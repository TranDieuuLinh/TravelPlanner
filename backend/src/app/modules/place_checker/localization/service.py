from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict

from app.modules.place_checker.localization.contract import (
    SourceNoteTranslationRequest,
)
from app.modules.place_checker.output_contract import PlaceCheckerResult
from app.modules.place_checker.planning.notes import select_planner_source_note
from app.modules.place_checker.ports import SourceNoteTranslator

logger = logging.getLogger(__name__)

_VIETNAMESE_CHARACTERS = re.compile(
    r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
    re.IGNORECASE,
)
_VIETNAMESE_WORDS = {
    "bảo",
    "chủ",
    "chùa",
    "có",
    "của",
    "đây",
    "địa",
    "điểm",
    "được",
    "giờ",
    "hồ",
    "khu",
    "là",
    "lăng",
    "một",
    "nơi",
    "quảng",
    "tại",
    "tham",
    "thành",
    "tích",
    "trường",
    "việt",
}
_ENGLISH_WORDS = {
    "and",
    "body",
    "declared",
    "from",
    "grand",
    "has",
    "his",
    "independence",
    "is",
    "lies",
    "located",
    "now",
    "place",
    "plaza",
    "square",
    "the",
    "this",
    "was",
    "where",
    "with",
}
_WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)


def is_probably_vietnamese(value: str) -> bool:
    """Conservatively accept text that is suitable for the Vietnamese UI."""

    words = {word.casefold() for word in _WORD_PATTERN.findall(value)}
    english_score = len(words & _ENGLISH_WORDS)
    vietnamese_score = len(words & _VIETNAMESE_WORDS)
    if english_score >= 2 and english_score > vietnamese_score:
        return False
    return bool(_VIETNAMESE_CHARACTERS.search(value)) or vietnamese_score >= 2


class SourceNoteLocalizationService:
    """Localize selected provider notes without mutating their stored source."""

    def __init__(
        self,
        translator: SourceNoteTranslator | None = None,
        *,
        batch_size: int = 12,
        cache_size: int = 2048,
    ) -> None:
        self._translator = translator
        self._batch_size = max(1, batch_size)
        self._cache_size = max(1, cache_size)
        self._cache: OrderedDict[str, str] = OrderedDict()

    async def localize(self, result: PlaceCheckerResult) -> PlaceCheckerResult:
        pending: dict[str, SourceNoteTranslationRequest] = {}
        place_keys: dict[int, str] = {}

        for index, place in enumerate(result.checked_places):
            note = select_planner_source_note(place)
            if note is None or note.source_type not in {
                "google_maps",
                "knowledge_graph",
            }:
                continue
            if is_probably_vietnamese(note.text):
                continue
            place_name = place.canonical_name or next(
                iter(place.original_names), "Địa điểm"
            )
            cache_key = self._cache_key(place_name, note.text)
            place_keys[index] = cache_key
            if cache_key not in self._cache:
                pending.setdefault(
                    cache_key,
                    SourceNoteTranslationRequest(
                        request_id=cache_key,
                        place_name=place_name,
                        text=note.text,
                    ),
                )

        translated = await self._translate_pending(list(pending.values()))
        localized_places = list(result.checked_places)
        omitted_count = 0
        for index, cache_key in place_keys.items():
            place = localized_places[index]
            text = self._cache.get(cache_key) or translated.get(cache_key)
            if text and is_probably_vietnamese(text):
                note = place.provider_note
                if note is not None:
                    localized_places[index] = place.model_copy(
                        update={"provider_note": note.model_copy(update={"text": text})}
                    )
                continue
            localized_places[index] = place.model_copy(update={"provider_note": None})
            omitted_count += 1

        if not place_keys:
            return result
        warnings = list(result.warnings)
        if omitted_count:
            warnings.append(
                "Một số ghi chú nguồn đã được ẩn vì chưa thể Việt hóa."
            )
        return result.model_copy(
            update={
                "checked_places": localized_places,
                "warnings": list(dict.fromkeys(warnings)),
                "metadata": result.metadata.model_copy(
                    update={"partial": result.metadata.partial or bool(omitted_count)}
                ),
            }
        )

    async def _translate_pending(
        self,
        requests: list[SourceNoteTranslationRequest],
    ) -> dict[str, str]:
        translated: dict[str, str] = {}
        if self._translator is None:
            return translated
        for offset in range(0, len(requests), self._batch_size):
            batch = requests[offset : offset + self._batch_size]
            try:
                batch_result = await self._translator.translate_many(batch)
            except Exception as exc:
                logger.warning(
                    "PlaceChecker source note localization failed (%s)",
                    type(exc).__name__,
                )
                continue
            expected_ids = {request.request_id for request in batch}
            for request_id, text in batch_result.items():
                if not isinstance(text, str):
                    continue
                normalized = text.strip()
                if (
                    request_id not in expected_ids
                    or not normalized
                    or len(normalized) > 4000
                    or not is_probably_vietnamese(normalized)
                ):
                    continue
                translated[request_id] = normalized
                self._remember(request_id, normalized)
        return translated

    def _remember(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    @staticmethod
    def _cache_key(place_name: str, text: str) -> str:
        payload = f"source-note.vi.v1\0{place_name}\0{text}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
