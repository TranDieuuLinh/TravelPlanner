import json

from app.modules.place_checker.subplaces.contract import (
    GeneratedSubplaceNoteBatch,
    SubplaceNoteRequest,
)
from app.shared.llm import LlmClient


_SYSTEM_PROMPT = """Bạn tạo ghi chú ngắn cho điểm tham quan nằm bên trong một địa điểm.
Mỗi ghi chú phải viết bằng tiếng Việt tự nhiên, tối đa hai câu và 300 ký tự.
Chỉ dùng dữ kiện có trong SubPlace, Offer_Item và ActivityItem được cung cấp.
Hãy nói ngắn gọn khách có thể làm hoặc xem gì tại SubPlace. Không suy diễn lịch
sử, tuyến đường, khoảng cách, thời gian, giá hoặc dữ kiện không có trong input.
Không nhắc tới cấu trúc database. Trả đúng một note cho mỗi requestId, không trả
requestId lạ hoặc nội dung ngoài JSON schema."""


class GeminiSubplaceNoteGenerator:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 2048) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def generate_many(
        self,
        requests: list[SubplaceNoteRequest],
    ) -> dict[str, str]:
        if not requests:
            return {}
        raw = await self._client.generate(
            json.dumps(
                {"subplaces": [request.model_dump(by_alias=True) for request in requests]},
                ensure_ascii=False,
            ),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_json_schema=GeneratedSubplaceNoteBatch.model_json_schema(),
        )
        output = GeneratedSubplaceNoteBatch.model_validate_json(raw)
        expected_ids = {request.request_id for request in requests}
        notes: dict[str, str] = {}
        for generated in output.notes:
            if generated.request_id not in expected_ids or generated.request_id in notes:
                raise ValueError("Gemini returned an unknown or duplicate requestId")
            notes[generated.request_id] = generated.note.strip()
        if set(notes) != expected_ids:
            raise ValueError("Gemini did not return every requested SubPlace note")
        return notes
