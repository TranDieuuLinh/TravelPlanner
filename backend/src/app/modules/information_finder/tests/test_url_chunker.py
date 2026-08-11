import asyncio
import json

import pytest

from app.modules.information_finder.adapters.gemini_url_chunker import (
    GeminiUrlSourceChunker,
)
from app.modules.information_finder.contract import SearchResult
from app.modules.information_finder.errors import SourceChunkingError


def result() -> SearchResult:
    from datetime import datetime, timezone

    return SearchResult(
        title="Museum",
        url="https://example.test/museum",
        content="Fallback content " * 100,
        provider_score=0.9,
        fetched_at=datetime.now(timezone.utc),
    )


def test_chunker_requests_url_context_and_parses_semantic_chunks():
    class Client:
        def __init__(self):
            self.calls = []

        async def generate(self, prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            return json.dumps({"chunks": ["Museum opening hours", "Ticket prices"]})

    client = Client()
    chunks = asyncio.run(GeminiUrlSourceChunker(client).chunk(result()))

    assert chunks == ["Museum opening hours", "Ticket prices"]
    assert client.calls[0][1]["tools"] == [{"url_context": {}}]
    assert "https://example.test/museum" in client.calls[0][0]


def test_chunker_rejects_oversized_output():
    class Client:
        async def generate(self, prompt, **kwargs):
            return json.dumps({"chunks": ["word " * 361]})

    with pytest.raises(SourceChunkingError):
        asyncio.run(GeminiUrlSourceChunker(Client()).chunk(result()))
