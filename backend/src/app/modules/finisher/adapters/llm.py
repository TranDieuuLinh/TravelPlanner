import json

from pydantic import ValidationError

from app.modules.finisher.contract import FinisherInput, FinisherOutput
from app.shared.llm import LlmClient

_SYSTEM_PROMPT = """Bạn là bước Finisher của TravelPlanner.
Viết một phản hồi ngắn, tự nhiên hoàn toàn bằng tiếng Việt để báo lịch trình đã sẵn sàng.
Chỉ dùng dữ liệu JSON đã chuẩn hóa; không suy diễn, không thêm địa điểm, giờ hoặc chi phí.
Nếu có notes, ưu tiên note đầu tiên vì danh sách đã xếp URL trước
Google Maps/Knowledge Graph. Diễn đạt hoặc dịch ý note tự nhiên, không chép URL.
Nhắc người dùng có thể mở từng điểm để xem đầy đủ ghi chú và nguồn.
Trả đúng JSON theo schema."""


class GeminiFinisherResponseGenerator:
    def __init__(self, client: LlmClient, *, max_output_tokens: int = 320) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def generate(self, payload: FinisherInput) -> FinisherOutput:
        raw = await self._client.generate(
            payload.model_dump_json(by_alias=True),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_json_schema=FinisherOutput.model_json_schema(),
        )
        try:
            return FinisherOutput.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("Finisher returned invalid structured output") from exc
