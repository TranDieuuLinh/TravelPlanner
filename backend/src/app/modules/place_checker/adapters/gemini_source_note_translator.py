import json

from app.modules.place_checker.localization.contract import (
    SourceNoteTranslationBatch,
    SourceNoteTranslationRequest,
)
from app.shared.llm import LlmClient

_SYSTEM_PROMPT = """Bạn là bộ Việt hóa source note của TravelPlanner.
Dịch từng `text` sang tiếng Việt tự nhiên, ngắn gọn và phù hợp để hiển thị cho
người dùng. Giữ nguyên tên riêng và toàn bộ ý nghĩa thực tế; không thêm, bỏ hoặc
suy diễn địa điểm, mốc thời gian, chi phí hay dữ kiện. Nếu text đã là tiếng Việt
thì giữ nguyên. Trả đúng một translation cho mỗi requestId và đúng JSON schema.
Không trả URL hoặc lời giải thích ngoài bản dịch."""


class GeminiSourceNoteTranslator:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 2048) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def translate_many(
        self,
        requests: list[SourceNoteTranslationRequest],
    ) -> dict[str, str]:
        if not requests:
            return {}
        raw = await self._client.generate(
            json.dumps(
                {"notes": [request.model_dump(by_alias=True) for request in requests]},
                ensure_ascii=False,
            ),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_json_schema=SourceNoteTranslationBatch.model_json_schema(),
        )
        output = SourceNoteTranslationBatch.model_validate_json(raw)
        expected_ids = {request.request_id for request in requests}
        translations: dict[str, str] = {}
        for translation in output.translations:
            if (
                translation.request_id not in expected_ids
                or translation.request_id in translations
            ):
                raise ValueError("Translator returned an unknown or duplicate requestId")
            translations[translation.request_id] = translation.text.strip()
        if set(translations) != expected_ids:
            raise ValueError("Translator did not return every requested note")
        return translations
