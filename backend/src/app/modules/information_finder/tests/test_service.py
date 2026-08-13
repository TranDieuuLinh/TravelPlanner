import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.information_finder.adapters.development import (
    ExtractiveAnswerGenerator,
    HashingEmbeddingProvider,
    InMemorySourceRepository,
)
from app.modules.information_finder.errors import SearchQueryPlanningError
from app.modules.information_finder.contract import (
    RetrievedSource,
    SearchQueryPlan,
    SearchResponse,
    SearchResult,
)
from app.modules.information_finder.ports import (
    SearchProviderQuotaExceeded,
    SearchProviderTimeout,
)
from app.modules.information_finder.errors import EmbeddingProviderQuotaExceeded
from app.modules.information_finder.service import (
    InformationFinderOptions,
    InformationFinderService,
)
from app.modules.information_finder.utils import canonicalize_url

NOW = datetime.now(timezone.utc)
CONTENT = "Thông tin tham quan bảo tàng và giờ mở cửa dành cho khách du lịch. " * 3


class FakeSearch:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = 0
        self.queries = []

    async def search(self, query):
        self.calls += 1
        self.queries.append(query)
        if self.error:
            raise self.error("failure")
        return SearchResponse(results=self.results, provider_request_id="req-1")


class FakeChunker:
    version = "semantic-test-v1"

    async def chunk(self, source):
        return ["semantic chunk one", "semantic chunk two"]


class QuotaEmbedding:
    @property
    def identity(self):
        raise AssertionError("identity should not be read after quota failure")

    async def embed_query(self, text):
        raise EmbeddingProviderQuotaExceeded("quota")

    async def embed_documents(self, texts):
        raise AssertionError("document embeddings should be skipped")


class FakeSearchQueryPlanner:
    def __init__(self, queries=None, error=None):
        self.queries_to_return = queries or ["Hà Nội du lịch tổng quan"]
        self.error = error
        self.inputs = []

    async def generate(self, query, sources=None):
        self.inputs.append((query, sources or []))
        if self.error:
            raise self.error("planning failed")
        return SearchQueryPlan(should_search=True, queries=self.queries_to_return)


class SkipSearchQueryPlanner:
    def __init__(self):
        self.inputs = []

    async def generate(self, query, sources=None):
        self.inputs.append((query, sources or []))
        return SearchQueryPlan(should_search=False, queries=[])


class StaticRepository:
    def __init__(self, local=None):
        self.local = local or []
        self.saved = []
        self.failures = []

    async def retrieve(self, *args, **kwargs):
        return self.local

    async def save_search(self, *, sources, **kwargs):
        self.saved.extend(sources)
        return [
            source(
                f"web-{index}",
                prepared.canonical_url,
                score=prepared.result.provider_score or 0,
                content=prepared.result.content,
            )
            for index, prepared in enumerate(sources)
        ]

    async def record_failed_search(self, **kwargs):
        self.failures.append(kwargs["error_code"])


def source(identifier, url, *, score=0.9, fresh=True, content=CONTENT):
    return RetrievedSource(
        source_id=identifier,
        snapshot_id=f"snapshot-{identifier}",
        title=f"Source {identifier}",
        url=url,
        content=content,
        semantic_score=score,
        lexical_score=0.5,
        last_fetched_at=NOW,
        expires_at=NOW + (timedelta(days=1) if fresh else -timedelta(seconds=1)),
    )


def web_result(
    url="https://new.example/info",
    content="museum " * 100,
    score=0.9,
):
    return SearchResult(
        title="Tavily result",
        url=url,
        content=content,
        provider_score=score,
        fetched_at=NOW,
    )


def service(repository, search=None, *, minimum=1, chunker=None, planner=None):
    return InformationFinderService(
        repository=repository,
        embeddings=HashingEmbeddingProvider(),
        answers=ExtractiveAnswerGenerator(),
        chunker=chunker,
        search_provider=search,
        search_query_planner=planner,
        options=InformationFinderOptions(
            minimum_local_sources=minimum,
            similarity_threshold=0.5,
            provider_relevance_threshold=0.5,
        ),
    )


def test_fresh_sufficient_local_skips_tavily():
    search = FakeSearch()
    output = asyncio.run(
        service(StaticRepository([source("1", "https://a.test/x")]), search).find(
            "museum"
        )
    )
    assert search.calls == 0
    assert len(output.sources) == 1


def test_llm_receives_top_five_and_can_skip_tavily():
    planner = SkipSearchQueryPlanner()
    search = FakeSearch()
    local = [
        source(
            str(index),
            f"https://source.test/{index}",
            score=0.6 + (index * 0.05),
        )
        for index in range(6)
    ]

    asyncio.run(service(StaticRepository(local), search, planner=planner).find("museum"))

    assert [item.source_id for item in planner.inputs[0][1]] == [
        "5",
        "4",
        "3",
        "2",
        "1",
    ]
    assert search.calls == 0


def test_empty_local_calls_tavily_and_saves():
    repository = StaticRepository()
    search = FakeSearch([web_result()])
    planner = FakeSearchQueryPlanner(["museum"])
    output = asyncio.run(service(repository, search, planner=planner).find("museum"))
    assert search.calls == 1 and len(repository.saved) == 1
    assert len(output.sources) == 1


def test_embedding_quota_falls_back_to_tavily_without_failing():
    repository = StaticRepository()
    finder = InformationFinderService(
        repository=repository,
        embeddings=QuotaEmbedding(),
        answers=ExtractiveAnswerGenerator(),
        search_provider=FakeSearch([web_result()]),
        options=InformationFinderOptions(
            minimum_local_sources=1,
            provider_relevance_threshold=0.5,
        ),
    )

    output = asyncio.run(finder.find("giờ mở cửa bảo tàng"))

    assert len(output.sources) == 1
    assert output.warnings == ["embedding_fallback:embedding_provider_quota_exceeded"]


def test_empty_local_uses_llm_queries_before_tavily():
    repository = StaticRepository()
    search = FakeSearch([web_result()])
    planner = FakeSearchQueryPlanner(
        ["Hà Nội du lịch lịch sử", "Hà Nội điểm tham quan nổi bật"]
    )

    asyncio.run(
        service(
            repository,
            search,
            planner=planner,
        ).find("Cho tôi biết về Hà Nộil")
    )

    assert planner.inputs[0][0] == "Cho tôi biết về Hà Nộil"
    assert len(planner.inputs[0][1]) <= 5
    assert search.queries[0] == "Hà Nội du lịch lịch sử"
    assert len(search.queries) <= 2


def test_search_query_planner_failure_uses_deterministic_queries():
    repository = StaticRepository()
    search = FakeSearch([web_result()])
    planner = FakeSearchQueryPlanner(error=SearchQueryPlanningError)

    output = asyncio.run(
        service(repository, search, planner=planner).find("museum")
    )

    assert search.queries[0] == "museum"
    assert len(search.queries) == 3
    assert "search_query_planner_fallback" in output.warnings


def test_topic_mismatch_forces_tavily_even_with_high_embedding_score():
    repository = StaticRepository(
        [
            source(
                "hanoi",
                "https://a.test/hanoi",
                content="Hà Nội là thủ đô của Việt Nam với nhiều di tích lịch sử.",
            )
        ]
    )
    search = FakeSearch(
        [
            web_result(
                "https://web.test/hochiminh",
                content="Thành phố Hồ Chí Minh là trung tâm kinh tế lớn của Việt Nam.",
            )
        ]
    )

    planner = FakeSearchQueryPlanner(["Thông tin du lịch Thành phố Hồ Chí Minh"])
    asyncio.run(
        service(repository, search, planner=planner).find("Thông tin về Hồ Chí Minh")
    )

    assert search.calls == 1


def test_new_destination_refreshes_tavily_after_hanoi_cache_is_populated():
    class DestinationSearch:
        calls = 0

        async def search(self, query):
            self.calls += 1
            destination = "Hà Nội" if self.calls == 1 else "Hải Phòng"
            return SearchResponse(
                results=[
                    web_result(
                        url=f"https://travel.test/{self.calls}",
                        content=(
                            f"{destination} là điểm đến nổi bật của Việt Nam. "
                            "Nơi đây có nhiều địa danh, món ăn và hoạt động cho du khách. "
                        )
                        * 3,
                    )
                ],
                provider_request_id=f"req-{self.calls}",
            )

    search = DestinationSearch()
    repository = InMemorySourceRepository()
    finder = InformationFinderService(
        repository=repository,
        embeddings=HashingEmbeddingProvider(),
        answers=ExtractiveAnswerGenerator(),
        search_provider=search,
        options=InformationFinderOptions(
            minimum_local_sources=1,
            similarity_threshold=0.9,
            provider_relevance_threshold=0.5,
        ),
    )

    asyncio.run(finder.find("Mô tả Hà Nội"))
    asyncio.run(finder.find("Mô tả Hải Phòng"))

    assert search.calls == 3


def test_insufficient_local_merges_local_and_tavily():
    repository = StaticRepository([source("1", "https://a.test/x")])
    output = asyncio.run(
        service(repository, FakeSearch([web_result()]), minimum=2).find("museum")
    )
    assert {item.source_id for item in output.sources} == {"1"}


def test_expired_source_refreshes_with_tavily():
    search = FakeSearch([web_result()])
    asyncio.run(
        service(
            StaticRepository([source("1", "https://a.test/x", fresh=False)]), search
        ).find("museum")
    )
    assert search.calls == 3


def test_live_query_forces_refresh_even_with_good_local():
    search = FakeSearch([web_result()])
    asyncio.run(
        service(StaticRepository([source("1", "https://a.test/x")]), search).find(
            "giá hiện tại"
        )
    )
    assert search.calls == 3


def test_url_and_content_deduplication():
    repository = StaticRepository()
    search = FakeSearch(
        [
            web_result("https://EXAMPLE.com/a/?utm_source=x"),
            web_result("https://example.com/a"),
            web_result("https://other.test/a"),
        ]
    )
    asyncio.run(service(repository, search).find("museum"))
    assert len(repository.saved) == 3
    assert repository.saved[0].canonical_url == "https://example.com/a"
    assert canonicalize_url("https://x.test/a/?gclid=1") == "https://x.test/a"


def test_semantic_chunker_output_is_embedded_and_prepared():
    finder = service(StaticRepository(), chunker=FakeChunker())
    prepared = asyncio.run(
        finder._prepare_sources(
            [web_result()],
            query_embedding=[0.0] * 384,
            expires_at=NOW + timedelta(days=1),
        )
    )

    assert prepared[0].chunking_version == "semantic-test-v1"
    assert [chunk.content for chunk in prepared[0].chunks] == [
        "semantic chunk one",
        "semantic chunk two",
    ]
    assert all(len(chunk.embedding) == 384 for chunk in prepared[0].chunks)


def test_tavily_timeout_keeps_usable_local_source():
    search = FakeSearch(error=SearchProviderTimeout)
    repository = StaticRepository([source("1", "https://a.test/x", score=0.4)])
    planner = FakeSearchQueryPlanner(["museum"])
    output = asyncio.run(service(repository, search, planner=planner).find("museum"))
    assert [item.source_id for item in output.sources] == ["1"]
    assert "Web search unavailable" in output.warnings[-1]
    assert search.calls == 1
    assert repository.failures == ["provider_timeout"]


def test_source_at_similarity_threshold_is_kept():
    repository = StaticRepository([source("1", "https://a.test/x", score=0.8)])
    output = asyncio.run(
        InformationFinderService(
            repository=repository,
            embeddings=HashingEmbeddingProvider(),
            answers=ExtractiveAnswerGenerator(),
            options=InformationFinderOptions(
                minimum_local_sources=1,
                similarity_threshold=0.8,
            ),
        ).find("museum")
    )

    assert [item.source_id for item in output.sources] == ["1"]


def test_quota_is_mapped_to_warning():
    output = asyncio.run(
        service(StaticRepository(), FakeSearch(error=SearchProviderQuotaExceeded)).find(
            "museum"
        )
    )
    assert "provider_quota_exceeded" in output.warnings[0]


def test_citation_date_kind_review_and_camel_case():
    output = asyncio.run(
        service(StaticRepository([source("1", "https://a.test/x")])).find("museum")
    )
    payload = output.model_dump(mode="json", by_alias=True)
    citation = payload["sources"][0]
    assert citation["updatedAt"] and citation["dateKind"] == "last_fetched_at"
    assert citation["reviewStatus"] == "pending" and citation["sourceId"] == "1"
