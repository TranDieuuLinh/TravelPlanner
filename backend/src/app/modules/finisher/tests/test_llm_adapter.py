import asyncio
import json

from app.modules.finisher.adapters.llm import GeminiFinisherResponseGenerator
from app.modules.finisher.contract import FinisherInput, FinisherNote


def test_llm_finisher_uses_structured_vietnamese_prompt() -> None:
    class Client:
        call = None

        async def generate(self, user_prompt, **kwargs):
            self.call = (user_prompt, kwargs)
            return json.dumps(
                {"response": "Đã xếp lịch và ưu tiên lưu ý từ URL của bạn."},
                ensure_ascii=False,
            )

    client = Client()
    payload = FinisherInput(
        destination="Hà Nội",
        day_count=1,
        stop_count=1,
        notes=[
            FinisherNote(
                place_name="Hồ Gươm",
                text="Arrive before 8 AM.",
                source_type="url",
                source_url="https://example.test/video",
            )
        ],
    )

    result = asyncio.run(GeminiFinisherResponseGenerator(client).generate(payload))

    sent_payload = json.loads(client.call[0])
    assert sent_payload["notes"][0]["sourceType"] == "url"
    assert "hoàn toàn bằng tiếng Việt" in client.call[1]["system_prompt"]
    assert client.call[1]["response_json_schema"]["properties"]["response"]
    assert result.response.startswith("Đã xếp lịch")
