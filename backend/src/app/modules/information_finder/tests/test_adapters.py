import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.information_finder.adapters.development import InMemorySourceRepository
from app.modules.information_finder.adapters.multilingual_e5 import MultilingualE5EmbeddingProvider
from app.modules.information_finder.adapters.tavily_search import TavilySearchProvider
from app.modules.information_finder.contract import (
    EmbeddingIdentity,
    PreparedChunk,
    PreparedSource,
    SearchResult,
)
from app.modules.information_finder.ports import SearchProviderQuotaExceeded

NOW = datetime.now(timezone.utc)


def prepared(content, embedding=None):
    return PreparedSource(
        result=SearchResult(
            title="Title", url="https://example.test/a", content=content,
            provider_score=0.9, fetched_at=NOW,
        ),
        canonical_url="https://example.test/a",
        domain="example.test",
        content_hash=content,
        expires_at=NOW + timedelta(days=1),
        chunks=[PreparedChunk(
            chunk_index=0, content=content, token_count=2,
            content_hash=content, embedding=embedding or [1.0] + [0.0] * 383,
            embedded_at=NOW,
        )],
    )


def save(repository, item, identity):
    return asyncio.run(repository.save_search(
        original_query="q", normalized_query="q", sources=[item], identity=identity,
        provider_request_id="r", search_parameters={},
    ))


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
    wrong = asyncio.run(repository.retrieve(
        "q", [1.0] + [0.0] * 383,
        EmbeddingIdentity(model_name="m", model_revision="2"), 5,
    ))
    assert len(found) == 1 and wrong == []


def test_multilingual_e5_applies_query_and_passage_prefixes():
    provider = MultilingualE5EmbeddingProvider()
    seen = []

    async def fake_encode(texts):
        seen.extend(texts)
        return [[0.0] * 384 for _ in texts]

    provider._encode = fake_encode
    asyncio.run(provider.embed_query("xin chào"))
    asyncio.run(provider.embed_documents(["nội dung"]))
    assert seen == ["query: xin chào", "passage: nội dung"]


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
