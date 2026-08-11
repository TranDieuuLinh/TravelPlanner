import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.modules.information_finder.adapters.development import InMemorySourceRepository
from app.modules.information_finder.adapters.gemini_embedding import (
    GeminiEmbeddingProvider,
)
from app.modules.information_finder.adapters.tavily_search import TavilySearchProvider
from app.modules.information_finder.contract import (
    EmbeddingIdentity,
    PreparedChunk,
    PreparedSource,
    SearchResult,
)
from app.modules.information_finder.errors import EmbeddingProviderError
from app.modules.information_finder.ports import SearchProviderQuotaExceeded

NOW = datetime.now(timezone.utc)


def prepared(content, embedding=None):
    return PreparedSource(
        result=SearchResult(
            title="Title",
            url="https://example.test/a",
            content=content,
            provider_score=0.9,
            fetched_at=NOW,
        ),
        canonical_url="https://example.test/a",
        domain="example.test",
        content_hash=content,
        expires_at=NOW + timedelta(days=1),
        chunks=[
            PreparedChunk(
                chunk_index=0,
                content=content,
                token_count=2,
                content_hash=content,
                embedding=embedding or [1.0] + [0.0] * 383,
                embedded_at=NOW,
            )
        ],
    )


def save(repository, item, identity):
    return asyncio.run(
        repository.save_search(
            original_query="q",
            normalized_query="q",
            sources=[item],
            identity=identity,
            provider_request_id="r",
            search_parameters={},
        )
    )


def test_unchanged_content_does_not_create_snapshot_but_changed_does():
    repository = InMemorySourceRepository()
    identity = EmbeddingIdentity(model_name="m", model_revision="1")
    save(repository, prepared("hash-1"), identity)
    save(repository, prepared("hash-1"), identity)
    assert repository.snapshot_counts["https://example.test/a"] == 1
    save(repository, prepared("hash-2"), identity)
    assert repository.snapshot_counts["https://example.test/a"] == 2


def test_repository_does_not_mix_embedding_model_or_revision():
    repository = InMemorySourceRepository()
    identity = EmbeddingIdentity(model_name="m", model_revision="1")
    save(repository, prepared("hash"), identity)
    found = asyncio.run(repository.retrieve("q", [1.0] + [0.0] * 383, identity, 5))
    wrong = asyncio.run(
        repository.retrieve(
            "q",
            [1.0] + [0.0] * 383,
            EmbeddingIdentity(model_name="m", model_revision="2"),
            5,
        )
    )
    assert len(found) == 1 and wrong == []


def test_gemini_embedding_uses_retrieval_tasks_and_normalizes_vectors():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), json.loads(request.content)))
        body = requests[-1][1]
        if "batchEmbedContents" in str(request.url):
            values = [{"values": [3.0] + [0.0] * 383} for _ in body["requests"]]
            return httpx.Response(200, json={"embeddings": values})
        return httpx.Response(200, json={"embedding": {"values": [4.0] + [0.0] * 383}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiEmbeddingProvider("secret", client=client)
    query = asyncio.run(provider.embed_query("query"))
    documents = asyncio.run(provider.embed_documents(["document"]))
    asyncio.run(client.aclose())

    assert query == [1.0] + [0.0] * 383
    assert documents == [[1.0] + [0.0] * 383]
    assert requests[0][1]["taskType"] == "RETRIEVAL_QUERY"
    assert requests[0][1]["outputDimensionality"] == 384
    assert requests[1][1]["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert requests[1][1]["requests"][0]["outputDimensionality"] == 384
    assert "embedContentConfig" not in requests[0][1]


def test_gemini_embedding_splits_batches_at_provider_limit():
    batch_sizes = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batch_sizes.append(len(body["requests"]))
        values = [{"values": [1.0] + [0.0] * 383} for _ in body["requests"]]
        return httpx.Response(200, json={"embeddings": values})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiEmbeddingProvider("secret", client=client)
    vectors = asyncio.run(provider.embed_documents(["document"] * 101))
    asyncio.run(client.aclose())

    assert len(vectors) == 101
    assert batch_sizes == [100, 1]


def test_gemini_embedding_rotates_comma_separated_keys_on_quota():
    seen_keys = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["x-goog-api-key"])
        if len(seen_keys) == 1:
            return httpx.Response(429, json={"error": "quota"})
        return httpx.Response(200, json={"embedding": {"values": [1.0] + [0.0] * 383}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiEmbeddingProvider("api1, api2,api1", client=client)
    asyncio.run(provider.embed_query("query"))
    asyncio.run(client.aclose())

    assert provider.key_count == 2
    assert seen_keys == ["api1", "api2"]


def test_gemini_embedding_includes_provider_message_for_bad_request():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid argument: output dimensionality",
                    "details": [{"private": "must not be logged"}],
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeminiEmbeddingProvider("api1", client=client)
    try:
        with pytest.raises(EmbeddingProviderError) as error:
            asyncio.run(provider.embed_query("query"))
        assert str(error.value) == (
            "Gemini embedding provider returned HTTP 400: "
            "Invalid argument: output dimensionality"
        )
        assert "must not be logged" not in str(error.value)
    finally:
        asyncio.run(client.aclose())


def test_tavily_maps_quota_error_without_exposing_raw_payload():
    class QuotaError(Exception):
        status_code = 429

    class Client:
        async def search(self, **kwargs):
            raise QuotaError("provider payload is private")

    provider = TavilySearchProvider("test-key", client=Client())
    try:
        asyncio.run(provider.search("query"))
    except SearchProviderQuotaExceeded as exc:
        assert str(exc) == "Tavily quota or rate limit reached"
    else:
        raise AssertionError("quota error was not mapped")
