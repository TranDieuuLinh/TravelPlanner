import asyncio
import json

import pytest

from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.adapters.gemini import GeminiExplorerDraftGenerator
from app.modules.explorer.errors import ExplorerOperationError


class TagDraftClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.system_prompts: list[str] = []
        self.schemas: list[dict] = []

    async def generate(self, user_prompt: str, **kwargs) -> str:
        self.system_prompts.append(kwargs["system_prompt"])
        self.schemas.append(kwargs["response_json_schema"])
        return json.dumps(self.responses.pop(0), ensure_ascii=False)


def test_prompt_uses_runtime_tag_keys_in_prompt_schema_and_result(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text(
        "Văn hóa: [culture, bảo tàng]\nđồ uống: [coffee, cà phê]\n",
        encoding="utf-8",
    )
    client = TagDraftClient([{
        "shortPreferences": ["Văn hóa"],
        "shortAvoids": ["đồ uống"],
    }])
    generator = GeminiExplorerDraftGenerator(
        client, tag_catalog=YamlTagCatalog(path)
    )  # type: ignore[arg-type]

    draft = asyncio.run(generator.from_prompt("Thích văn hóa, tránh cà phê"))

    assert draft.short_preferences == ["Văn hóa"]
    assert draft.short_avoids == ["đồ uống"]
    assert '"Văn hóa":["culture","bảo tàng"]' in client.system_prompts[0]
    assert client.schemas[0]["properties"]["shortPreferences"]["items"][
        "enum"
    ] == ["Văn hóa", "đồ uống"]
    assert client.schemas[0]["properties"]["shortAvoids"]["items"]["enum"] == [
        "Văn hóa",
        "đồ uống",
    ]


def test_prompt_rejects_tag_not_declared_in_runtime_taxonomy(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text("Văn hóa: [culture]\n", encoding="utf-8")
    client = TagDraftClient([{"shortPreferences": ["made_up"]}])
    generator = GeminiExplorerDraftGenerator(
        client, tag_catalog=YamlTagCatalog(path)
    )  # type: ignore[arg-type]

    with pytest.raises(ExplorerOperationError) as caught:
        asyncio.run(generator.from_prompt("Thích văn hóa"))

    assert caught.value.code == "DRAFT_GENERATION_INVALID"


def test_prompt_rereads_tag_taxonomy_without_backend_restart(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text("Văn hóa: [culture]\n", encoding="utf-8")
    client = TagDraftClient([
        {"shortPreferences": ["Văn hóa"]},
        {"shortPreferences": ["nightlife"]},
    ])
    generator = GeminiExplorerDraftGenerator(
        client, tag_catalog=YamlTagCatalog(path)
    )  # type: ignore[arg-type]

    asyncio.run(generator.from_prompt("Thích văn hóa"))
    path.write_text("nightlife: [bar]\n", encoding="utf-8")
    asyncio.run(generator.from_prompt("Thích bar"))

    first = client.schemas[0]["properties"]["shortPreferences"]["items"]["enum"]
    second = client.schemas[1]["properties"]["shortPreferences"]["items"]["enum"]
    assert first == ["Văn hóa"]
    assert second == ["nightlife"]
