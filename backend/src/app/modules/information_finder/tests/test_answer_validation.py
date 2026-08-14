import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.information_finder.adapters.development import (
    ExtractiveAnswerGenerator,
    HashingEmbeddingProvider,
)
from app.modules.information_finder.contract import (
    AnswerClaim,
    GeneratedAnswer,
    RetrievedSource,
    SearchResponse,
    SearchResult,
)
from app.modules.information_finder.errors import (
    AnswerProviderTimeout,
)
from app.modules.information_finder.entity_linking import EntityResolver, ResolvedEntity
from app.modules.information_finder.service import (
    InformationFinderOptions,
    InformationFinderService,
)

NOW = datetime.now(timezone.utc)
CONTENT = "Museum opening hours are 8:00 to 17:00 for visitors. " * 3


def run(coro):
    return asyncio.run(coro)


def source(identifier, domain="example.test", content=CONTENT):
    return RetrievedSource(
        source_id=identifier,
        snapshot_id=f"snap-{identifier}",
        title=f"Source {identifier}",
        url=f"https://{domain}/{identifier}",
        content=content,
        semantic_score=0.9,
        lexical_score=0.5,
        last_fetched_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )


class Repository:
    def __init__(self, local=None):
        self.local = local or []

    async def retrieve(self, *args, **kwargs):
        return self.local

    async def save_search(self, *, sources, **kwargs):
        return [
            source(
                f"web-{index}",
                "web.test",
                content=item.result.content,
            )
            for index, item in enumerate(sources)
        ]

    async def record_failed_search(self, **kwargs):
        return None


class Search:
    def __init__(self, content=CONTENT):
        self.calls = 0
        self.content = content

    async def search(self, query):
        self.calls += 1
        return SearchResponse(
            results=[
                SearchResult(
                    title="Web",
                    url="https://web.test/result",
                    content=self.content,
                    provider_score=0.9,
                    fetched_at=NOW,
                )
            ]
        )


class Answer:
    def __init__(self, generated=None, error=None):
        self.generated = generated
        self.error = error
        self.calls = 0

    async def generate(self, query, sources):
        self.calls += 1
        if self.error:
            raise self.error("failed")
        return self.generated


def make_service(
    repository,
    answer,
    *,
    search=None,
    fallback=None,
    enabled=True,
    entity_resolver=None,
):
    return InformationFinderService(
        repository=repository,
        embeddings=HashingEmbeddingProvider(),
        answers=answer,
        fallback_answers=fallback,
        search_provider=search,
        entity_resolver=entity_resolver,
        options=InformationFinderOptions(
            minimum_local_sources=1,
            similarity_threshold=0.5,
            provider_relevance_threshold=0.5,
            answer_fallback_enabled=enabled,
        ),
    )


def generated(*claims, entity_names=None):
    return GeneratedAnswer(
        claims=[AnswerClaim(text=text, source_ids=ids) for text, ids in claims],
        entity_names=entity_names or [],
    )


def test_only_cited_sources_are_returned_and_duplicate_ids_keep_order():
    answer = Answer(generated(("Fact", ["s2", "s2", "s1"])))
    output = run(
        make_service(
            Repository([source("s1", "one.test"), source("s2", "two.test")]), answer
        ).find("hours")
    )
    assert [item.source_id for item in output.sources] == ["s2", "s1"]
    assert output.answer.endswith("[1][2]")


def test_verified_entity_name_is_linked_after_knowledge_graph_lookup():
    class Resolver(EntityResolver):
        async def resolve(self, name):
            if name == "Lăng Bác":
                return ResolvedEntity(name=name, entity_id="lang-bac")
            return None

    answer = Answer(
        generated(
            (
                "## Hà Nội\n\nGhé Lăng Bác.",
                ["s1"],
            ),
            entity_names=["Lăng Bác"],
        )
    )
    output = run(
        make_service(
            Repository([source("s1")]),
            answer,
            entity_resolver=Resolver(),
        ).find("Hà Nội")
    )
    assert output.answer.startswith("## Hà Nội")
    assert "[Lăng Bác](travel-entity://entity)" in output.answer


def test_unknown_source_id_falls_back_with_warning():
    answer = Answer(generated(("Fact", ["invented"])))
    output = run(
        make_service(
            Repository([source("s1")]), answer, fallback=ExtractiveAnswerGenerator()
        ).find("hours")
    )
    assert output.sources[0].source_id == "s1"
    assert (
        output.warnings[-1]
        == "answer_extractive_fallback:answer_provider_invalid_output"
    )


def test_timeout_falls_back_when_enabled_and_raises_when_disabled():
    failing = Answer(error=AnswerProviderTimeout)
    output = run(
        make_service(
            Repository([source("s1")]),
            failing,
            fallback=ExtractiveAnswerGenerator(),
            enabled=True,
        ).find("hours")
    )
    assert "answer_extractive_fallback:answer_provider_timeout" in output.warnings
    with pytest.raises(AnswerProviderTimeout):
        run(
            make_service(
                Repository([source("s1")]),
                failing,
                fallback=ExtractiveAnswerGenerator(),
                enabled=False,
            ).find("hours")
        )


def test_no_source_does_not_call_llm():
    answer = Answer(generated(("Fact", ["s1"])))
    output = run(make_service(Repository(), answer).find("hours"))
    assert answer.calls == 0 and output.sources == []


def test_cache_hit_skips_tavily_and_calls_llm_once():
    answer = Answer(generated(("Fact", ["s1"])))
    search = Search()
    run(make_service(Repository([source("s1")]), answer, search=search).find("hours"))
    assert search.calls == 0 and answer.calls == 1


def test_cache_miss_calls_tavily_and_llm_once():
    answer = Answer(generated(("Fact", ["web-0"])))
    search = Search(content="hours " * 100)
    run(make_service(Repository(), answer, search=search).find("hours"))
    assert search.calls == 3 and answer.calls == 1
