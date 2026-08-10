from typing import Protocol

from app.modules.information_finder.contract import (
    EmbeddingIdentity,
    GeneratedAnswer,
    PreparedSource,
    RetrievedSource,
    SearchResponse,
)


class SearchProviderError(RuntimeError):
    code = "provider_error"


class SearchProviderTimeout(SearchProviderError):
    code = "provider_timeout"


class SearchProviderUnauthorized(SearchProviderError):
    code = "provider_unauthorized"


class SearchProviderQuotaExceeded(SearchProviderError):
    code = "provider_quota_exceeded"


class SearchProvider(Protocol):
    async def search(self, query: str) -> SearchResponse: ...


class SourceRepository(Protocol):
    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        identity: EmbeddingIdentity,
        limit: int,
    ) -> list[RetrievedSource]: ...

    async def save_search(
        self,
        *,
        original_query: str,
        normalized_query: str,
        sources: list[PreparedSource],
        identity: EmbeddingIdentity,
        provider_request_id: str | None,
        search_parameters: dict,
    ) -> list[RetrievedSource]: ...

    async def record_failed_search(
        self,
        *,
        original_query: str,
        normalized_query: str,
        provider: str,
        error_code: str,
        search_parameters: dict,
    ) -> None: ...


class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> EmbeddingIdentity: ...

    async def embed_query(self, text: str) -> list[float]: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class AnswerGenerator(Protocol):
    async def generate(
        self, query: str, sources: list[RetrievedSource]
    ) -> GeneratedAnswer: ...
